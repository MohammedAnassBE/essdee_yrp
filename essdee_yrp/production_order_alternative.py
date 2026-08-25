"""Essdee Production Order adapter for Finishing alternative-item transfers."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, nowdate

from essdee_yrp.lot_pricing import get_effective_lot_price_map
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import build_variant_attributes, get_attribute_details, get_or_create_variant


ALTERNATIVE_PPO_COPY_FIELDS = (
	"naming_series",
	"fabric",
	"dia",
	"gsm",
	"delivery_date",
	"posting_date",
	"lead_time_given",
	"dont_deliver_after",
	"production_term",
	"comments",
	"skip_box_sticker_print",
)
QUANTITY_REQUEST_STATUS = "Pending Request"
QUANTITY_REQUEST_FIELD = "quantity_ratio_request"
STATUS_REQUEST_FIELD = "status_change_request"
INCOMING_TRANSFER_REQUEST_FIELD = "incoming_quantity_transfer_request"
TRANSFER_MARKER_FIELD = "transferred_to_ppo"


def get_alternative_items(item):
	items = frappe.db.get_all(
		"Item Alternative", filters={"item": item}, pluck="alternative_item"
	)
	return sorted({alternative for alternative in items if alternative and alternative != item})


def get_rows_by_size(doc):
	primary_attribute = frappe.db.get_value("Item", doc.item, "primary_attribute")
	rows = {}
	for row in doc.get("production_order_details") or []:
		size = get_variant_attr_details(row.item_variant).get(primary_attribute) or row.item_variant
		if size in rows:
			frappe.throw(_("Production Order has more than one row for size {0}").format(size))
		rows[size] = row
	return rows


def create_alternative_plan_production_order(
	source_production_order,
	source_lot,
	target_lot,
	alternative_item,
	transfers,
	finishing_plan,
):
	"""Create the paired PPO and apply the first alternative-item quantity move."""
	piece_transfers = _normalise_transfers(transfers)
	_lock_production_orders(source_production_order)
	source = frappe.get_doc("Production Order", source_production_order)
	if source.docstatus != 1:
		frappe.throw(_("Source Production Order {0} must be submitted").format(source.name))
	if frappe.db.get_value("Lot", source_lot, "production_order") != source.name:
		frappe.throw(_("Source Lot is not linked to the selected Production Order"))
	if alternative_item not in get_alternative_items(source.item):
		frappe.throw(_("Item {0} is not configured as an alternative of {1}").format(
			alternative_item, source.item
		))

	source_rows = get_rows_by_size(source)
	target_item = frappe.get_cached_doc("Item", alternative_item)
	target_sizes = set(get_attribute_details(alternative_item).get("primary_attribute_values") or [])
	invalid_sizes = [size for size in piece_transfers if size not in target_sizes]
	if invalid_sizes:
		frappe.throw(
			_("Item {0} is not made in size {1}").format(
				alternative_item, ", ".join(invalid_sizes)
			)
		)
	for size in piece_transfers:
		if size not in source_rows:
			frappe.throw(_("Size {0} is not present in {1}").format(size, source.name))

	target = frappe.new_doc("Production Order")
	for fieldname in ALTERNATIVE_PPO_COPY_FIELDS:
		if target.meta.has_field(fieldname):
			target.set(fieldname, source.get(fieldname))
	target.naming_series = target.naming_series or "PPO-"
	target.item = alternative_item
	# The alternative PPO is created now even when the source PPO's promised
	# dates are historical. Keep the original dates where still valid, otherwise
	# advance only the target's delivery window to the current posting date.
	if not target.delivery_date or getdate(target.delivery_date) < getdate(nowdate()):
		target.delivery_date = nowdate()
	if not target.dont_deliver_after or getdate(target.dont_deliver_after) < getdate(
		target.delivery_date
	):
		target.dont_deliver_after = target.delivery_date
	pack_out_stage = frappe.db.get_single_value("IPD Settings", "default_pack_out_stage")
	seen = set()
	for size, source_row in source_rows.items():
		if size not in target_sizes:
			continue
		seen.add(size)
		target.append(
			"production_order_details",
			_production_order_detail(
				target,
				target_item,
				size,
				pack_out_stage,
				source_row,
			),
		)
	missing = [size for size in piece_transfers if size not in seen]
	if missing:
		frappe.throw(_("Could not create PPO rows for size {0}").format(", ".join(missing)))

	source_prices = get_effective_lot_price_map(source_lot, source.name)
	target.insert(ignore_permissions=True)
	target.status = "PPO Request"
	target.flags.ignore_permissions = True
	target.flags.allow_system_generated_alternative_ppo = True
	target.submit()

	lot_doc = frappe.get_doc("Lot", target_lot)
	if lot_doc.production_order and lot_doc.production_order != target.name:
		frappe.throw(_("Alternative Lot is already linked to another Production Order"))
	if lot_doc.item != alternative_item:
		frappe.throw(_("Alternative Lot is linked to a different Item"))
	lot_doc.production_order = target.name
	lot_doc.status = "Open"
	lot_doc.save(ignore_permissions=True)

	target = frappe.get_doc("Production Order", target.name)
	for size, mrp in source_prices.items():
		row = get_rows_by_size(target).get(size)
		if not row or flt(mrp) <= 0 or flt(mrp) == flt(row.mrp):
			continue
		target.append(
			"lot_price_overrides",
			{
				"lot": target_lot,
				"size": size,
				"mrp": flt(mrp),
				"changed_by": frappe.session.user,
				"changed_on": now_datetime(),
			},
		).db_insert()

	_append_comment_log(
		target,
		"\n".join(
			[
				f"[{frappe.utils.formatdate(frappe.utils.nowdate(), 'dd-mm-yyyy')}] "
				f"Alternative PPO Created - {frappe.session.user}",
				f"From Production Order: {source.name}",
				f"From Finishing Plan: {finishing_plan}",
				f"Alternative Lot: {target_lot}",
			]
		),
	)
	apply_alternative_plan_ppo_transfer(
		source.name,
		target.name,
		source_lot,
		target_lot,
		piece_transfers,
		f"Alternative item conversion from Finishing Plan {finishing_plan}",
	)
	return target.name


def apply_alternative_plan_ppo_transfer(
	source_production_order,
	target_production_order,
	source_lot,
	target_lot,
	transfers,
	reason,
):
	"""Move equivalent box quantities between a submitted Essdee PPO pair."""
	piece_transfers = _normalise_transfers(transfers)
	requested_source_boxes = _pieces_to_boxes(
		piece_transfers, _packing_combo(source_lot)
	)
	target_boxes = _pieces_to_boxes(piece_transfers, _packing_combo(target_lot))
	_lock_production_orders(source_production_order, target_production_order)
	source = frappe.get_doc("Production Order", source_production_order)
	target = frappe.get_doc("Production Order", target_production_order)
	_validate_pair(source, target, source_lot, target_lot)

	source_rows = get_rows_by_size(source)
	target_rows = get_rows_by_size(target)
	actual_source_boxes = {}
	changes = []
	for size, piece_quantity in piece_transfers.items():
		source_row = source_rows.get(size)
		if not source_row:
			frappe.throw(_("Size {0} is not present in {1}").format(size, source.name))
		target_row = target_rows.get(size)
		if not target_row:
			target_row = _insert_target_size_row(target, source_row, size)
			target_rows[size] = target_row

		source_before = flt(source_row.quantity)
		source_quantity = min(requested_source_boxes[size], max(source_before, 0))
		actual_source_boxes[size] = source_quantity
		target_before = flt(target_row.quantity)
		target_quantity = target_boxes[size]
		source_after = source_before - source_quantity
		target_after = target_before + target_quantity
		source_row.db_set("quantity", source_after, update_modified=False)
		target_row.db_set("quantity", target_after, update_modified=False)
		changes.append(
			{
				"size": size,
				"qty": target_quantity,
				"piece_qty": piece_quantity,
				"source_qty": source_quantity,
				"target_qty": target_quantity,
				"old_qty": target_before,
				"new_qty": target_after,
				"source_old_qty": source_before,
				"source_new_qty": source_after,
			}
		)

	approved_on = now_datetime()
	request = {
		"transfer_reference": frappe.generate_hash(length=10),
		"requested_user": frappe.session.user,
		"requested_on": str(approved_on),
		"reason": reason,
	}
	_append_transfer_history(source, target, changes, request, approved_on)
	frappe.clear_document_cache("Production Order", source.name)
	frappe.clear_document_cache("Production Order", target.name)
	return {
		"source_production_order": source.name,
		"target_production_order": target.name,
		"transferred": piece_transfers,
		"source_boxes": actual_source_boxes,
		"requested_source_boxes": requested_source_boxes,
		"target_boxes": target_boxes,
	}


def _normalise_transfers(transfers):
	values = update_if_string_instance(transfers) or {}
	values = {str(size): flt(qty) for size, qty in values.items() if flt(qty) > 0}
	if not values:
		frappe.throw(_("Enter a quantity to move to the alternative item"))
	return values


def _packing_combo(lot):
	ipd = frappe.db.get_value("Lot", lot, "production_detail")
	combo = flt(frappe.db.get_value("Item Production Detail", ipd, "packing_combo"))
	if combo <= 0:
		frappe.throw(_("Lot {0} has no valid Packing Combo").format(lot))
	return combo


def _pieces_to_boxes(transfers, combo):
	return {size: round(quantity / combo, 6) for size, quantity in transfers.items()}


def _lock_production_orders(*names):
	for name in sorted(set(filter(None, names))):
		if not frappe.db.sql(
			"SELECT name FROM `tabProduction Order` WHERE name = %s FOR UPDATE", name
		):
			frappe.throw(_("Production Order {0} does not exist").format(name))


def _validate_pair(source, target, source_lot, target_lot):
	if source.docstatus != 1 or target.docstatus != 1:
		frappe.throw(_("Alternative quantity requires two submitted Production Orders"))
	if frappe.db.get_value("Lot", source_lot, "production_order") != source.name:
		frappe.throw(_("Source Lot is not linked to its Production Order"))
	if frappe.db.get_value("Lot", target_lot, "production_order") != target.name:
		frappe.throw(_("Alternative Lot is not linked to its Production Order"))
	if target.item not in get_alternative_items(source.item):
		frappe.throw(_("Target item is not configured as an alternative"))
	for doc in (source, target):
		if (
			doc.status == QUANTITY_REQUEST_STATUS
			or doc.get(QUANTITY_REQUEST_FIELD)
			or doc.get(STATUS_REQUEST_FIELD)
			or doc.get(INCOMING_TRANSFER_REQUEST_FIELD)
		):
			frappe.throw(
				_("Production Order {0} has a pending request").format(doc.name)
			)
		if doc.get(TRANSFER_MARKER_FIELD):
			frappe.throw(
				_("Production Order {0} is locked by another quantity transfer").format(
					doc.name
				)
			)


def _production_order_detail(target, item_doc, size, stage, source_row):
	attributes = {item_doc.primary_attribute: size}
	return {
		"item": target.item,
		"item_variant": get_or_create_variant(
			target.item,
			build_variant_attributes(attributes, stage, item_doc),
		),
		"attributes_json": frappe.as_json(attributes),
		"quantity": 0,
		"ratio": flt(source_row.ratio),
		"mrp": flt(source_row.mrp),
		"production_order_mrp": flt(source_row.production_order_mrp),
		"wholesale_price": flt(source_row.wholesale_price),
		"retail_price": flt(source_row.retail_price),
	}


def _insert_target_size_row(target, source_row, size):
	item_doc = frappe.get_cached_doc("Item", target.item)
	stage = frappe.db.get_single_value("IPD Settings", "default_pack_out_stage")
	row = target.append(
		"production_order_details",
		_production_order_detail(target, item_doc, size, stage, source_row),
	)
	row.parent = target.name
	row.parenttype = "Production Order"
	row.parentfield = "production_order_details"
	row.db_insert()
	return row


def _append_transfer_history(source, target, changes, request, approved_on):
	common = {
		"transfer_reference": request["transfer_reference"],
		"requested_by": request["requested_user"],
		"requested_on": request["requested_on"],
		"approved_by": frappe.session.user,
		"approved_on": approved_on,
		"reason": request["reason"],
	}
	for change in changes:
		rows = (
			(
				source,
				{
					**common,
					"movement": "Reduced",
					"counterpart_production_order": target.name,
					"size": change["size"],
					"quantity": change["source_qty"],
					"quantity_before": change["source_old_qty"],
					"quantity_after": change["source_new_qty"],
				},
			),
			(
				target,
				{
					**common,
					"movement": "Added",
					"counterpart_production_order": source.name,
					"size": change["size"],
					"quantity": change["target_qty"],
					"quantity_before": change["old_qty"],
					"quantity_after": change["new_qty"],
				},
			),
		)
		for parent, values in rows:
			parent.append("quantity_transfer_history", values).db_insert()


def _append_comment_log(doc, block):
	existing = doc.comment_log or ""
	doc.db_set("comment_log", f"{existing}\n{block}" if existing else block)

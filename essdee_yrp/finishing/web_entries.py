"""Finishing Plan quantity-entry commands for /web, delegating to the Frappe 15 services."""

from __future__ import annotations

import copy

import frappe
from frappe import _
from frappe.utils import cstr, flt

from essdee_yrp.cut_panel_store.common import parse_json_object
from essdee_yrp.finishing import alternative, old_lot, source_entries, transactions, views
from essdee_yrp.finishing.dispatch_locations import DISPATCH_LOCATION_FIELDS

DELIVERY_CHALLAN_TYPES = ("balance", "return_qty", "pack_return")
ENTRY_VIEWS = {
	"finishing_qty": "finishing_qty",
	"finishing_ironing": "finishing_ironing",
	"pack_return": "pack_return",
}


def quantity(value, label):
	"""Return a non-negative number or fail loudly with the offending cell."""

	if value in (None, ""):
		return 0
	try:
		number = float(value)
	except TypeError, ValueError:
		frappe.throw(_("{0} must be a number.").format(label))
	if number < 0:
		frappe.throw(_("{0} cannot be negative.").format(label))
	return number


def require(values, *fields):
	missing = [field for field in fields if values.get(field) in (None, "")]
	if missing:
		frappe.throw(_("Enter {0}.").format(", ".join(field.replace("_", " ").title() for field in missing)))


def get_entry_matrix(doc, view, field, quantities, checked_default=None):
	"""Copy a server view model and overlay browser quantities into ``field``."""

	plan_views = views.build_plan_views(doc)
	block = copy.deepcopy(plan_views[ENTRY_VIEWS[view]])
	rows = block.get("data") or {}
	entries = parse_json_object(quantities, label=_("Quantities"))
	unknown = set(entries) - set(rows)
	if unknown:
		frappe.throw(
			_("Colour {0} does not belong to this Finishing Plan.").format(", ".join(sorted(unknown)))
		)
	for colour, row in rows.items():
		entry = parse_json_object(entries.get(colour), label=colour)
		sizes = parse_json_object(entry.get("sizes"), label=colour)
		for size in sorted(set(sizes) - set(row.get("values") or {})):
			if quantity(sizes[size], f"{colour} {size}"):
				frappe.throw(_("No stock for {0} {1} in this Finishing Plan.").format(colour, size))
		for size, values in (row.get("values") or {}).items():
			values[field] = quantity(sizes.get(size), f"{colour} {size}")
		if checked_default is not None:
			row["check_value"] = bool(entry.get("checked", checked_default))
	return {
		"primary_values": plan_views["primary_values"],
		"is_set_item": plan_views["is_set_item"],
		"set_attr": plan_views["set_attr"],
		"data": block,
	}


def document(doctype, name, related=None):
	result = {"doctype": doctype, "name": name}
	if related:
		result["related"] = related
	return result


def create_delivery_challan(doc, values):
	require(values, "from_location", "actual_date")
	selected_type = values.get("selected_type")
	if selected_type not in DELIVERY_CHALLAN_TYPES:
		frappe.throw(_("Choose Balance, Loose Piece or Loose Piece Packed."))
	source_entry = cstr(values.get("source_entry"))
	if source_entry:
		source_entries.get_source_list_key(doc, source_entry)
	items = get_entry_matrix(
		doc, "finishing_qty", "balance_dc", values.get("quantities"), checked_default=False
	)
	name = transactions.create_delivery_challan(
		{"items": items, "selected_type": selected_type},
		doc.item,
		doc.work_order,
		doc.lot,
		values["from_location"],
		"NA",
		doc.name,
		values["actual_date"],
		source_entry=source_entry or None,
	)
	return document("YRP Delivery Challan", name)


def return_location_popup(doc, received_type):
	return {
		"from_location": doc.delivery_location,
		"delivery_location": doc.delivery_location,
		"vehicle_no": "NA",
		"received_type": received_type,
	}


def return_items(doc, values):
	require(values, "received_type")
	items = get_entry_matrix(doc, "finishing_qty", "return_qty", values.get("quantities"))
	name = transactions.return_items(
		items, doc.work_order, doc.lot, doc.item, return_location_popup(doc, values["received_type"])
	)
	return document("YRP Goods Received Note", name)


def convert_to_loose_piece(doc, values):
	require(values, "from_location")
	items = get_entry_matrix(doc, "finishing_qty", "return_qty", values.get("quantities"))
	created = transactions.convert_to_loose_piece_items(
		items, doc.work_order, doc.lot, doc.item, values["from_location"]
	)
	return document(
		"YRP Delivery Challan",
		created["delivery_challan"],
		related=document("YRP Goods Received Note", created["goods_received_note"]),
	)


def size_quantities(doc, values, label):
	sizes = transactions.get_primary_values(doc.lot, doc.production_detail)
	entries = parse_json_object(values.get("quantities"), label=_("Quantities"))
	unknown = set(entries) - set(sizes)
	if unknown:
		frappe.throw(_("Size {0} does not belong to this Finishing Plan.").format(", ".join(sorted(unknown))))
	return {size: quantity(entries.get(size), f"{label} {size}") for size in sizes}


def create_grn(doc, values):
	require(values, "delivery_location", "actual_date")
	name = transactions.create_grn(
		work_order=doc.work_order,
		lot=doc.lot,
		item_name=doc.item,
		data=size_quantities(doc, values, _("Packed boxes")),
		delivery_location=values["delivery_location"],
		actual_date=values["actual_date"],
		packing_batches=values.get("packing_batches") or None,
		request_id=cstr(values.get("request_id")) or None,
	)
	return document("YRP Goods Received Note", name)


def dispatch_box(doc, values):
	require(values, *DISPATCH_LOCATION_FIELDS, "goods_value", "vehicle_no")
	dispatch = {
		size: {"cur_dispatch": value} for size, value in size_quantities(doc, values, _("Dispatch")).items()
	}
	name = transactions.create_stock_entry(
		data=dispatch,
		item_name=doc.item,
		doc_name=doc.name,
		lot=doc.lot,
		**{field: values[field] for field in DISPATCH_LOCATION_FIELDS},
		goods_value=flt(values["goods_value"]),
		vehicle_no=values["vehicle_no"],
		colour_details=values.get("colour_details") or None,
		packing_batch_dispatches=values.get("packing_batch_dispatches") or None,
	)
	return document("YRP Stock Entry", name)


def add_ironing_excess(doc, values):
	items = get_entry_matrix(doc, "finishing_ironing", "ironing_dc", values.get("quantities"))
	name = transactions.create_material_receipt(
		items, doc.item, doc.lot, doc.production_detail, doc.name, doc.delivery_location
	)
	return document("YRP Stock Entry", name)


def return_pack(doc, values):
	items = get_entry_matrix(doc, "pack_return", "pack_return", values.get("quantities"))
	name = transactions.return_items(
		items, doc.work_order, doc.lot, doc.item, return_location_popup(doc, "Accepted"), is_pack=True
	)
	return document("YRP Goods Received Note", name)


def lot_transfer_rows(doc, transfers):
	available = copy.deepcopy(old_lot.fetch_from_old_lot(doc.name))
	groups = {(row["source_fp"], row["lot"], row["warehouse"]): row for row in available.get("data") or []}
	for transfer in transfers:
		key = (transfer.get("source_fp"), transfer.get("lot"), transfer.get("warehouse"))
		if key not in groups:
			frappe.throw(
				_("Loose pieces from {0} are no longer available. Fetch Items again.").format(key[0])
			)
		apply_lot_transfer(groups[key], transfer, available.get("colours") or [])
	return list(groups.values())


def apply_lot_transfer(group, transfer, colours):
	data = group["old_lot_inward"]["data"]
	for colour, entry in parse_json_object(transfer.get("colours"), label=_("Colours")).items():
		if colour not in data:
			frappe.throw(_("Colour {0} is not available in {1}.").format(colour, group["source_fp"]))
		total = 0
		for size, cell in parse_json_object(entry.get("sizes"), label=colour).items():
			total += apply_lot_transfer_cell(data[colour]["values"], colour, size, cell)
		if total and entry.get("set_combination") not in colours:
			frappe.throw(_("Please mention Set Colour"))
		data[colour]["set_combination"] = entry.get("set_combination")


def apply_lot_transfer_cell(values, colour, size, cell):
	if size not in values:
		frappe.throw(_("Size {0} does not belong to {1}.").format(size, colour))
	target = values[size]
	for bucket, balance, field in (
		("loose_piece", "balance_loose_piece", "transfer_loose_piece"),
		("loose_piece_set", "balance_loose_piece_set", "transfer_loose_piece_set"),
	):
		amount = quantity(cell.get(bucket), f"{colour} {size}")
		if amount > flt(target.get(balance)) + 1e-9:
			frappe.throw(
				_("Transfer ({0}) exceeds available ({1}) for {2} / {3}").format(
					amount, flt(target.get(balance)), colour, size
				)
			)
		target[field] = amount
	return flt(target["transfer_loose_piece"]) + flt(target["transfer_loose_piece_set"])


def lot_transfer(doc, values):
	transfers = values.get("transfers") or []
	if not isinstance(transfers, list):
		frappe.throw(_("Transfers must be a list."))
	rows = lot_transfer_rows(doc, transfers)
	name = old_lot.create_lot_transfer(rows, doc.item, doc.production_detail, doc.lot, doc.name)
	return document("SD YRP Lot Transfer", name)


def create_alternative_plan(doc, values):
	require(values, "alternative_item", "production_detail")
	if values["alternative_item"] not in (alternative.check_is_alternative_item(doc.item) or []):
		frappe.throw(
			_("{0} is not an alternative item for {1}.").format(values["alternative_item"], doc.item)
		)
	existing = values.get("lot_source") == "Existing Lot"
	require(values, "existing_lot" if existing else "lot_name")
	created = alternative.create_alternative_fp(
		doc_name=doc.name,
		alternative_item=values["alternative_item"],
		production_detail=values["production_detail"],
		lot_name=values.get("lot_name"),
		lot_source="existing" if existing else "new",
		existing_lot=values.get("existing_lot") if existing else None,
		qty_details=get_entry_matrix(
			doc, "finishing_qty", "conversion_qty", values.get("quantities"), checked_default=False
		),
	)
	return document("YRP Work Order", created["work_order"])


def update_alternative_quantity(doc, values):
	require(values, "target_lot")
	if values["target_lot"] not in (alternative.get_fp_alternate_lots(doc.lot) or []):
		frappe.throw(_("{0} is not an alternate lot of {1}.").format(values["target_lot"], doc.lot))
	work_order = alternative.update_alternative_lot_quantity(
		doc.name,
		values["target_lot"],
		get_entry_matrix(
			doc, "finishing_qty", "conversion_qty", values.get("quantities"), checked_default=False
		),
	)
	return document("YRP Work Order", work_order)


ENTRY_COMMANDS = {
	"create_delivery_challan": ("create_entries", create_delivery_challan),
	"return_items": ("create_entries", return_items),
	"convert_to_loose_piece": ("create_entries", convert_to_loose_piece),
	"create_grn": ("create_entries", create_grn),
	"dispatch_box": ("create_entries", dispatch_box),
	"add_ironing_excess": ("create_entries", add_ironing_excess),
	"return_pack": ("create_entries", return_pack),
	"lot_transfer": ("fetch_old_lot", lot_transfer),
	"create_alternative_plan": ("create_entries", create_alternative_plan),
	"update_alternative_quantity": ("create_entries", update_alternative_quantity),
}

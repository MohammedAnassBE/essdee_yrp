"""Transfer auditable leftover Finishing quantities between lots."""
from yrp.attribute_links import value as _attribute_value

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from essdee_yrp.finishing.old_lot_history import (
	get_old_lot_source_balance,
)
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.state import get_finishing_plan_dict, get_finishing_plan_list
from essdee_yrp.finishing.status import apply_auto_fp_status
from essdee_yrp.finishing.views import reshape_old_lot_rows_for_ui
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes, get_or_create_variant


@frappe.whitelist()
def fetch_from_old_lot(doc_name):
	"""Return current sibling-lot loose balances without persisting UI rows."""
	doc = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	doc.check_permission("write")
	if doc.fp_status == "OCR Completed":
		frappe.throw("Fetch Items is disabled for Finishing Plans in OCR Completed status.")
	ipd = frappe.get_cached_doc('YRP Item Production Detail', doc.production_detail)
	current_colours = {
		get_variant_attr_details(row.item_variant).get(ipd.packing_attribute)
		for row in doc.get("finishing_plan_details") or []
	}
	current_colours.discard(None)
	aggregated = {}
	for source_name in frappe.get_all(
		'SD YRP Finishing Plan',
		filters={
			"item": doc.item,
			"name": ["!=", doc.name],
			"docstatus": ["<", 2],
		},
		pluck="name",
	):
		source = frappe.get_doc('SD YRP Finishing Plan', source_name)
		warehouse = _warehouse_for_supplier(source.delivery_location)
		seen_variants = set()
		for row in source.get("finishing_plan_details") or []:
			if row.item_variant in seen_variants:
				continue
			seen_variants.add(row.item_variant)
			loose, loose_set = get_old_lot_source_balance(
				source, row.item_variant
			)
			if not loose and not loose_set:
				continue
			attributes = get_variant_attr_details(row.item_variant)
			if attributes.get(ipd.packing_attribute) not in current_colours:
				continue
			key = (source.name, source.lot, warehouse, row.item_variant)
			previous = aggregated.get(key, (0, 0))
			aggregated[key] = (previous[0] + loose, previous[1] + loose_set)

	fetched_rows = []
	for (source_name, source_lot, warehouse, item_variant), quantities in aggregated.items():
		attributes = get_variant_attr_details(item_variant)
		colour = attributes.get(ipd.packing_attribute)
		part = attributes.get(ipd.set_item_attribute) if ipd.is_set_item else None
		set_value = colour if not ipd.is_set_item or _attribute_value(ipd.major_attribute_value) == part else None
		fetched_rows.append(
			frappe._dict({
				"source_fp": source_name,
				"source_lot": source_lot,
				"warehouse": warehouse,
					"warehouse_name": frappe.db.get_value('Warehouse', warehouse, "warehouse_name") or warehouse,
				"item_variant": item_variant,
				"colour": colour,
				"part": part,
				"set_combination": set_value,
				"size": attributes.get(ipd.primary_item_attribute),
				"balance_loose_piece": quantities[0],
				"balance_loose_piece_set": quantities[1],
			}),
		)
	return reshape_old_lot_rows_for_ui(
		frappe._dict(
			lot=doc.lot,
			production_detail=doc.production_detail,
			finishing_old_lot_items=fetched_rows,
		),
		ipd,
	)


@frappe.whitelist()
def create_lot_transfer(data, item_name, ipd, lot, doc_name):
	payload = update_if_string_instance(data) or []
	destination = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	destination.check_permission("write")
	if destination.item != item_name or destination.lot != lot or destination.production_detail != ipd:
		frappe.throw("Finishing Plan, Item, Lot, and Production Detail do not match")
	ipd_doc = frappe.get_cached_doc('YRP Item Production Detail', ipd)
	default_type = frappe.db.get_single_value('YRP Stock Settings', "default_received_type")
	uom = frappe.db.get_value('Item', item_name, "stock_uom")
	items = []
	contributions = []
	row_index = 0
	for table_index, group in enumerate(payload):
		source_fp = group.get("source_fp")
		if not source_fp:
			frappe.throw("Source Finishing Plan is missing. Fetch Items again.")
		for colour, colour_entry in (group.get("old_lot_inward", {}).get("data", {}) or {}).items():
			for size, cell in (colour_entry.get("values") or {}).items():
				loose = flt(cell.get("transfer_loose_piece"))
				loose_set = flt(cell.get("transfer_loose_piece_set"))
				quantity = loose + loose_set
				if quantity <= 0:
					continue
				attributes = {
					ipd_doc.primary_item_attribute: size,
					ipd_doc.packing_attribute: colour,
				}
				if ipd_doc.is_set_item:
					attributes[ipd_doc.set_item_attribute] = _attribute_value(colour_entry.get("part"))
				variant = get_or_create_variant(
					item_name,
					build_variant_attributes(attributes, _attribute_value(ipd_doc.stiching_out_stage), ipd),
				)
				combination = {"major_colour": colour_entry.get("set_combination")}
				if ipd_doc.is_set_item:
					combination["major_part"] = _attribute_value(ipd_doc.major_attribute_value)
				items.append(
					{
						"item": variant,
						"from_lot": group.get("lot"),
						"to_lot": lot,
						"warehouse": group.get("warehouse"),
						"uom": uom,
						"qty": quantity,
						"table_index": table_index,
						"row_index": row_index,
						"received_type": default_type,
						"set_combination": frappe.as_json(combination),
					}
				)
				contributions.append(
					{
						"source_fp": source_fp,
						"source_lot": group.get("lot"),
						"warehouse": group.get("warehouse"),
						"item_variant": variant,
						"colour": colour,
						"part": _attribute_value(colour_entry.get("part")),
						"set_combination": combination,
						"size": size,
						"loose_piece": loose,
						"loose_piece_set": loose_set,
					}
				)
			row_index += 1
	if not items:
		frappe.throw("Select at least one old-lot quantity")
	_validate_old_lot_transfer_balances(
		contributions,
		destination_fp=doc_name,
		item_name=item_name,
	)
	transfer = frappe.new_doc('SD YRP Lot Transfer')
	transfer.finishing_plan = doc_name
	for row in items:
		transfer.append("items", row)
	transfer.insert()
	transfer.submit()
	_record_split_history(destination, transfer, contributions)
	return transfer.name


def _validate_old_lot_transfer_balances(
	contributions, destination_fp=None, item_name=None
):
	requested = {}
	for entry in contributions:
		key = (entry["source_fp"], entry["item_variant"])
		values = requested.setdefault(
			key, {"loose_piece": 0, "loose_piece_set": 0}
		)
		values["loose_piece"] += flt(entry["loose_piece"])
		values["loose_piece_set"] += flt(entry["loose_piece_set"])

	for source_fp in sorted({key[0] for key in requested}):
		frappe.db.sql(
			"SELECT name FROM `tabSD YRP Finishing Plan` WHERE name = %s FOR UPDATE",
			source_fp,
		)

	for (source_name, item_variant), quantities in requested.items():
		source = frappe.get_doc('SD YRP Finishing Plan', source_name)
		entries = [
			entry
			for entry in contributions
			if entry["source_fp"] == source_name
			and entry["item_variant"] == item_variant
		]
		if destination_fp and source_name == destination_fp:
			frappe.throw("Source and destination Finishing Plans cannot be the same.")
		if item_name and source.item != item_name:
			frappe.throw(f"Source Finishing Plan {source_name} has a different item.")
		if any(entry["source_lot"] != source.lot for entry in entries):
			frappe.throw(f"Source lot changed for {source_name}. Fetch Items again.")
		source_warehouse = _warehouse_for_supplier(source.delivery_location)
		if any(entry["warehouse"] != source_warehouse for entry in entries):
			frappe.throw(f"Source warehouse changed for {source_name}. Fetch Items again.")
		if item_variant not in {
			row.item_variant for row in source.get("finishing_plan_details") or []
		}:
			frappe.throw(
				f"Item {item_variant} is no longer available in {source_name}. "
				"Fetch Items again."
			)
		available_loose, available_loose_set = get_old_lot_source_balance(
			source, item_variant
		)
		if quantities["loose_piece"] > available_loose:
			frappe.throw(
				f"Loose Piece requested from {source_name} exceeds the current "
				f"available quantity ({available_loose}). Fetch Items again."
			)
		if quantities["loose_piece_set"] > available_loose_set:
			frappe.throw(
				f"Loose Piece Set requested from {source_name} exceeds the current "
				f"available quantity ({available_loose_set}). Fetch Items again."
			)


def on_lot_transfer_submit(transfer, method=None):
	_apply_lot_transfer_to_finishing(transfer, cancelled=False)


def on_lot_transfer_cancel(transfer, method=None):
	_apply_lot_transfer_to_finishing(transfer, cancelled=True)
	_reverse_split_history(transfer)


def _apply_lot_transfer_to_finishing(transfer, *, cancelled):
	"""Apply the generic Lot Transfer rows to the linked Finishing Plan.

	The base YRP controller owns stock movement. This adapter owns only the
	Essdee Finishing quantities and audit-list marker.
	"""
	if not transfer.get("finishing_plan"):
		return

	finishing_doc = frappe.get_doc('SD YRP Finishing Plan', transfer.finishing_plan)
	transfer_list = update_if_string_instance(finishing_doc.lot_transfer_list) or {}
	already_applied = transfer.name in transfer_list
	if (cancelled and not already_applied) or (not cancelled and already_applied):
		return

	finishing_items = get_finishing_plan_dict(finishing_doc)
	operation = -1 if cancelled else 1
	for row in transfer.get("items") or []:
		combination = json_object(row.set_combination)
		key = (row.item, tuple(sorted(combination.items())))
		if key not in finishing_items:
			frappe.throw(
				_("Item {0} with its set combination is not part of Finishing Plan {1}").format(
					row.item, finishing_doc.name
				)
			)
		finishing_items[key]["lot_transferred"] += operation * flt(row.qty)

	if cancelled:
		transfer_list.pop(transfer.name, None)
	else:
		transfer_list[transfer.name] = now_datetime().strftime("%d-%m-%Y %H:%M:%S")
	finishing_doc.lot_transfer_list = frappe.as_json(transfer_list)
	finishing_doc.set("finishing_plan_details", get_finishing_plan_list(finishing_items))
	apply_auto_fp_status(finishing_doc)
	finishing_doc.save(ignore_permissions=True)


def _record_split_history(_destination, transfer, contributions):
	"""Store each split once on its source Finishing Plan."""
	if not contributions:
		return

	source_docs = {}
	for entry in contributions:
		source = source_docs.setdefault(
			entry["source_fp"],
			frappe.get_doc('SD YRP Finishing Plan', entry["source_fp"]),
		)
		if any(
			row.lot_transfer == transfer.name
			and row.item_variant == entry["item_variant"]
			and row.size == _attribute_value(entry["size"])
			for row in source.get("finishing_old_lot_given_items") or []
		):
			continue
		source.append(
			"finishing_old_lot_given_items",
			{
				"destination_fp": transfer.finishing_plan,
				"destination_lot": transfer.get("items")[0].to_lot,
				"item_variant": entry["item_variant"],
				"colour": _attribute_value(entry["colour"]),
				"part": _attribute_value(entry["part"]),
				"set_combination": frappe.as_json(entry["set_combination"]),
				"size": _attribute_value(entry["size"]),
				"loose_piece_given": entry["loose_piece"],
				"loose_piece_set_given": entry["loose_piece_set"],
				"lot_transfer": transfer.name,
			},
		)

	for source in source_docs.values():
		source.save(ignore_permissions=True)


def _reverse_split_history(transfer):
	"""Remove source history and any legacy destination copy on cancellation."""
	for child_doctype, parentfield in (
		('SD YRP Finishing Plan Old Lot Given', "finishing_old_lot_given_items"),
		('SD YRP Finishing Plan Old Lot Received', "finishing_old_lot_received_items"),
	):
		parents = set(
			frappe.get_all(
				child_doctype,
				filters={"lot_transfer": transfer.name},
				pluck="parent",
			)
		)
		for parent in parents:
			plan = frappe.get_doc('SD YRP Finishing Plan', parent)
			plan.set(
				parentfield,
				[
					row
					for row in plan.get(parentfield) or []
					if row.lot_transfer != transfer.name
				],
			)
			plan.save(ignore_permissions=True)


def _warehouse_for_supplier(supplier):
	if not supplier:
		frappe.throw(_("Finishing Plan delivery location is required for old-lot transfer"))
	if frappe.db.exists('Warehouse', {"name": supplier, "disabled": 0, "is_group": 0}):
		return supplier
	warehouses = frappe.get_all(
		'Warehouse',
		filters={"supplier": supplier, "disabled": 0, "is_group": 0},
		pluck="name",
	)
	if len(warehouses) == 1:
		return warehouses[0]
	if not warehouses:
		frappe.throw(_("No active stock Warehouse is linked to Supplier {0}").format(supplier))
	frappe.throw(
		_("Multiple stock Warehouses are linked to Supplier {0}; select a unique mapping").format(
			supplier
		)
	)

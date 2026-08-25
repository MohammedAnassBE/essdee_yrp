"""Transfer auditable leftover Finishing quantities between lots."""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, now_datetime

from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.state import get_finishing_plan_dict, get_finishing_plan_list
from essdee_yrp.finishing.status import apply_auto_fp_status
from essdee_yrp.finishing.views import reshape_old_lot_rows_for_ui
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.item.item import build_variant_attributes, get_or_create_variant


@frappe.whitelist()
def fetch_from_old_lot(doc_name):
	"""Persist available OCR-completed sibling-lot quantities for selection."""
	doc = frappe.get_doc("Finishing Plan", doc_name)
	doc.check_permission("write")
	if doc.fp_status == "OCR Completed":
		frappe.throw("Fetch Items is disabled for Finishing Plans in OCR Completed status.")
	ipd = frappe.get_cached_doc("Item Production Detail", doc.production_detail)
	open_plans = frappe.get_all(
		"Finishing Plan",
		filters={
			"item": doc.item,
			"name": ["!=", doc.name],
			"fp_status": ["not in", ["OCR Completed", "P&L Submitted"]],
		},
		fields=["name", "lot", "fp_status"],
	)
	if open_plans:
		rows = "".join(
			f"<tr><td>{escape_html(row.name)}</td><td>{escape_html(row.lot)}</td>"
			f"<td>{escape_html(row.fp_status)}</td></tr>"
			for row in open_plans
		)
		frappe.throw(
			"Close Other Finishing Plans to fetch the items.<br><br>"
			"<table class='table table-bordered'>"
			"<thead><tr><th>Finishing Plan</th><th>Lot</th><th>Status</th></tr></thead>"
			f"<tbody>{rows}</tbody></table>",
			title="Other Finishing Plans Still Open",
		)
	current_colours = {
		get_variant_attr_details(row.item_variant).get(ipd.packing_attribute)
		for row in doc.get("finishing_plan_details") or []
	}
	current_colours.discard(None)
	aggregated = {}
	for source_name in frappe.get_all(
		"Finishing Plan",
		filters={
			"item": doc.item,
			"fp_status": "OCR Completed",
			"name": ["!=", doc.name],
		},
		pluck="name",
	):
		source = frappe.get_doc("Finishing Plan", source_name)
		warehouse = _warehouse_for_supplier(source.delivery_location)
		given_loose = {}
		given_set = {}
		for row in source.get("finishing_old_lot_given_items") or []:
			given_loose[row.item_variant] = given_loose.get(row.item_variant, 0) + flt(row.loose_piece_given)
			given_set[row.item_variant] = given_set.get(row.item_variant, 0) + flt(row.loose_piece_set_given)
		for row in source.get("finishing_plan_details") or []:
			loose = max(flt(row.return_qty) - given_loose.get(row.item_variant, 0), 0)
			loose_set = max(flt(row.pack_return_qty) - given_set.get(row.item_variant, 0), 0)
			if not loose and not loose_set:
				continue
			attributes = get_variant_attr_details(row.item_variant)
			if attributes.get(ipd.packing_attribute) not in current_colours:
				continue
			key = (source.name, source.lot, warehouse, row.item_variant)
			previous = aggregated.get(key, (0, 0))
			aggregated[key] = (previous[0] + loose, previous[1] + loose_set)

	doc.set("finishing_old_lot_items", [])
	for (source_name, source_lot, warehouse, item_variant), quantities in aggregated.items():
		attributes = get_variant_attr_details(item_variant)
		colour = attributes.get(ipd.packing_attribute)
		part = attributes.get(ipd.set_item_attribute) if ipd.is_set_item else None
		set_value = colour if not ipd.is_set_item or ipd.major_attribute_value == part else None
		doc.append(
			"finishing_old_lot_items",
			{
				"source_fp": source_name,
				"source_lot": source_lot,
				"warehouse": warehouse,
				"warehouse_name": frappe.db.get_value("Warehouse", warehouse, "name1") or warehouse,
				"item_variant": item_variant,
				"colour": colour,
				"part": part,
				"set_combination": set_value,
				"size": attributes.get(ipd.primary_item_attribute),
				"balance_loose_piece": quantities[0],
				"balance_loose_piece_set": quantities[1],
			},
		)
	doc.save(ignore_permissions=True)
	return reshape_old_lot_rows_for_ui(doc, ipd)


@frappe.whitelist()
def create_lot_transfer(data, item_name, ipd, lot, doc_name):
	payload = update_if_string_instance(data) or []
	destination = frappe.get_doc("Finishing Plan", doc_name)
	destination.check_permission("write")
	if destination.item != item_name or destination.lot != lot or destination.production_detail != ipd:
		frappe.throw("Finishing Plan, Item, Lot, and Production Detail do not match")
	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd)
	default_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	uom = frappe.db.get_value("Item", item_name, "default_unit_of_measure")
	available_rows = {
		(row.source_lot, row.warehouse, row.item_variant): row
		for row in destination.get("finishing_old_lot_items") or []
	}
	items = []
	contributions = []
	row_index = 0
	for table_index, group in enumerate(payload):
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
					attributes[ipd_doc.set_item_attribute] = colour_entry.get("part")
				variant = get_or_create_variant(
					item_name,
					build_variant_attributes(attributes, ipd_doc.stiching_out_stage, ipd),
				)
				available = available_rows.get(
					(group.get("lot"), group.get("warehouse"), variant)
				)
				if not available:
					frappe.throw(f"No old-lot balance exists for {group.get('lot')} / {variant}")
				if loose > flt(available.balance_loose_piece) or loose_set > flt(available.balance_loose_piece_set):
					frappe.throw(f"Transfer quantity exceeds old-lot balance for {variant}")
				combination = {"major_colour": colour_entry.get("set_combination")}
				if ipd_doc.is_set_item:
					combination["major_part"] = ipd_doc.major_attribute_value
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
						"available_row": available,
						"source_fp": available.source_fp,
						"source_lot": group.get("lot"),
						"item_variant": variant,
						"colour": colour,
						"part": colour_entry.get("part"),
						"set_combination": combination,
						"size": size,
						"loose_piece": loose,
						"loose_piece_set": loose_set,
					}
				)
			row_index += 1
	if not items:
		frappe.throw("Select at least one old-lot quantity")
	transfer = frappe.new_doc("Lot Transfer")
	transfer.finishing_plan = doc_name
	for row in items:
		transfer.append("items", row)
	transfer.insert()
	transfer.submit()
	_record_split_history(destination, transfer, contributions)
	return transfer.name


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

	finishing_doc = frappe.get_doc("Finishing Plan", transfer.finishing_plan)
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
	"""Record which old-lot loose quantities funded a submitted transfer."""
	if not contributions:
		return

	# The Lot Transfer on_submit hook saves this document, so reload instead of
	# writing a stale pre-submit instance over the freshly applied quantities.
	destination = frappe.get_doc("Finishing Plan", transfer.finishing_plan)
	if any(
		row.lot_transfer == transfer.name
		for row in destination.get("finishing_old_lot_received_items") or []
	):
		return

	source_docs = {}
	for entry in contributions:
		available = next(
			(
				row
				for row in destination.get("finishing_old_lot_items") or []
				if row.source_fp == entry["source_fp"]
				and row.source_lot == entry["source_lot"]
				and row.item_variant == entry["item_variant"]
			),
			None,
		)
		if not available:
			frappe.throw(
				_("Old-lot balance row disappeared for {0}").format(entry["item_variant"])
			)
		available.balance_loose_piece = flt(available.balance_loose_piece) - flt(
			entry["loose_piece"]
		)
		available.balance_loose_piece_set = flt(
			available.balance_loose_piece_set
		) - flt(entry["loose_piece_set"])
		if available.balance_loose_piece < 0 or available.balance_loose_piece_set < 0:
			frappe.throw(
				_("Old-lot balance became negative for {0}").format(entry["item_variant"])
			)
		available.transfer_loose_piece = 0
		available.transfer_loose_piece_set = 0

		combination_json = frappe.as_json(entry["set_combination"])
		destination.append(
			"finishing_old_lot_received_items",
			{
				"source_fp": entry["source_fp"],
				"source_lot": entry["source_lot"],
				"item_variant": entry["item_variant"],
				"colour": entry["colour"],
				"part": entry["part"],
				"set_combination": combination_json,
				"size": entry["size"],
				"loose_piece_taken": entry["loose_piece"],
				"loose_piece_set_taken": entry["loose_piece_set"],
				"lot_transfer": transfer.name,
			},
		)

		source = source_docs.setdefault(
			entry["source_fp"],
			frappe.get_doc("Finishing Plan", entry["source_fp"]),
		)
		source.append(
			"finishing_old_lot_given_items",
			{
				"destination_fp": destination.name,
				"destination_lot": destination.lot,
				"item_variant": entry["item_variant"],
				"colour": entry["colour"],
				"part": entry["part"],
				"set_combination": combination_json,
				"size": entry["size"],
				"loose_piece_given": entry["loose_piece"],
				"loose_piece_set_given": entry["loose_piece_set"],
				"lot_transfer": transfer.name,
			},
		)

	destination.set(
		"finishing_old_lot_items",
		[
			row
			for row in destination.get("finishing_old_lot_items") or []
			if flt(row.balance_loose_piece) > 0
			or flt(row.balance_loose_piece_set) > 0
		],
	)
	apply_auto_fp_status(destination)
	destination.save(ignore_permissions=True)
	for source in source_docs.values():
		apply_auto_fp_status(source)
		source.save(ignore_permissions=True)


def _reverse_split_history(transfer):
	"""Restore old-lot balances and remove both audit rows on cancellation."""
	if not transfer.get("finishing_plan"):
		return
	destination = frappe.get_doc("Finishing Plan", transfer.finishing_plan)
	received_rows = [
		row
		for row in destination.get("finishing_old_lot_received_items") or []
		if row.lot_transfer == transfer.name
	]
	if not received_rows:
		return

	source_docs = {}
	for history in received_rows:
		source = source_docs.setdefault(
			history.source_fp,
			frappe.get_doc("Finishing Plan", history.source_fp),
		)
		available = next(
			(
				row
				for row in destination.get("finishing_old_lot_items") or []
				if row.source_fp == history.source_fp
				and row.source_lot == history.source_lot
				and row.item_variant == history.item_variant
			),
			None,
		)
		if not available:
			combination = json_object(history.set_combination)
			available = destination.append(
				"finishing_old_lot_items",
				{
					"source_fp": history.source_fp,
					"source_lot": history.source_lot,
					"warehouse": _warehouse_for_supplier(source.delivery_location),
					"warehouse_name": frappe.db.get_value(
						"Warehouse",
						_warehouse_for_supplier(source.delivery_location),
						"name1",
					)
					or source.delivery_location,
					"item_variant": history.item_variant,
					"colour": history.colour,
					"part": history.part,
					"set_combination": combination.get("major_colour") or history.colour,
					"size": history.size,
					"balance_loose_piece": 0,
					"balance_loose_piece_set": 0,
				},
			)
		available.balance_loose_piece = flt(available.balance_loose_piece) + flt(
			history.loose_piece_taken
		)
		available.balance_loose_piece_set = flt(
			available.balance_loose_piece_set
		) + flt(history.loose_piece_set_taken)

	destination.set(
		"finishing_old_lot_received_items",
		[
			row
			for row in destination.get("finishing_old_lot_received_items") or []
			if row.lot_transfer != transfer.name
		],
	)
	apply_auto_fp_status(destination)
	destination.save(ignore_permissions=True)
	for source in source_docs.values():
		source.set(
			"finishing_old_lot_given_items",
			[
				row
				for row in source.get("finishing_old_lot_given_items") or []
				if row.lot_transfer != transfer.name
			],
		)
		apply_auto_fp_status(source)
		source.save(ignore_permissions=True)


def _warehouse_for_supplier(supplier):
	if not supplier:
		frappe.throw(_("Finishing Plan delivery location is required for old-lot transfer"))
	if frappe.db.exists("Warehouse", {"name": supplier, "disabled": 0, "is_group": 0}):
		return supplier
	warehouses = frappe.get_all(
		"Warehouse",
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

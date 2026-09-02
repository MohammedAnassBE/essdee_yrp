"""Alternative-item Finishing Plan orchestration for Essdee."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.finishing.work_order_packing import (
	build_packing_work_order_rows,
	create_alternative_packing_work_order,
)
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.production_order_alternative import (
	apply_alternative_plan_ppo_transfer,
	create_alternative_plan_production_order,
)
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes, get_or_create_variant


@frappe.whitelist()
def get_fp_alternate_lots(fp_lot):
	return frappe.get_list(
		'SD YRP Lot',
		filters={"transferred_lot": fp_lot, "is_transferred": 1},
		pluck="name",
		order_by="creation desc",
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_unconfigured_lots(doctype, txt, searchfield, start, page_len, filters):
	like = f"%{txt or ''}%"
	return frappe.db.sql(
		"""
			SELECT l.name
			FROM `tabSD YRP Lot` l
			WHERE COALESCE(l.production_detail, '') = ''
			  AND COALESCE(l.production_order, '') = ''
			  AND COALESCE(l.item, '') = ''
			  AND COALESCE(l.status, '') != 'Closed'
			  AND (l.name LIKE %(txt)s OR l.lot_name LIKE %(txt)s)
			  AND NOT EXISTS (
				SELECT 1 FROM `tabSD YRP Lot Order Detail` lod WHERE lod.parent = l.name
			  )
			  AND NOT EXISTS (
				SELECT 1 FROM `tabSD YRP Lot Order Item` loi WHERE loi.parent = l.name
			  )
			ORDER BY l.modified DESC
			LIMIT %(start)s, %(page_len)s
		""",
		{"txt": like, "start": int(start or 0), "page_len": int(page_len or 20)},
	)


def validate_lot_is_unconfigured(lot_doc):
	problems = []
	if lot_doc.production_detail:
		problems.append(_("Item Production Detail"))
	if lot_doc.production_order:
		problems.append(_("Production Order"))
	if lot_doc.item:
		problems.append(_("Item"))
	if lot_doc.get("lot_order_details"):
		problems.append(_("Lot Order Details"))
	if lot_doc.get("items"):
		problems.append(_("Items"))
	if lot_doc.status == "Closed":
		problems.append(_("Status is Closed"))
	if problems:
		frappe.throw(
			_("Lot {0} is already configured ({1})").format(
				lot_doc.name, ", ".join(problems)
			)
		)


def resolve_alternative_lot(
	lot_source,
	lot_name,
	existing_lot,
	production_detail,
	alternative_item,
	finishing_plan,
):
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import get_isfinal_uom

	if lot_source == "existing":
		if not existing_lot:
			frappe.throw(_("Please select an existing Lot"))
		lot_doc = frappe.get_doc('SD YRP Lot', existing_lot)
		lot_doc.check_permission("write")
		validate_lot_is_unconfigured(lot_doc)
	else:
		frappe.has_permission('SD YRP Lot', "create", throw=True)
		lot_doc = frappe.new_doc('SD YRP Lot')
		lot_doc.lot_name = lot_name

	ipd = frappe.get_cached_doc('YRP Item Production Detail', production_detail)
	if ipd.item != alternative_item:
		frappe.throw(
			_("Item Production Detail {0} belongs to {1}, not {2}").format(
				ipd.name, ipd.item, alternative_item
			)
		)
	response = get_isfinal_uom(production_detail, get_pack_stage=True)
	lot_doc.update(
		{
			"production_detail": production_detail,
			"item": alternative_item,
			"uom": response["uom"],
			"pack_in_stage": response["pack_in_stage"],
			"packing_uom": response["packing_uom"],
			"pack_out_stage": response["pack_out_stage"],
			"dependent_attribute_mapping": response["dependent_attr_mapping"],
			"tech_pack_version": response["tech_pack_version"],
			"pattern_version": response["pattern_version"],
			"packing_combo": response["packing_combo"],
			"is_transferred": 1,
			"transferred_lot": finishing_plan.lot,
		}
	)
	lot_doc.save(ignore_permissions=lot_source != "existing")
	return lot_doc


@frappe.whitelist()
def create_alternative_fp(
	doc_name,
	alternative_item,
	production_detail,
	lot_name,
	qty_details,
	lot_source="new",
	existing_lot=None,
):
	finishing_plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	finishing_plan.check_permission("write")
	qty_details = update_if_string_instance(qty_details) or {}
	lot_source = (
		"existing"
		if str(lot_source).strip().lower() in ("existing", "existing lot")
		else "new"
	)
	conversions = _collect_conversions(qty_details)
	if not conversions:
		frappe.throw(_("Enter a quantity to move"))
	_validate_conversion_balance(finishing_plan, conversions)
	check_colours_and_sizes(
		production_detail,
		sorted({row["colour"] for row in conversions}),
		sorted({row["size"] for row in conversions}),
	)
	work_order = frappe.get_doc('YRP Work Order', finishing_plan.work_order)
	source_production_order = frappe.db.get_value(
		'SD YRP Lot', finishing_plan.lot, "production_order"
	)
	if not source_production_order:
		frappe.throw(
			_("Source Lot {0} has no Production Order").format(finishing_plan.lot)
		)

	lot_doc = resolve_alternative_lot(
		lot_source,
		lot_name,
		existing_lot,
		production_detail,
		alternative_item,
		finishing_plan,
	)
	_append_conversions_to_lot(lot_doc, conversions)
	size_quantities = _size_quantities(conversions)
	target_production_order = create_alternative_plan_production_order(
		source_production_order=source_production_order,
		source_lot=finishing_plan.lot,
		target_lot=lot_doc.name,
		alternative_item=alternative_item,
		transfers=size_quantities,
		finishing_plan=finishing_plan.name,
	)
	_reduce_source_lot_quantity(finishing_plan.lot, conversions)
	target_work_order = create_alternative_packing_work_order(
		work_order.name, lot_doc.name
	)
	frappe.db.set_value('SD YRP Lot', finishing_plan.lot, "has_transferred", 1)
	return {
		"work_order": target_work_order,
		"lot": lot_doc.name,
		"production_order": target_production_order,
	}


@frappe.whitelist()
def update_alternative_lot_quantity(doc_name, target_lot, qty_details):
	source_plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	source_plan.check_permission("write")
	_validate_alternate_lot(target_lot, source_plan.lot)
	conversions = _collect_conversions(update_if_string_instance(qty_details) or {})
	if not conversions:
		frappe.throw(_("Enter a quantity to move"))
	_validate_conversion_balance(source_plan, conversions)

	lot_doc = frappe.get_doc('SD YRP Lot', target_lot)
	_append_conversions_to_lot(lot_doc, conversions)
	source_ppo = frappe.db.get_value('SD YRP Lot', source_plan.lot, "production_order")
	target_ppo = frappe.db.get_value('SD YRP Lot', target_lot, "production_order")
	if not source_ppo or not target_ppo:
		frappe.throw(_("Both Lots must be linked to Production Orders"))
	apply_alternative_plan_ppo_transfer(
		source_production_order=source_ppo,
		target_production_order=target_ppo,
		source_lot=source_plan.lot,
		target_lot=target_lot,
		transfers=_size_quantities(conversions),
		reason=_("Additional alternative conversion from Finishing Plan {0}").format(
			source_plan.name
		),
	)
	_reduce_source_lot_quantity(source_plan.lot, conversions)

	work_order = frappe.get_doc('YRP Work Order', _get_packing_work_order(target_lot))
	rows = build_packing_work_order_rows(lot_doc, work_order.process_name)
	if work_order.docstatus == 0:
		_apply_draft_work_order_rows(work_order, rows)
	else:
		from essdee_yrp.finishing.work_order import update_submitted_alternative_work_order

		update_submitted_alternative_work_order(source_plan, work_order, rows)
	return work_order.name


@frappe.whitelist()
def get_alternative_details(lot):
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import fetch_order_item_details

	frappe.get_doc('SD YRP Lot', lot).check_permission("read")
	result = {}
	for name in frappe.get_list(
		'SD YRP Lot', filters={"transferred_lot": lot}, pluck="name"
	):
		lot_doc = frappe.get_doc('SD YRP Lot', name)
		result[name] = {
			"item": lot_doc.item,
			"ipd": lot_doc.production_detail,
			"details": fetch_order_item_details(
				lot_doc.lot_order_details, lot_doc.production_detail
			),
		}
	return result


@frappe.whitelist()
def check_is_alternative_item(item):
	return frappe.get_list(
		'SD YRP Item Alternative', filters={"item": item}, pluck="alternative_item"
	)


def _collect_conversions(qty_details):
	conversions = []
	data = ((qty_details.get("data") or {}).get("data") or {})
	for colour, row in data.items():
		if not row.get("check_value"):
			continue
		for size, values in (row.get("values") or {}).items():
			quantity = flt(values.get("conversion_qty"))
			if quantity > 0:
				conversions.append(
					{"colour": colour, "size": size, "qty": quantity}
				)
	return conversions


def _size_quantities(conversions):
	result = {}
	for row in conversions:
		result[row["size"]] = result.get(row["size"], 0) + flt(row["qty"])
	return result


def _append_conversions_to_lot(lot_doc, conversions):
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE", (lot_doc.name,)
	)
	lot_doc.reload()
	ipd = frappe.get_cached_doc('YRP Item Production Detail', lot_doc.production_detail)
	rows_by_key = {
		_lot_row_key(row, ipd): row for row in lot_doc.get("lot_order_details") or []
	}
	row_index_by_colour = {}
	max_row_index = -1
	for row in lot_doc.get("lot_order_details") or []:
		combination = json_object(row.set_combination)
		colour = combination.get("major_colour")
		if colour:
			row_index_by_colour.setdefault(colour, row.row_index)
		max_row_index = max(max_row_index, int(row.row_index or 0))

	for conversion in conversions:
		key = (str(conversion["colour"]), str(conversion["size"]))
		row = rows_by_key.get(key)
		if row:
			row.quantity = flt(row.quantity) + conversion["qty"]
			row.cut_qty = flt(row.cut_qty) + conversion["qty"]
			continue
		colour = conversion["colour"]
		if colour not in row_index_by_colour:
			max_row_index += 1
			row_index_by_colour[colour] = max_row_index
		variant = get_or_create_variant(
			lot_doc.item,
			build_variant_attributes(
				{
					ipd.primary_item_attribute: conversion["size"],
					ipd.packing_attribute: colour,
				},
				ipd.pack_in_stage,
				ipd.name,
			),
		)
		row = lot_doc.append(
			"lot_order_details",
			{
				"item_variant": variant,
				"quantity": conversion["qty"],
				"cut_qty": conversion["qty"],
				"pack_qty": 0,
				"stich_qty": 0,
				"table_index": 0,
				"row_index": row_index_by_colour[colour],
				"set_combination": frappe.as_json({"major_colour": colour}),
			},
		)
		rows_by_key[key] = row
	_rebuild_lot_order_items(lot_doc, ipd)
	lot_doc.total_order_quantity = sum(
		flt(row.quantity) for row in lot_doc.get("lot_order_details") or []
	)
	lot_doc.total_quantity = sum(flt(row.qty) for row in lot_doc.get("items") or [])
	lot_doc.save(ignore_permissions=True)


def _lot_row_key(row, ipd):
	attributes = get_variant_attr_details(row.item_variant)
	combination = json_object(row.set_combination)
	return (
		str(
			attributes.get(ipd.packing_attribute)
			or combination.get("major_colour")
			or ""
		),
		str(attributes.get(ipd.primary_item_attribute) or ""),
	)


def _rebuild_lot_order_items(lot_doc, ipd):
	size_totals = {}
	for row in lot_doc.get("lot_order_details") or []:
		size = get_variant_attr_details(row.item_variant).get(ipd.primary_item_attribute)
		if size:
			size_totals[size] = size_totals.get(size, 0) + flt(row.quantity)
	if flt(ipd.packing_combo) <= 0:
		frappe.throw(_("Packing Combo must be greater than zero"))
	existing = {}
	for row in lot_doc.get("items") or []:
		size = get_variant_attr_details(row.item_variant).get(ipd.primary_item_attribute)
		if size:
			existing[size] = row
	for index, (size, quantity) in enumerate(size_totals.items()):
		box_quantity = round(quantity / flt(ipd.packing_combo), 6)
		if size in existing:
			existing[size].qty = box_quantity
			continue
		variant = get_or_create_variant(
			lot_doc.item,
			build_variant_attributes(
				{ipd.primary_item_attribute: size}, ipd.pack_out_stage, ipd.name
			),
		)
		lot_doc.append(
			"items",
			{
				"item_variant": variant,
				"qty": box_quantity,
				"ratio": 1,
				"mrp": 0,
				"table_index": 0,
				"row_index": index,
			},
		)


def _reduce_source_lot_quantity(source_lot, conversions):
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE", (source_lot,)
	)
	lot_doc = frappe.get_doc('SD YRP Lot', source_lot)
	ipd = frappe.get_cached_doc('YRP Item Production Detail', lot_doc.production_detail)
	requested = {}
	for row in conversions:
		key = (str(row["colour"]), str(row["size"]))
		requested[key] = requested.get(key, 0) + flt(row["qty"])
	rows_by_key = {}
	for row in lot_doc.get("lot_order_details") or []:
		rows_by_key.setdefault(_lot_row_key(row, ipd), []).append(row)
	for key, quantity in requested.items():
		remaining = quantity
		for row in rows_by_key.get(key, []):
			available = max(flt(row.quantity), 0)
			deduction = min(available, remaining)
			row.quantity = available - deduction
			remaining -= deduction
			if remaining <= 0:
				break
	_rebuild_lot_order_items(lot_doc, ipd)
	lot_doc.total_order_quantity = sum(
		flt(row.quantity) for row in lot_doc.get("lot_order_details") or []
	)
	lot_doc.total_quantity = sum(flt(row.qty) for row in lot_doc.get("items") or [])
	lot_doc.save(ignore_permissions=True)


def _validate_conversion_balance(source_plan, conversions):
	data = source_plan.get_finishing_plans()["finishing_qty"]["data"]
	for row in conversions:
		available = flt(
			(
				((data.get(row["colour"]) or {}).get("values") or {}).get(
					row["size"], {}
				)
			).get("balance")
		)
		if row["qty"] > available + 1e-6:
			frappe.throw(
				_("Only {0} is available for {1} / {2}").format(
					available, row["colour"], row["size"]
				)
			)


def _validate_alternate_lot(target_lot, source_lot):
	values = frappe.db.get_value(
		'SD YRP Lot', target_lot, ["is_transferred", "transferred_lot"]
	)
	if not values or not values[0] or values[1] != source_lot:
		frappe.throw(
			_("Lot {0} is not an alternative of {1}").format(target_lot, source_lot)
		)


def _get_packing_work_order(target_lot):
	work_orders = frappe.get_all(
		'YRP Work Order',
		filters={"lot": target_lot, "includes_packing": 1, "docstatus": ["in", [0, 1]]},
		pluck="name",
		order_by="docstatus desc, creation desc",
	)
	if not work_orders:
		frappe.throw(_("No packing Work Order found for Lot {0}").format(target_lot))
	return work_orders[0]


def _apply_draft_work_order_rows(work_order, rows):
	work_order.set("deliverables", rows["deliverables"])
	work_order.set("receivables", rows["receivables"])
	work_order.set("work_order_calculated_items", rows["calculated_items"])
	work_order.total_quantity = rows["total_quantity"]
	work_order.planned_quantity = rows["total_quantity"]
	if work_order.meta.get_field("wo_colours"):
		work_order.wo_colours = rows["colour_summary"]
	work_order.save(ignore_permissions=True)


def check_colours_and_sizes(ipd_name, converting_colours, converting_sizes):
	ipd = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
	if ipd.is_set_item:
		frappe.throw(_("Set Item is not applicable for Alternative Items"))
	mappings = {row.attribute: row.mapping for row in ipd.get("item_attributes") or []}
	colour_mapping = mappings.get(ipd.packing_attribute)
	size_mapping = mappings.get(ipd.primary_item_attribute)
	if not colour_mapping or not size_mapping:
		frappe.throw(_("Item Production Detail {0} has invalid mappings").format(ipd.name))
	colours = set(
		frappe.get_all(
			'YRP Item Item Attribute Mapping Value',
			filters={"parent": colour_mapping},
			pluck="attribute_value",
		)
	)
	sizes = set(
		frappe.get_all(
			'YRP Item Item Attribute Mapping Value',
			filters={"parent": size_mapping},
			pluck="attribute_value",
		)
	)
	missing_colours = set(converting_colours).difference(colours)
	missing_sizes = set(converting_sizes).difference(sizes)
	if missing_colours:
		frappe.throw(
			_("Production Detail does not contain colour(s): {0}").format(
				", ".join(sorted(missing_colours))
			)
		)
	if missing_sizes:
		frappe.throw(
			_("Production Detail does not contain size(s): {0}").format(
				", ".join(sorted(missing_sizes))
			)
		)

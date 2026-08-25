"""Finishing inward drill-down and print-size validation."""

import frappe
from frappe.utils import flt

from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.rebuild import (
	get_configured_cutting_process,
	get_process_work_orders,
)
from yrp.utils import get_variant_attr_details, update_if_string_instance


@frappe.whitelist()
def cache_selected_size(key, size, finishing_id):
	check_eqi_status(size, finishing_id)
	frappe.cache().set_value(f"{key}{frappe.session.user}", size)


def check_eqi_status(print_size, finishing_id):
	lot = frappe.db.get_value("Finishing Plan", finishing_id, "lot")
	process = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	inspection = get_eqi_status(get_process_work_orders(process, lot))
	failed_suppliers = []
	for supplier, colours in inspection.items():
		if any(
			sizes.get(print_size) and sizes.get(print_size) != "Pass"
			for sizes in colours.values()
		):
			failed_suppliers.append(supplier)
	if failed_suppliers:
		frappe.throw(
			f"EQI not passed for Size {print_size}: {', '.join(failed_suppliers)}"
		)


def get_eqi_status(work_orders):
	if not work_orders:
		return {}
	inspection_names = frappe.get_all(
		"Essdee Quality Inspection",
		filters={
			"docstatus": 1,
			"against": "Work Order",
			"against_id": ["in", work_orders],
		},
		order_by="posting_date desc",
		pluck="name",
	)
	result = {}
	for name in inspection_names:
		doc = frappe.get_doc("Essdee Quality Inspection", name)
		result.setdefault(doc.supplier_name, {})
		for row in doc.get("essdee_quality_inspection_colours") or []:
			if row.selected:
				result[doc.supplier_name].setdefault(row.colour, {})
		for row in doc.get("essdee_quality_inspection_sizes") or []:
			if row.selected:
				for colour in result[doc.supplier_name].values():
					colour.setdefault(row.size, doc.result)
	return result


@frappe.whitelist()
def get_finishing_plan_inward_details(key, lot):
	cache_key = f"{key}{frappe.session.user}"
	selected_size = frappe.cache().get_value(cache_key)
	if not selected_size:
		return {}
	frappe.cache().delete_value(cache_key)

	settings = frappe.get_cached_doc("YRP Stock Settings")
	rejected_type = settings.default_rejected_received_type
	default_type = settings.default_received_type
	process = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	production_detail = frappe.db.get_value("Lot", lot, "production_detail")
	ipd = frappe.get_cached_doc("Item Production Detail", production_detail)
	result = {"data": {}}
	received_types = [default_type]

	for work_order in get_process_work_orders(process, lot):
		_add_inward_rows(
			result["data"],
			frappe.get_all(
				"Work Order Calculated Item",
				filters={"parent": work_order},
				fields=["*"],
			),
			ipd,
			selected_size,
			rejected_type,
			received_types,
			cutting=False,
		)
	for work_order in get_process_work_orders(
		get_configured_cutting_process(production_detail=production_detail, lot=lot),
		lot,
	):
		_add_inward_rows(
			result["data"],
			frappe.get_all(
				"Work Order Calculated Item",
				filters={"parent": work_order},
				fields=["*"],
			),
			ipd,
			selected_size,
			rejected_type,
			received_types,
			cutting=True,
		)
	return {
		"selected_size": selected_size,
		"types": received_types,
		"data": result["data"],
		"is_set_item": ipd.is_set_item,
		"set_attr": ipd.set_item_attribute,
	}


def _add_inward_rows(
	data,
	rows,
	ipd,
	selected_size,
	rejected_type,
	type_list,
	*,
	cutting,
):
	for row in rows:
		attributes = get_variant_attr_details(row.item_variant)
		if attributes.get(ipd.primary_item_attribute) != selected_size:
			continue
		combination = json_object(row.set_combination)
		major_colour = combination.get("major_colour") or attributes.get(ipd.packing_attribute) or ""
		part = attributes.get(ipd.set_item_attribute) if ipd.is_set_item else "item"
		part = part or "item"
		variant_colour = attributes.get(ipd.packing_attribute) or major_colour
		colour = f"{variant_colour}({major_colour})" if ipd.is_set_item else major_colour
		part_data = data.setdefault(
			part,
			{
				"colours": {},
				"colour_type": {},
				"type_wise": {},
				"cut_detail": {},
				"total_sew": 0,
				"total_cut": 0,
				"part_colours": [],
			},
		)
		if colour not in part_data["part_colours"]:
			part_data["part_colours"].append(colour)
			part_data["colours"][colour] = {"sewing_received": 0}
			part_data["colour_type"][colour] = {"type_wise": {}}
		for received_type, quantity in (
			update_if_string_instance(row.received_type_json) or {}
		).items():
			if received_type == rejected_type:
				continue
			if received_type not in type_list:
				type_list.append(received_type)
			quantity = flt(quantity)
			if cutting:
				part_data["cut_detail"].setdefault(colour, 0)
				part_data["cut_detail"][colour] += quantity
				part_data["total_cut"] += quantity
			else:
				part_data["total_sew"] += quantity
				part_data["colours"][colour]["sewing_received"] += quantity
				part_data["colour_type"][colour]["type_wise"].setdefault(received_type, 0)
				part_data["colour_type"][colour]["type_wise"][received_type] += quantity
				part_data["type_wise"].setdefault(received_type, 0)
				part_data["type_wise"][received_type] += quantity


@frappe.whitelist()
def get_part_value(set_attribute, production_detail):
	if not set_attribute or not production_detail:
		return None
	ipd = frappe.get_cached_doc("Item Production Detail", production_detail)
	mapping = next(
		(
			row.mapping
			for row in ipd.get("item_attributes") or []
			if row.attribute == set_attribute and row.mapping
		),
		None,
	)
	if not mapping:
		return None
	return frappe.get_all(
		"Item Item Attribute Mapping Value",
		filters={"parent": mapping},
		pluck="attribute_value",
		order_by="idx asc",
	)

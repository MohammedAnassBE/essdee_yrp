"""Read models and rebuild actions for the Finishing Plan Desk views."""

import frappe
from frappe.utils import flt, today

from essdee_yrp.finishing.parsing import json_object
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item.item import get_attribute_details


@frappe.whitelist()
def get_fp_consumption_details(doc_name):
	doc = frappe.get_doc("Finishing Plan", doc_name)
	doc.check_permission("read")
	if not doc.lot:
		return {"lot": doc.lot, "processes": []}

	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	rows = []
	for row in _get_jobwork_issued_rows(doc.lot):
		if row.get("item") == doc.item:
			continue
		row.received_type = row.received_type or default_received_type
		row.source_report = "Jobwork"
		rows.append(row)
	rows.extend(_get_fp_grn_deduction_rows(doc))
	return {
		"lot": doc.lot,
		"processes": _group_fp_item_rows(
			rows,
			group_field="process",
			default_group="Non Process",
			merge_received_type=True,
			clamp_negative=True,
			remove_zero_items=True,
		),
	}


def _get_jobwork_issued_rows(lot):
	"""Return DC and Stock Entry issues using the F16 YRP field contract."""
	params = {"lot": lot}
	delivery_challans = frappe.db.sql(
		"""
			SELECT
				'Work Order' AS against,
				dc.work_order AS against_id,
				'Delivery Challan' AS source_doctype,
				dc.name AS source_name,
				dc.from_warehouse AS from_location,
				dc.from_location_name,
				dc.to_warehouse AS supplier,
				dc.supplier_name,
				COALESCE(dci.lot, dc.lot) AS lot,
				dc.process_name AS process,
				iv.item AS item,
				dci.item_variant,
				dci.delivered_quantity AS quantity,
				dci.received_type,
				dci.comments AS remarks,
				dc.posting_date,
				dc.posting_time
			FROM `tabDelivery Challan Item` dci
			INNER JOIN `tabDelivery Challan` dc ON dc.name = dci.parent
			LEFT JOIN `tabItem Variant` iv ON iv.name = dci.item_variant
			WHERE dc.docstatus = 1
				AND dci.docstatus = 1
				AND dci.delivered_quantity > 0
				AND (dci.lot = %(lot)s OR dc.lot = %(lot)s)
		""",
		params,
		as_dict=True,
	)
	stock_entries = frappe.db.sql(
		"""
			SELECT
				se.against,
				se.against_id,
				'Stock Entry' AS source_doctype,
				se.name AS source_name,
				se.from_warehouse AS from_location,
				from_wh.name1 AS from_location_name,
				COALESCE(se.to_supplier, se.transfer_supplier, se.to_warehouse) AS supplier,
				to_wh.name1 AS supplier_name,
				sed.lot,
				wo.process_name AS process,
				iv.item AS item,
				sed.item AS item_variant,
				sed.qty AS quantity,
				sed.received_type,
				sed.remarks,
				se.posting_date,
				se.posting_time
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			LEFT JOIN `tabWarehouse` from_wh ON from_wh.name = se.from_warehouse
			LEFT JOIN `tabWarehouse` to_wh ON to_wh.name = se.to_warehouse
			LEFT JOIN `tabWork Order` wo
				ON se.against = 'Work Order' AND wo.name = se.against_id
			LEFT JOIN `tabItem Variant` iv ON iv.name = sed.item
			WHERE se.docstatus = 1
				AND sed.docstatus = 1
				AND se.purpose = 'Material Issue'
				AND COALESCE(se.against, '') != ''
				AND sed.lot = %(lot)s
		""",
		params,
		as_dict=True,
	)
	return sorted(
		[*delivery_challans, *stock_entries],
		key=lambda row: (
			row.get("posting_date") or "",
			str(row.get("posting_time") or ""),
			row.get("source_name") or "",
		),
		reverse=True,
	)


def _get_fp_grn_deduction_rows(doc):
	if not doc.work_order:
		return []
	params = {"lot": doc.lot, "work_order": doc.work_order, "fp_item": doc.item}
	conditions = [
		"grn.docstatus = 1",
		"gri.docstatus = 1",
		"grn.against = 'Work Order'",
		"grn.against_id = %(work_order)s",
		"(grn.lot = %(lot)s OR gri.lot = %(lot)s)",
		"COALESCE(gri.quantity, 0) > 0",
	]
	if doc.item:
		conditions.append("(iv.item IS NULL OR iv.item != %(fp_item)s)")
	rows = frappe.db.sql(
		"""
			SELECT
				'Work Order' AS against,
				grn.against_id,
				'Goods Received Note' AS source_doctype,
				grn.name AS source_name,
				COALESCE(gri.lot, grn.lot) AS lot,
				COALESCE(grn.process_name, wo.process_name) AS process,
				iv.item,
				gri.item_variant,
				-gri.quantity AS quantity,
				gri.received_type,
				gri.comments AS remarks,
				grn.posting_date,
				grn.posting_time
			FROM `tabGoods Received Note Item` gri
			INNER JOIN `tabGoods Received Note` grn ON grn.name = gri.parent
			LEFT JOIN `tabWork Order` wo ON wo.name = grn.against_id
			LEFT JOIN `tabItem Variant` iv ON iv.name = gri.item_variant
			WHERE {conditions}
		""".format(conditions=" AND ".join(conditions)),
		params,
		as_dict=True,
	)
	for row in rows:
		row.source_report = "GRN"
		row.is_grn_deduction = 1
	return rows


@frappe.whitelist()
def get_fp_stock_balance_details(doc_name):
	doc = frappe.get_doc("Finishing Plan", doc_name)
	doc.check_permission("read")
	if not doc.lot:
		return {"lot": doc.lot, "warehouses": []}

	from yrp.yrp_stock.report.stock_balance.stock_balance import execute

	_columns, balances = execute(
		frappe._dict(
			{
				"from_date": "1900-01-01",
				"to_date": today(),
				"lot": doc.lot,
				"remove_zero_balance_item": 1,
			}
		)
	)
	rows = []
	for balance in balances:
		row = frappe._dict(balance)
		if row.get("item_name") == doc.item or not flt(row.get("bal_qty")):
			continue
		row.item_variant = row.item
		row.item = row.item_name
		row.quantity = row.bal_qty
		row.warehouse_name = row.get("warehouse_name") or frappe.db.get_value(
			"Warehouse", row.warehouse, "name1"
		)
		rows.append(row)
	return {
		"lot": doc.lot,
		"warehouses": _group_fp_item_rows(
			rows,
			group_field="warehouse",
			group_name_field="warehouse_name",
			item_key_fields=("received_type", "stock_uom"),
		),
	}


def _group_fp_item_rows(
	rows,
	group_field,
	default_group=None,
	group_name_field=None,
	item_key_fields=None,
	merge_received_type=False,
	clamp_negative=False,
	remove_zero_items=False,
):
	group_map = {}
	variant_cache = {}
	item_attribute_cache = {}
	item_key_fields = tuple(item_key_fields or [])
	for row in rows:
		if not row.get("item_variant"):
			continue
		group_value = row.get(group_field) or default_group or ""
		top_group = group_map.setdefault(
			group_value,
			{group_field: group_value, "groups": [], "_group_index": {}},
		)
		if group_name_field:
			top_group[group_name_field] = row.get(group_name_field) or group_value
		variant = variant_cache.get(row.item_variant)
		if not variant:
			variant = frappe.get_cached_doc("Item Variant", row.item_variant)
			variant_cache[row.item_variant] = variant
		item_name = row.get("item") or variant.item
		item_attributes = item_attribute_cache.get(item_name)
		if not item_attributes:
			item_attributes = get_attribute_details(item_name)
			item_attribute_cache[item_name] = item_attributes
		attribute_names = item_attributes.get("attributes") or []
		attributes = {
			attr.attribute: attr.attribute_value
			for attr in variant.attributes
			if attr.attribute in attribute_names
		}
		primary_attribute = item_attributes.get("primary_attribute")
		primary_values = list(item_attributes.get("primary_attribute_values") or [])
		primary_value = _get_primary_attribute_value(variant, primary_attribute)
		group_key = (primary_attribute or "", tuple(attribute_names))
		group = top_group["_group_index"].get(group_key)
		if not group:
			group = {
				"attributes": attribute_names,
				"primary_attribute": primary_attribute,
				"primary_attribute_values": primary_values,
				"items": [],
				"total_details": (
					{value: 0 for value in primary_values}
					if primary_attribute
					else {"default": 0}
				),
				"overall_total": 0,
				"_item_index": {},
			}
			top_group["_group_index"][group_key] = group
			top_group["groups"].append(group)
		# Several items can share one attribute-shape group while their own
		# mappings expose different subsets of the primary values. Build the
		# stable union so report columns do not depend on SQL row order.
		for mapped_value in primary_values:
			if mapped_value in group["primary_attribute_values"]:
				continue
			group["primary_attribute_values"].append(mapped_value)
			group["total_details"][mapped_value] = 0
			for existing_item in group["items"]:
				existing_item["values"][mapped_value] = {"quantity": 0, "sources": []}
		if primary_attribute and primary_value and primary_value not in group["primary_attribute_values"]:
			group["primary_attribute_values"].append(primary_value)
			group["total_details"][primary_value] = 0
			for item in group["items"]:
				item["values"][primary_value] = {"quantity": 0, "sources": []}
		row_key = (
			item_name,
			*(row.get(field) or "" for field in item_key_fields),
			tuple((attribute, attributes.get(attribute)) for attribute in attribute_names),
		)
		item = group["_item_index"].get(row_key)
		if not item:
			item = {
				"source_report": row.get("source_report"),
				"item": item_name,
				"attributes": attributes,
				"received_type": (
					row.get("received_type") if "received_type" in item_key_fields else None
				),
				"stock_uom": row.get("stock_uom"),
				"values": {},
				"total_quantity": 0,
			}
			value_keys = group["primary_attribute_values"] if primary_attribute else ["default"]
			for value in value_keys:
				item["values"][value] = {"quantity": 0, "sources": []}
			group["_item_index"][row_key] = item
			group["items"].append(item)
		if merge_received_type and not row.get("is_grn_deduction"):
			_update_fp_consumption_received_type(item, row.get("received_type"))
		value_key = primary_value if primary_attribute else "default"
		if primary_attribute and not value_key:
			continue
		quantity = flt(row.get("quantity"))
		item["values"][value_key]["quantity"] += quantity
		item["values"][value_key]["sources"].append(
			{
				"source_doctype": row.get("source_doctype"),
				"source_name": row.get("source_name"),
			}
		)
		item["total_quantity"] += quantity

	grouped_rows = list(group_map.values())
	for top_group in grouped_rows:
		top_group["groups"].sort(key=lambda group: group.get("primary_attribute") or "")
		for group in top_group["groups"]:
			_recalculate_fp_item_group_totals(
				group,
				clamp_negative=clamp_negative,
				remove_zero_items=remove_zero_items,
			)
			group["items"].sort(
				key=lambda item: (item.get("item") or "", item.get("received_type") or "")
			)
			group.pop("_item_index", None)
		top_group["groups"] = [group for group in top_group["groups"] if group.get("items")]
		top_group.pop("_group_index", None)
	grouped_rows = [row for row in grouped_rows if row.get("groups")]
	if group_field == "process":
		grouped_rows.sort(key=lambda row: (row[group_field] == "Non Process", row[group_field]))
	elif group_name_field:
		grouped_rows.sort(key=lambda row: (row.get(group_name_field) or "", row.get(group_field) or ""))
	else:
		grouped_rows.sort(key=lambda row: row.get(group_field) or "")
	return grouped_rows


def _update_fp_consumption_received_type(item, received_type):
	if not received_type:
		return
	if not item.get("received_type"):
		item["received_type"] = received_type
		return
	received_types = [value.strip() for value in item["received_type"].split(",") if value.strip()]
	if received_type not in received_types:
		received_types.append(received_type)
	item["received_type"] = ", ".join(received_types)


def _recalculate_fp_item_group_totals(group, clamp_negative=False, remove_zero_items=False):
	total_details = {
		value: 0 for value in group.get("primary_attribute_values") or []
	} if group.get("primary_attribute") else {"default": 0}
	items = []
	for item in group.get("items") or []:
		total_quantity = 0
		for value_key, value in (item.get("values") or {}).items():
			quantity = flt(value.get("quantity"))
			if clamp_negative:
				quantity = max(quantity, 0)
			value["quantity"] = quantity
			total_quantity += quantity
			total_details.setdefault(value_key, 0)
			total_details[value_key] += quantity
		item["total_quantity"] = total_quantity
		if not remove_zero_items or total_quantity:
			items.append(item)
	group["items"] = items
	group["total_details"] = total_details
	group["overall_total"] = sum(total_details.values())


def _get_primary_attribute_value(variant, primary_attribute):
	if not primary_attribute:
		return None
	for attribute in variant.attributes:
		if attribute.attribute == primary_attribute:
			return attribute.attribute_value
	return None


@frappe.whitelist()
def fetch_rejected_quantity(doc_name):
	"""Rebuild Finishing rework/rejection totals from migrated GRN Rework rows."""
	finishing_doc = frappe.get_doc("Finishing Plan", doc_name)
	finishing_doc.check_permission("write")
	rework_items = {}
	for name in frappe.get_all("GRN Rework Item", filters={"lot": finishing_doc.lot}, pluck="name"):
		doc = frappe.get_doc("GRN Rework Item", name)
		for row in doc.get("grn_rework_item_details") or []:
			if not flt(row.quantity):
				continue
			key, combination = _variant_combination_key(row)
			values = rework_items.setdefault(key, _empty_rework_row(row.item_variant, combination))
			values["quantity"] += flt(row.quantity)
			if row.get("completed"):
				values["rejected_qty"] += flt(row.get("rejection"))
		for row in doc.get("grn_reworked_item_details") or []:
			if not flt(row.quantity):
				continue
			key, combination = _variant_combination_key(row)
			values = rework_items.setdefault(key, _empty_rework_row(row.item_variant, combination))
			values["reworked_quantity"] += flt(row.quantity)
	finishing_doc.set("finishing_plan_reworked_details", list(rework_items.values()))

	cutting_process = "Cutting"
	if frappe.get_meta("MRP Settings").has_field("cutting_process"):
		cutting_process = (
			frappe.db.get_single_value("MRP Settings", "cutting_process") or cutting_process
		)
	cutting = {}
	for work_order_name in frappe.get_all(
		"Work Order",
		filters={
			"docstatus": 1,
			"lot": finishing_doc.lot,
			"process_name": cutting_process,
		},
		pluck="name",
	):
		work_order = frappe.get_doc("Work Order", work_order_name)
		for row in work_order.get("work_order_calculated_items") or []:
			if flt(row.received_qty) <= 0:
				continue
			key, _combination = _variant_combination_key(row)
			cutting[key] = cutting.get(key, 0) + flt(row.received_qty)
	for row in finishing_doc.get("finishing_plan_details") or []:
		key, _combination = _variant_combination_key(row)
		row.reworked = rework_items.get(key, {}).get("reworked_quantity", 0)
		if key in cutting:
			row.cutting_qty = cutting[key]
	finishing_doc.save()


def _variant_combination_key(row):
	combination = json_object(row.set_combination)
	return (row.item_variant, tuple(sorted(combination.items()))), combination


def _empty_rework_row(item_variant, combination):
	return {
		"item_variant": item_variant,
		"quantity": 0,
		"reworked_quantity": 0,
		"rejected_qty": 0,
		"set_combination": frappe.as_json(combination),
	}

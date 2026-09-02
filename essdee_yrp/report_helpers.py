"""Essdee-owned read helpers used by migrated operational reports."""

import json

import frappe
from frappe.utils import flt, getdate, get_time
from six import string_types

from yrp.stock.save_stock_items import group_items_for_ui


def _normalize_multiselect_filter(value):
	if isinstance(value, string_types):
		try:
			value = json.loads(value)
		except ValueError:
			value = [value]

	if not value:
		return []

	if isinstance(value, dict):
		value = list(value.values())
	elif not isinstance(value, (list, tuple, set)):
		value = [value]

	normalized = []
	for row in value:
		if isinstance(row, dict):
			row = row.get("value") or row.get("name") or row.get("label")
		if row is None:
			continue

		row = str(row).strip()
		if row and row not in normalized:
			normalized.append(row)

	return normalized


def get_dispatch_percentage_report(percentage=None, lot_list=None, item_list=None):
	target_percentage = flt(percentage)
	if target_percentage <= 0:
		frappe.throw("Percentage must be greater than 0")

	lot_list = _normalize_multiselect_filter(lot_list)
	item_list = _normalize_multiselect_filter(item_list)
	conditions = [
		"fp.docstatus < 2",
		"log.parenttype = 'SD YRP Finishing Plan'",
		"log.parentfield = 'finishing_plan_dispatch_logs'",
		"ifnull(log.cancelled, 0) = 0",
		"ifnull(log.dispatch_percentage_before, 0) < %(percentage)s",
		"ifnull(log.dispatch_percentage_after, 0) >= %(percentage)s",
	]
	values = {"percentage": target_percentage}

	if lot_list:
		conditions.append("fp.lot in %(lot_list)s")
		values["lot_list"] = tuple(lot_list)

	if item_list:
		conditions.append("fp.item in %(item_list)s")
		values["item_list"] = tuple(item_list)

	rows = frappe.db.sql(
		f"""
			SELECT
				log.parent AS finishing_plan,
				log.stock_entry,
				log.posting_date AS date,
				log.posting_time,
				log.idx,
				fp.lot,
				fp.item,
				log.dispatch_percentage_after AS percentage
			FROM `tabSD YRP Finishing Plan Dispatch Log` log
			INNER JOIN `tabSD YRP Finishing Plan` fp ON fp.name = log.parent
			WHERE {" AND ".join(conditions)}
			ORDER BY log.parent, log.posting_date, log.posting_time, log.idx
		""",
		values,
		as_dict=True,
	)

	first_crossing_by_plan = {}
	for row in rows:
		if row.finishing_plan in first_crossing_by_plan:
			continue

		first_crossing_by_plan[row.finishing_plan] = {
			"date": row.date,
			"stock_entry": row.stock_entry,
			"lot": row.lot,
			"item": row.item,
			"percentage": flt(row.percentage, 3),
		}

	return sorted(
		first_crossing_by_plan.values(),
		key=lambda row: (getdate(row.get("date")), row.get("lot") or "", row.get("item") or ""),
	)


def get_work_order_pending_report(
	production_order=None,
	lot=None,
	process=None,
	supplier=None,
	item=None,
	item_variant=None,
	from_date=None,
	to_date=None,
	status=None,
	wos=None,
):
	"""Delivered, received, and difference values from submitted Work Orders."""
	conditions = ""
	con = {}
	production_order = _normalize_multiselect_filter(production_order)
	lot = _normalize_multiselect_filter(lot)
	process = _normalize_multiselect_filter(process)
	supplier = _normalize_multiselect_filter(supplier)
	item = _normalize_multiselect_filter(item)
	item_variant = _normalize_multiselect_filter(item_variant)
	wos = _normalize_multiselect_filter(wos)

	if production_order:
		conditions += " AND l.production_order IN %(production_order)s"
		con["production_order"] = tuple(production_order)
	if lot:
		conditions += " AND t1.lot IN %(lot)s"
		con["lot"] = tuple(lot)
	if process:
		conditions += " AND t1.process_name IN %(process)s"
		con["process"] = tuple(process)
	if supplier:
		conditions += " AND t1.supplier IN %(supplier)s"
		con["supplier"] = tuple(supplier)
	if item:
		conditions += (
			" AND ("
			"	(COALESCE(t1.includes_packing, 0) = 1 AND t1.item IN %(item)s)"
			"	OR (COALESCE(t1.includes_packing, 0) = 0 AND ("
			"		iv.item IN %(item)s OR i.name IN %(item)s OR i.name1 IN %(item)s"
			"	))"
			")"
		)
		con["item"] = tuple(item)
	if item_variant:
		conditions += (
			" AND ("
			"	(COALESCE(t1.includes_packing, 0) = 1 AND t1.item IN %(item_variant)s)"
			"	OR (COALESCE(t1.includes_packing, 0) = 0 "
			"		AND t2.item_variant IN %(item_variant)s)"
			")"
		)
		con["item_variant"] = tuple(item_variant)
	if wos:
		conditions += " AND t1.name IN %(wos)s"
		con["wos"] = tuple(wos)

	if bool(from_date) != bool(to_date):
		frappe.throw("Set both From Date and To Date.")
	if from_date and to_date:
		conditions += " AND t1.wo_date BETWEEN %(from_date)s AND %(to_date)s"
		con["from_date"] = from_date
		con["to_date"] = to_date

	if status:
		conditions += " AND t1.open_status = %(open_status)s"
		con["open_status"] = status

	return frappe.db.sql(
		f"""
			SELECT
				COALESCE(l.production_order, '') AS production_order,
				t1.name AS work_order,
				t1.lot,
				t1.process_name,
				COALESCE(t1.supplier_name, t3.supplier_name, t1.supplier, '') AS supplier_name,
				CASE
					WHEN COALESCE(t1.includes_packing, 0) = 1
						THEN COALESCE(t1.item, '')
					ELSE COALESCE(NULLIF(i.name1, ''), i.name, iv.item, '')
				END AS item_name,
				CASE
					WHEN COALESCE(t1.includes_packing, 0) = 1
						THEN COALESCE(t1.item, '')
					ELSE t2.item_variant
				END AS item_variant,
				SUM(COALESCE(t2.delivered_quantity, 0)) AS delivered_qty,
				CASE
					WHEN COALESCE(t1.includes_packing, 0) = 1
						THEN COALESCE(packing_grn.dynamic_received_qty, 0)
							+ COALESCE(packing_grn.legacy_received_qty, 0)
								* COALESCE(NULLIF(ipd.packing_combo, 0), 1)
					ELSE SUM(COALESCE(t2.received_qty, 0))
				END AS received_qty,
				SUM(COALESCE(t2.delivered_quantity, 0))
					- CASE
						WHEN COALESCE(t1.includes_packing, 0) = 1
							THEN COALESCE(packing_grn.dynamic_received_qty, 0)
								+ COALESCE(packing_grn.legacy_received_qty, 0)
									* COALESCE(NULLIF(ipd.packing_combo, 0), 1)
						ELSE SUM(COALESCE(t2.received_qty, 0))
					END AS pending_quantity
			FROM `tabYRP Work Order` t1
			JOIN `tabYRP Work Order Calculated Item` t2 ON t2.parent = t1.name
			LEFT JOIN `tabSD YRP Lot` l ON l.name = t1.lot
			LEFT JOIN `tabYRP Item Production Detail` ipd ON ipd.name = l.production_detail
			LEFT JOIN (
				SELECT
					grn.against_id AS work_order,
					SUM(
						CASE WHEN COALESCE(grn.packing_calculation_version, 0) >= 2
							THEN COALESCE(grn_item.quantity, 0) ELSE 0 END
					) AS dynamic_received_qty,
					SUM(
						CASE WHEN COALESCE(grn.packing_calculation_version, 0) < 2
							THEN COALESCE(grn_item.quantity, 0) ELSE 0 END
					) AS legacy_received_qty
				FROM `tabYRP Goods Received Note` grn
				JOIN `tabYRP Goods Received Note Item` grn_item
					ON grn_item.parent = grn.name
				WHERE
					grn.docstatus = 1
					AND grn.against = 'YRP Work Order'
					AND grn.is_return = 0
				GROUP BY grn.against_id
			) packing_grn ON packing_grn.work_order = t1.name
			LEFT JOIN `tabYRP Item Variant` iv ON iv.name = t2.item_variant
			LEFT JOIN `tabYRP Item` i ON i.name = iv.item
			LEFT JOIN `tabYRP Supplier` t3 ON t3.name = t1.supplier
			WHERE t1.docstatus = 1 {conditions}
			GROUP BY
				l.production_order,
				t1.name,
				t1.lot,
				t1.process_name,
				t1.supplier,
				t1.supplier_name,
				t3.supplier_name,
				CASE
					WHEN COALESCE(t1.includes_packing, 0) = 1
						THEN COALESCE(t1.item, '')
					ELSE COALESCE(NULLIF(i.name1, ''), i.name, iv.item, '')
				END,
				CASE
					WHEN COALESCE(t1.includes_packing, 0) = 1
						THEN COALESCE(t1.item, '')
					ELSE t2.item_variant
				END,
				t1.includes_packing,
				ipd.packing_combo,
				packing_grn.dynamic_received_qty,
				packing_grn.legacy_received_qty
			ORDER BY
				l.production_order,
				t1.lot,
				t1.name,
				t1.process_name,
				supplier_name,
				item_name,
				item_variant
		""",
		con,
		as_dict=True,
	)


def get_combine_datetime(posting_date, posting_time):
	import datetime

	if isinstance(posting_date, str):
		posting_date = getdate(posting_date)

	if isinstance(posting_time, str):
		posting_time = get_time(posting_time)

	if isinstance(posting_time, datetime.timedelta):
		posting_time = (datetime.datetime.min + posting_time).time()

	return datetime.datetime.combine(posting_date, posting_time).replace(microsecond=0)


@frappe.whitelist()
def make_purchase_order_mapped_doc(items):
	"""Build a draft Purchase Order from selected Lot Purchase Summary rows."""
	frappe.has_permission('YRP Purchase Order', "create", throw=True)
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not isinstance(items, list) or not items:
		frappe.throw("Select at least one purchase requirement.")

	rows = []
	for index, item in enumerate(items):
		item = frappe._dict(item)
		item_variant = item.item
		if not item_variant or not frappe.db.exists('YRP Item Variant', item_variant):
			frappe.throw(f"Row {index + 1}: a valid Item Variant is required.")
		if flt(item.qty) <= 0:
			frappe.throw(f"Row {index + 1}: quantity must be greater than zero.")
		if item.delivery_location and not frappe.db.exists(
			'YRP Supplier', item.delivery_location
		):
			frappe.throw(f"Row {index + 1}: delivery location does not exist.")
		rows.append(
			{
				"item_variant": item_variant,
				"qty": flt(item.qty),
				"lot": item.lot,
				"delivery_location": item.delivery_location,
				"delivery_date": item.delivery_date,
				"expected_delivery_date": item.expected_delivery_date
				or item.delivery_date,
				"row_index": index,
				"table_index": index,
			}
		)

	doc = frappe.new_doc('YRP Purchase Order')
	doc.set_onload("item_details", group_items_for_ui(rows, 'YRP Purchase Order'))
	return doc

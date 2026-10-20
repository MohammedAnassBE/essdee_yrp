"""Configured sewing input less line output, by line, lot and item."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.sewing.read_models import _plans


def finish_rows(rows, filters):
	result = []
	search = (filters.get("search") or "").casefold()
	for row in rows:
		if filters.get("work_station") and row["sewing_line"] != filters["work_station"]:
			continue
		if search and not any(
			search in str(row.get(f) or "").casefold() for f in ("sewing_line", "lot", "item")
		):
			continue
		result.append(
			dict(
				row,
				serial_no=len(result) + 1,
				input_qty=flt(row["input_qty"]),
				line_output_qty=flt(row["line_output_qty"]),
				input_pending=flt(row["input_qty"]) - flt(row["line_output_qty"]),
			)
		)
	return result


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# MRP scopes the sewing plan's supplier, not the linked Work Order's owner.
	# Retain permission checks on both doctypes without imposing another supplier filter.
	frappe.has_permission("SD YRP Sewing Plan", "report", throw=True)
	plans = _plans(filters.supplier)
	work_orders = []
	if plans:
		work_orders = frappe.get_list(
			"YRP Work Order",
			filters={
				"name": ["in", list({p.work_order for p in plans if p.work_order})],
				"docstatus": 1,
				"open_status": "Open",
			},
			pluck="name",
			limit_page_length=0,
		)
	work_orders = set(work_orders)
	plans = [p for p in plans if p.work_order in work_orders]
	settings = frappe.get_cached_doc("SD YRP MRP Settings")
	input_type, output_type = settings.sewing_input_qty_type, settings.sewing_line_output_type
	if not input_type or not output_type:
		frappe.throw(_("Configure Sewing Input Qty Type and Sewing Line Output Type in MRP Settings"))
	entries = []
	if plans:
		entries = frappe.get_list(
			"SD YRP Sewing Plan Entry Detail",
			filters={
				"sewing_plan": ["in", [p.name for p in plans]],
				"input_type": ["in", [input_type, output_type]],
			},
			pluck="name",
			limit_page_length=0,
		)
	rows = []
	if entries:
		rows = frappe.db.sql(
			"""
			SELECT COALESCE(NULLIF(e.work_station, ''), 'Not Specified') AS sewing_line,
				p.lot, p.item,
				SUM(CASE WHEN e.input_type = %(input)s THEN d.quantity ELSE 0 END) AS input_qty,
				SUM(CASE WHEN e.input_type = %(output)s THEN d.quantity ELSE 0 END) AS line_output_qty
			FROM `tabSD YRP Sewing Plan` p
			JOIN `tabYRP Work Order` w ON w.name = p.work_order
			JOIN `tabSD YRP Sewing Plan Entry Detail` e ON e.sewing_plan = p.name
			JOIN `tabSD YRP Sewing Plan Detail` d ON d.parent = e.name
			WHERE e.name IN %(entries)s AND w.docstatus = 1 AND w.open_status = 'Open'
			GROUP BY e.work_station, p.lot, p.item
			ORDER BY sewing_line, p.lot, p.item
		""",
			{"entries": entries, "input": input_type, "output": output_type},
			as_dict=True,
		)
	rows = finish_rows(rows, filters)
	columns = [
		{"fieldname": "serial_no", "label": _("#"), "fieldtype": "Int", "width": 50},
		{"fieldname": "sewing_line", "label": _("Sewing Line"), "fieldtype": "Data", "width": 140},
		{"fieldname": "lot", "label": _("Lot"), "fieldtype": "Link", "options": "SD YRP Lot", "width": 140},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 220},
		{"fieldname": "input_qty", "label": _("Input Qty"), "fieldtype": "Float", "width": 130},
		{"fieldname": "line_output_qty", "label": _("Line Output Qty"), "fieldtype": "Float", "width": 140},
		{"fieldname": "input_pending", "label": _("Input Pending"), "fieldtype": "Float", "width": 140},
	]
	summary = [
		dict(label=_(label), value=sum(row[field] for row in rows), datatype="Float")
		for field, label in [
			("input_qty", "Total Input Qty"),
			("line_output_qty", "Total Line Output"),
			("input_pending", "Total Input Pending"),
		]
	]
	return columns, rows, _("{0} minus {1}").format(input_type, output_type), None, summary

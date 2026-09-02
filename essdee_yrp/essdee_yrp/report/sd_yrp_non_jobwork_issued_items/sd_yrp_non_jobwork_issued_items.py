# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	return get_columns(), get_data(filters)


def validate_filters(filters):
	if filters.get("from_date") and filters.get("to_date") and filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))


def get_columns():
	return [
		{"fieldname": "source_doctype", "fieldtype": "Data", "label": "Source Type", "width": 130},
		{"fieldname": "source_name", "fieldtype": "Dynamic Link", "options": "source_doctype", "label": "Source ID", "width": 170},
		{"fieldname": "purpose", "fieldtype": "Data", "label": "Purpose", "width": 140},
		{"fieldname": "from_location", "fieldtype": "Link", "options": 'YRP Warehouse', "label": "From Warehouse", "width": 130},
		{"fieldname": "from_location_name", "fieldtype": "Data", "label": "From Location Name", "width": 200},
		{"fieldname": "supplier", "fieldtype": "Link", "options": 'YRP Supplier', "label": "Supplier", "width": 130},
		{"fieldname": "supplier_name", "fieldtype": "Data", "label": "Supplier Name", "width": 200},
		{"fieldname": "lot", "fieldtype": "Link", "options": 'SD YRP Lot', "label": "Lot", "width": 120},
		{"fieldname": "item", "fieldtype": "Link", "options": 'YRP Item', "label": "Item", "width": 180},
		{"fieldname": "item_variant", "fieldtype": "Link", "options": 'YRP Item Variant', "label": "Item Variant", "width": 220},
		{"fieldname": "quantity", "fieldtype": "Float", "label": "Quantity", "width": 110},
		{"fieldname": "received_type", "fieldtype": "Link", "options": 'YRP Received Type', "label": "Received Type", "width": 130},
		{"fieldname": "remarks", "fieldtype": "Data", "label": "Remarks", "width": 200},
	]


def get_data(filters):
	params = {}
	conditions = [
		"se.docstatus = 1",
		"sed.docstatus = 1",
		"se.purpose IN ('Material Issue', 'Send to Warehouse')",
		"IFNULL(se.against, '') = ''",
	]
	supplier_expression = "se.transfer_supplier"

	if filters.get("from_date"):
		conditions.append("se.posting_date >= %(from_date)s")
		params["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("se.posting_date <= %(to_date)s")
		params["to_date"] = filters.to_date

	if filters.get("purpose"):
		conditions.append("se.purpose = %(purpose)s")
		params["purpose"] = filters.purpose

	if filters.get("lot"):
		conditions.append("sed.lot = %(lot)s")
		params["lot"] = filters.lot

	if filters.get("from_location"):
		conditions.append("se.from_warehouse = %(from_location)s")
		params["from_location"] = filters.from_location

	if filters.get("supplier"):
		conditions.append(supplier_expression + " = %(supplier)s")
		params["supplier"] = filters.supplier

	if filters.get("item"):
		conditions.append("iv.item = %(item)s")
		params["item"] = filters.item

	query = """
		SELECT
			'YRP Stock Entry' AS source_doctype,
			se.name AS source_name,
			se.purpose AS purpose,
			se.from_warehouse AS from_location,
			from_warehouse.name1 AS from_location_name,
			{supplier_expression} AS supplier,
			supplier.supplier_name AS supplier_name,
			sed.lot AS lot,
			iv.item AS item,
			sed.item AS item_variant,
			sed.qty AS quantity,
			sed.received_type AS received_type,
			sed.remarks AS remarks,
			se.posting_date AS posting_date,
			se.posting_time AS posting_time
		FROM `tabYRP Stock Entry Detail` sed
		INNER JOIN `tabYRP Stock Entry` se ON se.name = sed.parent
		LEFT JOIN `tabYRP Warehouse` from_warehouse ON from_warehouse.name = se.from_warehouse
		LEFT JOIN `tabYRP Supplier` supplier ON supplier.name = {supplier_expression}
		LEFT JOIN `tabYRP Item Variant` iv ON iv.name = sed.item
		WHERE {conditions}
		ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC
	""".format(
		conditions=" AND ".join(conditions),
		supplier_expression=supplier_expression,
	)

	return frappe.db.sql(query, params, as_dict=True)

# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe

ADDRESS_FIELD_MAP = {
	"address_line1": "address_line_1",
	"address_line2": "address_line_2",
	"city": "city",
	"state": "state",
	"pincode": "pin",
	"phone": "phone_no",
	"email_id": "email_id",
}


@frappe.whitelist()
def get_supplier_warehouse_context(supplier: str) -> dict:
	"""Return the supplier's enabled warehouse and pre-fill values for a new one.

	Supplier warehouses are named after the Supplier ID, like the SD-YRP sync and F15 migration.
	"""
	supplier_doc = frappe.get_doc("Supplier", supplier)
	supplier_doc.check_permission("read")
	warehouse_name = frappe.db.get_value("Warehouse", {"supplier": supplier, "disabled": 0}, "name")
	warehouse = _get_readable_document("Warehouse", warehouse_name)
	defaults = {
		"supplier": supplier,
		"warehouse_name": supplier,
		"is_group": 0,
		"email_id": supplier_doc.email_id,
		"mobile_no": supplier_doc.mobile_no,
	}
	company = frappe.defaults.get_user_default("Company")
	if company and frappe.has_permission("Company", "read", doc=company):
		defaults["company"] = company
	address = _get_readable_document("Address", supplier_doc.supplier_primary_address)
	if address:
		for address_field, warehouse_field in ADDRESS_FIELD_MAP.items():
			defaults[warehouse_field] = address.get(address_field) or defaults.get(warehouse_field)
	return {
		"warehouse": warehouse.name if warehouse else None,
		"warehouse_exists": bool(warehouse_name),
		"defaults": defaults,
	}


def _get_readable_document(doctype: str, name: str | None):
	if not name:
		return None
	document = frappe.get_doc(doctype, name)
	return document if frappe.has_permission(document.doctype, "read", doc=document) else None

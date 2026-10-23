# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe.contacts.doctype.address.address import get_address_display

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


@frappe.whitelist()
def get_single_location_options(
	supplier: str | None = None, warehouse: str | None = None, prefer_primary: bool = False
) -> dict:
	"""Return the only enabled warehouse and the only enabled address of a location, else None.

	A warehouse resolves to its location through Warehouse.supplier. Values the user cannot read are None.
	With prefer_primary, several addresses resolve to the location's only primary address.
	"""
	if warehouse:
		warehouse_doc = frappe.get_doc("Warehouse", warehouse)
		warehouse_doc.check_permission("read")
		supplier = warehouse_doc.supplier
	if supplier:
		frappe.get_doc("Supplier", supplier).check_permission("read")
	address = _get_only_address(supplier, frappe.utils.sbool(prefer_primary)) if supplier else None
	if not warehouse and supplier:
		warehouse = _get_only_readable("Warehouse", {"supplier": supplier, "disabled": 0})
	return {
		"supplier": supplier or None,
		"warehouse": warehouse or None,
		"address": address,
		"address_display": get_address_display(address) if address else None,
	}


def _get_only_address(supplier: str, prefer_primary: bool) -> str | None:
	filters = [
		["Dynamic Link", "parenttype", "=", "Address"],
		["Dynamic Link", "link_doctype", "=", "Supplier"],
		["Dynamic Link", "link_name", "=", supplier],
		["Address", "disabled", "=", 0],
	]
	address = _get_only_readable("Address", filters)
	if address or not prefer_primary:
		return address
	return _get_only_readable("Address", [*filters, ["Address", "is_primary_address", "=", 1]])


def _get_only_readable(doctype: str, filters) -> str | None:
	names = frappe.get_all(doctype, filters=filters, pluck="name", distinct=True, limit=2)
	if len(names) != 1:
		return None
	return names[0] if frappe.has_permission(doctype, "read", doc=names[0]) else None


def _get_readable_document(doctype: str, name: str | None):
	if not name:
		return None
	document = frappe.get_doc(doctype, name)
	return document if frappe.has_permission(document.doctype, "read", doc=document) else None

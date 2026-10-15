import frappe
from frappe import _

DISPATCH_LOCATION_FIELDS = ("from_supplier", "from_warehouse", "to_supplier", "to_warehouse")


@frappe.whitelist()
def get_supplier_warehouses(supplier: str) -> list[str]:
	"""Return the enabled Warehouses linked to a Supplier."""
	return frappe.get_list(
		"Warehouse", filters={"supplier": supplier, "disabled": 0}, pluck="name", order_by="name asc"
	)


def get_dispatch_locations(from_supplier, from_warehouse, to_supplier, to_warehouse):
	"""Validate both dispatch ends and return their YRP Stock Entry header fields."""
	validate_supplier_warehouse(_("From"), from_supplier, from_warehouse)
	validate_supplier_warehouse(_("To"), to_supplier, to_warehouse)
	return {
		"from_supplier": from_supplier,
		"from_warehouse": from_warehouse,
		"to_supplier": to_supplier,
		"to_warehouse": to_warehouse,
		"transfer_supplier": to_supplier,
	}


def validate_supplier_warehouse(side, supplier, warehouse):
	if not supplier or not warehouse:
		frappe.throw(_("Select {0} Supplier and {0} Warehouse.").format(side))
	if not frappe.db.exists("Warehouse", {"supplier": supplier, "disabled": 0}):
		frappe.throw(_("Supplier {0} has no Warehouse. Create one from the Supplier.").format(supplier))
	details = frappe.db.get_value("Warehouse", warehouse, ["supplier", "disabled"], as_dict=True)
	if not details:
		frappe.throw(_("Warehouse {0} does not exist.").format(warehouse))
	if details.disabled:
		frappe.throw(_("Warehouse {0} is disabled.").format(warehouse))
	if details.supplier != supplier:
		frappe.throw(_("Warehouse {0} is not linked to Supplier {1}.").format(warehouse, supplier))

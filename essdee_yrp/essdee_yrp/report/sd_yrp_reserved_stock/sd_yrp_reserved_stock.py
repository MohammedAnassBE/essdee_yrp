"""Source-compatible migrated reserved stock report."""

import frappe
from frappe import _


def validate_filters(filters):
	if not filters:
		frappe.throw(_("Please set filters"))

	for field in ["from_date", "to_date"]:
		if not filters.get(field):
			frappe.throw(_("Please set {0}").format(field))

	if filters.get("from_date") > filters.get("to_date"):
		frappe.throw(_("From Date cannot be greater than To Date"))


def get_columns():
	columns = [
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{
			"fieldname": "item",
			"label": _("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"label": "Lot",
			"width": 100,
		},
		{
			"fieldname": "received_type",
			"fieldtype": "Link",
			"options": "YRP Received Type",
			"label": "Received Type",
			"width": 100,
		},
		{
			"fieldname": "stock_uom",
			"label": _("Stock UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"fieldname": "voucher_qty",
			"label": _("Voucher Qty"),
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"fieldname": "reserved_qty",
			"label": _("Reserved Qty"),
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"fieldname": "delivered_qty",
			"label": _("Delivered Qty"),
			"fieldtype": "Float",
			"width": 110,
			"convertible": "qty",
		},
		{
			"fieldname": "available_qty",
			"label": _("Available Qty to Reserve"),
			"fieldtype": "Float",
			"width": 120,
			"convertible": "qty",
		},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 120,
		},
		{
			"fieldname": "stock_reservation_entry",
			"label": _("Stock Reservation Entry"),
			"fieldtype": "Link",
			"options": "YRP Stock Reservation Entry",
			"width": 150,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "brand",
			"label": _("Brand"),
			"fieldtype": "Link",
			"options": "Brand",
			"width": 110,
		},
	]

	return columns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	return get_columns(), get_data(filters)


def get_data(filters):
	"""Keep MRP's brand predicate, including its unset-brand behavior."""
	conditions = ["sre.docstatus = 1", "DATE(sre.creation) BETWEEN %(from_date)s AND %(to_date)s"]
	values = dict(filters)
	if filters.get("brand") is None:
		# MRP emits `brand = NULL`, which matches no rows.
		return []
	else:
		conditions.append("i.brand = %(brand)s")
	for field in ("item_code", "warehouse", "lot", "voucher_type", "status", "received_type"):
		if filters.get(field):
			conditions.append(f"sre.{field} = %({field})s")
	if filters.get("voucher_no"):
		conditions.append("sre.voucher_no LIKE %(voucher_pattern)s")
		values["voucher_pattern"] = f"%{filters['voucher_no']}%"
	if filters.get("stock_reservation_entry"):
		conditions.append("sre.name = %(stock_reservation_entry)s")
	# The source's item filter only narrows the variant selector in the browser.
	return frappe.db.sql(
		f"""
		SELECT sre.creation AS date, sre.warehouse, i.name AS item,
			sre.item_code, sre.lot, sre.received_type, sre.stock_uom,
			sre.voucher_qty, sre.reserved_qty, sre.delivered_qty,
			(sre.available_qty - sre.reserved_qty) AS available_qty,
			sre.voucher_type, sre.voucher_no, sre.name AS stock_reservation_entry,
			sre.status, brand.name AS brand
		FROM `tabYRP Stock Reservation Entry` sre
		LEFT JOIN `tabItem` iv ON iv.name = sre.item_code
		LEFT JOIN `tabItem` i ON i.name = iv.variant_of
		LEFT JOIN `tabBrand` brand ON brand.name = i.brand
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)

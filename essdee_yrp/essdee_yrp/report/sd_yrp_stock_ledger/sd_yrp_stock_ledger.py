"""Source-compatible migrated stock ledger report."""

import frappe
from frappe import _


def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Datetime", "width": 150},
		{
			"label": _("Lot"),
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"width": 100,
		},
		{
			"label": _("Item"),
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "width": 100},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
	]

	columns.extend(
		[
			{
				"label": _("In Qty"),
				"fieldname": "in_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Out Qty"),
				"fieldname": "out_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Balance Qty"),
				"fieldname": "qty_after_transaction",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
			{
				"label": _("Voucher #"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 150,
			},
			{
				"label": _("Warehouse"),
				"fieldname": "warehouse_name",
				"fieldtype": "Data",
				"options": "Supplier",
				"width": 150,
			},
			{
				"fieldname": "received_type",
				"label": "Received Type",
				"fieldtype": "Link",
				"options": "YRP Received Type",
				"width": "80",
			},
			{
				"label": _("Incoming Rate"),
				"fieldname": "rate",
				"fieldtype": "Currency",
				"width": 110,
				"options": "Company:company:default_currency",
				"convertible": "rate",
			},
			{
				"label": _("Avg Rate (Balance Stock)"),
				"fieldname": "valuation_rate",
				"fieldtype": "Currency",
				"width": 180,
				"options": "Company:company:default_currency",
				"convertible": "rate",
			},
			{
				"label": _("Valuation Rate"),
				"fieldname": "in_out_rate",
				"fieldtype": "Currency",
				"width": 140,
				"options": "Company:company:default_currency",
				"convertible": "rate",
			},
			{
				"label": _("Balance Value"),
				"fieldname": "stock_value",
				"fieldtype": "Currency",
				"width": 110,
				"options": "Company:company:default_currency",
			},
			{
				"label": _("Value Change"),
				"fieldname": "stock_value_difference",
				"fieldtype": "Currency",
				"width": 110,
				"options": "Company:company:default_currency",
			},
			{
				"label": "Remarks",
				"fieldname": "remarks",
				"fieldtype": "Data",
				"width": 100,
			},
			{"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
			{
				"label": _("Voucher #"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 100,
			},
		]
	)

	return columns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	for row in data:
		row.update(in_qty=max(row.qty, 0), out_qty=min(row.qty, 0))
		# MRP never selects actual_qty; only reconciliation rows display this rate.
		if row.voucher_type in ("Stock Reconciliation", "YRP Stock Reconciliation"):
			row.in_out_rate = row.valuation_rate
	return get_columns(filters), data


def get_data(filters):
	"""Read migrated ledger and parent Item metadata in two queries."""
	item_conditions = ["iv.variant_of = i.name"]
	if filters.get("parent_item"):
		item_conditions.append("i.name = %(parent_item)s")
	elif filters.get("item"):
		item_conditions.append("iv.name = %(item)s")
	else:
		if filters.get("brand"):
			item_conditions.append("i.brand = %(brand)s")
		if filters.get("item_group"):
			item_conditions.append("""i.item_group IN (
				SELECT child.name FROM `tabItem Group` child
				JOIN `tabItem Group` parent ON parent.name = %(item_group)s
				WHERE child.lft >= parent.lft AND child.rgt <= parent.rgt)""")
	items = frappe.db.sql(
		f"SELECT iv.name FROM `tabItem` iv JOIN `tabItem` i ON iv.variant_of = i.name WHERE {' AND '.join(item_conditions)}",
		filters,
		pluck=True,
	)
	conditions = [
		"sle.docstatus < 2",
		"sle.is_cancelled = 0",
		"sle.posting_date BETWEEN %(from_date)s AND %(to_date)s",
	]
	values = dict(filters)
	# Preserve MRP's empty item-list behavior.
	if items:
		conditions.append("sle.item IN %(items)s")
		values["items"] = tuple(items)
	for field in ("voucher_no", "lot", "warehouse", "received_type"):
		if filters.get(field):
			conditions.append(f"sle.{field} = %({field})s")
	return frappe.db.sql(
		f"""
		SELECT sle.item, TIMESTAMP(sle.posting_date, sle.posting_time) AS date,
			sle.warehouse, s.supplier_name AS warehouse_name, sle.received_type,
			sle.posting_date, sle.posting_time, sle.qty, sle.rate, sle.valuation_rate,
			sle.voucher_type, sle.qty_after_transaction, sle.stock_value_difference,
			sle.voucher_no, sle.stock_value, sle.lot, sle.remarks,
			iv.name, i.name AS item_name, i.brand, i.stock_uom, i.item_group
		FROM `tabYRP Stock Ledger Entry` sle
		JOIN `tabSupplier` s ON s.name = sle.warehouse
		JOIN `tabItem` iv ON iv.name = sle.item
		JOIN `tabItem` i ON i.name = iv.variant_of
		WHERE {" AND ".join(conditions)}
		ORDER BY TIMESTAMP(sle.posting_date, sle.posting_time), sle.creation
		""",
		values,
		as_dict=True,
	)

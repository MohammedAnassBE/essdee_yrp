# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import frappe

from essdee_yrp.stock_report_compat import item_group_aliases


def execute(filters=None):
	columns = get_columns()
	data = get_data(frappe._dict(filters or {}))
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "stock_ledger_entry",
			"fieldtype": "Link",
			"options": "YRP Stock Ledger Entry",
			"label": "Stock Ledger Entry",
			"width": 170,
		},
		{"fieldname": "lot", "fieldtype": "Link", "label": "Lot", "options": "SD YRP Lot", "width": 100},
		{
			"fieldname": "item_variant",
			"fieldtype": "Link",
			"label": "Item Variant",
			"options": "Item",
			"width": 250,
		},
		{"fieldname": "quantity", "fieldtype": "Float", "label": "Quantity", "width": 100},
		{"fieldname": "valuation_rate", "fieldtype": "Currency", "label": "Valuation Rate", "width": 100},
		{
			"fieldname": "item_group",
			"fieldtype": "Link",
			"label": "Item Group",
			"options": "Item Group",
			"width": 150,
		},
		{"fieldname": "item_name", "fieldtype": "Link", "label": "Item", "options": "Item", "width": 170},
		{
			"fieldname": "from_warehouse",
			"fieldtype": "Link",
			"label": "From Warehouse",
			"options": "Supplier",
			"width": 150,
		},
		{
			"fieldname": "to_warehouse",
			"fieldtype": "Link",
			"label": "To Warehouse",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "voucher_type", "fieldtype": "Data", "label": "Voucher Type", "width": 130},
		{
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"label": "Voucher No",
			"width": 130,
		},
	]


def get_data(filters):
	"""Keep MRP's item/rate buckets with a stable voucher representative."""
	groups = frappe.get_all("Item Group", fields=["name", "parent_item_group", "is_group"])
	aliases = item_group_aliases(groups)
	item_groups = get_item_groups(filters.get("item_group"), groups)
	doctypes = ["YRP Stock Entry", "SD YRP Lot Transfer", "YRP Delivery Challan", "YRP Goods Received Note"]
	# User decision (2026-10-20): show the earliest voucher in each item/rate
	# bucket. Keep every representative field from that same ledger row.
	data = frappe.db.sql(
		"""
			SELECT stock_ledger_entry, lot, item_variant, quantity, valuation_rate,
				item_group, item_name, from_warehouse, voucher_type, voucher_no
			FROM (
			SELECT t1.name as stock_ledger_entry, t1.lot, t1.item as item_variant,
			SUM(t1.qty) OVER (PARTITION BY t1.item, t1.valuation_rate) as quantity, t1.valuation_rate, t3.item_group,
			t3.name as item_name, t1.warehouse as from_warehouse,
			t1.voucher_type, t1.voucher_no,
			ROW_NUMBER() OVER (
				PARTITION BY t1.item, t1.valuation_rate
				ORDER BY t1.posting_date, t1.posting_time, t1.voucher_no, t1.name
			) AS bucket_row
			FROM `tabYRP Stock Ledger Entry` as t1
			JOIN `tabItem` as t2 ON t1.item = t2.name
			JOIN `tabItem` as t3 ON COALESCE(NULLIF(t2.variant_of, ''), t2.name) = t3.name
			JOIN `tabItem Group` as t4 ON t3.item_group = t4.name
			WHERE t1.posting_date >= %(start_date)s
			AND t1.posting_date <= %(end_date)s
			AND t1.lot = %(lot)s
			AND t3.item_group IN %(item_groups)s
			AND t1.qty < 0
			AND t1.is_cancelled = 0
			AND t1.voucher_type IN %(doctypes)s
			) grouped WHERE bucket_row = 1
			ORDER BY item_variant, valuation_rate
		""",
		{
			"start_date": filters.get("start_date"),
			"end_date": filters.get("end_date"),
			"lot": filters.get("lot"),
			"item_groups": tuple(item_groups),
			"doctypes": tuple(doctypes),
		},
		as_dict=True,
	)
	destinations = {}
	for doctype, field in {
		"YRP Delivery Challan": "supplier",
		"YRP Goods Received Note": "delivery_location",
		"YRP Stock Entry": "to_warehouse",
	}.items():
		names = {row.voucher_no for row in data if row.voucher_type == doctype}
		if not names:
			continue
		fields = ["name", field]
		if doctype == "YRP Stock Entry":
			fields.append("transfer_supplier")
		for doc in frappe.get_all(doctype, filters={"name": ["in", list(names)]}, fields=fields):
			destinations[(doctype, doc.name)] = doc.get(field) or (
				doc.get("transfer_supplier") if doctype == "YRP Stock Entry" else doc.get(field)
			)
	for row in data:
		row.item_group = aliases.get(row.item_group, row.item_group)
		row["to_warehouse"] = (
			row.from_warehouse
			if row.voucher_type == "SD YRP Lot Transfer"
			else destinations.get((row.voucher_type, row.voucher_no))
		)
	return data


def get_item_groups(item_group, groups=None):
	"""Expand descendants across the original and copied migration group trees."""
	if groups is None:
		groups = frappe.get_all("Item Group", fields=["name", "parent_item_group", "is_group"])
	aliases = item_group_aliases(groups)
	selected = next((row for row in groups if row.name == item_group), None)
	if not selected:
		frappe.throw("Item Group does not exist: {0}".format(item_group), frappe.DoesNotExistError)
	children = {}
	for row in groups:
		parent = aliases.get(row.parent_item_group, row.parent_item_group)
		children.setdefault(parent, []).append(aliases[row.name])
	pending, seen = [aliases[item_group]], set()
	while pending:
		name = pending.pop()
		if name in seen:
			continue
		seen.add(name)
		if selected.is_group:
			pending.extend(children.get(name, []))
	return [row.name for row in groups if aliases[row.name] in seen]

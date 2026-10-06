"""Transactional smoke test for Cutting Plan stock-transfer composers.

Creates real Draft documents through the public workspace service, then rolls
the database transaction back so the verification leaves no business records.
"""

import json

import frappe

SITE = "erp-migration-test.site"
PLAN = "CP-2609-00007"
ITEM = "441057-O.KIDS CAPYBARA VALENTINES BU"


def item_details(dimensions):
	return [
		{
			"items": [
				{
					"name": ITEM,
					"dimensions": dimensions,
					"attributes": {"Stage": "Cut", "Colour": "White", "Panel": "Collar"},
					"values": {"7-8": {"qty": 1}},
				}
			]
		}
	]


frappe.init(site=SITE)
frappe.connect()
frappe.set_user("Administrator")
try:
	from essdee_yrp.cutting.web_workspace import (
		create_work_order_delivery_challan,
		get_work_order_delivery_editor,
		save_stock_operation,
	)

	created = {}
	created["stock_update"] = save_stock_operation(
		PLAN,
		"stock_update",
		{
			"update_type": "Reduce",
			"item_details": item_details({"lot": "JB2627-016", "received_type": "Accepted"}),
		},
		False,
	)["name"]

	target_lot = frappe.db.get_value(
		"SD YRP Lot",
		{"name": ["!=", "JB2627-016"]},
		"name",
	)
	created["lot_transfer"] = save_stock_operation(
		PLAN,
		"lot_transfer",
		{
			"item_details": item_details(
				{
					"from_lot": "JB2627-016",
					"to_lot": target_lot,
					"received_type": "Accepted",
				}
			),
		},
		False,
	)["name"]

	editor = get_work_order_delivery_editor(PLAN)
	reference = next(
		value["ref_docname"]
		for group in editor["item_details"]
		for entry in group["items"]
		for value in entry["values"].values()
		if value.get("ref_docname") not in (None, "", 0, "0")
	)
	created["delivery_challan"] = create_work_order_delivery_challan(
		PLAN,
		{"quantities": {reference: 0.001}},
		False,
	)["name"]
	print(json.dumps(created, indent=2))
finally:
	frappe.db.rollback()
	frappe.destroy()

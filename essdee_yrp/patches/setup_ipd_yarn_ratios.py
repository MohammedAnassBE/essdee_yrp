import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields({
		"Item Production Detail": [{
			"fieldname": "yarn_ratio_details",
			"fieldtype": "Table",
			"label": "Yarn Ratio",
			"options": "IPD Yarn Ratio",
			"insert_after": "yarn_item",
			"depends_on": "eval:doc.is_cloth_item",
			"description": (
				"Yarn composition used by the knitting matrix. "
				"Ratios must total exactly 100."
			),
		}],
	})

	# The single link is retained as a hidden compatibility/default field while
	# the child table becomes authoritative.
	if frappe.db.exists("Custom Field", "Item Production Detail-yarn_item"):
		frappe.db.set_value(
			"Custom Field",
			"Item Production Detail-yarn_item",
			{"hidden": 1, "mandatory_depends_on": None},
			update_modified=False,
		)

	_insert_into_field_order()
	_backfill_single_yarns()
	frappe.clear_cache(doctype="Item Production Detail")


def _insert_into_field_order():
	name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Item Production Detail", "property": "field_order"},
		"name",
	)
	if not name:
		return
	raw = frappe.db.get_value("Property Setter", name, "value")
	try:
		order = json.loads(raw or "[]")
	except (TypeError, ValueError):
		return
	if "yarn_ratio_details" in order:
		return
	position = order.index("yarn_item") + 1 if "yarn_item" in order else len(order)
	order.insert(position, "yarn_ratio_details")
	frappe.db.set_value("Property Setter", name, "value", json.dumps(order), update_modified=False)


def _backfill_single_yarns():
	ipds = frappe.get_all(
		"Item Production Detail",
		filters={"is_cloth_item": 1, "yarn_item": ["is", "set"]},
		fields=["name", "yarn_item"],
	)
	for ipd in ipds:
		if frappe.db.exists("IPD Yarn Ratio", {
			"parent": ipd.name,
			"parenttype": "Item Production Detail",
			"parentfield": "yarn_ratio_details",
		}):
			continue
		row = frappe.new_doc("IPD Yarn Ratio")
		row.parent = ipd.name
		row.parenttype = "Item Production Detail"
		row.parentfield = "yarn_ratio_details"
		row.idx = 1
		row.yarn_item = ipd.yarn_item
		row.ratio = 100
		row.db_insert()

"""In-/web inline editor for Item Attribute Mappings.

`ItemAttributeListView.vue` (the /web SPA frontend) calls
`update_mapping_values` when the user finishes editing an attribute's value
list inline. Doing this server-side as a single unit avoids the timestamp
race that a multi-call frontend flow (insert each Item Attribute Value, then
PUT the parent) ran into — the parent's `modified` would change between the
last insert and the parent save.

Permission model: respects standard DocType perms; the user must have write
on Item Item Attribute Mapping (and create on Item Attribute Value, if a new
value is introduced).
"""

import json

import frappe
from frappe import _


@frappe.whitelist()
def update_mapping_values(mapping, attribute_name, values):
	"""Replace an Item Item Attribute Mapping's `values` table.

	`values` is a list of plain strings (the attribute values). For each
	value that has no backing Item Attribute Value doc, one is inserted
	first (so the child-table Link target resolves on the subsequent save).

	Returns the updated value list in the order it was persisted.
	"""
	if not mapping:
		frappe.throw(_("Mapping is required"))
	if not attribute_name:
		frappe.throw(_("Attribute name is required"))

	if isinstance(values, str):
		try:
			values = json.loads(values)
		except (TypeError, ValueError):
			frappe.throw(_("Invalid `values` payload"))
	if not isinstance(values, list):
		frappe.throw(_("`values` must be a list"))

	# The mapping owns exactly one attribute — reject a call whose attribute_name
	# doesn't match it, so a misdirected request can't create Item Attribute
	# Values under the wrong attribute.
	doc = frappe.get_doc("Item Item Attribute Mapping", mapping)
	if doc.attribute_name and doc.attribute_name != attribute_name:
		frappe.throw(
			_("Mapping {0} is for attribute {1}, not {2}.").format(
				mapping, doc.attribute_name, attribute_name
			)
		)

	# Deduplicate while preserving order — defensive; the frontend already
	# blocks duplicates client-side, but we don't trust the client alone.
	seen = set()
	clean_values = []
	for v in values:
		s = str(v or "").strip()
		if not s or s in seen:
			continue
		seen.add(s)
		clean_values.append(s)

	# 1. Ensure every value has a backing Item Attribute Value doc. Insert
	#    inside the same transaction so the subsequent mapping.save doesn't
	#    race with an external commit on the same Attribute Value records.
	for v in clean_values:
		if not frappe.db.exists("Item Attribute Value", v):
			frappe.get_doc(
				{
					"doctype": "Item Attribute Value",
					"attribute_name": attribute_name,
					"attribute_value": v,
				}
			).insert()

	# 2. Replace the mapping's child rows in one shot.
	doc.set("values", [])
	for i, v in enumerate(clean_values, start=1):
		doc.append("values", {"attribute_value": v, "idx": i})
	doc.save()
	return {
		"name": doc.name,
		"attribute_name": doc.attribute_name,
		"values": [r.attribute_value for r in doc.values],
	}

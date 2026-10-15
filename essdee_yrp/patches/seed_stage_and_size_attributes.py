import frappe

ATTRIBUTES = {
	"Size": [],
	"Stage": ["Cut", "Pack", "Piece", "Loose Piece"],
}


def execute():
	"""Insert the Size and Stage Item Attributes when missing; never change existing ones."""
	for attribute, values in ATTRIBUTES.items():
		if frappe.db.exists("Item Attribute", attribute):
			continue
		frappe.get_doc({
			"doctype": "Item Attribute",
			"attribute_name": attribute,
			"item_attribute_values": [{"attribute_value": value, "abbr": value} for value in values],
		}).insert(ignore_permissions=True)

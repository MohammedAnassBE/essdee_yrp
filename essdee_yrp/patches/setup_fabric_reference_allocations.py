from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	fields = []
	for doctype in ("Work Order Deliverables", "Work Order Receivables"):
		fields.append({
			"fieldname": "fabric_reference_variant",
			"fieldtype": "Link",
			"label": "Fabric Reference Variant",
			"options": "Item Variant",
			"insert_after": "set_combination",
			"hidden": 1,
			"no_copy": 1,
		})
		fields.append({
			"fieldname": "fabric_reference_allocations",
			"fieldtype": "JSON",
			"label": "Fabric Reference Allocations",
			"insert_after": "fabric_reference_variant",
			"hidden": 1,
			"no_copy": 1,
		})
		create_custom_fields({doctype: fields[-2:]}, update=True)

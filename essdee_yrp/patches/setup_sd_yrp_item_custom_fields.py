from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Item": [
				{
					"fieldname": "product_category",
					"fieldtype": "Link",
					"label": "Product Category",
					"options": "Product Category",
					"insert_after": "categories",
					"permlevel": 1,
				}
			]
		}
	)

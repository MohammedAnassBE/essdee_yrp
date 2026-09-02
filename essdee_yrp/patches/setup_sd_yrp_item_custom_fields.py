from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			'YRP Item': [
				{
					"fieldname": "product_category",
					"fieldtype": "Link",
					"label": "Product Category",
					"options": 'SD YRP Product Category',
					"insert_after": "categories",
					"permlevel": 1,
				}
			]
		}
	)

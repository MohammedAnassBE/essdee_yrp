from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from essdee_yrp.sd_yrp_sync import ensure_consumer_config


def execute():
	create_custom_fields(
		{
			"Supplier": [
				{
					"fieldname": "apply_sewing_plan",
					"fieldtype": "Check",
					"label": "Apply Sewing Plan",
					"insert_after": "is_company_location",
					"default": "0",
				}
			]
		}
	)
	ensure_consumer_config()

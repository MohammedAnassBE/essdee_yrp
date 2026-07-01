from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from essdee_yrp.sd_yrp_sync import ensure_consumer_config


def execute():
	create_custom_fields(
		{
			"Process": [
				{
					"fieldname": "includes_packing",
					"fieldtype": "Check",
					"label": "Includes Packing",
					"insert_after": "is_manual_entry_in_grn",
					"default": "0",
				},
				{
					"fieldname": "item",
					"fieldtype": "Link",
					"label": "Item",
					"options": "Item",
					"insert_after": "includes_packing",
				},
				{
					"fieldname": "additional_allowance",
					"fieldtype": "Percent",
					"label": "Additional Allowance",
					"insert_after": "process_details",
				},
			]
		}
	)
	ensure_consumer_config()

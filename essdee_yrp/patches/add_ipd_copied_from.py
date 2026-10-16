from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	"""Record the source IPD of a web-copied version without touching amended_from."""
	create_custom_field(
		"YRP Item Production Detail",
		{
			"fieldname": "copied_from",
			"label": "Copied From",
			"fieldtype": "Link",
			"options": "YRP Item Production Detail",
			"insert_after": "pattern_version",
			"read_only": 1,
			"no_copy": 1,
			"ignore_user_permissions": 1,
			"print_hide": 1,
			"module": "Essdee YRP",
		},
	)

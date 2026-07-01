import frappe

from essdee_yrp.patches.setup_sd_yrp_ipd_custom_fields import (
	IPD_CUSTOM_FIELDS,
	execute as setup_ipd_fields,
)


def execute():
	setup_ipd_fields()
	for field in IPD_CUSTOM_FIELDS:
		values = {
			key: field[key]
			for key in ("mandatory_depends_on", "description")
			if field.get(key) is not None
		}
		if values:
			frappe.db.set_value(
				"Custom Field",
				f"Item Production Detail-{field['fieldname']}",
				values,
				update_modified=False,
			)
	frappe.clear_cache(doctype="Item Production Detail")

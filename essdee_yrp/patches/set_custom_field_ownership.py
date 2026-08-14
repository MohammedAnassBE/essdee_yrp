import json

import frappe


def execute():
	"""Assign this app's explicitly-fixtured Custom Fields to Essdee YRP."""
	fixture_path = frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json")
	with open(fixture_path, encoding="utf-8") as fixture_file:
		custom_fields = json.load(fixture_file)

	for custom_field in custom_fields:
		field_name = custom_field.get("name")
		if field_name and frappe.db.exists("Custom Field", field_name):
			frappe.db.set_value(
				"Custom Field",
				field_name,
				"module",
				"Essdee YRP",
				update_modified=False,
			)

	frappe.clear_cache()

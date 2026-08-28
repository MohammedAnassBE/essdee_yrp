import frappe
from frappe.utils import flt


LEGACY_CUSTOM_FIELD = "Process-additional_allowance"


def choose_excess_percentage(base_value, legacy_value):
	"""Preserve an authored base value; otherwise carry the legacy percentage."""
	return flt(base_value) if flt(base_value) else flt(legacy_value)


def execute():
	"""Move Essdee's duplicate Process allowance into base YRP and remove it."""
	if not frappe.db.exists("Custom Field", LEGACY_CUSTOM_FIELD):
		return

	for row in frappe.get_all(
		"Process",
		fields=["name", "additional_allowance", "wo_excess_allowed_percentage"],
	):
		percentage = choose_excess_percentage(
			row.wo_excess_allowed_percentage,
			row.additional_allowance,
		)
		if percentage != flt(row.wo_excess_allowed_percentage):
			frappe.db.set_value(
				"Process",
				row.name,
				"wo_excess_allowed_percentage",
				percentage,
				update_modified=False,
			)

	frappe.db.delete("Custom Field", {"name": LEGACY_CUSTOM_FIELD})
	frappe.clear_cache(doctype="Process")

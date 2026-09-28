from yrp.attribute_links import value as _attribute_value
# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SDYRPIPDSettings(Document):
	def validate(self):
		get_knitting_colour(self.default_knitting_output_colour)


def get_knitting_colour(value):
	"""Resolve the Colour Link at the settings/business boundary."""
	if not value:
		return ""
	row = frappe.db.get_value("YRP Item Attribute Value", value,
		["attribute_name", "attribute_value"], as_dict=True)
	if not row or row.attribute_name != "Colour":
		frappe.throw(_("Default Knitting Yarn Colour must be a Colour value from YRP Item Attribute Value."))
	return _attribute_value(row.attribute_value)


IPDSettings = SDYRPIPDSettings

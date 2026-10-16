# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from yrp.attribute_links import value as _attribute_value

SETTINGS = "SD YRP IPD Settings"


class SDYRPIPDSettings(Document):
	def validate(self):
		get_knitting_colour(self.default_knitting_output_colour, self.default_packing_attribute)


def get_colour_attribute():
	"""The Item Attribute holding garment and fabric colour: the packing attribute."""
	return _get_required_attribute("default_packing_attribute")


def get_dia_attribute():
	"""The Item Attribute holding fabric dia on cloth variants."""
	return _get_required_attribute("default_dia_attribute")


def _get_required_attribute(fieldname):
	attribute = frappe.db.get_single_value(SETTINGS, fieldname)
	if not attribute:
		label = frappe.get_meta(SETTINGS).get_label(fieldname)
		frappe.throw(_("Set {0} in {1}").format(_(label), _(SETTINGS)))
	return attribute


def get_knitting_colour(value, colour_attribute=None):
	"""Resolve the Colour Link at the settings/business boundary."""
	if not value:
		return ""
	colour_attribute = colour_attribute or get_colour_attribute()
	row = frappe.db.get_value(
		"YRP Item Attribute Value", value, ["attribute_name", "attribute_value"], as_dict=True
	)
	if not row or row.attribute_name != colour_attribute:
		frappe.throw(
			_("Default Non-Dyed Colour must be a {0} value from YRP Item Attribute Value.").format(
				colour_attribute
			)
		)
	return _attribute_value(row.attribute_value)


IPDSettings = SDYRPIPDSettings

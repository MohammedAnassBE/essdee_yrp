# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class IPDSettings(Document):
	def validate(self):
		colour = self.get("default_knitting_output_colour")
		if colour and frappe.db.get_value(
			"Item Attribute Value", colour, "attribute_name"
		) != "Colour":
			frappe.throw(_(
				"Default Non-Dyed Colour must be an Item Attribute Value "
				"belonging to Colour."
			))

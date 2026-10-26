from unittest import TestCase
from unittest.mock import patch

import frappe

VALUES = {
	"IAV-BLACK": frappe._dict(attribute_name="Colour", attribute_value="Black"),
	"IAV-DIA-60": frappe._dict(attribute_name="Dia", attribute_value="60 Dia"),
}


class TestCuttingOrderPrint(TestCase):
	def print_values(self, colour, dia):
		"""Run before_print on an unsaved Cutting Order whose ``colour`` and ``dia`` are registered links."""
		doc = frappe.get_doc({"doctype": "SD YRP Cutting Order", "colour": colour, "dia": dia})
		with (
			patch.object(frappe.local, "attribute_link_values", dict(VALUES), create=True),
			patch(
				"essdee_yrp.print_helpers.attribute_db.fields",
				return_value={"SD YRP Cutting Order": ["colour", "dia"]},
			),
		):
			doc.run_method("before_print")
		return doc.colour, doc.dia

	def test_before_print_replaces_attribute_ids_with_text(self):
		self.assertEqual(self.print_values("IAV-BLACK", "IAV-DIA-60"), ("Black", "60 Dia"))

	def test_before_print_keeps_text_values(self):
		self.assertEqual(self.print_values("Black", "60 Dia"), ("Black", "60 Dia"))

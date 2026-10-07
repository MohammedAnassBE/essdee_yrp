import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.boot import boot_session
from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import (
	get_colour_attribute,
	get_dia_attribute,
)
from essdee_yrp.patches.seed_default_dia_attribute import execute as seed_default_dia_attribute

SETTINGS = "SD YRP IPD Settings"


class TestIPDAttributeSettings(IntegrationTestCase):
	def test_dia_attribute_comes_from_ipd_settings(self):
		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", "Width")

		self.assertEqual(get_dia_attribute(), "Width")

	def test_colour_attribute_is_the_packing_attribute(self):
		frappe.db.set_single_value(SETTINGS, "default_packing_attribute", "Shade")

		self.assertEqual(get_colour_attribute(), "Shade")

	def test_unset_dia_attribute_fails_loudly(self):
		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", None)

		with self.assertRaises(frappe.ValidationError) as raised:
			get_dia_attribute()

		self.assertIn("Default Dia Attribute", str(raised.exception))

	def test_boot_exposes_configured_attribute_names(self):
		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", "Width")
		frappe.db.set_single_value(SETTINGS, "default_packing_attribute", "Shade")
		bootinfo = frappe._dict(session_defaults=[])

		boot_session(bootinfo)

		self.assertEqual(bootinfo.essdee_yrp_ipd_attributes, {"colour": "Shade", "dia": "Width"})

	def test_seed_sets_dia_only_when_unset(self):
		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", None)
		seed_default_dia_attribute()
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "default_dia_attribute"), "Dia")

		frappe.db.set_single_value(SETTINGS, "default_dia_attribute", "Width")
		seed_default_dia_attribute()
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "default_dia_attribute"), "Width")

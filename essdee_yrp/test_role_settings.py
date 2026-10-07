import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.patches.seed_role_settings import execute as seed_role_settings

ROLE_SETTINGS = {
	("SD YRP MRP Settings", "production_planner_role"): "Production Planner",
	("SD YRP T and A Settings", "t_and_a_admin_role"): "T & A Admin",
}


class TestEssdeeRoleSettings(IntegrationTestCase):
	def test_seed_sets_todays_roles_when_unset(self):
		for doctype, fieldname in ROLE_SETTINGS:
			frappe.db.set_single_value(doctype, fieldname, None)

		seed_role_settings()

		for (doctype, fieldname), role in ROLE_SETTINGS.items():
			self.assertEqual(frappe.db.get_single_value(doctype, fieldname), role)

	def test_seed_keeps_configured_roles(self):
		for doctype, fieldname in ROLE_SETTINGS:
			frappe.db.set_single_value(doctype, fieldname, "Stock User")

		seed_role_settings()

		for doctype, fieldname in ROLE_SETTINGS:
			self.assertEqual(frappe.db.get_single_value(doctype, fieldname), "Stock User")

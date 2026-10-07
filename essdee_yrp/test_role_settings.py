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


class TestFreshInstallSettings(IntegrationTestCase):
	def test_fresh_install_seeds_role_settings_and_dia_attribute(self):
		from contextlib import ExitStack
		from unittest.mock import patch

		import essdee_yrp.setup as setup

		steps = [name for name in dir(setup) if name.startswith("ensure_") and callable(getattr(setup, name))]
		with ExitStack() as stack:
			for step in steps:
				stack.enter_context(patch.object(setup, step))
			stack.enter_context(
				patch("essdee_yrp.purchase_order_approval.ensure_purchase_order_approval_route")
			)
			seed_roles = stack.enter_context(patch("essdee_yrp.patches.seed_role_settings.execute"))
			seed_dia = stack.enter_context(patch("essdee_yrp.patches.seed_default_dia_attribute.execute"))
			setup.after_install()

		seed_roles.assert_called_once_with()
		seed_dia.assert_called_once_with()

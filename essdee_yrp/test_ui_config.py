import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.ui_config import (
	PREMIUM_LAYOUT_NAME,
	get_my_ui_config,
	get_ui_config_for,
	resolve_config,
	reset_my_ui_overrides,
	save_my_ui_overrides,
)


class TestPremiumWhiteUIConfig(IntegrationTestCase):
	def test_premium_white_is_used_without_a_preference(self):
		config, meta = resolve_config("Guest")

		self.assertEqual(meta["layout"], PREMIUM_LAYOUT_NAME)
		self.assertFalse(meta["has_preference"])
		self.assertEqual(config["nav"]["sidebar"], "pinned")
		self.assertEqual(config["theme"]["accent"], "#C15F3F")

	def test_personal_overrides_do_not_change_the_base_layout(self):
		user = "Administrator"
		if frappe.db.exists("YRP UI Preference", user):
			frappe.delete_doc(
				"YRP UI Preference", user, ignore_permissions=True, force=True
			)
		frappe.get_doc(
			{
				"doctype": "YRP UI Preference",
				"user": user,
				"layout": PREMIUM_LAYOUT_NAME,
				"overrides": json.dumps(
					{"schema_version": 1, "theme": {"density": "compact"}}
				),
			}
		).insert(ignore_permissions=True)

		config, meta = resolve_config(user)

		self.assertEqual(meta["layout"], PREMIUM_LAYOUT_NAME)
		self.assertTrue(meta["has_preference"])
		self.assertEqual(config["theme"]["density"], "compact")
		self.assertEqual(config["theme"]["accent"], "#C15F3F")

	def test_refresh_save_reset_and_user_preview_keep_premium_white(self):
		user = frappe.session.user
		if frappe.db.exists("YRP UI Preference", user):
			frappe.delete_doc(
				"YRP UI Preference", user, ignore_permissions=True, force=True
			)

		self.assertEqual(get_my_ui_config()["meta"]["layout"], PREMIUM_LAYOUT_NAME)

		saved = save_my_ui_overrides(
			{"schema_version": 1, "theme": {"density": "compact"}}
		)
		self.assertEqual(saved["meta"]["layout"], PREMIUM_LAYOUT_NAME)
		self.assertEqual(saved["config"]["theme"]["density"], "compact")
		self.assertEqual(
			frappe.db.get_value("YRP UI Preference", user, "layout"),
			PREMIUM_LAYOUT_NAME,
		)

		reset = reset_my_ui_overrides()
		self.assertEqual(reset["meta"]["layout"], PREMIUM_LAYOUT_NAME)
		self.assertEqual(reset["config"]["theme"]["density"], "comfortable")

		preview = get_ui_config_for(user=user)
		self.assertEqual(preview["meta"]["layout"], PREMIUM_LAYOUT_NAME)


class TestDepartmentLayoutUIConfig(IntegrationTestCase):
	user = "Administrator"

	def setUp(self):
		self.remove_preference()
		self.addCleanup(self.remove_preference)

	def remove_preference(self):
		if frappe.db.exists("YRP UI Preference", self.user):
			frappe.delete_doc("YRP UI Preference", self.user, ignore_permissions=True, force=True)

	def set_layout(self, layout):
		frappe.get_doc({"doctype": "YRP UI Preference", "user": self.user, "layout": layout}).insert(
			ignore_permissions=True
		)

	def test_registered_experience_layout_narrows_to_its_department(self):
		self.set_layout("Sales")

		config, meta = resolve_config(self.user)

		self.assertEqual(meta["render_mode"], "Registered Experience")
		self.assertEqual(meta["experience_key"], "sales")
		self.assertEqual(meta["department_layout"], "Sales")
		self.assertEqual(meta["layout"], PREMIUM_LAYOUT_NAME)
		self.assertEqual(config["experience_props"]["workspaces"], ["production_orders", "reports"])
		self.assertEqual(config["theme"]["accent"], "#C15F3F")

	def test_configurable_layout_keeps_the_permission_based_view(self):
		self.set_layout(PREMIUM_LAYOUT_NAME)

		config, meta = resolve_config(self.user)

		self.assertEqual(meta["render_mode"], "Configurable Layout")
		self.assertIsNone(meta["experience_key"])
		self.assertNotIn("experience_props", config)

	def test_disabled_department_layout_warns_and_keeps_the_permission_based_view(self):
		layout = frappe.get_doc(
			{
				"doctype": "YRP UI Layout",
				"layout_name": "Test Disabled Sales",
				"render_mode": "Registered Experience",
				"experience_key": "sales",
				"config": json.dumps({"schema_version": 1, "experience_props": {"workspaces": ["reports"]}}),
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "YRP UI Layout", layout.name, ignore_permissions=True, force=True)
		self.addCleanup(self.remove_preference)
		self.set_layout(layout.name)
		layout.db_set("disabled", 1)

		config, meta = resolve_config(self.user)

		self.assertEqual(meta["render_mode"], "Configurable Layout")
		self.assertNotIn("experience_props", config)
		self.assertTrue(any("Test Disabled Sales" in warning for warning in meta["warnings"]))

	def test_saving_overrides_keeps_the_department_layout(self):
		self.set_layout("Sales")
		frappe.set_user(self.user)

		saved = save_my_ui_overrides({"schema_version": 1, "theme": {"density": "compact"}})

		self.assertEqual(frappe.db.get_value("YRP UI Preference", self.user, "layout"), "Sales")
		self.assertEqual(saved["meta"]["experience_key"], "sales")

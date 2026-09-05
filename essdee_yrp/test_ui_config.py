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

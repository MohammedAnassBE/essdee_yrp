from unittest import TestCase

import frappe

from essdee_yrp.www import web


class TestWebSessionUser(TestCase):
	"""/web boot carries what the top-bar avatar needs."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_boot_user_has_full_name_image_and_roles(self):
		user = web.get_boot()["user"]
		full_name, user_image = frappe.db.get_value("User", "Administrator", ["full_name", "user_image"])
		self.assertEqual(user["full_name"], full_name)
		self.assertEqual(user["user_image"], user_image)
		self.assertIn("System Manager", user["roles"])

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo

from essdee_yrp.www import web


class TestWebBrand(TestCase):
	"""/web shows the same logo and favicon as Desk."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_boot_app_logo_is_desks_app_logo(self):
		self.assertEqual(web.get_boot()["app_logo"], get_app_logo())

	def test_configured_logo_reaches_boot(self):
		with patch.object(web, "get_app_logo", return_value="/files/company-logo.png"):
			self.assertEqual(web.get_boot()["app_logo"], "/files/company-logo.png")

	def test_context_keeps_the_website_favicon(self):
		context = frappe._dict(favicon="/assets/erpnext/images/erpnext-favicon.svg")
		with patch.object(web, "get_boot", return_value={}), patch.object(frappe.sessions, "get_csrf_token", return_value="token"):
			web.get_context(context)
		self.assertEqual(context.favicon, "/assets/erpnext/images/erpnext-favicon.svg")

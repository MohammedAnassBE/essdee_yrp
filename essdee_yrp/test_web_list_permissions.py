import re
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.www.web import WEB_DOCTYPES, _apply_accurate_web_perms

LIST_PERMISSION_SOURCE = (
	Path(__file__).resolve().parent.parent / "frontend" / "src" / "router" / "listPermission.js"
)


def list_route_doctypes():
	"""DocTypes the /web list-route guard reads from boot.user.can_read."""
	return set(re.findall(r':\s*"([^"]+)",?\n', LIST_PERMISSION_SOURCE.read_text()))


class TestWebListPermissions(TestCase):
	def test_guarded_list_doctypes_exist_and_are_in_both_web_catalogs(self):
		doctypes = list_route_doctypes()
		self.assertIn("YRP Delivery Challan", doctypes)
		for doctype in doctypes:
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.db.exists("DocType", doctype))
				self.assertIn(doctype, WEB_DOCTYPES)
				self.assertIn(doctype, hooks.yrp_web_doctype_catalog)

	def test_boot_drops_list_doctypes_the_server_denies(self):
		doctypes = sorted(list_route_doctypes())
		user = {"can_read": doctypes[:]}
		with patch.object(
			frappe, "has_permission", side_effect=lambda doctype, ptype: doctype != "YRP Delivery Challan"
		):
			_apply_accurate_web_perms(user)
		self.assertNotIn("YRP Delivery Challan", user["can_read"])
		self.assertEqual(set(user["can_read"]) & set(doctypes), set(doctypes) - {"YRP Delivery Challan"})

	def test_boot_adds_list_doctypes_the_server_allows(self):
		user = {"can_read": []}
		with patch.object(frappe, "has_permission", return_value=True):
			_apply_accurate_web_perms(user)
		self.assertTrue(list_route_doctypes() <= set(user["can_read"]))

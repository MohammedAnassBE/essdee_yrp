from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from essdee_yrp.essdee_yrp.doctype.shortened_link.shortened_link import (
	ShortenedLink,
	get_print_pdf,
	parse_short_link,
)


class TestShortenedLink(IntegrationTestCase):
	def test_only_system_manager_can_manage_tokens(self):
		path = frappe.get_app_path(
			"essdee_yrp", "essdee_yrp", "doctype", "shortened_link", "shortened_link.json"
		)
		schema = frappe.get_file_json(path)
		self.assertEqual([row["role"] for row in schema["permissions"]], ["System Manager"])

	def test_expiry_boundary_and_redirect_scheme(self):
		doc = frappe.new_doc("Shortened Link")
		doc.type = "Link"
		doc.link = "javascript:alert(1)"
		with self.assertRaises(frappe.ValidationError):
			ShortenedLink.validate(doc)
		doc.link = "https://essdee.example/path"
		doc.link_expiry = add_days(now_datetime(), -1)
		self.assertTrue(ShortenedLink.is_expired(doc))

	def test_authenticated_print_preview_checks_target_permission(self):
		target = MagicMock()
		with (
			patch("essdee_yrp.essdee_yrp.doctype.shortened_link.shortened_link.frappe.get_doc", return_value=target),
			patch("essdee_yrp.essdee_yrp.doctype.shortened_link.shortened_link.render_document_print", return_value="html"),
		):
			self.assertEqual(get_print_pdf("Lot", "LOT-1"), "html")
		target.check_permission.assert_called_once_with("print")

	def test_unknown_public_token_is_rejected(self):
		with patch(
			"essdee_yrp.essdee_yrp.doctype.shortened_link.shortened_link.frappe.db.exists",
			return_value=False,
		):
			with self.assertRaises(frappe.DoesNotExistError):
				parse_short_link(token="missing")

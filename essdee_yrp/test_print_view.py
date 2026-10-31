import re
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.website.serve import get_response_content

PRINTS = (
	("Purchase Order", "Essdee Purchase Order"),
	("YRP Production Order", "Essdee Production Order"),
)


class TestPrintViewTitle(TestCase):
	"""Save as PDF takes its filename from the /printview title."""

	def test_printview_title_is_document_name(self):
		for doctype, print_format in PRINTS:
			name = frappe.db.get_value(doctype, {"docstatus": ["<", 2]}, "name")
			if not name:
				self.skipTest(f"No {doctype} on this site")
			with self.subTest(doctype=doctype, name=name):
				self.assertEqual(self.get_printview_title(doctype, name, print_format), name)

	def get_printview_title(self, doctype, name, print_format):
		params = frappe._dict(doctype=doctype, name=name, format=print_format, trigger_print="1")
		with patch.object(frappe.local, "form_dict", params):
			html = get_response_content("printview")
		return re.search(r"<title>(.*?)</title>", html).group(1)

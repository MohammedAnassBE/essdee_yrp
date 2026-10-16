from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.print_registry import get_document_print_formats


class TestDocumentPrintFormats(TestCase):
	def test_print_settings_gate_drafts_and_cancelled_documents(self):
		formats = [{"label": "Production Order", "format": "Essdee Production Order"}]
		for docstatus, fieldname in ((0, "allow_print_for_draft"), (2, "allow_print_for_cancelled")):
			for enabled in (0, 1, "0", "1", None):
				with self.subTest(docstatus=docstatus, enabled=enabled):
					doc = Mock(doctype="YRP Production Order", docstatus=docstatus)
					doc.meta.is_submittable = True
					doc.has_permission.return_value = True
					with patch.object(frappe.db, "get_single_value", return_value=enabled) as settings:
						self.assertEqual(get_document_print_formats(doc), formats if enabled in (1, "1") else [])
					settings.assert_called_once_with("Print Settings", fieldname)

	def test_submitted_documents_do_not_require_draft_or_cancelled_print_settings(self):
		doc = Mock(doctype="YRP Production Order", docstatus=1)
		doc.meta.is_submittable = True
		doc.has_permission.return_value = True
		with patch.object(frappe.db, "get_single_value", return_value=0) as settings:
			self.assertEqual(get_document_print_formats(doc), [{"label": "Production Order", "format": "Essdee Production Order"}])
		settings.assert_not_called()

	def test_non_submittable_drafts_ignore_draft_print_setting(self):
		doc = Mock(doctype="YRP Stock Update", docstatus=0)
		doc.meta.is_submittable = False
		doc.has_permission.return_value = True
		with patch.object(frappe.db, "get_single_value", return_value=0) as settings:
			self.assertEqual(get_document_print_formats(doc), [{"label": "Standard Print", "format": "Standard"}])
		settings.assert_not_called()

	def test_print_permission_is_still_required(self):
		doc = Mock(doctype="YRP Production Order", docstatus=2)
		doc.has_permission.return_value = False
		with patch.object(frappe.db, "get_single_value", return_value=1) as settings:
			self.assertEqual(get_document_print_formats(doc), [])
			self.assertEqual(get_document_print_formats(None), [])
		doc.has_permission.assert_called_once_with("print")
		settings.assert_not_called()

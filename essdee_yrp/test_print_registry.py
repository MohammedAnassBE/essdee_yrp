from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.print_registry import get_document_print_formats, print_format_scope


class TestDocumentPrintFormats(TestCase):
	def setUp(self):
		db_patch = patch.object(frappe, "db", Mock())
		self.db = db_patch.start()
		self.addCleanup(db_patch.stop)
		formats_patch = patch("essdee_yrp.print_registry.get_desk_print_formats", return_value=["Standard", "Essdee Production Order"])
		self.formats = formats_patch.start()
		self.addCleanup(formats_patch.stop)
		permission_patch = patch.object(frappe, "has_permission", return_value=True)
		self.has_permission = permission_patch.start()
		self.addCleanup(permission_patch.stop)

	def test_print_settings_gate_drafts_and_cancelled_documents(self):
		formats = [{"label": name, "format": name} for name in ["Standard", "Essdee Production Order"]]
		for docstatus, fieldname in ((0, "allow_print_for_draft"), (2, "allow_print_for_cancelled")):
			for enabled in (0, 1, "0", "1", None):
				with self.subTest(docstatus=docstatus, enabled=enabled):
					doc = Mock(doctype="YRP Production Order", docstatus=docstatus)
					doc.meta.is_submittable = True
					with patch.object(self.db, "get_single_value", return_value=enabled) as settings:
						self.assertEqual(get_document_print_formats(doc), formats if enabled in (1, "1") else [])
					settings.assert_called_once_with("Print Settings", fieldname)

	def test_submitted_documents_reuse_desk_formats_without_status_gate(self):
		doc = Mock(doctype="YRP Production Order", docstatus=1)
		doc.meta.is_submittable = True
		self.assertEqual(get_document_print_formats(doc), [{"label": name, "format": name} for name in ["Standard", "Essdee Production Order"]])
		self.formats.assert_called_once_with(doc.doctype)
		self.db.get_single_value.assert_not_called()

	def test_non_submittable_drafts_ignore_draft_print_setting(self):
		doc = Mock(doctype="YRP Stock Update", docstatus=0)
		doc.meta.is_submittable = False
		self.formats.return_value = ["Standard"]
		self.assertEqual(get_document_print_formats(doc), [{"label": "Standard", "format": "Standard"}])
		self.db.get_single_value.assert_not_called()

	def test_print_permission_is_still_required(self):
		doc = Mock(doctype="YRP Production Order", docstatus=2)
		self.has_permission.return_value = False
		self.assertEqual(get_document_print_formats(doc), [])
		self.assertEqual(get_document_print_formats(None), [])
		self.has_permission.assert_called_once_with("YRP Production Order", "print", doc=doc)
		self.db.get_single_value.assert_not_called()
		self.formats.assert_not_called()


class TestPrintFormatScope(TestCase):
	def setUp(self):
		db_patch = patch.object(frappe, "db", Mock())
		db_patch.start()
		self.addCleanup(db_patch.stop)
		formats_patch = patch("essdee_yrp.print_registry.get_desk_print_formats", side_effect=lambda doctype: [f"{doctype} Format"])
		self.formats = formats_patch.start()
		self.addCleanup(formats_patch.stop)
		permission_patch = patch.object(frappe, "has_permission", return_value=True)
		self.has_permission = permission_patch.start()
		self.addCleanup(permission_patch.stop)

	def _doc(self, doctype, docstatus=1):
		doc = Mock(doctype=doctype, docstatus=docstatus)
		doc.meta.is_submittable = True
		return doc

	def test_formats_are_read_once_per_doctype_inside_scope(self):
		first, second, other = self._doc("A"), self._doc("A"), self._doc("B")
		with print_format_scope():
			results = [get_document_print_formats(doc) for doc in (first, second, other, first)]
		self.assertEqual(results[0], [{"label": "A Format", "format": "A Format"}])
		self.assertEqual(results[1], results[0])
		self.assertIsNot(results[1], results[0])
		self.assertEqual(results[2], [{"label": "B Format", "format": "B Format"}])
		self.assertEqual([call.args[0] for call in self.formats.call_args_list], ["A", "B"])
		self.assertEqual(self.has_permission.call_count, 4)

	def test_permission_and_restriction_are_checked_per_document_inside_scope(self):
		allowed, denied, draft = self._doc("A"), self._doc("A"), self._doc("A", docstatus=0)
		self.has_permission.side_effect = lambda doctype, ptype, doc: doc is not denied
		frappe.db.get_single_value.return_value = 0
		with print_format_scope():
			self.assertEqual(get_document_print_formats(allowed), [{"label": "A Format", "format": "A Format"}])
			self.assertEqual(get_document_print_formats(denied), [])
			self.assertEqual(get_document_print_formats(draft), [])

	def test_outside_scope_always_reads_and_scope_is_dropped_on_exit_and_error(self):
		doc = self._doc("A")
		get_document_print_formats(doc)
		get_document_print_formats(doc)
		self.assertEqual(self.formats.call_count, 2)
		with print_format_scope():
			with print_format_scope():
				get_document_print_formats(doc)
			get_document_print_formats(doc)
		self.assertEqual(self.formats.call_count, 3)
		self.assertIsNone(frappe.local.web_print_formats)
		with self.assertRaises(RuntimeError), print_format_scope():
			raise RuntimeError
		self.assertIsNone(frappe.local.web_print_formats)
		get_document_print_formats(doc)
		self.assertEqual(self.formats.call_count, 4)

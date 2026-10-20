from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.api.print import (
	get_print_options,
	order_print_formats,
	resolve_default_letter_head,
)


class TestPrintOrdering(TestCase):
	def test_standard_then_desk_descending_order_then_valid_default_moved_first(self):
		# Desk's meta.get_print_formats comparator reverses the name-ordered list it loads.
		rows = [{"name": "Zebra"}, {"name": "alpha"}, {"name": "Essdee DC"}, {"name": "Essdee Delivery Challan"}, {"name": "Standard"}]
		self.assertEqual(order_print_formats(rows), ["Standard", "Zebra", "Essdee Delivery Challan", "Essdee DC", "alpha"])
		self.assertEqual(order_print_formats(rows, "alpha"), ["alpha", "Standard", "Zebra", "Essdee Delivery Challan", "Essdee DC"])
		self.assertEqual(order_print_formats(rows, "Missing")[0], "Standard")
		self.assertEqual(order_print_formats(rows, "Standard")[0], "Standard")

	def test_js_disabled_and_raw_formats_are_filtered(self):
		rows = [
			{"name": "JS", "print_format_type": "JS"},
			{"name": "Disabled", "disabled": 1},
			{"name": "Disabled String", "disabled": "1"},
			{"name": "Raw", "raw_printing": 1},
			{"name": "HTML", "raw_printing": "0"},
		]
		self.assertEqual(order_print_formats(rows, "JS"), ["Standard", "HTML"])
		self.assertEqual(order_print_formats(rows, enable_raw_printing="0"), ["Standard", "HTML"])
		self.assertEqual(order_print_formats(rows, enable_raw_printing="1"), ["Standard", "Raw", "HTML"])

	def test_letter_head_uses_enabled_document_then_enabled_default_then_empty(self):
		for document, default, expected in (("Doc", "Default", "Doc"), ("Disabled", "Default", "Default"), ("", "Default", "Default"), ("", None, ""), ("Disabled", "Disabled", "")):
			with self.subTest(document=document, default=default):
				self.assertEqual(resolve_default_letter_head(["Default", "Doc"], document, default), expected)


class TestPrintOptions(TestCase):
	def setUp(self):
		self.doc = Mock(doctype="Test Doc", name="DOC-1", docstatus=1)
		self.doc.meta = SimpleNamespace(is_submittable=True)
		self.doc.get.return_value = "Doc Head"
		self.meta = SimpleNamespace(default_print_format="Zebra")
		self.db = Mock()
		self.db.get_single_value.return_value = 0
		self.db.get_value.return_value = "Default Head"
		for target, value in (("get_doc", self.doc), ("get_meta", self.meta), ("has_permission", True)):
			mock = patch.object(frappe, target, return_value=value)
			setattr(self, target, mock.start())
			self.addCleanup(mock.stop)
		db_patch = patch.object(frappe, "db", self.db)
		db_patch.start()
		self.addCleanup(db_patch.stop)
		all_patch = patch.object(frappe, "get_all", side_effect=lambda doctype, **kwargs: (
			[{"name": "Zebra"}, {"name": "Alpha"}] if doctype == "Print Format" else ["Default Head", "Doc Head"]
		))
		self.get_all = all_patch.start()
		self.addCleanup(all_patch.stop)

	def test_endpoint_requires_print_permission_and_returns_desk_options(self):
		self.assertEqual(get_print_options("Test Doc", "DOC-1"), {
			"formats": ["Zebra", "Standard", "Alpha"], "default_format": "Zebra",
			"letter_heads": ["Default Head", "Doc Head"], "default_letter_head": "Doc Head",
			"raw_formats": [],
		})
		self.get_doc.assert_called_once_with("Test Doc", "DOC-1")
		self.has_permission.assert_called_once_with("Test Doc", "print", self.doc, throw=True)
		self.get_all.assert_any_call("Print Format", filters={"doc_type": "Test Doc", "disabled": 0}, fields=["name", "print_format_type", "raw_printing", "disabled"], order_by="name asc")
		self.get_all.assert_any_call("Letter Head", filters={"disabled": 0}, pluck="name", order_by="name asc")

	def test_raw_format_metadata_only_includes_available_formats(self):
		self.meta.default_print_format = "Raw"
		self.get_all.side_effect = lambda doctype, **kwargs: (
			[{"name": "Raw", "raw_printing": "1"}, {"name": "HTML", "raw_printing": "0"},
			 {"name": "Disabled Raw", "raw_printing": 1, "disabled": 1}]
			if doctype == "Print Format" else []
		)
		self.db.get_single_value.return_value = 1
		options = get_print_options("Test Doc", "DOC-1")
		self.assertEqual(options["formats"], ["Raw", "Standard", "HTML"])
		self.assertEqual(options["raw_formats"], ["Raw"])
		self.assertEqual(options["default_format"], "Raw")
		self.db.get_single_value.return_value = 0
		options = get_print_options("Test Doc", "DOC-1")
		self.assertEqual(options["formats"], ["Standard", "HTML"])
		self.assertEqual(options["raw_formats"], [])
		self.assertEqual(options["default_format"], "Standard")

	def test_permission_denial_stops_option_queries(self):
		self.has_permission.side_effect = frappe.PermissionError
		with self.assertRaises(frappe.PermissionError):
			get_print_options("Test Doc", "DOC-1")
		self.get_all.assert_not_called()

	def test_missing_default_format_falls_back_to_standard(self):
		self.meta.default_print_format = "Missing"
		self.assertEqual(get_print_options("Test Doc", "DOC-1")["default_format"], "Standard")

	def test_default_letter_head_query_and_empty_fallback(self):
		self.doc.get.return_value = "Disabled"
		self.assertEqual(get_print_options("Test Doc", "DOC-1")["default_letter_head"], "Default Head")
		self.db.get_value.assert_called_with("Letter Head", {"disabled": 0, "is_default": 1}, "name")
		self.db.get_value.return_value = None
		self.assertEqual(get_print_options("Test Doc", "DOC-1")["default_letter_head"], "")

	def test_print_settings_block_only_submittable_drafts_and_cancelled(self):
		for status, field in ((0, "allow_print_for_draft"), (2, "allow_print_for_cancelled")):
			with self.subTest(status=status):
				self.doc.docstatus = status
				with patch.object(frappe, "throw", side_effect=frappe.ValidationError) as throw:
					with self.assertRaises(frappe.ValidationError):
						get_print_options("Test Doc", "DOC-1")
					self.assertIn("Print Settings", throw.call_args.args[0])
				self.db.get_single_value.assert_called_with("Print Settings", field)
				self.db.get_single_value.return_value = 1
				self.assertTrue(get_print_options("Test Doc", "DOC-1")["formats"])
				self.db.get_single_value.return_value = 0
		self.doc.meta.is_submittable = False
		self.assertTrue(get_print_options("Test Doc", "DOC-1")["formats"])

import json
import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from jinja2 import nodes


PRINT_CONTEXT_NAMES = {
	"doc",
	"footer",
	"lang",
	"layout",
	"letter_head",
	"meta",
	"no_letterhead",
	"print_settings",
}

DOCUMENT_RUNTIME_ATTRIBUTES = {
	"as_dict",
	"doctype",
	"docstatus",
	"get",
	"get_formatted",
	"name",
}

PRINT_ALIASES = {
	'YRP Goods Received Note': {
		"approved_by",
		"grand_total",
		"grn_date",
		"in_words",
		"show_delivery_details",
		"supplier_address_display",
		"supplier_name",
		"total_tax",
	},
	'YRP Work Order': {
		"delivery_address_details",
		"supplier_address_details",
		"work_order_calculated_items",
	},
}

LEGACY_PRINT_DOCTYPE_NAMES = {
	"Company Settings",
	"Product Brand",
	"Product Category Item",
	"Product Colour Code",
	"Product Image",
	"Product Measurement",
	"Product Sub brand",
	"Production Term Detail",
	"Terms and Condition",
	"Terms and Condition Detail",
	"Work Order",
}


class TestPrintFormatParity(IntegrationTestCase):
	def _formats(self):
		root = Path(frappe.get_app_path("essdee_yrp")) / "essdee_yrp" / "print_format"
		for path in sorted(root.glob("essdee_*/essdee_*.json")):
			yield path, json.loads(path.read_text())

	@staticmethod
	def _template_texts(data):
		if data.get("html"):
			yield data["html"]
		if data.get("format_data"):
			for row in json.loads(data["format_data"]):
				if row.get("options"):
					yield row["options"]

	def test_all_formats_are_essdee_owned(self):
		formats = list(self._formats())
		self.assertEqual(len(formats), 32)
		for path, data in formats:
			with self.subTest(format=path.parent.name):
				self.assertEqual(data["module"], "Essdee YRP")
				self.assertTrue(data["name"].startswith("Essdee "))
				self.assertEqual(data["standard"], "Yes")

	def test_jinja_helpers_are_registered(self):
		jenv = frappe.get_jenv()
		for path, data in self._formats():
			template = data.get("html") or ""
			if not template:
				continue
			with self.subTest(format=path.parent.name):
				parsed = jenv.parse(template)
				called_globals = {
					call.node.name
					for call in parsed.find_all(nodes.Call)
					if isinstance(call.node, nodes.Name)
				}
				missing = sorted(
					name
					for name in called_globals
					if name not in PRINT_CONTEXT_NAMES and name not in jenv.globals
				)
				self.assertEqual(missing, [])

	def test_templates_do_not_query_pre_namespace_doctypes(self):
		for path, data in self._formats():
			for template in self._template_texts(data):
				for old_name in LEGACY_PRINT_DOCTYPE_NAMES:
					with self.subTest(format=path.parent.name, old_name=old_name):
						self.assertIsNone(
							re.search(rf"([\"']){re.escape(old_name)}\1", template)
						)

	def test_print_doc_fields_exist_in_f16(self):
		for path, data in self._formats():
			with self.subTest(format=path.parent.name):
				meta = frappe.get_meta(data["doc_type"])
				references = set(re.findall(r"\bdoc\.([A-Za-z_][A-Za-z0-9_]*)", data.get("html") or ""))
				allowed = DOCUMENT_RUNTIME_ATTRIBUTES | PRINT_ALIASES.get(data["doc_type"], set())
				missing = sorted(
					fieldname
					for fieldname in references
					if fieldname not in allowed and not meta.get_field(fieldname)
				)
				self.assertEqual(missing, [])

	def test_purchase_order_print_adapters(self):
		from essdee_yrp.print_helpers import (
			check_key_value_in_dict_or_list_of_dict,
			get_item_size,
			get_value_with_pad,
			parse_json,
		)

		self.assertTrue(check_key_value_in_dict_or_list_of_dict("lot", [{"lot": "L1"}]))
		self.assertFalse(check_key_value_in_dict_or_list_of_dict("lot", [{"lot": ""}]))
		self.assertEqual(parse_json('[{"key": "value"}]'), [{"key": "value"}])
		self.assertEqual(get_item_size("Small", [5, 10], [30, 20, 10]), 30)
		self.assertEqual(get_item_size("A very long item", [5, 10], [30, 20, 10]), 10)
		self.assertEqual(get_value_with_pad("ABC", 5), "ABC  ")

	def test_templates_render_against_migrated_documents(self):
		from essdee_yrp.print_helpers import prepare_print_document
		if not frappe.db.exists('SD YRP Cutting Plan', "CP-2608-00006"):
			self.skipTest("Print rendering against source records runs after data migration")

		for path, data in self._formats():
			with self.subTest(format=path.parent.name):
				name = frappe.db.get_value(data["doc_type"], {}, "name", order_by="modified desc")
				self.assertTrue(name)
				doc = frappe.get_doc(data["doc_type"], name)
				prepare_print_document(doc)
				html = frappe.render_template(
					data.get("html") or "",
					{
						"doc": doc,
						"footer": "",
						"letter_head": "",
						"no_letterhead": 1,
						"print_settings": frappe._dict(),
					},
				)
				self.assertIsInstance(html, str)

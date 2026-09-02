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


class TestPrintFormatParity(IntegrationTestCase):
	def _formats(self):
		root = Path(frappe.get_app_path("essdee_yrp")) / "essdee_yrp" / "print_format"
		for path in sorted(root.glob("essdee_*/essdee_*.json")):
			yield path, json.loads(path.read_text())

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
			parse_json,
		)

		self.assertTrue(check_key_value_in_dict_or_list_of_dict("lot", [{"lot": "L1"}]))
		self.assertFalse(check_key_value_in_dict_or_list_of_dict("lot", [{"lot": ""}]))
		self.assertEqual(parse_json('[{"key": "value"}]'), [{"key": "value"}])

	def test_templates_render_against_migrated_documents(self):
		from essdee_yrp.print_helpers import prepare_print_document

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

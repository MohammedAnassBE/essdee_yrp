import json
import re
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


def _attribute_details(item, primary_attribute=""):
	return {
		"item": item,
		"attributes": ["Colour"],
		"primary_attribute": primary_attribute,
		"primary_attribute_values": ["S", "M"] if primary_attribute else [],
		"dependent_attribute": None,
		"dependent_attribute_details": {},
		"additional_parameters": [{"additional_parameter_key": "GSM", "additional_parameter_value": "180"}],
		"secondary_uom": "Kg",
	}


def _entry(item, row_index, primary_attribute=""):
	return {
		"name": item,
		"row_index": row_index,
		"primary_attribute": primary_attribute,
		"attributes": {"Colour": "Red"},
		"values": {"default": {"qty": 1, "rate": 2}},
		"schedule_date": "2026-09-20",
		"additional_parameters": "[]",
	}


class TestPurchaseOrderPrint(IntegrationTestCase):
	def _fetch(self, entries, rows, details):
		from essdee_yrp import print_helpers

		with (
			patch.object(print_helpers, "_group_items", return_value=[{"items": entries}]),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_attribute_details", side_effect=details),
		):
			return print_helpers.fetch_item_details(rows)

	def test_each_size_item_gets_its_own_table_like_mrp(self):
		entries = [_entry("Shirt", "0", "Size"), _entry("Trouser", "1", "Size"), _entry("Shirt", "2", "Size")]
		groups = self._fetch(entries, [], lambda item: _attribute_details(item, "Size"))

		self.assertEqual(
			[[row["name"] for row in group["items"]] for group in groups], [["Shirt", "Shirt"], ["Trouser"]]
		)

	def test_rows_follow_mrp_text_order_and_carry_print_fields(self):
		entries = [_entry("Tape", "2"), _entry("Tape", "10")]
		rows = [
			frappe._dict(row_index="2", schedule_date="2026-09-23", secondary_uom=None),
			frappe._dict(row_index="10", schedule_date="2026-09-21", secondary_uom=None),
			frappe._dict(row_index="10", schedule_date="2026-09-25", secondary_uom=None),
		]
		groups = self._fetch(entries, rows, _attribute_details)

		self.assertEqual(len(groups), 1)
		self.assertEqual([row["row_index"] for row in groups[0]["items"]], ["10", "2"])
		self.assertEqual([row["delivery_date"] for row in groups[0]["items"]], ["2026-09-25", "2026-09-23"])
		self.assertEqual(groups[0]["items"][0]["secondary_uom"], "Kg")
		self.assertEqual(groups[0]["additional_parameters"][0]["additional_parameter_key"], "GSM")

	def test_template_uses_purchase_order_fields(self):
		path = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "essdee_yrp"
			/ "print_format"
			/ "essdee_purchase_order"
			/ "essdee_purchase_order.json"
		)
		template = json.loads(json.loads(path.read_text())["format_data"])[-1]["options"]

		self.assertIn('doc.get_formatted("transaction_date")', template)
		self.assertIn("doc.supplier_address", template)
		self.assertNotIn("po_date", template)
		self.assertNotIn("supplier_address_display", template)
		self.assertIn("get_created_date(j.delivery_date)", template)
		self.assertNotIn("{{ j.delivery_date }}", template)

	def test_missing_schedule_date_leaves_delivery_date_blank(self):
		rows = [frappe._dict(row_index="2", schedule_date=None, secondary_uom=None)]
		entry = dict(_entry("Tape", "2"), schedule_date=None)
		groups = self._fetch([entry], rows, _attribute_details)

		self.assertEqual(groups[0]["items"][0]["delivery_date"], "")

	def test_print_dates_render_day_first(self):
		from essdee_yrp import print_helpers

		self.assertEqual(print_helpers.get_created_date("2026-10-23 14:05:09"), "23-10-2026")
		self.assertRegex(print_helpers.get_current_user_time()[1], r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")

	def test_print_formats_do_not_print_raw_iso_dates(self):
		raw_date = re.compile(r"\{\{\s*[\w.]*(?:\.|\[')\w*date'?\]?\s*\}\}")
		app = Path(frappe.get_app_path("essdee_yrp"))
		sources = [*app.glob("essdee_yrp/print_format/*/*.json"), *app.glob("templates/print_formats/*.html")]
		offenders = [f"{path.name}: {match}" for path in sources for match in raw_date.findall(path.read_text())]

		self.assertEqual(offenders, [])

	def test_migrated_order_renders_without_missing_fields(self):
		name = "PO-2627-1082"
		if not frappe.db.exists("Purchase Order", name):
			self.skipTest("Needs the migrated MRP purchase order")
		html = frappe.get_print("Purchase Order", name, "Essdee Purchase Order")

		self.assertNotIn("no such element", html)
		self.assertIn("21-09-2026", html)
		self.assertIn("TIRUPUR, Tamil Nadu - 641602", html)

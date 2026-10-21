import json
from pathlib import Path

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.overrides.purchase_invoice import EssdeePurchaseInvoice

APPS = Path(__file__).resolve().parents[2]


def _fields(path):
	return {field["fieldname"]: field for field in json.loads((APPS / path).read_text())["fields"]}


class TestPurchaseInvoicePrint(UnitTestCase):
	def test_internal_item_columns_are_hidden_in_print(self):
		yrp_item = _fields("yrp/yrp/yrp/doctype/yrp_purchase_invoice_item/yrp_purchase_invoice_item.json")
		essdee_item = _fields(
			"essdee_yrp/essdee_yrp/essdee_yrp/doctype/sd_yrp_essdee_purchase_invoice_item/sd_yrp_essdee_purchase_invoice_item.json"
		)
		for field in ("source_rate", "actual_rate", "set_combination"):
			self.assertEqual(yrp_item[field].get("print_hide"), 1, field)
		self.assertEqual(essdee_item["group_key"].get("print_hide"), 1)

	def test_custom_group_key_fields_are_hidden_in_print(self):
		custom = json.loads((APPS / "essdee_yrp/essdee_yrp/fixtures/custom_field.json").read_text())
		hidden = {row["name"]: row.get("print_hide") for row in custom}
		for name in (
			"YRP Purchase Invoice Item-essdee_group_key",
			"YRP Purchase Invoice Item-essdee_rate_weight",
			"YRP PI Work Order Billed Detail-essdee_group_key",
			"YRP Purchase Invoice-essdee_rate_table_source",
		):
			self.assertEqual(hidden[name], 1, name)

	def test_variant_rows_are_hidden_only_when_grouped_rows_exist(self):
		grouped = EssdeePurchaseInvoice({"doctype": "YRP Purchase Invoice", "essdee_items": [{"item": "X"}]})
		plain = EssdeePurchaseInvoice({"doctype": "YRP Purchase Invoice", "items": [{"item": "X"}]})
		self.assertTrue(grouped.is_print_hide("items"))
		self.assertFalse(plain.is_print_hide("items"))
		self.assertEqual(grouped.is_print_hide("supplier"), plain.is_print_hide("supplier"))

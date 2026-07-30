from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.mrp_stock_transfer import (
	_build_mrp_item_details,
	_ensure_remote_receipt,
)


class TestMrpStockTransfer(UnitTestCase):
	def test_builds_frappe_15_grouped_item_details(self):
		variant = frappe._dict(
			{
				"item": "Test Cloth",
				"attributes": [
					frappe._dict({"attribute": "Dia", "attribute_value": "24 Dia"}),
					frappe._dict({"attribute": "Colour", "attribute_value": "Grey"}),
				],
			}
		)
		row = frappe._dict(
			{
				"parent": "YRP-GRN-TEST",
				"item_variant": "Test Cloth-24 Dia-Grey",
				"quantity": 3.5,
				"rate": 130,
				"uom": "Kg",
				"lot": "LOT-1",
				"received_type": "Accepted",
			}
		)

		with (
			patch("frappe.get_cached_doc", return_value=variant),
			patch("frappe.get_cached_value", return_value="Dia"),
		):
			result = _build_mrp_item_details([row])

		self.assertEqual(len(result), 1)
		group = result[0]
		self.assertEqual(group["primary_attribute"], "Dia")
		self.assertEqual(group["primary_attribute_values"], ["24 Dia"])
		self.assertEqual(group["attributes"], ["Colour"])
		item = group["items"][0]
		self.assertEqual(item["name"], "Test Cloth")
		self.assertEqual(item["attributes"], {"Colour": "Grey"})
		self.assertEqual(item["lot"], "LOT-1")
		self.assertEqual(item["received_type"], "Accepted")
		self.assertEqual(
			item["values"]["24 Dia"],
			{
				"qty": 3.5,
				"rate": 130.0,
				"secondary_qty": 0.0,
				"secondary_uom": None,
				"set_combination": {},
			},
		)

	def test_retry_submits_an_existing_remote_draft(self):
		draft = {"name": "STE-DRAFT", "docstatus": 0, "purpose": "Material Receipt"}
		with (
			patch(
				"essdee_yrp.api.mrp_stock_transfer._remote_get",
				return_value=draft,
			) as remote_get,
			patch(
				"essdee_yrp.api.mrp_stock_transfer._submit_remote_receipt",
				return_value="STE-DRAFT",
			) as submit_remote,
		):
			name = _ensure_remote_receipt(
				{"name": "STE-DRAFT", "docstatus": 0},
				frappe._dict(),
				[],
			)

		self.assertEqual(name, "STE-DRAFT")
		remote_get.assert_called_once_with("Stock Entry", "STE-DRAFT")
		submit_remote.assert_called_once_with(draft)

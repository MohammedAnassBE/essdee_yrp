from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestLotTransfer(IntegrationTestCase):
	def test_posting_fields_require_edit_checkbox(self):
		meta = frappe.get_meta("Lot Transfer", cached=False)
		edit_control = meta.get_field("edit_posting_date_and_time")
		posting_date = meta.get_field("posting_date")
		posting_time = meta.get_field("posting_time")

		self.assertEqual(edit_control.fieldtype, "Check")
		self.assertLess(edit_control.idx, posting_date.idx)
		self.assertEqual(posting_date.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertEqual(posting_time.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertTrue(posting_date.no_copy)
		self.assertTrue(posting_time.no_copy)
		self.assertEqual(meta.get_field("items").options, "Lot Transfer Item")
		finishing_plan = meta.get_field("finishing_plan")
		self.assertEqual(finishing_plan.options, "Finishing Plan")
		self.assertTrue(finishing_plan.hidden)

		item_meta = frappe.get_meta("Lot Transfer Item", cached=False)
		self.assertEqual(item_meta.get_field("warehouse").options, "Warehouse")
		self.assertTrue(item_meta.get_field("warehouse").reqd)
		self.assertEqual(item_meta.get_field("received_type").options, "Received Type")
		self.assertTrue(item_meta.get_field("received_type").reqd)

	def test_valuation_lookup_passes_stock_dimensions_by_name(self):
		transfer = frappe.new_doc("Lot Transfer")
		transfer.posting_date = "2026-07-29"
		transfer.posting_time = "12:34:56"
		row = frappe._dict(
			{
				"idx": 1,
				"item": "_Test Lot Transfer Variant",
				"from_lot": "LOT-A",
				"to_lot": "LOT-B",
				"warehouse": "Main Warehouse",
				"received_type": "Accepted",
				"quality_grade": "A",
				"qty": 2,
				"uom": "Kg",
				"rate": 0,
			}
		)

		with (
			patch(
				"frappe.db.get_value",
				return_value="_Test Lot Transfer Item",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_disabled",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_is_stock_item",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_cancelled_item",
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.lot_transfer.lot_transfer.apply_item_uom",
				side_effect=lambda target, item_field: target.update(
					{"uom": "Kg", "stock_uom": "Kg", "conversion_factor": 1}
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.lot_transfer.lot_transfer.get_dimension_fieldnames",
				return_value=["lot", "received_type", "quality_grade"],
			),
			patch(
				"yrp.stock.utils.get_stock_balance",
				return_value=(6.67, 130),
			) as get_stock_balance,
		):
			transfer._validate_row(row)

		get_stock_balance.assert_called_once_with(
			"_Test Lot Transfer Variant",
			"Main Warehouse",
			posting_date="2026-07-29",
			posting_time="12:34:56",
			with_valuation_rate=True,
			lot="LOT-A",
			received_type="Accepted",
			quality_grade="A",
			uom="Kg",
		)
		self.assertEqual(row.rate, 130)
		self.assertEqual(row.stock_qty, 2)
		self.assertEqual(row.stock_uom_rate, 130)
		self.assertEqual(row.amount, 260)

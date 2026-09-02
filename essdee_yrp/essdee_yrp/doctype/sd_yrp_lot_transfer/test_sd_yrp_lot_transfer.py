from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestLotTransfer(IntegrationTestCase):
	def test_posting_fields_require_edit_checkbox(self):
		meta = frappe.get_meta('SD YRP Lot Transfer', cached=False)
		edit_control = meta.get_field("edit_posting_date_and_time")
		posting_date = meta.get_field("posting_date")
		posting_time = meta.get_field("posting_time")

		self.assertEqual(edit_control.fieldtype, "Check")
		self.assertLess(edit_control.idx, posting_date.idx)
		self.assertEqual(posting_date.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertEqual(posting_time.read_only_depends_on, "eval: !doc.edit_posting_date_and_time")
		self.assertTrue(posting_date.no_copy)
		self.assertTrue(posting_time.no_copy)
		self.assertEqual(meta.get_field("items").options, 'SD YRP Lot Transfer Item')
		finishing_plan = meta.get_field("finishing_plan")
		self.assertEqual(finishing_plan.options, 'SD YRP Finishing Plan')
		self.assertTrue(finishing_plan.hidden)

		item_meta = frappe.get_meta('SD YRP Lot Transfer Item', cached=False)
		self.assertEqual(item_meta.get_field("warehouse").options, 'YRP Warehouse')
		self.assertTrue(item_meta.get_field("warehouse").reqd)
		self.assertEqual(item_meta.get_field("received_type").options, 'YRP Received Type')
		self.assertTrue(item_meta.get_field("received_type").reqd)

	def test_valuation_lookup_passes_stock_dimensions_by_name(self):
		transfer = frappe.new_doc('SD YRP Lot Transfer')
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
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_disabled",
			),
			patch(
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_is_stock_item",
			),
			patch(
				"yrp.yrp.doctype.yrp_item.yrp_item.validate_cancelled_item",
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.apply_item_uom",
				side_effect=lambda target, item_field: target.update(
					{"uom": "Kg", "stock_uom": "Kg", "conversion_factor": 1}
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_dimension_fieldnames",
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
		)
		self.assertEqual(row.rate, 130)
		self.assertEqual(row.stock_qty, 2)
		self.assertEqual(row.stock_uom_rate, 130)
		self.assertEqual(row.amount, 260)

	def test_submit_persists_actual_fifo_transfer_value(self):
		transfer = frappe.new_doc('SD YRP Lot Transfer')
		transfer.name = "LT-ACTUAL-RATE"
		transfer.docstatus = 1
		transfer.posting_date = "2026-07-29"
		transfer.posting_time = "12:34:56"
		row = frappe._dict(
			doctype='SD YRP Lot Transfer Item',
			name="LT-ROW-1",
			item="_Test Lot Transfer Variant",
			from_lot="LOT-A",
			to_lot="LOT-B",
			warehouse="Main Warehouse",
			received_type="Accepted",
			quality_grade="A",
			stock_qty=4,
			stock_uom="Kg",
			stock_uom_rate=100,
			conversion_factor=2,
		)
		transfer.items = [row]

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_transfer.sd_yrp_lot_transfer.get_dimension_fieldnames",
				return_value=["lot", "received_type", "quality_grade"],
			),
			patch(
				"yrp.stock.stock_ledger.make_sl_entries",
				return_value={"LT-ACTUAL-RATE:LT-ROW-1": 125},
			) as make_entries,
			patch("frappe.db.set_value") as set_value,
		):
			transfer._update_stock_ledger()

		entries = make_entries.call_args.args[0]
		self.assertEqual(entries[0]["_transfer_role"], "outgoing")
		self.assertEqual(entries[1]["_transfer_role"], "incoming")
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		self.assertEqual(row.stock_uom_rate, 125)
		self.assertEqual(row.rate, 250)
		self.assertEqual(row.amount, 500)
		set_value.assert_called_once_with(
			'SD YRP Lot Transfer Item',
			"LT-ROW-1",
			{"stock_uom_rate": 125.0, "rate": 250.0, "amount": 500.0},
			update_modified=False,
		)

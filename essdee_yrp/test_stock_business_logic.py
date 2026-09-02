from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_stock_entry.sd_yrp_fg_stock_entry import FGStockEntry
from essdee_yrp.essdee_yrp.doctype.sd_yrp_item_conversion.sd_yrp_item_conversion import ItemConversion
from essdee_yrp.cutting.movement import apply_transaction
from essdee_yrp.essdee_yrp.doctype.sd_yrp_stock_summary import (
	sd_yrp_stock_summary as stock_summary,
)
from essdee_yrp.stock_dimensions import ensure_essdee_stock_dimension_fields


class _StockEntryStub:
	def __init__(self):
		self.items = []

	def append(self, fieldname, values):
		assert fieldname == "items"
		self.items.append(frappe._dict(values))


class TestStockBusinessLogic(IntegrationTestCase):
	def test_recut_valid_issue_submit_and_cancel(self):
		plan = frappe.get_doc('SD YRP Cutting Plan', "CP-2606-00038")
		cloth_row = next(
			row
			for row in plan.cutting_plan_cloth_details
			if row.colour == "White Red Stripes"
			and row.cloth_type == "MAIN FABRIC"
			and row.dia == "60 Dia"
		)
		original_used_weight = cloth_row.used_weight
		doc = frappe.get_doc(
			{
				"doctype": 'SD YRP Recut and Print Panel',
				"cutting_plan": plan.name,
				"work_order": plan.work_order,
				"lot": plan.lot,
				"item": plan.item,
				"supplier": "S-0164",
				"type": "Recut",
				"posting_date": "2026-08-18",
				"posting_time": "12:00:00",
				"recut_and_print_panel_details": [
					{
						"cloth_type": "MAIN FABRIC",
						"colour": "White Red Stripes",
						"dia": "60 Dia",
						"shade": "A",
						"weight": 0.001,
						"panel_count": 1,
						"no_of_rolls": 1,
					}
				],
			}
		)
		doc.insert()
		self.assertEqual(
			doc.recut_and_print_panel_details[0].item_variant,
			"FCC - 95%Poly,5%Elast Snit Jersey Fabric-White Red Stripes-60 Dia",
		)
		self.assertGreater(doc.recut_and_print_panel_details[0].rate, 0)
		doc.submit()

		plan.reload()
		cloth_row = next(
			row
			for row in plan.cutting_plan_cloth_details
			if row.colour == "White Red Stripes"
			and row.cloth_type == "MAIN FABRIC"
			and row.dia == "60 Dia"
		)
		self.assertAlmostEqual(cloth_row.used_weight, original_used_weight + 0.001)
		self.assertEqual(
			frappe.db.count(
				'YRP Stock Ledger Entry',
				{
					"voucher_type": 'SD YRP Recut and Print Panel',
					"voucher_no": doc.name,
					"is_cancelled": 0,
				},
			),
			1,
		)

		doc.cancel()
		plan.reload()
		cloth_row = next(
			row
			for row in plan.cutting_plan_cloth_details
			if row.colour == "White Red Stripes"
			and row.cloth_type == "MAIN FABRIC"
			and row.dia == "60 Dia"
		)
		self.assertAlmostEqual(cloth_row.used_weight, original_used_weight)
		self.assertEqual(doc.docstatus, 2)

	def test_fg_stock_entry_valid_receipt_submit_and_cancel(self):
		doc = frappe.get_doc(
			{
				"doctype": 'SD YRP FG Stock Entry',
				"warehouse": "S-0165",
				"posting_date": "2026-08-18",
				"posting_time": "10:30:00",
				"consumed": 0,
				"comments": "Rollback-only runtime acceptance",
				"items": [
					{
						"item_variant": "Fusing Sticker-REGULAR-White-Move Air",
						"qty": 1,
						"uom": "Nos",
						"rate": 0.26,
						"lot": "Open Lot",
						"received_type": "Accepted",
					}
				],
			}
		)
		doc.insert()
		doc.submit()

		linked = frappe.get_doc('YRP Stock Entry', doc.yrp_stock_entry)
		self.assertEqual(linked.docstatus, 1)
		self.assertEqual(linked.against, 'SD YRP FG Stock Entry')
		self.assertEqual(linked.against_id, doc.name)
		self.assertEqual(linked.items[0].lot, "Open Lot")
		self.assertEqual(linked.items[0].received_type, "Accepted")

		doc.cancel()
		linked.reload()
		self.assertEqual(doc.docstatus, 2)
		self.assertEqual(linked.docstatus, 2)

	def test_item_conversion_valid_transfer_submit_and_cancel(self):
		variant = "Fusing Sticker-REGULAR-White-Move Air"
		detail = {
			"item": variant,
			"qty": 1,
			"uom": "Nos",
			"lot": "Open Lot",
			"received_type": "Accepted",
		}
		doc = frappe.get_doc(
			{
				"doctype": 'SD YRP Item Conversion',
				"naming_series": "IC-.YYYY.-",
				"warehouse": "S-0165",
				"from_item": "Fusing Sticker",
				"to_item": "Fusing Sticker",
				"posting_date": "2026-08-18",
				"posting_time": "11:00:00",
				"from_items": [detail],
				"to_items": [detail],
			}
		)
		doc.insert()
		doc.submit()

		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.from_total_amount, doc.to_total_amount)
		self.assertEqual(
			frappe.db.count(
				'YRP Stock Ledger Entry',
				{"voucher_type": 'SD YRP Item Conversion', "voucher_no": doc.name},
			),
			2,
		)

		doc.cancel()
		self.assertEqual(doc.docstatus, 2)

	def test_unrelated_stock_entry_does_not_enter_cut_bundle_tracking(self):
		doc = frappe._dict(
			doctype='YRP Stock Entry',
			name="STE-RUNTIME-TEST",
			against='SD YRP Finishing Plan Dispatch',
			against_id="FPD-RUNTIME-TEST",
			cut_panel_movement=None,
			allow_non_bundle=0,
		)
		with patch("essdee_yrp.cutting.movement.frappe.get_meta") as get_meta:
			apply_transaction(doc, cancelled=True)
		get_meta.assert_not_called()

	def test_essdee_rows_follow_configured_dimensions(self):
		dimensions = [
			{
				"fieldname": "lot",
				"dimension_doctype": 'SD YRP Lot',
				"label": "Lot",
				"mandatory": 1,
			},
			{
				"fieldname": "quality_grade",
				"dimension_doctype": "Quality Grade",
				"label": "Quality Grade",
				"mandatory": 0,
			},
		]
		meta = MagicMock()
		meta.get_field.return_value = None
		with (
			patch("essdee_yrp.stock_dimensions.get_stock_dimensions", return_value=dimensions),
			patch("essdee_yrp.stock_dimensions.frappe.db.exists", return_value=True),
			patch("essdee_yrp.stock_dimensions.frappe.get_meta", return_value=meta),
			patch("essdee_yrp.stock_dimensions.frappe.get_all", return_value=[]),
			patch("essdee_yrp.stock_dimensions.create_custom_fields") as create_fields,
		):
			ensure_essdee_stock_dimension_fields()

		fields = create_fields.call_args.args[0]
		self.assertEqual(
			{row["fieldname"] for row in fields['SD YRP FG Stock Entry Detail']},
			{"lot", "quality_grade"},
		)
		self.assertEqual(
			{row["fieldname"] for row in fields['SD YRP Item Conversion Detail']},
			{"lot", "quality_grade"},
		)
		self.assertEqual(
			{row["fieldname"] for row in fields['SD YRP Lot Transfer Item']},
			{"quality_grade"},
		)

	def test_fg_stock_entry_builds_base_stock_entry_with_dimensions(self):
		doc = frappe.new_doc('SD YRP FG Stock Entry')
		doc.name = "FG-TEST-1"
		doc.warehouse = "Main Warehouse"
		doc.posting_date = "2026-08-18"
		doc.posting_time = "10:30:00"
		doc.consumed = 0
		doc.comments = "Receipt"
		doc.items = [
			frappe._dict(
				item_variant="VAR-1",
				qty=4,
				uom="Box",
				conversion_factor=5,
				rate=100,
				lot="LOT-1",
				quality_grade="A",
			)
		]
		stock_entry = _StockEntryStub()
		meta = MagicMock()
		meta.get_field.return_value = True
		with (
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_stock_entry.sd_yrp_fg_stock_entry.frappe.has_permission"),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_stock_entry.sd_yrp_fg_stock_entry.frappe.new_doc", return_value=stock_entry),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_stock_entry.sd_yrp_fg_stock_entry.frappe.get_meta", return_value=meta),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_stock_entry.sd_yrp_fg_stock_entry.get_dimension_fieldnames", return_value=["lot", "quality_grade"]),
		):
			result = FGStockEntry._make_yrp_stock_entry(doc)

		self.assertIs(result, stock_entry)
		self.assertEqual(stock_entry.purpose, "Material Receipt")
		self.assertEqual(stock_entry.to_warehouse, "Main Warehouse")
		self.assertEqual(stock_entry.against, 'SD YRP FG Stock Entry')
		self.assertEqual(stock_entry.items[0].rate, 20)
		self.assertEqual(stock_entry.items[0].lot, "LOT-1")
		self.assertEqual(stock_entry.items[0].quality_grade, "A")

	def test_item_conversion_preserves_total_value_when_quantities_differ(self):
		doc = frappe.new_doc('SD YRP Item Conversion')
		doc.name = "IC-TEST-1"
		doc.warehouse = "Main Warehouse"
		doc.posting_date = "2026-08-18"
		doc.posting_time = "11:00:00"
		doc.from_items = [
			frappe._dict(
				item="FROM-VAR", stock_qty=2, stock_uom="Kg", stock_uom_rate=40,
				name="FROM-ROW", doctype='SD YRP Item Conversion Detail',
				conversion_factor=1, lot="LOT-1", quality_grade="A", remarks="from",
			)
		]
		doc.to_items = [
			frappe._dict(
				item="TO-VAR", stock_qty=4, stock_uom="Kg", stock_uom_rate=20,
				name="TO-ROW", doctype='SD YRP Item Conversion Detail',
				conversion_factor=1, lot="LOT-2", quality_grade="A", remarks="to",
			)
		]
		def post_entries(entries, **kwargs):
			key = entries[0].get("_result_key")
			if key == "item-conversion-input":
				return {
					"entries": {key: {"sle": "SLE-IN", "rate": 50, "value": 100}}
				}
			return {
				"entries": {key: {"sle": "SLE-OUT", "rate": 25, "value": 100}}
			}
		with (
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_item_conversion.sd_yrp_item_conversion.get_dimension_fieldnames", return_value=["lot", "quality_grade"]),
			patch("yrp.stock.stock_ledger.make_sl_entries", side_effect=post_entries) as make_entries,
			patch.object(frappe.db, "set_value"),
			patch(
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.register_production_links"
			) as register_links,
		):
			ItemConversion.update_stock_ledger(doc)

		self.assertEqual(make_entries.call_count, 2)
		outgoing = make_entries.call_args_list[0].args[0][0]
		incoming = make_entries.call_args_list[1].args[0][0]
		self.assertEqual((outgoing.qty, incoming.qty), (-2, 4))
		self.assertEqual(incoming.rate, 25)
		self.assertEqual(doc.from_items[0].amount, 100)
		self.assertEqual(doc.to_items[0].amount, 100)
		self.assertEqual(doc.from_total_amount, doc.to_total_amount)
		self.assertEqual(incoming.quality_grade, "A")
		register_links.assert_called_once()

	def test_stock_summary_delegates_to_dimension_aware_report(self):
		rows = [{"item": "VAR-1", "lot": "LOT-1", "bal_qty": 5}]
		with (
			patch.object(stock_summary, "_check_stock_read_permission"),
			patch.object(stock_summary, "get_dimension_fieldnames", return_value=["lot", "received_type"]),
			patch.object(stock_summary, "stock_balance", return_value=([], rows)) as report,
		):
			result = stock_summary.get_stock_summary(
				lot=[{"lot": "LOT-1"}], item="ITEM-1", warehouse="Main Warehouse",
				received_type="Accepted",
			)

		self.assertEqual(result, rows)
		filters = report.call_args.args[0]
		self.assertEqual(filters.parent_item, "ITEM-1")
		self.assertEqual(filters.warehouse, "Main Warehouse")
		self.assertEqual(filters.received_type, "Accepted")
		self.assertEqual(filters.lot, "LOT-1")

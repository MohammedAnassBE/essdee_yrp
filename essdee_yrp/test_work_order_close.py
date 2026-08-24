from contextlib import ExitStack
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.work_order_close import close_work_order


def _record_excess_usage(_doc, plan):
	plan["audit_row"] = frappe._dict(name=f"AUDIT-{plan['deliverable'].name}")
	return plan["audit_row"]


def _db_get_value(real_get_value, doctype, *args, **kwargs):
	if doctype == "Stock Ledger Entry":
		return frappe._dict(item="OUTPUT-ITEM", qty=10, rate=30)
	return real_get_value(doctype, *args, **kwargs)


def _work_order(rows):
	doc = frappe._dict(
		name="WO-TEST",
		doctype="Work Order",
		docstatus=1,
		open_status="Open",
		supplier="SUPPLIER-1",
		deliverables=rows,
	)
	doc.save = Mock()
	return doc


def _close_patches(doc, *, balance=(20, 20)):
	real_get_value = frappe.db.get_value
	return (
		patch.object(frappe.db, "sql"),
		patch("essdee_yrp.work_order_close.frappe.get_doc", return_value=doc),
		patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
		patch("essdee_yrp.work_order_close._validate_wo_close"),
		patch(
			"yrp.yrp.doctype.delivery_challan.delivery_challan._get_warehouse_for_supplier",
			return_value="SUPPLIER-WH",
		),
		patch(
			"essdee_yrp.work_order_close._stock_dimension_values",
			return_value={"received_type": "Accepted"},
		),
		patch("yrp.stock.utils.get_stock_balance", return_value=balance),
		patch("yrp.stock.stock_ledger.enqueue_voucher_repost"),
		patch("yrp.stock.utils.close_voucher_reservations"),
		patch(
			"essdee_yrp.work_order_close._get_excess_output_allocations",
			return_value=[
				{"output_receipt_sle": "SLE-OUTPUT", "allocation_weight": 1}
			],
		),
		patch(
			"essdee_yrp.work_order_close._record_excess_usage",
			side_effect=_record_excess_usage,
		),
		patch.object(
			frappe.db,
			"get_value",
			side_effect=lambda doctype, *args, **kwargs: _db_get_value(
				real_get_value, doctype, *args, **kwargs
			),
		),
		patch(
			"yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.register_production_links"
		),
		patch(
			"yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.create_adjustment"
		),
		patch("essdee_yrp.work_order_close.nowdate", return_value="2026-08-11"),
		patch("essdee_yrp.work_order_close.nowtime", return_value="10:00:00"),
	)


class TestEssdeeWorkOrderClose(UnitTestCase):
	def test_close_fails_in_full_before_posting_when_duplicate_rows_exceed_stock(self):
		rows = [
			frappe._dict(
				name="DEL-1",
				idx=1,
				item_variant="YARN-BLUE",
				qty=8,
				pending_quantity=0,
				stock_update=0,
				uom="Kg",
				valuation_rate=20,
				rate=0,
			),
			frappe._dict(
				name="DEL-2",
				idx=2,
				item_variant="YARN-BLUE",
				qty=8,
				pending_quantity=0,
				stock_update=0,
				uom="Kg",
				valuation_rate=20,
				rate=0,
			),
		]
		doc = _work_order(rows)
		with ExitStack() as stack:
			for context in _close_patches(doc, balance=(10, 20)):
				stack.enter_context(context)
			stack.enter_context(patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Kg"},
			))
			make_sl_entries = stack.enter_context(
				patch("yrp.stock.stock_ledger.make_sl_entries")
			)
			with self.assertRaisesRegex(frappe.ValidationError, "requires 8.*only 2"):
				close_work_order("WO-TEST")

		make_sl_entries.assert_not_called()
		self.assertEqual(rows[0].stock_update, 0)
		self.assertEqual(rows[1].stock_update, 0)

	def test_close_uses_stock_uom_and_actual_fifo_value_for_adjustment(self):
		row = frappe._dict(
			name="DEL-1",
			idx=1,
			item_variant="YARN-CONE",
			qty=8,
			pending_quantity=0,
			stock_update=0,
			uom="Cone",
			valuation_rate=18,
			rate=0,
		)
		doc = _work_order([row])
		with ExitStack() as stack:
			for context in _close_patches(doc):
				stack.enter_context(context)
			stack.enter_context(patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 2, "stock_uom": "Kg"},
			))
			make_sl_entries = stack.enter_context(
				patch("yrp.stock.stock_ledger.make_sl_entries")
			)
			create_adjustment = stack.enter_context(patch(
				"yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.create_adjustment"
			))
			make_sl_entries.return_value = {
				"entries": {
					"wo-close:DEL-1": {
						"sle": "SLE-EXCESS-1",
						"qty": 16,
						"value": 352,
						"rate": 22,
					}
				}
			}
			result = close_work_order("WO-TEST")

		entry = make_sl_entries.call_args.args[0][0]
		self.assertEqual(entry["qty"], -16)
		self.assertEqual(entry["uom"], "Kg")
		self.assertTrue(make_sl_entries.call_args.kwargs["return_details"])
		self.assertTrue(make_sl_entries.call_args.kwargs["force_inline"])
		self.assertEqual(row.stock_update, 8)
		self.assertEqual(result, {"status": "Close", "deducted_qty": 16.0})
		allocation = create_adjustment.call_args.kwargs["allocations"][0]
		self.assertEqual(allocation["source_sle"], "SLE-EXCESS-1")
		self.assertEqual(allocation["difference"], 352)

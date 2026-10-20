from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.work_order_close import (
	_get_excess_output_allocations,
	_get_owned_output_sle,
	close_work_order,
)


class TestWorkOrderClose(UnitTestCase):
	def _manager_close_doc(self):
		row = frappe._dict(
			name="WOD-1",
			idx=1,
			item_variant="INPUT-VARIANT",
			uom="Piece",
			qty=5000,
			pending_quantity=-500,
			stock_update=5200,
			valuation_rate=0,
			rate=0,
		)
		doc = frappe._dict(
			name="WO-1",
			doctype="YRP Work Order",
			docstatus=1,
			open_status="Open",
			supplier="SUPPLIER-1",
			deliverables=[row],
			sd_close_reason=None,
		)
		doc.save = MagicMock()
		doc.check_permission = MagicMock()
		return doc, row

	def test_selected_reason_is_stored_only_in_essdee_fields(self):
		doc = frappe._dict(
			name="WO-1",
			docstatus=1,
			open_status="Open",
			sd_close_reason=None,
		)
		doc.save = MagicMock()
		doc.check_permission = MagicMock()
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=False),
			patch("essdee_yrp.work_order_close._apply_close_details") as apply_details,
			patch.object(frappe, "msgprint"),
		):
			result = close_work_order(
				"WO-1",
				sd_close_reason="Others",
				close_other_reason="Production stopped",
				close_remarks="Reviewed",
			)

		apply_details.assert_called_once_with(
			doc,
			"Close Request",
			None,
			"Production stopped",
			"Reviewed",
		)
		self.assertEqual(doc.sd_close_reason, "Others")
		doc.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result, {"status": "Close Request", "deducted_qty": 0.0})

	def test_base_desk_close_reason_argument_is_an_input_alias(self):
		doc = frappe._dict(
			name="WO-1",
			docstatus=1,
			open_status="Open",
			sd_close_reason=None,
		)
		doc.save = MagicMock()
		doc.check_permission = MagicMock()
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=False),
			patch("essdee_yrp.work_order_close._apply_close_details"),
			patch.object(frappe, "msgprint"),
		):
			close_work_order("WO-1", close_reason="Sewing Shortage")

		self.assertEqual(doc.sd_close_reason, "Sewing Shortage")

	def test_invalid_fixed_reason_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			close_work_order("WO-1", sd_close_reason="Arbitrary free text")

	def test_close_requires_authoritative_work_order_write_permission(self):
		doc = frappe._dict(name="WO-1", docstatus=1, open_status="Open")
		doc.check_permission = MagicMock(side_effect=frappe.PermissionError("Not permitted"))
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager") as manager,
		):
			with self.assertRaises(frappe.PermissionError):
				close_work_order("WO-1", sd_close_reason="NA")

		manager.assert_not_called()

	def test_manager_close_reduces_unreturned_excess_at_actual_fifo_value(self):
		doc, row = self._manager_close_doc()
		ledger_result = {
			"entries": {
				"wo-close:WOD-1": {
					"sle": "SLE-EXCESS-IN",
					"rate": 13,
					"value": 3900,
				}
			}
		}

		def record_usage(_doc, plan):
			plan["audit_row"] = frappe._dict(name="WO-EXCESS-1")

		with (
			patch.object(frappe.db, "sql") as sql,
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(
				frappe.db,
				"get_value",
				return_value=frappe._dict(item="OUTPUT-VARIANT", qty=400, rate=20),
			),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
			patch("essdee_yrp.work_order_close._validate_wo_close"),
			patch("essdee_yrp.work_order_close._apply_close_details"),
			patch(
				"essdee_yrp.work_order_close._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"essdee_yrp.work_order_close._get_excess_output_allocations",
				return_value=[
					{
						"output_receipt_sle": "SLE-OUTPUT-1",
						"output_voucher": "GRN-1",
						"output_detail": "GRN-ITEM-1",
						"output_item": "OUTPUT-VARIANT",
						"allocation_weight": 2,
					}
				],
			),
			patch(
				"essdee_yrp.work_order_close._record_excess_usage",
				side_effect=record_usage,
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="WH-1",
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Piece"},
			),
			patch("yrp.stock.utils.get_stock_balance", return_value=(300, 12)),
			patch(
				"yrp.stock.stock_ledger.make_sl_entries",
				return_value=ledger_result,
			) as make_entries,
			patch("yrp.stock.stock_ledger.enqueue_voucher_repost") as enqueue_repost,
			patch("yrp.stock.utils.close_voucher_reservations") as close_reservations,
			patch(
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.register_production_links"
			) as register_links,
			patch(
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.create_adjustment"
			) as create_adjustment,
			patch("essdee_yrp.work_order_close.nowdate", return_value="2026-08-26"),
			patch("essdee_yrp.work_order_close.nowtime", return_value="17:30:00"),
		):
			result = close_work_order("WO-1", sd_close_reason="Sewing Shortage")

		self.assertIn("FOR UPDATE", sql.call_args.args[0])
		posted = make_entries.call_args.args[0]
		self.assertEqual(len(posted), 1)
		self.assertEqual(posted[0]["qty"], -300)
		self.assertEqual(posted[0]["outgoing_rate"], 12)
		self.assertTrue(make_entries.call_args.kwargs["return_details"])
		self.assertTrue(make_entries.call_args.kwargs["force_inline"])
		self.assertEqual(row.stock_update, 5500)
		self.assertEqual(result, {"status": "Close", "deducted_qty": 300.0})
		doc.save.assert_called_once_with(ignore_permissions=True)
		close_reservations.assert_called_once_with("YRP Work Order", "WO-1")
		enqueue_repost.assert_called_once()
		self.assertEqual(
			register_links.call_args.args[2][0]["consumption_sle"],
			"SLE-EXCESS-IN",
		)
		allocation = create_adjustment.call_args.kwargs["allocations"][0]
		self.assertEqual(allocation["target_sle"], "SLE-OUTPUT-1")
		self.assertEqual(allocation["difference"], 3900)
		self.assertEqual(allocation["new_rate"], 29.75)

	def test_manager_close_fails_instead_of_clipping_unavailable_excess(self):
		doc, _row = self._manager_close_doc()
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
			patch("essdee_yrp.work_order_close._validate_wo_close"),
			patch(
				"essdee_yrp.work_order_close._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="WH-1",
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Piece"},
			),
			patch("yrp.stock.utils.get_stock_balance", return_value=(1, 12)),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
			patch("essdee_yrp.work_order_close.nowdate", return_value="2026-08-26"),
			patch("essdee_yrp.work_order_close.nowtime", return_value="17:30:00"),
		):
			with self.assertRaises(frappe.ValidationError):
				close_work_order("WO-1", sd_close_reason="Sewing Shortage")

		make_entries.assert_not_called()
		doc.save.assert_not_called()

	def test_unconsumed_row_of_a_mapped_work_order_has_no_output_to_carry_value(self):
		work_order = frappe._dict(name="WO-1")
		deliverable = frappe._dict(name="WOD-UNSEWN", idx=4)
		dimensions = {"lot": "LOT-1", "received_type": "Accepted"}
		with (
			patch.object(frappe.db, "sql", return_value=[]),
			patch("essdee_yrp.work_order_close._has_mapped_output_lineage", return_value=True),
		):
			self.assertEqual(_get_excess_output_allocations(work_order, deliverable, dimensions), [])

		with (
			patch.object(frappe.db, "sql", return_value=[]),
			patch("essdee_yrp.work_order_close._has_mapped_output_lineage", return_value=False),
			self.assertRaisesRegex(frappe.ValidationError, "Historical ambiguous lineage"),
		):
			_get_excess_output_allocations(work_order, deliverable, dimensions)

		mismatched = frappe._dict(
			output_receipt_sle="SLE-1",
			output_voucher="GRN-1",
			output_detail="GRN-ITEM-1",
			output_item="OUT-1",
			stock_qty=5,
			stock_dimensions='{"lot": "LOT-2", "received_type": "Accepted"}',
		)
		with (
			patch.object(frappe.db, "sql", return_value=[mismatched]),
			patch("essdee_yrp.work_order_close._has_mapped_output_lineage", return_value=True),
			self.assertRaisesRegex(frappe.ValidationError, "matching Stock Dimensions"),
		):
			_get_excess_output_allocations(work_order, deliverable, dimensions)

	def test_close_consumes_unsewn_input_without_a_valuation_allocation(self):
		doc, row = self._manager_close_doc()
		ledger_result = {"entries": {"wo-close:WOD-1": {"sle": "SLE-UNSEWN", "rate": 13, "value": 3900}}}

		def record_usage(_doc, plan):
			plan["audit_row"] = frappe._dict(name="WO-EXCESS-1")

		with ExitStack() as stack:
			for target, kwargs in (
				("essdee_yrp.work_order_close._is_wo_close_manager", {"return_value": True}),
				("essdee_yrp.work_order_close._validate_wo_close", {}),
				("essdee_yrp.work_order_close._apply_close_details", {}),
				(
					"essdee_yrp.work_order_close._stock_dimension_values",
					{"return_value": {"lot": "LOT-1", "received_type": "Accepted"}},
				),
				("essdee_yrp.work_order_close._get_excess_output_allocations", {"return_value": []}),
				("essdee_yrp.work_order_close._record_excess_usage", {"side_effect": record_usage}),
				(
					"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
					{"return_value": "WH-1"},
				),
				(
					"yrp.stock.utils.get_conversion_factor",
					{"return_value": {"conversion_factor": 1, "stock_uom": "Piece"}},
				),
				("yrp.stock.utils.get_stock_balance", {"return_value": (300, 12)}),
				("yrp.stock.stock_ledger.enqueue_voucher_repost", {}),
				("yrp.stock.utils.close_voucher_reservations", {}),
				("essdee_yrp.work_order_close.nowdate", {"return_value": "2026-08-26"}),
				("essdee_yrp.work_order_close.nowtime", {"return_value": "17:30:00"}),
			):
				stack.enter_context(patch(target, **kwargs))
			stack.enter_context(patch.object(frappe.db, "sql"))
			stack.enter_context(patch.object(frappe, "get_doc", return_value=doc))
			make_entries = stack.enter_context(
				patch("yrp.stock.stock_ledger.make_sl_entries", return_value=ledger_result)
			)
			svc = "yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment"
			register_links = stack.enter_context(patch(f"{svc}.register_production_links"))
			create_adjustment = stack.enter_context(patch(f"{svc}.create_adjustment"))
			result = close_work_order("WO-1", sd_close_reason="Sewing Shortage")

		self.assertEqual(make_entries.call_args.args[0][0]["qty"], -300)
		self.assertEqual(row.stock_update, 5500)
		self.assertEqual(result, {"status": "Close", "deducted_qty": 300.0})
		self.assertEqual(register_links.call_args.args[2], [])
		self.assertEqual(create_adjustment.call_args.kwargs["allocations"], [])

	def test_close_leaves_pieces_the_packing_unit_holds_as_another_stage(self):
		doc, row = self._manager_close_doc()
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
			patch("essdee_yrp.work_order_close._validate_wo_close"),
			patch("essdee_yrp.work_order_close._apply_close_details"),
			patch(
				"essdee_yrp.work_order_close.get_job_worker_stock_variant",
				return_value="INPUT-VARIANT-LOOSE-PIECE",
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="WH-1",
			),
			patch("yrp.stock.utils.get_stock_balance") as get_balance,
			patch("yrp.stock.stock_ledger.make_sl_entries", return_value={"entries": {}}) as make_entries,
			patch("essdee_yrp.work_order_close.nowdate", return_value="2026-08-26"),
			patch("essdee_yrp.work_order_close.nowtime", return_value="17:30:00"),
			patch("yrp.stock.stock_ledger.enqueue_voucher_repost"),
			patch("yrp.stock.utils.close_voucher_reservations"),
			patch(
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.register_production_links"
			),
			patch(
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.create_adjustment"
			),
		):
			result = close_work_order("WO-1", sd_close_reason="Sewing Shortage")

		get_balance.assert_not_called()
		self.assertEqual(make_entries.call_args.args[0], [])
		self.assertEqual(row.stock_update, 5200)
		self.assertEqual(result, {"status": "Close", "deducted_qty": 0})

	def test_output_sle_must_be_an_active_receipt_owned_by_mapped_grn(self):
		output = {
			"output_receipt_sle": "SLE-WRONG",
			"output_voucher": "GRN-1",
			"output_detail": "GRN-ITEM-1",
			"output_item": "OUTPUT-VARIANT",
		}
		with patch.object(frappe.db, "get_value", return_value=None) as get_value:
			with self.assertRaisesRegex(frappe.ValidationError, "active owned GRN receipt"):
				_get_owned_output_sle(output)

		filters = get_value.call_args.args[1]
		self.assertEqual(filters["voucher_type"], "YRP Goods Received Note")
		self.assertEqual(filters["voucher_no"], "GRN-1")
		self.assertEqual(filters["voucher_detail_no"], "GRN-ITEM-1")
		self.assertEqual(filters["item"], "OUTPUT-VARIANT")
		self.assertEqual(filters["is_cancelled"], 0)

	def test_repeated_close_with_no_excess_is_a_read_only_success(self):
		doc = frappe._dict(
			name="WO-CLOSED",
			docstatus=1,
			open_status="Close",
			deliverables=[],
		)
		doc.check_permission = MagicMock()

		def sql(query, *args, **kwargs):
			return [[0]] if "COALESCE(SUM(qty)" in query else []

		with (
			patch.object(frappe.db, "sql", side_effect=sql),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
		):
			result = close_work_order("WO-CLOSED", sd_close_reason="NA")

		self.assertEqual(result, {"status": "Close", "deducted_qty": 0.0})
		make_entries.assert_not_called()

	def test_manager_close_propagates_stock_period_rejection_before_save(self):
		doc, _row = self._manager_close_doc()
		with (
			patch.object(frappe.db, "sql"),
			patch.object(frappe, "get_doc", return_value=doc),
			patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
			patch("essdee_yrp.work_order_close._validate_wo_close"),
			patch(
				"essdee_yrp.work_order_close._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"essdee_yrp.work_order_close._get_excess_output_allocations",
				return_value=[
					{
						"output_receipt_sle": "SLE-OUTPUT-1",
						"output_voucher": "GRN-1",
						"output_detail": "GRN-ITEM-1",
						"output_item": "OUTPUT-VARIANT",
						"allocation_weight": 2,
					}
				],
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="WH-1",
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Piece"},
			),
			patch("yrp.stock.utils.get_stock_balance", return_value=(300, 12)),
			patch(
				"yrp.stock.stock_ledger.make_sl_entries",
				side_effect=frappe.ValidationError("Stock valuation period is closed"),
			),
			patch("essdee_yrp.work_order_close.nowdate", return_value="2026-08-26"),
			patch("essdee_yrp.work_order_close.nowtime", return_value="17:30:00"),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "period is closed"):
				close_work_order("WO-1", sd_close_reason="Sewing Shortage")

		doc.save.assert_not_called()


def _record_excess_usage(_doc, plan):
	plan["audit_row"] = frappe._dict(name=f"AUDIT-{plan['deliverable'].name}")
	return plan["audit_row"]


def _db_get_value(real_get_value, doctype, *args, **kwargs):
	if doctype == "YRP Stock Ledger Entry":
		return frappe._dict(item="OUTPUT-ITEM", qty=10, rate=30)
	return real_get_value(doctype, *args, **kwargs)


def _work_order(rows):
	doc = frappe._dict(
		name="WO-TEST",
		doctype="YRP Work Order",
		docstatus=1,
		open_status="Open",
		supplier="SUPPLIER-1",
		deliverables=rows,
	)
	doc.save = MagicMock()
	doc.check_permission = MagicMock()
	return doc


def _close_patches(doc, *, balance=(20, 20)):
	real_get_value = frappe.db.get_value
	return (
		patch.object(frappe.db, "sql"),
		patch("essdee_yrp.work_order_close.frappe.get_doc", return_value=doc),
		patch("essdee_yrp.work_order_close._is_wo_close_manager", return_value=True),
		patch("essdee_yrp.work_order_close._validate_wo_close"),
		patch("essdee_yrp.work_order_close._apply_close_details"),
		patch(
			"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
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
				{"output_receipt_sle": "SLE-OUTPUT", "output_voucher": "GRN-1",
				 "output_detail": "GRNI-1", "output_item": "OUTPUT-ITEM", "allocation_weight": 1}
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
			"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.register_production_links"
		),
		patch(
			"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.create_adjustment"
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
				close_work_order("WO-TEST", sd_close_reason="NA")

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
				"yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment.create_adjustment"
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
			result = close_work_order("WO-TEST", sd_close_reason="NA")

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

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from yrp.yrp.doctype.yrp_purchase_invoice import yrp_purchase_invoice as purchase_invoice

from essdee_yrp.accounts import purchase_invoice_workspace
from essdee_yrp.cut_panel_store import movement_workspace, report_workspace
from essdee_yrp.cutting import movement
from essdee_yrp.erp_purchase_invoice import _create_local_erp_invoice, _validate_supplier_invoice_number
from essdee_yrp.fabric_store.documents import work_order
from essdee_yrp.finishing import grn
from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote
from essdee_yrp.sewing import plan


class TestWorkOrderCloseDetails(TestCase):
	def test_close_context_batches_children_of_permission_filtered_recuts(self):
		doc = MagicMock(name="WO-1")
		doc.name = "WO-1"
		doc.production_detail = "IPD-1"
		summary = {"item_detail": [{"items": [{"total_delivered": 12, "total_received": 10}]}]}
		parents = [frappe._dict(name=name) for name in ("RECUT-2", "RECUT-1", "RECUT-EMPTY")]
		children = [
			frappe._dict(parent="RECUT-1", item_variant="VARIANT-1", quantity=2, idx=1),
			frappe._dict(parent="RECUT-1", item_variant="VARIANT-2", quantity=3, idx=2),
			frappe._dict(parent="RECUT-2", item_variant="VARIANT-3", quantity=4, idx=1),
		]
		with (
			patch.object(work_order, "_get_work_order", return_value=doc),
			patch.object(work_order, "assert_expected_modified"),
			patch.object(work_order, "_target_read_permission", return_value=False),
			patch.object(work_order, "get_close_permission", return_value={}),
			patch.object(work_order, "fetch_summary_details", return_value=summary) as read_summary,
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=parents) as get_list,
			patch.object(frappe, "get_all", return_value=children) as get_all,
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(work_order, "group_items_for_ui", side_effect=lambda rows, _: rows),
		):
			result = work_order.execute_work_order_command("WO-1", "get_close_context")
		read_summary.assert_called_once_with("WO-1", "IPD-1")
		get_doc.assert_not_called()
		self.assertEqual(result["summary"], summary)
		self.assertEqual(
			result["recuts"],
			[
				{"name": "RECUT-2", "items": children[2:]},
				{"name": "RECUT-1", "items": children[:2]},
				{"name": "RECUT-EMPTY", "items": []},
			],
		)
		get_list.assert_called_once_with(
			"SD YRP WO Recut",
			filters={"work_order": "WO-1", "docstatus": 1},
			fields=["name"],
			order_by="creation asc",
			limit_page_length=0,
		)
		get_all.assert_called_once_with(
			"SD YRP WO Recut Detail",
			filters={
				"parent": ["in", [row.name for row in parents]],
				"parenttype": "SD YRP WO Recut",
				"parentfield": "wo_recut_details",
			},
			fields=["*"],
			order_by="parent asc, idx asc",
		)

	def test_no_visible_recuts_skips_child_query(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=[]),
			patch.object(frappe, "get_all") as get_all,
		):
			self.assertEqual(work_order._close_recuts("WO-1"), [])
		get_all.assert_not_called()

	def test_unreadable_recuts_are_not_queried(self):
		with (
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(frappe, "get_list") as get_list,
		):
			self.assertEqual(work_order._close_recuts("WO-1"), [])
		get_list.assert_not_called()

	def test_pi_approval_names_open_and_close_requested_work_orders(self):
		doc = frappe._dict(name="PI-1", docstatus=0, against="YRP Work Order")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(purchase_invoice, "get_merch_roles", return_value="merch_manager"),
			patch.object(purchase_invoice, "_override_pi_approve", return_value=False),
			patch.object(
				purchase_invoice,
				"check_all_wo_closed",
				return_value={
					"all_closed": False,
					"open_work_orders": ["WO-OPEN"],
					"close_request_wos": ["WO-REQUEST"],
				},
			),
			self.assertRaisesRegex(
				frappe.ValidationError, "Cannot approve before closing all Work Orders: WO-OPEN, WO-REQUEST"
			),
		):
			purchase_invoice.approve_invoice("PI-1")


class TestSewingPlanSkipNotice(TestCase):
	def test_submit_explains_both_supplier_skip_reasons(self):
		for internal, enabled, expected in (
			(0, 1, "is not a company location."),
			(1, 0, "does not use Sewing Plans."),
		):
			with self.subTest(internal=internal, enabled=enabled):
				doc = frappe._dict(supplier="S-0155", process_name="Stitching", is_internal_unit=internal)
				with (
					patch.object(frappe.db, "get_single_value", return_value="Stitching"),
					patch.object(
						frappe.db,
						"get_value",
						side_effect=lambda doctype, name, field: (
							enabled if field == "apply_sewing_plan" else "Sewing Unit"
						),
					),
					patch.object(frappe, "msgprint") as msgprint,
					patch.object(plan, "create_or_get_sewing_plan") as create,
				):
					plan.on_work_order_submit(doc)
				create.assert_not_called()
				msgprint.assert_called_once_with(
					f"No Sewing Plan was created: Sewing Unit {expected}", indicator="orange"
				)

	def test_unrelated_work_order_stays_quiet_and_eligible_sewing_still_creates(self):
		for process, expected_calls in (("Cutting", 0), ("Stitching", 1)):
			doc = frappe._dict(supplier="S-1", process_name=process, is_internal_unit=1)
			with (
				patch.object(frappe.db, "get_single_value", return_value="Stitching"),
				patch.object(
					frappe.db,
					"get_value",
					side_effect=lambda doctype, *args: 0 if doctype == "YRP Process" else 1,
				),
				patch.object(frappe, "msgprint") as msgprint,
				patch.object(plan, "create_or_get_sewing_plan") as create,
			):
				plan.on_work_order_submit(doc)
			self.assertEqual(create.call_count, expected_calls)
			msgprint.assert_not_called()


class TestCutPanelTransactionRecovery(TestCase):
	def test_grn_rejects_supplier_mismatch_before_stock_defaults(self):
		cut_panel_movement = frappe._dict(lot="LOT-1", from_warehouse="SUPPLIER-FROM")
		order = MagicMock()
		order.name = "WO-1"
		order.docstatus = 1
		order.open_status = "Open"
		order.lot = "LOT-1"
		order.supplier = "SUPPLIER-OTHER"
		with (
			patch.object(movement, "_require_create_permission"),
			patch.object(movement, "get_grouped_movement_rows", return_value=(cut_panel_movement, None, [])),
			patch.object(frappe, "get_doc", return_value=order),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Work Order WO-1 is with SUPPLIER-OTHER, but this Cut Panel Movement is from SUPPLIER-FROM",
			),
		):
			movement.build_goods_received_note_defaults("CPM-1", "WO-1")
		order.check_permission.assert_called_once_with("read")

	def test_work_order_picker_returns_process_name(self):
		doc = MagicMock()
		doc.lot = "LOT-1"
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=[]) as get_list,
		):
			movement_workspace.get_movement_work_orders("CPM-1")
		self.assertIn("process_name", get_list.call_args.kwargs["fields"])

	def test_skip_transit_is_passed_to_stock_entry(self):
		for skip in (False, True):
			doc = MagicMock()
			with (
				patch.object(
					movement_workspace, "_get_submitted_movement", return_value=frappe._dict(name="CPM-1")
				),
				patch.object(frappe, "has_permission", return_value=True),
				patch.object(movement_workspace, "get_active_root_transactions", return_value=[]),
				patch.object(movement_workspace, "build_stock_entry_defaults", return_value={}),
				patch.object(movement_workspace, "new_transaction_from_defaults", return_value=doc),
				patch.object(movement_workspace, "_transaction_record", return_value={}),
				patch.object(movement_workspace, "get_movement_linked_documents", return_value=[]),
			):
				movement_workspace.create_movement_transaction(
					"CPM-1", "stock_entry", {"to_warehouse": "WAREHOUSE-1", "skip_transit": skip}
				)
			self.assertEqual(doc.skip_transit, int(skip))
			doc.insert.assert_called_once()

	def test_bundle_report_hides_name_but_keeps_internal_key(self):
		self.assertNotIn("name", [column["fieldname"] for column in report_workspace.CUT_BUNDLE_COLUMNS])
		rows = report_workspace._safe_result([{"name": "HASH-1", "qty": 2, "lot": "LOT-1"}])
		self.assertEqual(rows[0]["name"], "HASH-1")


class TestPackingGrnCancellation(TestCase):
	def test_size_wise_dispatch_preflight_uses_remaining_boxes_per_variant(self):
		for dispatched, removed, blocked in ((8, 5, True), (4, 5, False), (0, 10, False)):
			receipt = frappe._dict(
				includes_packing=1,
				from_finishing=1,
				against_id="WO-1",
				lot="LOT-1",
				items=[frappe._dict(item_variant="PACK-S", quantity=removed)],
			)
			finishing = frappe._dict(
				finishing_plan_grn_details=[
					frappe._dict(item_variant="PACK-S", quantity=10, dispatched=dispatched)
				]
			)
			with (
				patch.object(frappe.db, "get_value", return_value="FP-1"),
				patch.object(frappe, "get_doc", return_value=finishing),
			):
				if blocked:
					with self.assertRaisesRegex(
						frappe.ValidationError,
						"Cancel the related Finishing Plan dispatch entries before cancelling this GRN",
					):
						grn.validate_packing_cancellation(receipt)
				else:
					grn.validate_packing_cancellation(receipt)

	def test_batch_dispatch_guard_is_preserved(self):
		receipt = frappe._dict(includes_packing=1, packing_batches=[frappe._dict(dispatched_boxes=1)])
		with self.assertRaisesRegex(frappe.ValidationError, "Finishing Plan dispatch entries"):
			grn.validate_packing_cancellation(receipt)

	def test_cancel_preflights_dispatch_before_cancelling_completion_stock_entries(self):
		for batches, dispatched, blocked in (
			(True, 1, True),
			(False, 8, True),
			(True, 0, False),
			(False, 4, False),
		):
			with self.subTest(batches=batches, dispatched=dispatched):
				receipt = object.__new__(EssdeeGoodsReceivedNote)
				receipt.__dict__.update(
					name="GRN-1",
					doctype="YRP Goods Received Note",
					docstatus=1,
					includes_packing=1,
					from_finishing=1,
					is_internal_unit=1,
					against_id="WO-1",
					lot="LOT-1",
					flags=frappe._dict(),
					_action="cancel",
					packing_batches=[frappe._dict(dispatched_boxes=dispatched)] if batches else [],
					items=[frappe._dict(item_variant="PACK-S", quantity=5)],
				)
				# Keep the real cancel/event/controller chain; replace persistence and unrelated guards.
				receipt.save = MagicMock(side_effect=receipt.run_before_save_methods)
				receipt.reset_seen = MagicMock()
				for method in (
					"validate_no_purchase_invoice",
					"validate_closed_purchase_order",
					"validate_age_limit",
					"validate_no_inspection_entry",
				):
					setattr(receipt, method, MagicMock())
				completion = MagicMock()
				completion.cancel.side_effect = frappe.ValidationError("raw stock error")
				finishing = frappe._dict(
					finishing_plan_grn_details=[
						frappe._dict(item_variant="PACK-S", quantity=10, dispatched=dispatched),
					]
				)
				with (
					patch("essdee_yrp.overrides.goods_received_note._lock_versioned_cloth_lot"),
					patch(
						"essdee_yrp.overrides.goods_received_note._requires_versioned_cloth_lifecycle",
						return_value=False,
					),
					patch(
						"essdee_yrp.overrides.goods_received_note._has_complete_mapped_consumption",
						return_value=False,
					),
					patch.object(frappe, "get_doc_hooks", return_value={}),
					patch.object(frappe.db, "get_value", return_value="FP-1"),
					patch.object(
						frappe,
						"get_doc",
						side_effect=lambda doctype, name: (
							finishing if doctype == "SD YRP Finishing Plan" else completion
						),
					),
					patch.object(frappe, "get_all", return_value=["STE-1"]) as get_all,
					self.assertRaisesRegex(
						frappe.ValidationError,
						"Finishing Plan dispatch entries" if blocked else "raw stock error",
					),
				):
					receipt.cancel()
				self.assertEqual(receipt.docstatus, 2)
				if blocked:
					get_all.assert_not_called()
					completion.cancel.assert_not_called()
				else:
					completion.cancel.assert_called_once_with()
					self.assertEqual(get_all.call_args.kwargs["filters"]["purpose"], "GRN Completion")


class TestPurchaseInvoiceRecovery(TestCase):
	def test_supplier_invoice_uniqueness_matches_erpnext_scope(self):
		payload = {
			"supplier": "S-ORIGINAL",
			"billing_supplier": "S-BILLING",
			"bill_no": "BILL-1",
			"posting_date": "2026-06-01",
			"items": [],
			"company": "IGNORED-PAYLOAD-COMPANY",
		}
		fiscal_year = frappe._dict(year_start_date="2026-04-01", year_end_date="2027-03-31")
		for enabled, posting_date, supplier, docstatus, blocked in (
			(1, "2026-03-31", "S-BILLING", 1, False),
			(1, "2027-04-01", "S-BILLING", 1, False),
			(0, "2026-06-01", "S-BILLING", 1, False),
			(1, "2026-04-01", "S-BILLING", 0, True),
			(1, "2027-03-31", "S-BILLING", 1, True),
			(1, "2026-06-01", "OTHER-SUPPLIER", 1, False),
			(1, "2026-06-01", "S-BILLING", 2, False),
		):
			with self.subTest(
				enabled=enabled, posting_date=posting_date, supplier=supplier, docstatus=docstatus
			):

				def find_duplicate(doctype, filters, field):
					self.assertEqual((doctype, field), ("Purchase Invoice", "name"))
					self.assertEqual(
						filters,
						{
							"supplier": "S-BILLING",
							"bill_no": "BILL-1",
							"docstatus": ["<", 2],
							"posting_date": ["between", ["2026-04-01", "2027-03-31"]],
						},
					)
					start, end = filters["posting_date"][1]
					if start <= posting_date <= end and supplier == filters["supplier"] and docstatus < 2:
						return "ERP-PI-1"

				with (
					patch.object(frappe, "get_single_value", return_value=enabled) as setting,
					patch("erpnext.get_default_company", return_value="ERP-COMPANY"),
					patch("erpnext.accounts.utils.get_fiscal_year", return_value=fiscal_year) as get_year,
					patch.object(frappe.db, "get_value", side_effect=find_duplicate) as get_value,
					patch("essdee_yrp.erp_purchase_invoice._local_erp_purchase_invoice_api") as api,
				):
					if blocked:
						with self.assertRaisesRegex(
							frappe.ValidationError,
							"ERP Purchase Invoice ERP-PI-1 already uses Supplier Invoice No BILL-1. "
							"Cancel that ERP bill or change the Supplier Invoice No, then submit again.",
						):
							_create_local_erp_invoice(payload)
						api.assert_not_called()
					else:
						_validate_supplier_invoice_number(payload)
					setting.assert_called_once_with("Accounts Settings", "check_supplier_invoice_uniqueness")
					if enabled:
						get_year.assert_called_once_with("2026-06-01", company="ERP-COMPANY", as_dict=True)
					else:
						get_year.assert_not_called()
						get_value.assert_not_called()

	def test_billing_supplier_displays_name_and_retains_link_id(self):
		doc = MagicMock()
		doc.flags.masked_fieldnames = []
		doc.get.side_effect = lambda name: {"billing_supplier": "S-1"}.get(name)
		doc.meta.get_field.return_value = frappe._dict(
			label="Billing Supplier", fieldtype="Link", options="Supplier"
		)
		with patch.object(frappe.db, "get_value", return_value="Billing Company"):
			field = purchase_invoice_workspace._detail_field(doc, "billing_supplier")
		self.assertEqual(field["value"], "Billing Company")
		self.assertEqual(field["link_name"], "S-1")

	def test_masked_billing_supplier_does_not_fetch_unmasked_name(self):
		doc = MagicMock()
		doc.flags.masked_fieldnames = ["billing_supplier"]
		doc.get.return_value = "********"
		with patch.object(frappe.db, "get_value") as get_value:
			self.assertEqual(
				purchase_invoice_workspace._supplier_display_name(doc, "billing_supplier"), "********"
			)
		get_value.assert_not_called()

from pathlib import Path
from unittest.mock import call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import hooks
from essdee_yrp.setup import ensure_stock_transaction_indexes
from essdee_yrp.stock_entry_hooks import sync_dc_completion_cutting_plan


class TestManualUATDeskRegressions(FrappeTestCase):
	def test_cutting_laysheet_restore_has_operator_feedback(self):
		source = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "essdee_yrp/doctype/cutting_laysheet/cutting_laysheet.js"
		).read_text(encoding="utf-8")
		self.assertIn("Restoring Label Printed status", source)
		self.assertIn("Label Printed restored", source)
		self.assertIn("frm.reload_doc()", source)

	def test_cutting_plan_list_status_indicator_is_registered(self):
		self.assertEqual(
			hooks.doctype_list_js["Cutting Plan"],
			"public/js/cutting_plan_list.js",
		)
		source = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "public/js/cutting_plan_list.js"
		).read_text(encoding="utf-8")
		for status in (
			"Planned",
			"Fabric Partially Received",
			"Ready to Cut",
			"Partially Completed",
			"Completed",
		):
			self.assertIn(status, source)

	def test_stock_voucher_index_is_deployed_idempotently(self):
		with patch.object(frappe.db, "add_index") as add_index:
			ensure_stock_transaction_indexes()
		add_index.assert_has_calls(
			[
				call(
					"Stock Ledger Entry",
					["voucher_type", "voucher_no", "is_cancelled"],
					index_name="idx_sle_voucher_active",
				),
				call(
					"Stock Reservation Entry",
					[
						"item_code",
						"warehouse",
						"lot",
						"received_type",
						"docstatus",
						"status",
					],
					index_name="idx_sre_active_stock_bucket",
				),
				call(
					"Stock Reservation Entry",
					[
						"voucher_type",
						"voucher_no",
						"voucher_detail_no",
						"docstatus",
					],
					index_name="idx_sre_voucher_detail_active",
				),
			]
		)
		self.assertEqual(add_index.call_count, 3)
		indexes = frappe.db.sql(
			"SHOW INDEX FROM `tabStock Ledger Entry` WHERE Key_name=%s",
			("idx_sle_voucher_active",),
			as_dict=True,
		)
		self.assertEqual(
			[row.Column_name for row in sorted(indexes, key=lambda row: row.Seq_in_index)],
			["voucher_type", "voucher_no", "is_cancelled"],
		)
		reservation_indexes = frappe.db.sql(
			"SHOW INDEX FROM `tabStock Reservation Entry` WHERE Key_name=%s",
			("idx_sre_active_stock_bucket",),
			as_dict=True,
		)
		self.assertEqual(
			[
				row.Column_name
				for row in sorted(reservation_indexes, key=lambda row: row.Seq_in_index)
			],
			[
				"item_code",
				"warehouse",
				"lot",
				"received_type",
				"docstatus",
				"status",
			],
		)
		voucher_indexes = frappe.db.sql(
			"SHOW INDEX FROM `tabStock Reservation Entry` WHERE Key_name=%s",
			("idx_sre_voucher_detail_active",),
			as_dict=True,
		)
		self.assertEqual(
			[
				row.Column_name
				for row in sorted(voucher_indexes, key=lambda row: row.Seq_in_index)
			],
			["voucher_type", "voucher_no", "voucher_detail_no", "docstatus"],
		)

	def test_only_dc_completion_stock_entries_refresh_cutting_plan_receipts(self):
		delivery_challan = frappe._dict(name="DC-COMPLETION-1")
		with (
			patch.object(frappe, "get_doc", return_value=delivery_challan) as get_doc,
			patch(
				"essdee_yrp.delivery_challan_hooks.sync_cutting_plan_received_cloth"
			) as sync,
		):
			sync_dc_completion_cutting_plan(
				frappe._dict(
					purpose="DC Completion",
					against="Delivery Challan",
					against_id="DC-COMPLETION-1",
				)
			)
		get_doc.assert_called_once_with("Delivery Challan", "DC-COMPLETION-1")
		sync.assert_called_once_with(delivery_challan)

		with patch.object(frappe, "get_doc") as get_doc:
			sync_dc_completion_cutting_plan(
				frappe._dict(
					purpose="Material Transfer",
					against="Delivery Challan",
					against_id="DC-COMPLETION-1",
				)
			)
		get_doc.assert_not_called()

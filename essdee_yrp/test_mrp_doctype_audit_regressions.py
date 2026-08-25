"""Focused regressions found by the screenshot-led MRP DocType audit."""

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet import (
	create_grn_entry,
	get_cut_sheet_data,
	print_labels,
	request_grammage_approval,
	update_cutting_plan,
)
from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import (
	calculate_laysheets,
	change_approval_grammage,
	create_recut_print_panel,
	fetch_received_cloth,
	get_cloth1,
)
from essdee_yrp.ipd_ui import duplicate_ipd, revert_ipd_approval


class TestMRPDocTypeAuditRegressions(IntegrationTestCase):
	def test_legacy_ipd_with_independent_process_stages_can_be_duplicated(self):
		name = "Maze Capri Set R.N.S-3"
		if not frappe.db.exists("Item Production Detail", name):
			self.skipTest(f"Legacy IPD oracle {name} is unavailable")

		duplicate_name = duplicate_ipd(name)
		duplicate = frappe.get_doc("Item Production Detail", duplicate_name)
		self.assertEqual(duplicate.item, "Maze Capri Set R.N.S")
		self.assertEqual(
			[(row.process_name, row.in_stage, row.out_stage) for row in duplicate.ipd_processes],
			[("Printing", "Cut", "Cut"), ("Yolk Fusing", "Cut", "Cut"), ("Ironing", "Piece", "Piece")],
		)

	def test_lot_onload_restores_current_time_and_action_rows(self):
		name = "C0425-26"
		if not frappe.db.exists(
			"Lot Time and Action Detail",
			{"parent": name},
		):
			self.skipTest(f"Time and Action Lot oracle {name} is unavailable")

		doc = frappe.get_doc("Lot", name)
		doc.run_method("onload")
		details = (doc.get("__onload") or {}).get("action_details") or []
		self.assertEqual(len(details), len(doc.lot_time_and_action_details))
		for row in details:
			self.assertTrue(
				{"colour", "master", "action", "department", "date", "process"}
				<= set(row)
			)

	def test_approved_ipd_requires_explicit_revert_before_any_save(self):
		name = "EE-36221 SHORTS SET HALF SLEEVE (CORD)-3"
		if not frappe.db.exists(
			"Item Production Detail", {"name": name, "approval_status": "Approved"}
		):
			self.skipTest(f"Approved IPD oracle {name} is unavailable")

		doc = frappe.get_doc("Item Production Detail", name)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Revert Approval before editing",
		):
			doc.save()

		self.assertEqual(revert_ipd_approval(name), {"status": "success"})
		self.assertEqual(
			frappe.db.get_value("Item Production Detail", name, "approval_status"),
			"Not Approved",
		)

	def test_terminal_laysheets_reject_mutation_apis(self):
		label_printed = "CLS-2603-00251"
		approval_pending = "CLS-2608-00093"
		bundles_generated = "CLS-2606-00294"
		for name in (label_printed, approval_pending, bundles_generated):
			if not frappe.db.exists("Cutting LaySheet", name):
				self.skipTest(f"Cutting LaySheet oracle {name} is unavailable")

		for target_status in ("Approval Pending", "Label Printed", "Cancelled"):
			doc = frappe.get_doc("Cutting LaySheet", bundles_generated)
			doc.status = target_status
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"approved Cutting LaySheet action",
			):
				doc.save()

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"cutting GRN can only be created from a Bundles Generated",
		):
			create_grn_entry(label_printed)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Labels can only be printed for a Bundles Generated",
		):
			print_labels([], 0, label_printed, "Panel")
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Cutting totals cannot be updated from a Approval Pending",
		):
			update_cutting_plan(approval_pending)

		pending = frappe.get_doc("Cutting LaySheet", approval_pending)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Bundles can only be generated",
		):
			get_cut_sheet_data(
				pending.name,
				pending.cutting_marker,
				[],
				[],
				[],
				1,
				0,
				pending.bundle_generated_date,
			)

		approval_request = "CLS-2608-00081"
		if not frappe.db.exists(
			"Cutting LaySheet",
			{"name": approval_request, "status": "Bundles Generated", "approved_by": ["is", "not set"]},
		):
			self.skipTest(f"Approval-request LaySheet oracle {approval_request} is unavailable")
		self.assertEqual(
			request_grammage_approval(approval_request)["status"],
			"Approval Pending",
		)

	def test_cancelled_cutting_plan_rejects_every_mutation_endpoint(self):
		name = "CP-2605-00019"
		if not frappe.db.exists("Cutting Plan", {"name": name, "docstatus": 2}):
			self.skipTest(f"Cancelled Cutting Plan oracle {name} is unavailable")

		calls = (
			lambda: get_cloth1(name),
			lambda: calculate_laysheets(name),
			lambda: fetch_received_cloth(name),
			lambda: create_recut_print_panel(name, "Recut", []),
			lambda: change_approval_grammage(name, 0.01),
		)
		for call in calls:
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"must be submitted for this action",
			):
				call()

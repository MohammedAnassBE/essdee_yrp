import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting import order_workspace, parent_adapter, plan_editor
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order import SDYRPCuttingOrder
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import SDYRPCuttingPlan
from essdee_yrp.patches import backfill_cancelled_cutting_statuses

CONTROLLERS = (
	(SDYRPCuttingOrder, "SD YRP Cutting Order", "co_status", order_workspace._record),
	(SDYRPCuttingPlan, "SD YRP Cutting Plan", "cp_status", plan_editor._record_payload),
)


def status_document(doctype, fieldname, status="Submitted", docstatus=1):
	doc = MagicMock()
	doc.name = "CUTTING-1"
	doc.doctype = doctype
	doc.docstatus = docstatus
	doc.modified = "same"
	doc.get.side_effect = lambda key, default=None: doc.__dict__.get(key, default)
	setattr(doc, fieldname, status)
	doc.db_set.side_effect = lambda field, value: setattr(doc, field, value)
	if doctype == "SD YRP Cutting Plan":
		doc._fabric_receipt_status.side_effect = lambda: SDYRPCuttingPlan._fabric_receipt_status(doc)
		doc._completion_status.side_effect = lambda: SDYRPCuttingPlan._completion_status(doc)
	return doc


class TestCuttingCancelledStatus(TestCase):
	def test_controller_cancel_persists_status_and_detail_payload(self):
		for controller, doctype, fieldname, record in CONTROLLERS:
			with self.subTest(doctype=doctype):
				doc = status_document(doctype, fieldname, docstatus=2)
				controller.on_cancel(doc)
				doc.db_set.assert_called_once_with(fieldname, "Cancelled")
				self.assertEqual(record(doc)["status"], "Cancelled")

	def test_web_cancel_uses_controller_status(self):
		for controller, doctype, fieldname, record in CONTROLLERS:
			with self.subTest(doctype=doctype):
				doc = status_document(doctype, fieldname)
				doc.cancel.side_effect = lambda: controller.on_cancel(doc)
				module = order_workspace if controller is SDYRPCuttingOrder else plan_editor
				action = module.change_order_status if controller is SDYRPCuttingOrder else module.change_status
				editor = "get_order_editor" if controller is SDYRPCuttingOrder else "get_editor"
				with (
					patch.object(frappe, "get_doc", return_value=doc),
					patch.object(frappe, "has_permission", return_value=True),
					patch.object(module, editor, side_effect=lambda name: {"record": record(doc)}),
				):
					payload = action(doc.name, "cancel", "same")
				self.assertEqual(payload["record"]["status"], "Cancelled")

	def test_cancelled_documents_skip_status_recomputation(self):
		for controller, doctype, fieldname, _record in CONTROLLERS:
			with self.subTest(doctype=doctype):
				doc = status_document(doctype, fieldname, "Cancelled", 2)
				with patch.object(frappe.db, "set_value") as update, patch.object(frappe.db, "sql") as query:
					controller.on_update_after_submit(doc)
				update.assert_not_called()
				query.assert_not_called()
				self.assertEqual(getattr(doc, fieldname), "Cancelled")

	def test_first_lay_updates_only_submitted_parents(self):
		for _controller, doctype, fieldname, _record in CONTROLLERS:
			with self.subTest(doctype=doctype), patch.object(frappe.db, "set_value") as update:
				parent_adapter.update_parent_status_on_first_lay(doctype, "CUTTING-1")
				update.assert_called_once_with(
					doctype, {"name": "CUTTING-1", "docstatus": 1}, fieldname,
					"Cutting In Progress", update_modified=False,
				)

	def test_order_status_progression_still_uses_completion_and_laysheets(self):
		for completed, has_laysheets, expected in (
			([False, False], False, "Submitted"),
			([False, False], True, "Cutting In Progress"),
			([True, False], True, "Partially Completed"),
			([True, True], True, "Completed"),
		):
			with self.subTest(expected=expected):
				doc = status_document("SD YRP Cutting Order", "co_status")
				doc.completed_items_json = {"items": [{"completed": value} for value in completed]}
				with (
					patch.object(frappe.db, "exists", return_value=has_laysheets),
					patch.object(frappe.db, "set_value") as update,
				):
					SDYRPCuttingOrder.on_update_after_submit(doc)
				update.assert_called_once_with(doc.doctype, doc.name, "co_status", expected)

	def test_plan_status_progression_still_uses_fabric_and_completion(self):
		for status, weight, completed, expected in (
			("Planned", 0, [False, False], "Planned"),
			("Planned", 4, [False, False], "Fabric Partially Received"),
			("Planned", 10, [False, False], "Ready to Cut"),
			("Cutting In Progress", 10, [False, False], "Cutting In Progress"),
			("Cutting In Progress", 10, [True, False], "Partially Completed"),
			("Cutting In Progress", 10, [True, True], "Completed"),
		):
			with self.subTest(expected=expected):
				doc = status_document("SD YRP Cutting Plan", "cp_status", status)
				doc.no_of_colours = 2
				doc.cutting_plan_cloth_details = [frappe._dict(weight=weight, required_weight=10)]
				doc.completed_items_json = {"items": [{"completed": value} for value in completed]}
				with (
					patch.object(frappe.db, "get_single_value", return_value=0),
					patch.object(frappe.db, "sql"),
					patch.object(frappe.db, "set_value") as update,
				):
					SDYRPCuttingPlan.on_update_after_submit(doc)
				update.assert_any_call(doc.doctype, doc.name, "cp_status", expected)

	def test_order_amendment_resets_cancelled_status_before_submit(self):
		doc = status_document("SD YRP Cutting Order", "co_status", "Cancelled", 0)
		doc.amended_from = "CTO-CANCELLED"
		doc.cutting_order_detail = "DETAIL-1"
		SDYRPCuttingOrder.validate(doc)
		self.assertEqual(doc.co_status, "Draft")
		doc.items_json = json.dumps({"items": [{"colour": "Navy", "quantities": {"S": 10}}]})
		detail = frappe._dict(is_set_item=0, item_attributes=[], stiching_item_details=[], stiching_attribute="Panel", packing_attribute="Colour")
		with patch.object(frappe, "get_doc", return_value=detail):
			SDYRPCuttingOrder.before_submit(doc)
		self.assertEqual(doc.co_status, "Submitted")

	def test_web_amendments_reset_copied_cancelled_status_on_insert(self):
		for controller, doctype, fieldname, record in CONTROLLERS:
			with self.subTest(doctype=doctype):
				doc = status_document(doctype, fieldname, "Cancelled", 2)
				amended = status_document(doctype, fieldname, "Cancelled", 0)
				amended.piece_weight_tolerance = 0.003
				amended.is_new.return_value = False
				validate = controller.validate if controller is SDYRPCuttingOrder else controller.before_validate
				amended.insert.side_effect = lambda: validate(amended)
				module = order_workspace if controller is SDYRPCuttingOrder else plan_editor
				action = module.change_order_status if controller is SDYRPCuttingOrder else module.change_status
				editor = "get_order_editor" if controller is SDYRPCuttingOrder else "get_editor"
				with (
					patch.object(frappe, "get_doc", return_value=doc),
					patch.object(frappe, "copy_doc", return_value=amended),
					patch.object(frappe, "has_permission", return_value=True),
					patch.object(module, editor, side_effect=lambda name: {"record": record(amended)}),
				):
					payload = action(doc.name, "amend", "same")
				self.assertEqual(payload["record"]["status"], "Draft")
				self.assertEqual(amended.docstatus, 0)
				self.assertEqual(amended.amended_from, doc.name)

	def test_plan_amendment_resets_cancelled_status_before_submit(self):
		doc = status_document("SD YRP Cutting Plan", "cp_status", "Cancelled", 0)
		doc.amended_from = "CP-CANCELLED"
		doc.piece_weight_tolerance = 0.003
		doc.is_new.return_value = False
		SDYRPCuttingPlan.before_validate(doc)
		self.assertEqual(doc.cp_status, "Draft")
		doc.cutting_plan_cloth_details = [frappe._dict(weight=0, required_weight=10)]
		with patch.object(frappe.db, "get_single_value", return_value=0):
			SDYRPCuttingPlan.before_submit(doc)
		self.assertEqual(doc.cp_status, "Planned")

	def test_backfill_is_idempotent_and_only_changes_cancelled_rows(self):
		rows = {
			"SD YRP Cutting Order": [
				frappe._dict(name="CTO-2603-00001", docstatus=2, co_status="Submitted"),
				frappe._dict(name="CTO-2603-00002", docstatus=2, co_status="Cutting In Progress"),
				frappe._dict(name="CTO-ACTIVE", docstatus=1, co_status="Submitted"),
				frappe._dict(name="CTO-DRAFT", docstatus=0, co_status="Draft"),
			],
			"SD YRP Cutting Plan": [
				frappe._dict(name="CP-CANCELLED", docstatus=2, cp_status="Planned"),
				frappe._dict(name="CP-ACTIVE", docstatus=1, cp_status="Ready to Cut"),
				frappe._dict(name="CP-DRAFT", docstatus=0, cp_status="Draft"),
			],
		}

		def update(doctype, filters, fieldname, value, update_modified):
			self.assertEqual(filters, {"docstatus": 2})
			self.assertFalse(update_modified)
			for row in rows[doctype]:
				if row.docstatus == filters["docstatus"]:
					row[fieldname] = value

		with patch.object(frappe.db, "set_value", side_effect=update):
			backfill_cancelled_cutting_statuses.execute()
			first_result = json.dumps(rows)
			backfill_cancelled_cutting_statuses.execute()
		self.assertEqual(json.dumps(rows), first_result)
		self.assertEqual([row.co_status for row in rows["SD YRP Cutting Order"]], ["Cancelled", "Cancelled", "Submitted", "Draft"])
		self.assertEqual([row.cp_status for row in rows["SD YRP Cutting Plan"]], ["Cancelled", "Ready to Cut", "Draft"])

	def test_status_selects_accept_cancelled_and_other_documents_need_no_backfill(self):
		root = Path(__file__).parent / "essdee_yrp" / "doctype"
		for kind, fieldname in (("order", "co_status"), ("plan", "cp_status")):
			with self.subTest(kind=kind):
				metadata = json.loads((root / f"sd_yrp_cutting_{kind}" / f"sd_yrp_cutting_{kind}.json").read_text())
				field = next(row for row in metadata["fields"] if row["fieldname"] == fieldname)
				self.assertIn("Cancelled", field["options"].splitlines())
				self.assertTrue(metadata["is_submittable"])
		for kind in ("laysheet", "bulk_lay_sheets", "laysheet_planner", "order_detail"):
			metadata = json.loads((root / f"sd_yrp_cutting_{kind}" / f"sd_yrp_cutting_{kind}.json").read_text())
			self.assertFalse(metadata.get("is_submittable"), kind)
		marker = json.loads((root / "sd_yrp_cutting_marker" / "sd_yrp_cutting_marker.json").read_text())
		self.assertFalse(any(row["fieldname"] == "status" for row in marker["fields"]))

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting.plan_editor import _serialize_editor
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as controller
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
	SDYRPCuttingPlan,
	has_cutting_laysheets,
)

PLAN_JSON = Path(controller.__file__).with_name("sd_yrp_cutting_plan.json")
PLAN_JS = Path(controller.__file__).with_name("sd_yrp_cutting_plan.js")


def plan(name="CP-001", docstatus=1, before=None, **values):
	doc = frappe.get_doc({"doctype": "SD YRP Cutting Plan", "name": name, "docstatus": docstatus, **values})
	doc.get_doc_before_save = lambda: before
	doc.is_new = lambda: before is None
	return doc


def laysheets_for(*plans):
	return patch.object(
		controller.frappe.db,
		"exists",
		side_effect=lambda doctype, filters: (
			doctype == "SD YRP Cutting LaySheet" and filters.get("cutting_plan") in plans
		),
	)


class TestCuttingPlanLaySheetLock(TestCase):
	def test_location_and_manual_entry_change_without_laysheets(self):
		before = plan(cutting_location="Machine Cutting", is_manual_entry=0)
		doc = plan(before=before, cutting_location="Manual Cutting", is_manual_entry=1)
		with laysheets_for():
			SDYRPCuttingPlan.validate_laysheet_locked_fields(doc)

	def test_location_change_is_blocked_once_laysheets_exist(self):
		before = plan(cutting_location="Machine Cutting")
		doc = plan(before=before, cutting_location="Manual Cutting")
		with (
			laysheets_for("CP-001"),
			self.assertRaisesRegex(
				frappe.ValidationError, "Cutting Location cannot be changed because LaySheets exist"
			),
		):
			SDYRPCuttingPlan.validate_laysheet_locked_fields(doc)

	def test_manual_entry_change_is_blocked_once_laysheets_exist(self):
		before = plan(docstatus=0, is_manual_entry=0)
		doc = plan(docstatus=0, before=before, is_manual_entry=1)
		with (
			laysheets_for("CP-001"),
			self.assertRaisesRegex(frappe.ValidationError, "Is Manual Entry cannot be changed"),
		):
			SDYRPCuttingPlan.validate_laysheet_locked_fields(doc)

	def test_unchanged_fields_save_with_laysheets(self):
		before = plan(cutting_location="Machine Cutting", is_manual_entry=0, lay_no=2)
		doc = plan(before=before, cutting_location="Machine Cutting", is_manual_entry=0, lay_no=3)
		with laysheets_for("CP-001"):
			SDYRPCuttingPlan.validate_laysheet_locked_fields(doc)

	def test_amended_draft_ignores_laysheets_of_cancelled_original(self):
		before = plan(
			name="CP-001-1",
			docstatus=0,
			amended_from="CP-001",
			lay_no=4,
			cutting_location="Machine Cutting",
			is_manual_entry=0,
		)
		doc = plan(
			name="CP-001-1",
			docstatus=0,
			before=before,
			amended_from="CP-001",
			lay_no=4,
			cutting_location="Manual Cutting",
			is_manual_entry=1,
		)
		with laysheets_for("CP-001"):
			SDYRPCuttingPlan.validate_laysheet_locked_fields(doc)
			self.assertFalse(has_cutting_laysheets("CP-001-1"))

	def test_draft_and_update_after_submit_both_run_the_lock(self):
		with patch.object(SDYRPCuttingPlan, "validate_laysheet_locked_fields") as lock:
			doc = plan(before=plan())
			SDYRPCuttingPlan.validate(doc)
			SDYRPCuttingPlan.before_update_after_submit(doc)
		self.assertEqual(lock.call_count, 2)

	def test_any_laysheet_counts_regardless_of_docstatus(self):
		with patch.object(controller.frappe.db, "exists", return_value="CLS-1") as exists:
			self.assertTrue(has_cutting_laysheets("CP-001"))
		exists.assert_called_once_with("SD YRP Cutting LaySheet", {"cutting_plan": "CP-001"})
		self.assertFalse(has_cutting_laysheets(None))

	def test_location_is_allow_on_submit_and_manual_entry_stays_draft_only(self):
		fields = {field["fieldname"]: field for field in json.loads(PLAN_JSON.read_text())["fields"]}
		self.assertEqual(fields["cutting_location"].get("allow_on_submit"), 1)
		self.assertFalse(fields["is_manual_entry"].get("allow_on_submit"))

	def test_desk_locks_on_actual_laysheets_not_copied_lay_no(self):
		source = PLAN_JS.read_text()
		self.assertIn("__onload.has_laysheets", source)
		self.assertNotIn("frm.doc.lay_no != 0", source)


class TestCuttingPlanEditorLaySheetLock(TestCase):
	def editor(self, has_laysheets):
		doc = plan(cutting_location="Machine Cutting", cp_status="Planned")
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.cutting.plan_editor.get_permitted_fields",
				return_value=["cutting_location", "is_manual_entry"],
			),
			patch("essdee_yrp.cutting.plan_editor.has_cutting_laysheets", return_value=has_laysheets),
		):
			return _serialize_editor(doc, [])

	def test_submitted_plan_without_laysheets_can_change_location(self):
		payload = self.editor(False)
		self.assertEqual(payload["fields"]["allow_on_submit_fields"], ["cutting_location"])
		self.assertEqual(payload["fields"]["laysheet_locked_fields"], [])
		self.assertTrue(payload["permissions"]["can_update_after_submit"])

	def test_submitted_plan_with_laysheets_locks_location(self):
		payload = self.editor(True)
		self.assertEqual(payload["fields"]["allow_on_submit_fields"], ["cutting_location"])
		self.assertEqual(payload["fields"]["laysheet_locked_fields"], ["cutting_location", "is_manual_entry"])
		self.assertFalse(payload["permissions"]["can_update_after_submit"])

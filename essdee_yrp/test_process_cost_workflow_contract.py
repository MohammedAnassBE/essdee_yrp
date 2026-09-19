import json
from pathlib import Path

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.workflow import get_active_workflow


class TestProcessCostWorkflowContract(UnitTestCase):
	def test_essdee_does_not_own_process_cost_workflow_state_field(self):
		fixture_path = frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json")
		with open(fixture_path, encoding="utf-8") as fixture_file:
			custom_fields = {row["name"] for row in json.load(fixture_file)}

		self.assertNotIn("Process Cost-workflow_state", custom_fields)

	def test_live_process_cost_workflow_uses_yrp_managed_field(self):
		workflow = frappe.get_doc("Workflow", "Process Cost Workflow")
		self.assertEqual(workflow.document_type, "Process Cost")
		self.assertEqual(workflow.workflow_state_field, "workflow_state")
		transitions = {
			(row.state, row.action, row.next_state) for row in workflow.transitions
		}
		self.assertIn(("Draft", "Submit", "Approval Pending"), transitions)
		self.assertIn(("Approval Pending", "Approve", "Approved"), transitions)
		self.assertIn(("Approval Pending", "Reject", "Rejected"), transitions)

		field = frappe.get_meta("Process Cost").get_field("workflow_state")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Workflow State")

	def test_active_workflow_contract_is_server_authoritative(self):
		contract = get_active_workflow("Process Cost")
		self.assertEqual(contract["name"], "Process Cost Workflow")
		self.assertEqual(contract["state_field"], "workflow_state")
		self.assertIn("Approval Pending", contract["states"])
		self.assertIn("Approved", contract["states"])

		self.assertIsNone(get_active_workflow("Lot"))

	def test_web_uses_workflow_actions_exclusively(self):
		detail_path = (
			Path(frappe.get_app_path("essdee_yrp")).parent
			/ "frontend"
			/ "src"
			/ "views"
			/ "dynamic"
			/ "DocDetail.vue"
		)
		source = detail_path.read_text(encoding="utf-8")

		self.assertIn('v-if="workflowChecked && isWorkflow"', source)
		self.assertIn(
			'v-if="docstatus === 0 && plainLifecycleAllowed && isSubmittable && canSubmit(doctype)"',
			source,
		)
		self.assertIn(
			"plainLifecycleAllowed.value\n\t\t&& docstatus.value === 1",
			source,
		)
		self.assertIn(
			"docstatus.value === 0 && plainLifecycleAllowed.value && isSubmittable.value",
			source,
		)
		self.assertIn(
			"docstatus.value === 1 && plainLifecycleAllowed.value && isSubmittable.value",
			source,
		)

		list_path = detail_path.with_name("DynamicListPage.vue")
		list_source = list_path.read_text(encoding="utf-8")
		self.assertIn("getActiveWorkflow(dt)", list_source)
		self.assertIn("workflowChecked.value && !isWorkflow.value", list_source)

import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import SAMPLES, make_user, rolled_back

APPROVED = SAMPLES["panel_wise"]
WRITER = "_test_ipd_merch@example.com"
LOCKED = "Revert Approval before editing"


def unused_process(doc):
	used = {row.process_name for row in doc.ipd_processes}
	return frappe.get_all("YRP Process", filters={"name": ["not in", list(used)]}, pluck="name", limit=1)[0]


def modified(name):
	return str(frappe.db.get_value(DOCTYPE, name, "modified"))


class TestApprovedIpdEdits(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(WRITER, ["Merchandiser"])
		if frappe.db.get_value(DOCTYPE, APPROVED, "approval_status") != "Approved":
			raise AssertionError(f"{APPROVED} must be Approved for these tests")

	def tearDown(self):
		frappe.set_user("Administrator")

	def approved_doc(self):
		return frappe.get_doc(DOCTYPE, APPROVED)

	def assert_locked(self, doc, changed=None):
		pattern = f"{LOCKED}.*Changed: .*{changed}" if changed else LOCKED
		with self.assertRaisesRegex(frappe.ValidationError, pattern):
			doc.save()

	def test_appending_a_process_row_keeps_the_ipd_approved(self):
		with rolled_back("approved_append"):
			doc = self.approved_doc()
			stage = doc.ipd_processes[0].in_stage
			process = unused_process(doc)
			doc.append("ipd_processes", {"process_name": process, "in_stage": stage, "out_stage": stage})
			doc.save()
			saved = frappe.get_doc(DOCTYPE, APPROVED)
			self.assertEqual(saved.approval_status, "Approved")
			self.assertEqual(saved.ipd_processes[-1].process_name, process)

	def test_changing_embellishment_panels_is_allowed(self):
		with rolled_back("approved_panels"):
			doc = self.approved_doc()
			details = json.loads(doc.emblishment_details_json)
			process = next(iter(details))
			details[process] = [*details[process], "Back"] if "Back" not in details[process] else []
			doc.emblishment_details_json = json.dumps(details)
			doc.save()
			saved = frappe.get_doc(DOCTYPE, APPROVED)
			self.assertEqual(json.loads(saved.emblishment_details_json)[process], details[process])
			self.assertEqual(saved.approval_status, "Approved")

	def test_other_changes_stay_locked(self):
		with rolled_back("approved_locked"):
			doc = self.approved_doc()
			doc.ipd_processes[0].in_stage = doc.ipd_processes[-1].in_stage
			doc.ipd_processes[0].out_stage = doc.ipd_processes[-1].in_stage
			self.assert_locked(doc, "IPD Processes")

			doc = self.approved_doc()
			doc.ipd_processes.pop()
			self.assert_locked(doc, "IPD Processes")

			doc = self.approved_doc()
			details = json.loads(doc.emblishment_details_json)
			details[unused_process(doc)] = ["Front"]
			doc.emblishment_details_json = json.dumps(details)
			self.assert_locked(doc, "Emblishment")

			doc = self.approved_doc()
			doc.description = "changed"
			doc.append("ipd_processes", {"process_name": unused_process(doc)})
			self.assert_locked(doc, "Description")

			doc = self.approved_doc()
			doc.approval_status = "Not Approved"
			doc.append("ipd_processes", {"process_name": unused_process(doc)})
			self.assert_locked(doc, "Approval Status")

	def test_unchanged_save_stays_locked(self):
		self.assert_locked(self.approved_doc())

	def test_web_editor_appends_with_one_stage(self):
		frappe.set_user(WRITER)
		payload = workspace.get_ipd_editor(APPROVED)
		self.assertTrue(payload["capabilities"]["approved_edits"]["allowed"])
		self.assertFalse(payload["capabilities"]["edit"]["allowed"])
		rows = payload["values"]["ipd_processes"]
		stage = rows[0]["in_stage"]
		with rolled_back("approved_web_append"):
			process = unused_process(self.approved_doc())
			result = workspace.save_ipd(
				{"ipd_processes": [*rows, {"process_name": process, "in_stage": stage}]},
				APPROVED,
				modified(APPROVED),
			)
			added = result["values"]["ipd_processes"][-1]
			self.assertEqual((added["process_name"], added["out_stage"]), (process, stage))
			self.assertEqual(result["record"]["approval_status"], "Approved")

	def test_web_editor_refuses_other_fields(self):
		frappe.set_user(WRITER)
		with self.assertRaisesRegex(frappe.ValidationError, "Approved IPDs are read only"):
			workspace.save_ipd({"description": "x"}, APPROVED, modified(APPROVED))
		rows = workspace.get_ipd_editor(APPROVED)["values"]["ipd_processes"]
		with self.assertRaisesRegex(frappe.ValidationError, LOCKED):
			workspace.save_ipd({"ipd_processes": rows[:-1]}, APPROVED, modified(APPROVED))

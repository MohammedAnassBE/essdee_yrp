from datetime import timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import now_datetime
from rq.job import JobStatus
from rq.utils import now as rq_now

from essdee_yrp.cutting import planner_workspace
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet_planner import (
	sd_yrp_cutting_laysheet_planner as native,
)

NATIVE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet_planner.sd_yrp_cutting_laysheet_planner"


def active_doc(status="Queued", age_seconds=0):
	return frappe._dict(
		name="CLP-TEST-1",
		optimization_status=status,
		optimization_input_json='{"order":{"S":1}}',
		modified=now_datetime() - timedelta(seconds=age_seconds),
	)


def rq_job(status, exc_info=None):
	job = MagicMock()
	job.get_status.return_value = status
	job.exc_info = exc_info
	return job


class TestCuttingLaySheetPlannerJobRecovery(TestCase):
	def test_enqueued_method_resolves_to_the_worker_function(self):
		self.assertIs(frappe.get_attr(native.OPTIMIZATION_METHOD), native.run_optimization)

	def test_failed_job_reports_its_exception(self):
		job = rq_job(JobStatus.FAILED, "Traceback ...\nModuleNotFoundError: No module named 'x'\n")
		with patch(f"{NATIVE}.get_job", return_value=job):
			message = native.get_stuck_optimization_message(active_doc())
		self.assertIn("ModuleNotFoundError: No module named 'x'", message)

	def test_live_job_is_left_alone_until_overdue(self):
		with patch(f"{NATIVE}.get_job", return_value=rq_job(JobStatus.QUEUED)):
			self.assertIsNone(native.get_stuck_optimization_message(active_doc(age_seconds=60)))
			overdue = native.get_stuck_optimization_message(
				active_doc(age_seconds=native.STALE_OPTIMIZATION_SECONDS + 1)
			)
		self.assertIn("'long' queue", overdue)

	def test_missing_job_waits_for_enqueue_after_commit(self):
		with patch(f"{NATIVE}.get_job", return_value=None):
			self.assertIsNone(native.get_stuck_optimization_message(active_doc("Running", age_seconds=5)))
			self.assertIn(
				"without saving",
				native.get_stuck_optimization_message(active_doc("Running", age_seconds=120)),
			)

	def test_recover_marks_stuck_planner_failed(self):
		doc = active_doc()
		doc.reload = MagicMock()
		with (
			patch(f"{NATIVE}.get_job", return_value=rq_job(JobStatus.FAILED, "ValueError: boom")),
			patch(f"{NATIVE}._mark_optimization_failed") as mark_failed,
		):
			self.assertTrue(native.recover_stuck_optimization(doc))
		mark_failed.assert_called_once_with(
			doc.name, doc.optimization_input_json, "Lay optimization job failed: ValueError: boom"
		)
		doc.reload.assert_called_once_with()

	def test_recover_ignores_terminal_planner(self):
		with patch(f"{NATIVE}.get_job") as get_job:
			self.assertFalse(native.recover_stuck_optimization(active_doc("Failed")))
		get_job.assert_not_called()

	def test_retry_discards_stale_queued_job(self):
		job = rq_job(JobStatus.QUEUED)
		with patch(f"{NATIVE}.get_job", return_value=job):
			native.discard_stale_optimization_job("CLP-TEST-1")
		job.delete.assert_called_once_with()

	def test_retry_refuses_while_job_is_still_running(self):
		job = rq_job(JobStatus.STARTED)
		job.started_at = rq_now()
		with patch(f"{NATIVE}.get_job", return_value=job):
			with self.assertRaises(frappe.ValidationError):
				native.discard_stale_optimization_job("CLP-TEST-1")
		job.delete.assert_not_called()

	def test_retry_discards_abandoned_running_job(self):
		job = rq_job(JobStatus.STARTED)
		job.started_at = rq_now() - timedelta(seconds=native.STALE_OPTIMIZATION_SECONDS + 1)
		with patch(f"{NATIVE}.get_job", return_value=job):
			native.discard_stale_optimization_job("CLP-TEST-1")
		job.delete.assert_called_once_with()

	def test_web_status_recovers_stuck_planner_before_reporting(self):
		doc = MagicMock(optimization_status="Queued", optimization_error=None, result_json=None)
		doc.name = "CLP-TEST-1"

		def mark_failed(target):
			target.optimization_status = "Failed"
			target.optimization_error = "Lay optimization job failed: ValueError: boom"
			return True

		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.cutting.planner_workspace.native.recover_stuck_optimization",
				side_effect=mark_failed,
			),
			patch("essdee_yrp.cutting.planner_workspace._has_valid_inputs", return_value=True),
		):
			payload = planner_workspace.get_status("CLP-TEST-1")
		self.assertEqual(payload["status"], "Failed")
		self.assertTrue(payload["terminal"])
		self.assertTrue(payload["actions"]["can_retry"])
		self.assertIn("ValueError: boom", payload["error_message"])

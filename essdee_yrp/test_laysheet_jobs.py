from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import background_jobs

from essdee_yrp.cutting import laysheet_jobs

TARGET = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.calc"
ORIGINAL_GET_ATTR = frappe.get_attr


class TestLaySheetJobs(TestCase):
	def setUp(self):
		self.cache = {}
		cache = MagicMock()
		cache.set_value.side_effect = lambda key, value, expires_in_sec=None: self.cache.__setitem__(key, value)
		cache.get_value.side_effect = self.cache.get
		patcher = patch.object(laysheet_jobs.frappe, "cache", cache)
		patcher.start()
		self.addCleanup(patcher.stop)

	def status(self, token):
		return self.cache[laysheet_jobs._cache_key(token)]["status"]

	def test_enqueue_returns_a_token_for_the_job_queued_after_commit(self):
		with patch.object(frappe, "enqueue") as enqueue:
			token = laysheet_jobs.enqueue_tracked_job(TARGET, "SD YRP Cutting Plan", "CP-1", cutting_plan="CP-1")["job_token"]
		kwargs = enqueue.call_args.kwargs
		self.assertIs(enqueue.call_args.args[0], laysheet_jobs.run_tracked_job)
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual((kwargs["target"], kwargs["token"], kwargs["docname"], kwargs["target_kwargs"]), (TARGET, token, "CP-1", {"cutting_plan": "CP-1"}))
		self.assertEqual(self.status(token), "queued")

	def run_in_worker(self, target, token):
		"""Runs the job through Frappe's real `execute_job` (with its in-place retries), as the worker does."""
		callbacks = []
		job_kwargs = {"target": "essdee_yrp.test_laysheet_jobs.flaky_target", "token": token, "doctype": "SD YRP Cutting Plan", "docname": "CP-1", "user": "a@x.test", "target_kwargs": {}}
		error = None
		with (
			patch.object(frappe, "get_attr", side_effect=lambda path: target if path == job_kwargs["target"] else ORIGINAL_GET_ATTR(path)),
			patch.object(frappe.db, "after_commit", MagicMock(add=callbacks.append)),
			patch.object(frappe.db, "commit", side_effect=lambda **_: [callback() for callback in callbacks]),
			patch.object(frappe.db, "rollback", side_effect=lambda **_: callbacks.clear()),
			patch.object(frappe, "destroy"),
			patch.object(frappe, "log_error"),
			patch.object(background_jobs.time, "sleep"),
			patch.object(laysheet_jobs.frappe, "publish_realtime") as publish,
		):
			try:
				background_jobs.execute_job(frappe.local.site, laysheet_jobs.run_tracked_job, None, "test", job_kwargs, is_async=False)
			except Exception as exception:
				error = exception
				# RQ calls the failure callback only when execute_job finally raises.
				laysheet_jobs.on_tracked_job_failure(MagicMock(kwargs={"site": frappe.local.site, "kwargs": job_kwargs}), MagicMock(), type(exception), exception, None)
		return [call.args[1]["status"] for call in publish.call_args_list], error

	def test_retryable_failures_stay_running_and_a_later_success_reports_finished(self):
		attempts = []

		def target():
			attempts.append(self.status("R1"))
			if len(attempts) < 3:
				raise frappe.RetryBackgroundJobError("deadlock, try again")

		laysheet_jobs._store_status("R1", "SD YRP Cutting Plan", "CP-1", "queued")
		with patch.object(laysheet_jobs, "truncate_failed_registry"):
			published, error = self.run_in_worker(target, "R1")
		self.assertIsNone(error)
		self.assertEqual(attempts, ["running", "running", "running"], "retries are never reported as failed")
		self.assertEqual(published, ["finished"])
		self.assertEqual(self.status("R1"), "finished")

	def test_retryable_failures_report_failed_once_retries_are_exhausted(self):
		attempts = []

		def target():
			attempts.append(1)
			raise frappe.RetryBackgroundJobError("still locked")

		with patch.object(laysheet_jobs, "truncate_failed_registry") as truncate:
			published, error = self.run_in_worker(target, "R2")
		self.assertIsInstance(error, frappe.RetryBackgroundJobError)
		self.assertEqual(len(attempts), 6, "Frappe retries five times before giving up")
		self.assertEqual(published, ["failed"])
		self.assertEqual(self.status("R2"), "failed")
		truncate.assert_called_once()

	def test_a_non_retryable_error_reports_failed_once(self):
		def target():
			raise ValueError("bad plan")

		with patch.object(laysheet_jobs, "truncate_failed_registry"), patch.object(frappe.monitor, "add_data_to_monitor"):
			published, error = self.run_in_worker(target, "R3")
		self.assertIsInstance(error, ValueError)
		self.assertEqual(published, ["failed"])

	def test_success_is_published_to_the_queuing_user_room(self):
		with patch.object(laysheet_jobs.frappe, "publish_realtime") as publish:
			laysheet_jobs._finish("T1", "SD YRP Cutting Plan", "CP-1", "a@x.test", "finished")
		event, message = publish.call_args.args
		self.assertEqual((event, message["job_token"], message["status"]), (laysheet_jobs.DONE_EVENT, "T1", "finished"))
		self.assertEqual(publish.call_args.kwargs["room"], laysheet_jobs.get_user_room("a@x.test"))

	def test_the_failure_callback_is_wired_into_the_queue(self):
		with patch.object(frappe, "enqueue") as enqueue:
			laysheet_jobs.enqueue_tracked_job(TARGET, "SD YRP Cutting Plan", "CP-1", cutting_plan="CP-1")
		self.assertIs(enqueue.call_args.kwargs["on_failure"], laysheet_jobs.on_tracked_job_failure)

	def test_status_fallback_checks_read_permission_on_the_tracked_document(self):
		self.assertEqual(laysheet_jobs.get_tracked_job_status("missing"), {"status": "unknown"})
		laysheet_jobs._store_status("T3", "SD YRP Cutting Order", "CO-1", "finished")
		with patch.object(frappe, "has_permission") as has_permission:
			self.assertEqual(laysheet_jobs.get_tracked_job_status("T3"), {"status": "finished"})
		has_permission.assert_called_once_with("SD YRP Cutting Order", "read", "CO-1", throw=True)

	def test_plan_and_order_calculations_return_the_tracked_job_token(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order import sd_yrp_cutting_order as order_module
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as plan_module

		with (
			patch.object(plan_module, "_get_submitted_cutting_plan"),
			patch.object(plan_module, "get_phantom_panels", return_value=[]),
			patch.object(plan_module, "enqueue_tracked_job", return_value={"job_token": "P"}) as plan_job,
		):
			self.assertEqual(plan_module.calculate_laysheets("CP-1"), {"job_token": "P"})
		self.assertEqual(plan_job.call_args.args[1:], ("SD YRP Cutting Plan", "CP-1"))
		self.assertTrue(plan_job.call_args.args[0].endswith("sd_yrp_cutting_plan.calc"))
		with (
			patch.object(order_module.frappe, "get_doc"),
			patch.object(order_module, "enqueue_tracked_job", return_value={"job_token": "O"}) as order_job,
		):
			self.assertEqual(order_module.calculate_laysheets("CO-1"), {"job_token": "O"})
		self.assertEqual(order_job.call_args.args[1:], ("SD YRP Cutting Order", "CO-1"))
		self.assertTrue(order_job.call_args.args[0].endswith("sd_yrp_cutting_order.calc_laysheets"))
		for path in (plan_job.call_args.args[0], order_job.call_args.args[0]):
			self.assertTrue(callable(frappe.get_attr(path)))

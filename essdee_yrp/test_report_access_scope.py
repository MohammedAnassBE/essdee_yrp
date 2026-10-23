from collections import Counter
from unittest import TestCase
from unittest.mock import patch

import frappe

import essdee_yrp.fabric_store.web_workspace as fabric_store
from essdee_yrp.accounts import web_capabilities as accounts
from essdee_yrp.merch import web_workspace as merch
from essdee_yrp.merch_pd import web_workspace as merch_pd
from essdee_yrp.merch_purchase import web_workspace as merch_purchase
from essdee_yrp.planning import web_workspace as planning
from essdee_yrp.web_common import report_access_scope

SCOPED_ENDPOINTS = (planning, merch_pd, merch_purchase, accounts, merch, fabric_store)


class TestReportAccessScope(TestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, frappe.session.user)
		self.user = "Administrator"
		frappe.set_user(self.user)
		self.checks = Counter()
		self.failures = set()

		def check(report_name):
			self.checks[(frappe.session.user, report_name)] += 1
			if report_name in self.failures:
				self.failures.discard(report_name)
				raise frappe.DoesNotExistError
			return report_name == "Allowed" and frappe.session.user != "Guest"

		patcher = patch.object(fabric_store, "is_report_runnable", side_effect=check)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_outside_a_scope_every_call_checks_again(self):
		for _ in range(2):
			self.assertTrue(fabric_store.can_run_report("Allowed"))
			self.assertFalse(fabric_store.can_run_report("Denied"))
		self.assertEqual(self.checks, {(self.user, "Allowed"): 2, (self.user, "Denied"): 2})

	def test_scope_checks_each_report_once_per_user(self):
		with report_access_scope():
			for _ in range(3):
				self.assertTrue(fabric_store.can_run_report("Allowed"))
				self.assertFalse(fabric_store.can_run_report("Denied"))
			frappe.set_user("Guest")
			self.assertFalse(fabric_store.can_run_report("Allowed"))
			frappe.set_user("Administrator")
			self.assertTrue(fabric_store.can_run_report("Allowed"))
		self.assertEqual(self.checks, {
			("Administrator", "Allowed"): 1, ("Administrator", "Denied"): 1, ("Guest", "Allowed"): 1,
		})

	def test_failed_check_is_not_remembered(self):
		self.failures.add("Allowed")
		with report_access_scope():
			with self.assertRaises(frappe.DoesNotExistError):
				fabric_store.can_run_report("Allowed")
			self.assertTrue(fabric_store.can_run_report("Allowed"))
		self.assertEqual(self.checks[(self.user, "Allowed")], 2)

	def test_nested_scope_joins_outer_and_answers_drop_on_exit_and_error(self):
		with report_access_scope():
			fabric_store.can_run_report("Allowed")
			with report_access_scope():
				fabric_store.can_run_report("Allowed")
			fabric_store.can_run_report("Allowed")
		self.assertIsNone(frappe.local.report_access)
		self.assertEqual(self.checks[(self.user, "Allowed")], 1)

		with self.assertRaises(RuntimeError), report_access_scope():
			fabric_store.can_run_report("Allowed")
			raise RuntimeError
		self.assertIsNone(frappe.local.report_access)
		fabric_store.can_run_report("Allowed")
		self.assertEqual(self.checks[(self.user, "Allowed")], 3)

	def test_capability_endpoints_check_each_report_once(self):
		for module in SCOPED_ENDPOINTS:
			with self.subTest(endpoint=module.__name__):
				self.checks.clear()
				module.get_capabilities()
				self.assertTrue(self.checks)
				self.assertEqual(max(self.checks.values()), 1)
				self.assertIsNone(frappe.local.report_access)

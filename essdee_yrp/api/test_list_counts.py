import json
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.desk.reportview import get_count
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.list_counts import COUNT_METHOD, MAX_FILTER_SETS, get_counts

FILTER_SETS = [[], [["desk_access", "=", 1]], [["desk_access", "=", 0]], {"name": ["like", "%Manager%"]}]


class TestListCounts(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.caller_form = frappe._dict(cmd="essdee_yrp.api.list_counts.get_counts", marker="caller")
		frappe.local.form_dict = self.caller_form
		self.previous_request = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(
			method="POST", path="/api/method/essdee_yrp.api.list_counts.get_counts", environ={}
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		frappe.local.request = self.previous_request

	def single_count(self, doctype, filters, distinct=None):
		frappe.local.form_dict = frappe._dict(doctype=doctype, filters=json.dumps(filters))
		if distinct is not None:
			frappe.local.form_dict.distinct = distinct
		try:
			return get_count()
		finally:
			frappe.local.form_dict = self.caller_form

	def test_each_filter_set_matches_a_separate_get_count(self):
		expected = [self.single_count("Role", filters) for filters in FILTER_SETS]
		self.assertEqual(get_counts("Role", FILTER_SETS), expected)
		self.assertEqual(get_counts("Role", json.dumps(FILTER_SETS)), expected)
		self.assertIs(frappe.local.form_dict, self.caller_form)

	def test_distinct_is_passed_through(self):
		filters = [["Has Role", "role", "=", "System Manager"]]
		expected = self.single_count("User", filters, distinct=True)
		self.assertEqual(get_counts("User", [filters], distinct=True), [expected])

	def test_auth_hooks_see_each_count_as_its_own_request(self):
		seen = []
		with patch(
			"yrp.yrp_partner.customer_api.guard_request", lambda: seen.append(dict(frappe.local.form_dict))
		):
			get_counts("Role", FILTER_SETS[:2])
		self.assertEqual(
			seen,
			[
				{"cmd": COUNT_METHOD, "doctype": "Role", "filters": FILTER_SETS[0]},
				{"cmd": COUNT_METHOD, "doctype": "Role", "filters": FILTER_SETS[1]},
			],
		)

	def test_hook_denial_fails_the_batch_and_restores_form_dict(self):
		def deny():
			if frappe.local.form_dict.filters:
				frappe.throw("denied", frappe.PermissionError)

		with patch("yrp.yrp_partner.customer_api.guard_request", deny):
			self.assertRaises(frappe.PermissionError, get_counts, "Role", FILTER_SETS[:2])
		self.assertIs(frappe.local.form_dict, self.caller_form)

	def test_real_partner_guard_denies_raw_ledgers_per_count(self):
		with patch("yrp.yrp_partner.customer_api.is_customer_report_user", return_value=True):
			self.assertEqual(get_counts("Role", [[]]), [self.single_count("Role", [])])
			self.assertRaises(frappe.PermissionError, get_counts, "Payment Entry", [[]])
			with patch("essdee_yrp.api.list_counts.validate_auth_via_hooks", lambda: None):
				self.assertIsInstance(get_counts("Payment Entry", [[]])[0], int)

	def test_whitelisted_overrides_apply_to_each_count(self):
		with patch.object(frappe, "override_whitelisted_method", return_value="frappe.ping") as override:
			self.assertEqual(get_counts("Role", [[], []]), ["pong", "pong"])
		override.assert_called_with(COUNT_METHOD)

	def test_response_written_counts_are_returned_without_leaking(self):
		def script_answer(method):
			frappe.response["message"] = 42

		frappe.response["message"] = "caller"
		with patch("essdee_yrp.api.list_counts.execute_cmd", script_answer):
			self.assertEqual(get_counts("Role", [[], []]), [42, 42])
		self.assertEqual(frappe.response["message"], "caller")
		frappe.response.pop("message")

	def test_invalid_filter_fails_like_get_count_and_restores_form_dict(self):
		self.assertRaises(frappe.DataError, get_counts, "Role", [[["not_a_field", "=", 1]]])
		self.assertIs(frappe.local.form_dict, self.caller_form)

	def test_permission_denied_like_get_count(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, self.single_count, "Role", [])
		self.assertRaises(frappe.PermissionError, get_counts, "Role", [[]])

	def test_rejects_non_list_and_oversized_batches(self):
		self.assertRaises(frappe.ValidationError, get_counts, "Role", {"name": "x"})
		self.assertRaises(frappe.ValidationError, get_counts, "Role", [[]] * (MAX_FILTER_SETS + 1))

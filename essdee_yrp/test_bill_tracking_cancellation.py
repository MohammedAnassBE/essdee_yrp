import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

import essdee_yrp.setup as setup
from essdee_yrp.overrides import bill_tracking as bill_api


PROPERTY_SETTER_NAME = "YRP Bill Tracking-form_status-options"


class TestBillTrackingCancellationMetadata(unittest.TestCase):
	def test_property_setter_extends_form_status_options(self):
		fixture_path = Path(__file__).with_name("fixtures") / "property_setter.json"
		fixtures = json.loads(fixture_path.read_text())
		row = next(item for item in fixtures if item["name"] == PROPERTY_SETTER_NAME)
		options = row["value"].splitlines()

		self.assertEqual(row["doc_type"], "YRP Bill Tracking")
		self.assertEqual(row["field_name"], "form_status")
		self.assertEqual(row["property"], "options")
		self.assertEqual(options.count("Pending Approval"), 1)
		self.assertEqual(options.count("Cancel Request Approved"), 1)

	def test_property_setter_is_in_hooks_allowlist(self):
		from essdee_yrp import hooks

		property_fixture = next(item for item in hooks.fixtures if item["dt"] == "Property Setter")
		allowed_names = property_fixture["filters"][0][2]
		self.assertIn(PROPERTY_SETTER_NAME, allowed_names)

	def test_setup_declares_both_cancellation_roles(self):
		self.assertIn("HR User", setup.MRP_SCHEMA_ROLES)
		self.assertIn("HR Manager", setup.MRP_SCHEMA_ROLES)

	def test_role_setup_only_inserts_missing_roles(self):
		previous_db = getattr(frappe.local, "db", None)
		frappe.local.db = MagicMock()
		frappe.local.db.exists.side_effect = lambda _doctype, name: name != "HR Manager"
		new_role = MagicMock()
		try:
			with patch.object(setup.frappe, "get_doc", return_value=new_role) as get_doc:
				setup.ensure_mrp_schema_roles()
		finally:
			frappe.local.db = previous_db

		get_doc.assert_called_once_with(
			{
				"doctype": "Role",
				"role_name": "HR Manager",
				"desk_access": 1,
			}
		)
		new_role.insert.assert_called_once_with(ignore_permissions=True)

	def test_hooks_register_controller_and_cancel_route_overrides(self):
		from essdee_yrp import hooks

		self.assertEqual(
			hooks.override_doctype_class["YRP Bill Tracking"],
			"essdee_yrp.overrides.bill_tracking.EssdeeYRPBillTracking",
		)
		self.assertEqual(
			hooks.override_whitelisted_methods[
				"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.cancel_vendor_bill"
			],
			"essdee_yrp.overrides.bill_tracking.cancel_vendor_bill",
		)


class _FakeBillTracking(bill_api.EssdeeYRPBillTracking):
	def __init__(
		self,
		*,
		name="YRP-BT-TEST",
		docstatus=1,
		form_status="Open",
		purchase_invoice=None,
		erp_purchase_invoice=None,
	):
		self.name = name
		self.docstatus = docstatus
		self.form_status = form_status
		self.purchase_invoice = purchase_invoice
		self.erp_purchase_invoice = erp_purchase_invoice
		self.cancel_reason = None
		self.bill_tracking_history = []
		self.flags = frappe._dict()
		self.saved = False

	def set(self, fieldname, value):
		setattr(self, fieldname, value)

	def save(self, ignore_permissions=False):
		self.saved = ignore_permissions

	def append(self, fieldname, values):
		row = frappe._dict(values)
		getattr(self, fieldname).append(row)
		return row

	def cancel(self):
		previous_docstatus = self.docstatus
		self.docstatus = 2
		try:
			self.before_cancel()
		except Exception:
			self.docstatus = previous_docstatus
			raise


class TestBillTrackingCancellationStateMachine(unittest.TestCase):
	def call_as(self, roles, doc, method, *args):
		previous_db = getattr(frappe.local, "db", None)
		previous_flags = getattr(frappe.local, "flags", None)
		previous_message_log = getattr(frappe.local, "message_log", None)
		previous_session = getattr(frappe.local, "session", None)
		frappe.local.db = MagicMock()
		frappe.local.db.get_value.return_value = doc.name
		frappe.local.flags = frappe._dict(in_test=True, mute_messages=True)
		frappe.local.message_log = []
		frappe.local.session = frappe._dict(user="hr-user@example.com")
		try:
			with (
				patch.object(bill_api.frappe, "get_roles", return_value=roles),
				patch.object(bill_api.frappe, "get_doc", return_value=doc),
				patch.object(bill_api.frappe.utils, "now_datetime", return_value="2026-10-03 12:00:00"),
			):
				return method(doc.name, *args)
		finally:
			frappe.local.db = previous_db
			frappe.local.flags = previous_flags
			frappe.local.message_log = previous_message_log
			frappe.local.session = previous_session

	def test_hr_user_requests_each_allowed_status(self):
		for status in ("Open", "Assigned", "Reopen", "Amended"):
			with self.subTest(status=status):
				doc = _FakeBillTracking(form_status=status)
				self.call_as(["HR User"], doc, bill_api.request_bill_cancellation)
				self.assertEqual(doc.form_status, "Pending Approval")
				self.assertTrue(doc.saved)

	def test_request_rejects_wrong_role_invalid_state_and_docstatus(self):
		cases = (
			(["Accounts User"], _FakeBillTracking(), frappe.PermissionError),
			(["HR User"], _FakeBillTracking(form_status="Pending Approval"), frappe.ValidationError),
			(["HR User"], _FakeBillTracking(docstatus=0), frappe.ValidationError),
			(["HR User"], _FakeBillTracking(docstatus=2), frappe.ValidationError),
		)
		for roles, doc, error in cases:
			with self.subTest(roles=roles, status=doc.form_status, docstatus=doc.docstatus):
				with self.assertRaises(error):
					self.call_as(roles, doc, bill_api.request_bill_cancellation)

	def test_request_rejects_each_invoice_link(self):
		for fieldname in ("purchase_invoice", "erp_purchase_invoice"):
			with self.subTest(fieldname=fieldname):
				doc = _FakeBillTracking(**{fieldname: "PI-TEST"})
				with self.assertRaises(frappe.ValidationError):
					self.call_as(["HR User"], doc, bill_api.request_bill_cancellation)

	def test_hr_manager_approves_only_pending_request(self):
		doc = _FakeBillTracking(form_status="Pending Approval")
		self.call_as(["HR Manager"], doc, bill_api.approve_bill_cancellation)
		self.assertEqual(doc.form_status, "Cancel Request Approved")

		for status in ("Open", "Cancel Request Approved"):
			with self.subTest(status=status):
				invalid = _FakeBillTracking(form_status=status)
				with self.assertRaises(frappe.ValidationError):
					self.call_as(["HR Manager"], invalid, bill_api.approve_bill_cancellation)

	def test_approval_rejects_wrong_role_and_each_invoice_link(self):
		with self.assertRaises(frappe.PermissionError):
			self.call_as(
				["HR User"],
				_FakeBillTracking(form_status="Pending Approval"),
				bill_api.approve_bill_cancellation,
			)
		for fieldname in ("purchase_invoice", "erp_purchase_invoice"):
			with self.subTest(fieldname=fieldname):
				doc = _FakeBillTracking(form_status="Pending Approval", **{fieldname: "PI-TEST"})
				with self.assertRaises(frappe.ValidationError):
					self.call_as(["HR Manager"], doc, bill_api.approve_bill_cancellation)

	def test_user_with_both_roles_still_follows_both_transitions(self):
		doc = _FakeBillTracking()
		roles = ["HR User", "HR Manager"]
		with self.assertRaises(frappe.ValidationError):
			self.call_as(roles, doc, bill_api.approve_bill_cancellation)
		self.call_as(roles, doc, bill_api.request_bill_cancellation)
		self.call_as(roles, doc, bill_api.approve_bill_cancellation)
		self.assertEqual(doc.form_status, "Cancel Request Approved")

	def test_whitelist_and_direct_cancel_reject_unapproved_state(self):
		for method in (
			bill_api.cancel_vendor_bill,
			lambda _name, _reason: _FakeBillTracking(form_status="Open").cancel(),
		):
			with self.subTest(method=method):
				doc = _FakeBillTracking(form_status="Pending Approval")
				callable_method = method
				if getattr(method, "__name__", "") == "<lambda>":
					callable_method = lambda _name, _reason, doc=doc: doc.cancel()
				with self.assertRaises(frappe.ValidationError):
					self.call_as(["HR User"], doc, callable_method, "duplicate")
				self.assertEqual(doc.docstatus, 1)

	def test_cancel_rejects_wrong_role_and_late_invoice_link(self):
		with self.assertRaises(frappe.PermissionError):
			self.call_as(
				["HR Manager"],
				_FakeBillTracking(form_status="Cancel Request Approved"),
				bill_api.cancel_vendor_bill,
				"duplicate",
			)
		for fieldname in ("purchase_invoice", "erp_purchase_invoice"):
			with self.subTest(fieldname=fieldname):
				doc = _FakeBillTracking(
					form_status="Cancel Request Approved",
					**{fieldname: "PI-LATE"},
				)
				with self.assertRaises(frappe.ValidationError):
					self.call_as(["HR User"], doc, bill_api.cancel_vendor_bill, "duplicate")

	def test_approved_hr_user_cancels_with_base_history(self):
		doc = _FakeBillTracking(form_status="Cancel Request Approved")
		self.call_as(["HR User"], doc, bill_api.cancel_vendor_bill, "duplicate bill")
		self.assertEqual(doc.docstatus, 2)
		self.assertEqual(doc.form_status, "Cancelled")
		self.assertEqual(doc.cancel_reason, "duplicate bill")
		self.assertEqual(doc.bill_tracking_history[-1].action, "Cancel")


if __name__ == "__main__":
	unittest.main()

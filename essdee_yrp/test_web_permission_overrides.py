from unittest import TestCase
from unittest.mock import call, patch

import frappe

from essdee_yrp import hooks


class FakeDoc:
	def __init__(self, name="DOC-1", allowed=True):
		self.name = name
		self.allowed = allowed
		self.checked = []

	def check_permission(self, permission):
		self.checked.append(permission)
		if not self.allowed:
			raise frappe.PermissionError


class TestWebPermissionOverrides(TestCase):
	def test_only_intended_override_functions_are_whitelisted(self):
		from essdee_yrp.overrides import bill_tracking, purchase_invoice_api

		expected_functions = {
			purchase_invoice_api: {"approve_invoice", "check_all_wo_closed"},
			bill_tracking: {
				"approve_bill_cancellation",
				"assign_vendor_bill",
				"bulk_assign_bills",
				"cancel_vendor_bill",
				"make_bill_received_acknowledgement",
				"request_bill_cancellation",
			},
		}
		for module, expected_names in expected_functions.items():
			with self.subTest(module=module.__name__):
				exposed_names = {
					name
					for name, value in vars(module).items()
					if callable(value) and value in frappe.whitelisted
				}
				self.assertEqual(exposed_names, expected_names)

	def test_imported_base_modules_are_not_rpc_namespaces(self):
		paths = (
			"essdee_yrp.overrides.purchase_invoice_api.base_purchase_invoice.approve_invoice",
			"essdee_yrp.overrides.bill_tracking.base_bill_tracking.assign_vendor_bill",
		)
		for path in paths:
			with self.subTest(path=path), self.assertRaises(ModuleNotFoundError):
				frappe.get_attr(path)

	def test_hooks_route_base_paths_to_overrides(self):
		overrides = hooks.override_whitelisted_methods
		base = "yrp.yrp.doctype"
		self.assertEqual(
			overrides[f"{base}.yrp_purchase_invoice.yrp_purchase_invoice.approve_invoice"],
			"essdee_yrp.overrides.purchase_invoice_api.approve_invoice",
		)
		self.assertEqual(
			overrides[f"{base}.yrp_bill_tracking.yrp_bill_tracking.bulk_assign_bills"],
			"essdee_yrp.overrides.bill_tracking.bulk_assign_bills",
		)
		for key in ("check_all_wo_closed",):
			self.assertIn(f"{base}.yrp_purchase_invoice.yrp_purchase_invoice.{key}", overrides)
		for key in ("assign_vendor_bill", "make_bill_received_acknowledgement"):
			self.assertIn(f"{base}.yrp_bill_tracking.yrp_bill_tracking.{key}", overrides)

	def test_approve_invoice_requires_write(self):
		from essdee_yrp.overrides import purchase_invoice_api

		document = FakeDoc(allowed=False)
		with patch.object(frappe, "get_doc", return_value=document), patch.object(
			purchase_invoice_api.base_purchase_invoice, "approve_invoice"
		) as base:
			with self.assertRaises(frappe.PermissionError):
				purchase_invoice_api.approve_invoice("PI-1", "ok")
		self.assertEqual(document.checked, ["write"])
		base.assert_not_called()

	def test_approve_invoice_delegates_when_allowed(self):
		from essdee_yrp.overrides import purchase_invoice_api

		with patch.object(frappe, "get_doc", return_value=FakeDoc()), patch.object(
			purchase_invoice_api.base_purchase_invoice, "approve_invoice"
		) as base:
			purchase_invoice_api.approve_invoice("PI-1", "ok")
		base.assert_called_once_with("PI-1", comments="ok")

	def test_check_all_wo_closed_requires_read(self):
		from essdee_yrp.overrides import purchase_invoice_api

		document = FakeDoc(allowed=False)
		with patch.object(frappe, "get_doc", return_value=document):
			with self.assertRaises(frappe.PermissionError):
				purchase_invoice_api.check_all_wo_closed("PI-1")
		self.assertEqual(document.checked, ["read"])

	def test_assign_requires_write(self):
		from essdee_yrp.overrides import bill_tracking

		document = FakeDoc(allowed=False)
		with patch.object(frappe, "get_doc", return_value=document), patch.object(
			bill_tracking.base_bill_tracking, "assign_vendor_bill"
		) as base:
			with self.assertRaises(frappe.PermissionError):
				bill_tracking.assign_vendor_bill("BT-1", "Accounts")
		base.assert_not_called()

	def test_bulk_assign_reports_skipped_rows(self):
		from essdee_yrp.overrides import bill_tracking

		def fake_assign(name, assigned_to, remarks=None):
			if name == "BT-<2>":
				frappe.throw("Closed & archived", frappe.ValidationError)
			if name == "BT-3":
				raise frappe.PermissionError("Not <allowed>")

		with (
			patch.object(bill_tracking, "assign_vendor_bill", side_effect=fake_assign),
			patch.object(bill_tracking.frappe.db, "savepoint") as savepoint,
			patch.object(bill_tracking.frappe.db, "rollback") as rollback,
			patch.object(bill_tracking.frappe, "msgprint") as msgprint,
		):
			result = bill_tracking.bulk_assign_bills(
				"Accounts",
				'[{"name": "BT-1"}, {"name": "BT-<2>"}, {"name": "BT-3"}]',
			)
		self.assertEqual(result["assigned"], ["BT-1"])
		self.assertEqual(
			result["skipped"],
			[
				{"name": "BT-<2>", "reason": "Closed & archived"},
				{"name": "BT-3", "reason": "Not <allowed>"},
			],
		)
		self.assertEqual(savepoint.call_count, 3)
		self.assertEqual(
			rollback.call_args_list,
			[
				call(save_point="bulk_assign_bill_1"),
				call(save_point="bulk_assign_bill_2"),
			],
		)
		msgprint.assert_called_once()
		message = msgprint.call_args.args[0]
		self.assertIn("BT-&lt;2&gt;", message)
		self.assertIn("Closed &amp; archived", message)
		self.assertIn("BT-3", message)
		self.assertIn("Not &lt;allowed&gt;", message)
		self.assertEqual(msgprint.call_args.kwargs["title"], "Some bills were not assigned")
		self.assertEqual(msgprint.call_args.kwargs["indicator"], "orange")

	def test_bulk_assign_reports_bare_permission_errors_without_leaking_messages(self):
		from essdee_yrp.overrides import bill_tracking

		previous_error_message = getattr(frappe.flags, "error_message", None)
		previous_message_log = getattr(frappe.local, "message_log", None)
		frappe.flags.error_message = "Outer request message"
		frappe.local.message_log = [frappe._dict(message="Outer request message")]

		def deny_assignment(name, assigned_to, remarks=None):
			if name == "BT-1":
				frappe.flags.error_message = "No permission for YRP Bill Tracking BT-1"
				frappe.local.message_log.append(frappe._dict(message="Skipped row message"))
			raise frappe.PermissionError

		try:
			with (
				patch.object(bill_tracking, "assign_vendor_bill", side_effect=deny_assignment),
				patch.object(bill_tracking.frappe.db, "savepoint"),
				patch.object(bill_tracking.frappe.db, "rollback"),
			):
				result = bill_tracking.bulk_assign_bills("Accounts", ["BT-1", "BT-2"])
			self.assertEqual(
				result["skipped"],
				[
					{"name": "BT-1", "reason": "No permission for YRP Bill Tracking BT-1"},
					{"name": "BT-2", "reason": "No permission to assign this bill"},
				],
			)
			self.assertEqual(frappe.flags.error_message, "Outer request message")
			self.assertEqual(frappe.local.message_log[0], frappe._dict(message="Outer request message"))
			self.assertEqual(len(frappe.local.message_log), 2)
			self.assertEqual(frappe.local.message_log[1].title, "Some bills were not assigned")
			self.assertNotIn("Skipped row message", str(frappe.local.message_log))
		finally:
			frappe.flags.error_message = previous_error_message
			frappe.local.message_log = previous_message_log

	def test_bulk_assign_propagates_unexpected_errors(self):
		from essdee_yrp.overrides import bill_tracking

		with (
			patch.object(bill_tracking, "assign_vendor_bill", side_effect=RuntimeError("Database unavailable")),
			patch.object(bill_tracking.frappe.db, "savepoint"),
			self.assertRaisesRegex(RuntimeError, "Database unavailable"),
		):
			bill_tracking.bulk_assign_bills("Accounts", ["BT-1"])

	def test_bulk_assign_rejects_more_than_limit(self):
		from essdee_yrp.overrides import bill_tracking

		rows = [{"name": f"BT-{index}"} for index in range(bill_tracking.BULK_ASSIGN_LIMIT + 1)]
		with self.assertRaises(frappe.ValidationError):
			bill_tracking.bulk_assign_bills("Accounts", rows)

	def test_receive_requires_read(self):
		from essdee_yrp.overrides import bill_tracking

		document = FakeDoc(allowed=False)
		with patch.object(frappe, "get_doc", return_value=document), patch.object(
			bill_tracking.base_bill_tracking, "make_bill_received_acknowledgement"
		) as base:
			with self.assertRaises(frappe.PermissionError):
				bill_tracking.make_bill_received_acknowledgement("BT-1")
		self.assertEqual(document.checked, ["read"])
		base.assert_not_called()

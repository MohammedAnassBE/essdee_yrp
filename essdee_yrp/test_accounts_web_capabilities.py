from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.www.web import WEB_DOCTYPES

CUSTOM_PERMISSION_FIELDS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"print",
	"email",
	"report",
	"import",
	"export",
	"share",
	"mask",
)


class TestAccountsHrCapabilities(TestCase):
	def test_accounts_bill_tracking_follows_doctype_permissions(self):
		from essdee_yrp.accounts import web_capabilities

		for readable, creatable in ((True, False), (True, True), (False, False)):
			with (
				self.subTest(readable=readable, creatable=creatable),
				patch.object(web_capabilities, "can_view_accounts_reports", return_value=False),
				patch.object(
					frappe,
					"has_permission",
					side_effect=lambda doctype, ptype: (
						doctype == "YRP Bill Tracking" and {"read": readable, "create": creatable}[ptype]
					),
				),
			):
				section = web_capabilities.get_capabilities()["sections"]["bill_tracking"]
				self.assertEqual(section, {"label": "Bill Tracking", "can_read": readable, "can_create": creatable})

	def test_lot_and_lotwise_item_profit_cards_follow_their_doctype_read(self):
		from essdee_yrp.accounts import web_capabilities

		readable = {"SD YRP Lot"}
		with (
			patch.object(web_capabilities, "can_view_accounts_reports", return_value=False),
			patch.object(frappe, "has_permission", side_effect=lambda doctype, ptype: doctype in readable and ptype == "read"),
		):
			sections = web_capabilities.get_capabilities()["sections"]

		self.assertEqual(sections["lots"], {"label": "Lot", "can_read": True, "can_create": False})
		self.assertEqual(
			sections["lotwise_item_profits"], {"label": "Lotwise Item Profit", "can_read": False, "can_create": False}
		)

	def test_audit_pending_gate_is_last_and_requires_accounts_role_and_plan_read(self):
		from essdee_yrp.accounts import web_capabilities

		self.assertEqual(list(web_capabilities.REPORT_GATES)[-1], "audit_pending_finishing_plans")
		self.assertEqual(list(web_capabilities.REPORT_GATES)[:-1], [
			"stock_balance", "cutting_dpr", "sewing_dpr", "finishing_dispatch", "ironing_dpr",
		])
		original_gates = web_capabilities.REPORT_GATES
		gates = {key: (label, lambda: False) for key, (label, _) in original_gates.items()}
		gates["audit_pending_finishing_plans"] = original_gates["audit_pending_finishing_plans"]
		for roles, readable, expected in (
			(["Stock User"], True, False),
			(["Accounts User"], False, False),
			(["Accounts User"], True, True),
		):
			with self.subTest(roles=roles, readable=readable), patch.object(
				web_capabilities, "REPORT_GATES", gates
			), patch.object(frappe, "get_roles", return_value=roles), patch.object(
				frappe, "has_permission", return_value=readable
			):
				self.assertEqual(
					"audit_pending_finishing_plans" in web_capabilities.get_capabilities()["reports"], expected
				)

	def test_doctypes_registered_for_web(self):
		self.assertEqual(tuple(hooks.yrp_web_doctype_catalog), WEB_DOCTYPES)
		for doctype in ("YRP Purchase Invoice", "YRP Bill Tracking", "YRP Item Price"):
			self.assertIn(doctype, WEB_DOCTYPES)
			self.assertIn(doctype, hooks.yrp_web_doctype_catalog)

	def test_accounts_hides_reports_the_owner_denies(self):
		from essdee_yrp.accounts import web_capabilities

		gates = {
			key: (label, (lambda allowed=(key == "stock_balance"): allowed))
			for key, (label, _) in web_capabilities.REPORT_GATES.items()
		}
		with patch.object(web_capabilities, "REPORT_GATES", gates), patch.object(
			frappe, "has_permission", return_value=True
		), patch("essdee_yrp.desk_web_reports.can_run_desk_report", return_value=False):
			result = web_capabilities.get_capabilities()
		self.assertEqual(list(result["reports"]), ["stock_balance"])
		self.assertTrue(result["sections"]["reports"]["can_read"])
		self.assertTrue(result["sections"]["purchase_invoices"]["can_create"])

	def test_accounts_without_any_permission(self):
		from essdee_yrp.accounts import web_capabilities

		gates = {
			key: (label, lambda: False) for key, (label, _) in web_capabilities.REPORT_GATES.items()
		}
		with patch.object(web_capabilities, "REPORT_GATES", gates), patch.object(
			frappe, "has_permission", return_value=False
		):
			result = web_capabilities.get_capabilities()
		self.assertEqual(result["reports"], {})
		self.assertFalse(result["sections"]["reports"]["can_read"])
		self.assertFalse(result["sections"]["purchase_invoices"]["can_read"])

	def test_plain_desk_user_does_not_inherit_accounts_reports(self):
		from essdee_yrp.accounts import web_capabilities

		with patch.object(frappe, "get_roles", return_value=["All", "Desk User"]), patch.object(
			frappe, "has_permission", return_value=False
		):
			result = web_capabilities.get_capabilities()

		self.assertEqual(result["reports"], {})
		self.assertFalse(result["sections"]["reports"]["can_read"])

	def test_report_gate_keys_are_exactly_the_requested(self):
		from essdee_yrp.accounts import web_capabilities

		self.assertEqual(
			list(web_capabilities.REPORT_GATES),
			["stock_balance", "cutting_dpr", "sewing_dpr", "finishing_dispatch", "ironing_dpr", "audit_pending_finishing_plans"],
		)

	def test_hr_attendance_follows_sewing_attendance(self):
		from essdee_yrp.hr import web_workspace

		sewing = {"sections": {"attendance": {"can_read": True}}, "reports": {}}
		with patch.object(web_workspace, "get_sewing_capabilities", return_value=sewing), patch.object(
			frappe, "has_permission", return_value=True
		):
			result = web_workspace.get_capabilities()
		self.assertIn("attendance", result["reports"])
		self.assertTrue(result["sections"]["bill_tracking"]["can_create"])


class TestAccountsReportGrants(TestCase):
	user = "e2e.ahr.task2@example.test"

	def setUp(self):
		if frappe.db.exists("User", self.user):
			self.fail(f"Test user already exists: {self.user}")
		self.previous_user = frappe.session.user
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.user,
				"first_name": "E2E-AHR-Task-2",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Accounts User"}],
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user(self.previous_user)
		frappe.clear_cache(user=self.user)
		if frappe.db.exists("User", self.user):
			frappe.delete_doc("User", self.user, force=True, ignore_permissions=True)
		for contact in frappe.get_all("Contact", filters={"email_id": self.user}, pluck="name"):
			frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)

	def test_patch_grants_all_accounts_reports_without_removing_existing_read(self):
		from essdee_yrp.accounts.web_capabilities import get_capabilities
		from essdee_yrp.patches.grant_accounts_user_report_access import (
			ACCOUNTS_REPORT_GRANTS,
			execute,
		)

		preexisting_read = self._custom_read_permissions(ACCOUNTS_REPORT_GRANTS)
		preexisting_permissions = self._custom_permissions(ACCOUNTS_REPORT_GRANTS)
		execute()
		execute()
		self.assertTrue(preexisting_read.issubset(self._custom_read_permissions(ACCOUNTS_REPORT_GRANTS)))
		self._assert_report_permissions(ACCOUNTS_REPORT_GRANTS, preexisting_permissions)

		frappe.set_user(self.user)
		self.assertEqual(
			list(get_capabilities()["reports"]),
			["stock_balance", "cutting_dpr", "sewing_dpr", "finishing_dispatch", "ironing_dpr", "audit_pending_finishing_plans"],
		)
		self._assert_report_endpoints_run()

	def test_accounts_user_can_read_cutting_plan_work_order(self):
		from frappe.model import get_permitted_fields

		from essdee_yrp.patches.grant_accounts_user_report_access import execute

		execute()
		frappe.set_user(self.user)

		self.assertIn(
			"work_order",
			get_permitted_fields("SD YRP Cutting Plan", permission_type="read"),
		)

	def _custom_read_permissions(self, doctypes):
		return {
			(row.parent, row.role, row.permlevel, row.if_owner)
			for row in frappe.get_all(
				"Custom DocPerm",
				filters={"parent": ["in", list(doctypes)], "read": 1},
				fields=["parent", "role", "permlevel", "if_owner"],
			)
		}

	def _custom_permissions(self, doctypes):
		fields = [
			"name",
			"parent",
			"permlevel",
			*CUSTOM_PERMISSION_FIELDS,
		]
		return {
			(row.parent, row.permlevel): row
			for row in frappe.get_all(
				"Custom DocPerm",
				filters={"parent": ["in", list(doctypes)], "role": "Accounts User", "if_owner": 0},
				fields=fields,
			)
		}

	def _assert_report_permissions(self, grants, preexisting_permissions):
		for doctype, grants_by_level in grants.items():
			for permlevel, permission_types in grants_by_level.items():
				permission = frappe.db.get_value(
					"Custom DocPerm",
					{
						"parent": doctype,
						"role": "Accounts User",
						"permlevel": permlevel,
						"if_owner": 0,
					},
					list(CUSTOM_PERMISSION_FIELDS),
					as_dict=True,
				)
				preexisting = preexisting_permissions.get((doctype, permlevel)) or {}
				for permission_type in CUSTOM_PERMISSION_FIELDS:
					expected = bool(
						preexisting.get(permission_type) or permission_type in permission_types
					)
					self.assertEqual(
						bool(permission.get(permission_type)),
						expected,
						f"{doctype} at level {permlevel}: {permission_type}",
					)
				for permission_type in ("export", "print", "email", "share"):
					self.assertEqual(
						bool(permission.get(permission_type)),
						bool(preexisting.get(permission_type)),
						f"{doctype} at level {permlevel}: {permission_type}",
					)
		report = frappe.get_doc("Report", "YRP Stock Balance")
		custom_role_name = frappe.db.get_value(
			"Custom Role", {"report": report.name}, "name"
		)
		self.assertTrue(custom_role_name)
		custom_role_rows = [
			row.role for row in frappe.get_doc("Custom Role", custom_role_name).roles if row.role
		]
		custom_roles = set(custom_role_rows)
		standard_roles = {row.role for row in report.roles if row.role}
		self.assertTrue(standard_roles.issubset(custom_roles))
		self.assertIn("Accounts User", custom_roles)
		self.assertEqual(custom_role_rows.count("Accounts User"), 1)

	def _assert_report_endpoints_run(self):
		from frappe.desk.query_report import run

		from essdee_yrp.cutting.reports import get_daily_production_report
		from essdee_yrp.finishing.web_reports import get_dispatch_report, get_ironing_dpr
		from essdee_yrp.sewing.read_models import get_sewing_plan_dpr_data

		checks = {
			"stock balance": lambda: run("YRP Stock Balance", {"to_date": "1900-01-01"}),
			"cutting DPR": lambda: get_daily_production_report("2099-01-01", ""),
			"sewing DPR": lambda: get_sewing_plan_dpr_data("E2E-AHR-NO-SUPPLIER", "2099-01-01"),
			"finishing dispatch": lambda: get_dispatch_report("2099-01-01", "2099-01-01"),
			"ironing DPR": lambda: get_ironing_dpr(date="2099-01-01"),
		}
		for label, action in checks.items():
			with self.subTest(report=label):
				try:
					action()
				except frappe.PermissionError as error:
					self.fail(f"{label} rejected Accounts User: {error}")
				except frappe.ValidationError:
					pass


class TestAccountsReportGrantInstallation(TestCase):
	def test_grant_preserves_existing_unrestricted_permission_when_owner_rule_exists(self):
		from essdee_yrp.patches import grant_accounts_user_report_access as report_grants

		permissions = {
			"owner-only": {"if_owner": 1, "read": 0, "report": 0},
			"unrestricted": {
				"if_owner": 0,
				"read": 0,
				"report": 0,
				"write": 1,
				"export": 1,
				"print": 1,
				"email": 1,
				"share": 1,
			},
		}
		expected_filters = {
			"parent": "YRP Stock Ledger Entry",
			"role": "Accounts User",
			"permlevel": 0,
			"if_owner": 0,
		}

		def get_permission(doctype, filters, fields, as_dict):
			self.assertEqual(doctype, "Custom DocPerm")
			self.assertEqual(filters, expected_filters)
			self.assertEqual(fields, ["name", "read", "report"])
			self.assertTrue(as_dict)
			name = next(
				name
				for name, permission in permissions.items()
				if permission["if_owner"] == filters["if_owner"]
			)
			return frappe._dict(name=name, **permissions[name])

		def set_permission_values(doctype, name, values):
			self.assertEqual(doctype, "Custom DocPerm")
			permissions[name].update(values)

		with (
			patch.object(frappe.db, "get_value", side_effect=get_permission),
			patch.object(frappe.db, "set_value", side_effect=set_permission_values),
			patch.object(report_grants, "add_permission") as add_permission,
			patch.object(frappe, "clear_cache"),
		):
			report_grants._grant_permissions("YRP Stock Ledger Entry", 0, ("read", "report"))

		add_permission.assert_not_called()
		self.assertEqual(permissions["owner-only"], {"if_owner": 1, "read": 0, "report": 0})
		self.assertEqual(
			permissions["unrestricted"],
			{
				"if_owner": 0,
				"read": 1,
				"report": 1,
				"write": 1,
				"export": 1,
				"print": 1,
				"email": 1,
				"share": 1,
			},
		)

	def test_new_grant_sets_only_requested_permissions(self):
		from essdee_yrp.patches import grant_accounts_user_report_access as report_grants

		with (
			patch.object(frappe.db, "get_value", return_value=None),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(report_grants, "add_permission", return_value="new-permission") as add_permission,
			patch.object(frappe, "clear_cache"),
		):
			report_grants._grant_permissions("YRP Stock Ledger Entry", 0, ("read", "report"))

		add_permission.assert_called_once_with("YRP Stock Ledger Entry", "Accounts User", 0)
		values = set_value.call_args.args[2]
		self.assertEqual(
			values,
			{
				permission_type: int(permission_type in ("read", "report"))
				for permission_type in CUSTOM_PERMISSION_FIELDS
			},
		)

	def test_rerun_does_not_update_an_existing_complete_grant(self):
		from essdee_yrp.patches import grant_accounts_user_report_access as report_grants

		permission = frappe._dict(name="existing-permission", read=1, report=1)
		with (
			patch.object(frappe.db, "get_value", return_value=permission),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(report_grants, "add_permission") as add_permission,
			patch.object(frappe, "clear_cache"),
		):
			report_grants._grant_permissions("YRP Stock Ledger Entry", 0, ("read", "report"))

		add_permission.assert_not_called()
		set_value.assert_not_called()

	def test_after_install_runs_accounts_grants_in_install_mode(self):
		import essdee_yrp.setup as setup

		with ExitStack() as stack:
			for name in dir(setup):
				if name.startswith("ensure_") and callable(getattr(setup, name)):
					stack.enter_context(patch.object(setup, name))
			stack.enter_context(patch("essdee_yrp.patches.seed_role_settings.execute"))
			stack.enter_context(patch("essdee_yrp.patches.seed_default_dia_attribute.execute"))
			grants = stack.enter_context(
				patch("essdee_yrp.patches.grant_accounts_user_report_access.execute")
			)
			stack.enter_context(
				patch("essdee_yrp.purchase_order_approval.ensure_purchase_order_approval_route")
			)
			setup.after_install()

		grants.assert_called_once_with(allow_missing_report=True)

	def test_install_mode_grants_doctypes_when_stock_report_is_missing(self):
		from essdee_yrp.patches import grant_accounts_user_report_access as report_grants

		with (
			patch.object(report_grants, "_grant_permissions") as grant_permissions,
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_doc") as get_doc,
		):
			report_grants.execute(allow_missing_report=True)

		expected_grants = sum(len(grants) for grants in report_grants.ACCOUNTS_REPORT_GRANTS.values())
		self.assertEqual(grant_permissions.call_count, expected_grants)
		get_doc.assert_not_called()

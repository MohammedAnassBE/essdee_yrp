from importlib import import_module
from importlib.util import find_spec
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.www.web import WEB_DOCTYPES

DOCTYPE = "SD YRP Finishing Plan"
MODULE = "essdee_yrp.finishing.web_workspace"


class FakePlan(frappe._dict):
	doctype = DOCTYPE

	def check_permission(self, ptype="read"):
		if ptype in self.get("denied", ()):
			raise frappe.PermissionError(ptype)

	def get(self, key, default=None):
		return super().get(key, default)


def make_plan(**values):
	defaults = {
		"name": "FP-0001",
		"lot": "LOT-1",
		"item": "TSHIRT",
		"work_order": "WO-1",
		"fp_status": "Planned",
		"modified": "2026-10-09 10:00:00",
		"production_detail": "IPD-1",
		"finishing_process": "Finishing",
		"finishing_plan_dispatch_logs": [],
	}
	defaults.update(values)
	return FakePlan(defaults)


class TestFinishingWebWorkspace(TestCase):
	def test_inward_print_caches_size_and_matches_desk_url(self):
		workspace = self._workspace()
		plan = make_plan(name="FP/1 & 2")
		with (
			patch.object(workspace, "get_plan", return_value=plan),
			patch.object(workspace, "get_plan_actions", return_value={"print_inward": True}),
			patch.object(workspace.transactions, "get_primary_values", return_value=["S", "M"]),
			patch.object(workspace.inward, "cache_selected_size") as cache,
		):
			payload = workspace.prepare_inward_print(plan.name, "M")
		cache.assert_called_once_with("inward_pf_size", "M", plan.name)
		self.assertEqual(payload["url"], "/printview?doctype=SD+YRP+Finishing+Plan&name=FP%2F1+%26+2&trigger_print=1&format=Essdee+Finishing+Plan+Inward+Report&no_letterhead=1")

	def test_inward_print_rejects_denied_action_and_invalid_size_before_caching(self):
		workspace = self._workspace()
		for allowed, size in ((False, "M"), (True, "Unknown")):
			with (
				patch.object(workspace, "get_plan", return_value=make_plan()),
				patch.object(workspace, "get_plan_actions", return_value={"print_inward": allowed}),
				patch.object(workspace.transactions, "get_primary_values", return_value=["M"]),
				patch.object(workspace.inward, "cache_selected_size") as cache,
				patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			):
				with self.assertRaises(frappe.ValidationError):
					workspace.prepare_inward_print("FP-1", size)
				cache.assert_not_called()

	def _workspace(self):
		self.assertIsNotNone(find_spec(MODULE), "The Finishing web workspace must exist")
		return import_module(MODULE)

	def _permissions(self, denied=(), allowed=None):
		def has_permission(doctype, ptype="read", *args, **kwargs):
			if allowed is not None:
				return (doctype, ptype) in allowed
			return (doctype, ptype) not in denied

		return patch.object(frappe, "has_permission", side_effect=has_permission)

	def _roles(self, *roles, accounts_role="Accounts User", merch_role="Merch User"):
		settings = {"accounts_user_role": accounts_role, "merch_user_role": merch_role}
		return (
			patch.object(frappe, "get_roles", return_value=list(roles)),
			patch.object(
				frappe.db, "get_single_value", side_effect=lambda _doctype, field: settings.get(field)
			),
		)

	def _actions(self, plan, *roles, denied=()):
		workspace = self._workspace()
		roles_patch, settings_patch = self._roles(*roles)
		with self._permissions(denied=denied), roles_patch, settings_patch:
			return workspace.get_plan_actions(plan)

	def test_capabilities_expose_the_finishing_cards(self):
		with self._permissions():
			payload = self._workspace().get_capabilities()
		self.assertEqual(
			list(payload["sections"]),
			[
				"plans",
				"reports",
				"rework_details",
				"rework_groups",
				"dispatches",
				"work_orders",
				"delivery_challans",
				"goods_received_notes",
			],
		)
		self.assertEqual(payload["sections"]["plans"]["doctype"], DOCTYPE)
		self.assertEqual(payload["sections"]["dispatches"]["doctype"], "SD YRP Finishing Plan Dispatch")
		self.assertEqual(
			list(payload["sections"]["reports"]["reports"]),
			[
				"stock_balance",
				"packing_dpr",
				"dispatch_report",
				"ironing_dpr",
				"finishing_plan_report",
				"rejection_details",
				"rework_completion",
				"lot_cut_quantity",
				"inhouse_quantity",
				"grn_report",
				"grn_summary",
				"dc_report",
				"stock_entry_report",
				"stock_reconciliation_report",
				"stock_update_report",
			],
		)

	def test_work_orders_card_follows_work_order_read_and_create(self):
		with self._permissions(allowed={("YRP Work Order", "read")}):
			sections = self._workspace().get_capabilities()["sections"]
		self.assertEqual(
			sections["work_orders"],
			{"label": "Work Orders", "doctype": "YRP Work Order", "can_read": True, "can_create": False},
		)
		with self._permissions(allowed={("YRP Work Order", "read"), ("YRP Work Order", "create")}):
			self.assertTrue(self._workspace().get_capabilities()["sections"]["work_orders"]["can_create"])
		with self._permissions(denied={("YRP Work Order", "read")}):
			self.assertNotIn("work_orders", self._workspace().get_capabilities()["sections"])

	def test_lot_cut_quantity_follows_finishing_report_access(self):
		with self._permissions(denied={("SD YRP Cutting Plan", "read")}):
			reports = self._workspace().get_capabilities()["sections"]["reports"]["reports"]
		self.assertEqual(
			reports["lot_cut_quantity"],
			{"label": "Lot Cut Quantity", "can_read": True, "can_report": True, "can_read_cutting_plan": False},
		)
		with self._permissions(allowed={("SD YRP Cutting Plan", "read")}):
			self.assertFalse(self._workspace().has_report_access())
			self.assertNotIn("reports", self._workspace().get_capabilities()["sections"])

	def test_inhouse_quantity_requires_work_order_and_lot_read(self):
		with self._permissions():
			reports = self._workspace().get_capabilities()["sections"]["reports"]["reports"]
		self.assertEqual(
			reports["inhouse_quantity"], {"label": "In-house Quantity", "can_read": True, "can_report": True}
		)
		for missing in ("YRP Work Order", "SD YRP Lot"):
			with self.subTest(missing=missing), self._permissions(denied={(missing, "read")}):
				reports = self._workspace().get_capabilities()["sections"]["reports"]["reports"]
				self.assertNotIn("inhouse_quantity", reports)

	def test_capabilities_omit_unreadable_sections(self):
		with self._permissions(allowed=set()):
			payload = self._workspace().get_capabilities()
		self.assertEqual(payload["sections"], {})

	def test_each_report_follows_its_source_permission(self):
		cases = {
			("YRP Stock Ledger Entry", "report"): "stock_balance",
			("YRP Goods Received Note", "read"): "packing_dpr",
			("YRP Delivery Challan", "read"): "ironing_dpr",
			(DOCTYPE, "report"): "finishing_plan_report",
			("SD YRP GRN Rework Item", "read"): "rejection_details",
		}
		for denied, report in cases.items():
			with self.subTest(denied=denied):
				with self._permissions(denied={denied}):
					reports = (
						self._workspace().get_capabilities()["sections"].get("reports", {}).get("reports", {})
					)
				self.assertNotIn(report, reports)

	def test_rework_cards_need_rework_read_and_expose_write(self):
		with self._permissions(denied={("SD YRP GRN Rework Item", "write")}):
			sections = self._workspace().get_capabilities()["sections"]
		self.assertTrue(sections["rework_details"]["can_read"])
		self.assertFalse(sections["rework_groups"]["can_write"])
		with self._permissions(denied={("SD YRP GRN Rework Item", "read")}):
			sections = self._workspace().get_capabilities()["sections"]
		self.assertNotIn("rework_details", sections)
		self.assertNotIn("rework_groups", sections)

	def test_dispatch_card_flags_follow_doctype_permissions(self):
		with self._permissions(denied={("SD YRP Finishing Plan Dispatch", "submit")}):
			dispatches = self._workspace().get_capabilities()["sections"]["dispatches"]
		self.assertTrue(dispatches["can_create"])
		self.assertFalse(dispatches["can_submit"])

	def test_finishing_doctypes_are_registered_in_both_web_catalogs(self):
		for doctype in (DOCTYPE, "SD YRP Finishing Plan Dispatch"):
			for catalog in (WEB_DOCTYPES, hooks.yrp_web_doctype_catalog):
				with self.subTest(doctype=doctype, catalog=catalog):
					self.assertIn(doctype, catalog)

	def test_endpoints_are_whitelisted_for_authenticated_users_only(self):
		workspace = self._workspace()
		for endpoint in (
			workspace.get_capabilities,
			workspace.get_plan_workspace,
			workspace.get_plan_tab,
			workspace.execute_plan_command,
			workspace.prepare_inward_print,
		):
			with self.subTest(endpoint=endpoint.__name__):
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertNotIn(endpoint, frappe.guest_methods)

	def test_audit_request_is_offered_only_for_dispatched_plans(self):
		for status, expected in (("Planned", False), ("Dispatched", True), ("Fully Dispatched", True)):
			with self.subTest(status=status):
				actions = self._actions(make_plan(fp_status=status))
				self.assertIs(actions["request_audit"], expected)

	def test_audit_completion_needs_ready_status_and_accounts_role(self):
		ready = make_plan(fp_status="Ready for Audit")
		self.assertTrue(self._actions(ready, "Accounts User")["complete_audit"])
		self.assertFalse(self._actions(ready, "Stock User")["complete_audit"])
		self.assertFalse(self._actions(make_plan(fp_status="Dispatched"), "Accounts User")["complete_audit"])

	def test_ocr_completion_needs_audited_status_and_system_manager(self):
		for status in ("Audit Completed", "Auto Closed"):
			with self.subTest(status=status):
				self.assertTrue(self._actions(make_plan(fp_status=status), "System Manager")["complete_ocr"])
				self.assertFalse(self._actions(make_plan(fp_status=status), "Stock User")["complete_ocr"])

	def test_locked_plans_disable_entry_actions(self):
		for status in ("Auto Closed", "OCR Completed", "P&L Submitted"):
			with self.subTest(status=status):
				actions = self._actions(make_plan(fp_status=status), "System Manager")
				for key in (
					"request_audit",
					"complete_audit",
					"fetch_rejected_quantity",
					"cancel_linked_document",
					"print_inward",
				):
					self.assertFalse(actions[key], key)

	def test_write_permission_gates_plan_mutations(self):
		actions = self._actions(make_plan(fp_status="Dispatched"), denied={(DOCTYPE, "write")})
		self.assertFalse(actions["request_audit"])
		self.assertFalse(actions["fetch_rejected_quantity"])
		self.assertFalse(actions["cancel_linked_document"])

	def test_p_and_l_is_visible_to_merch_role_and_managed_after_ocr(self):
		self.assertFalse(self._actions(make_plan(), "Stock User")["view_p_and_l"])
		self.assertTrue(self._actions(make_plan(), "Merch User")["view_p_and_l"])
		self.assertFalse(self._actions(make_plan(), "Merch User")["manage_p_and_l"])
		self.assertTrue(self._actions(make_plan(fp_status="OCR Completed"), "Merch User")["manage_p_and_l"])

	def test_linked_documents_parse_plan_json_lists(self):
		plan = make_plan(
			dc_list='{"DC-1": "2026-10-01 10:00:00"}',
			grn_list='{"GRN-1": "2026-10-02 10:00:00"}',
			incomplete_transfer_dc_list='{"DC-9": true}',
		)
		groups = {group["key"]: group for group in self._workspace().get_linked_documents(plan)}
		self.assertEqual(groups["dc_list"]["documents"], [{"name": "DC-1", "date": "2026-10-01 10:00:00"}])
		self.assertEqual(groups["dc_list"]["doctype"], "YRP Delivery Challan")
		self.assertTrue(groups["dc_list"]["cancellable"])
		self.assertEqual(groups["incomplete_transfer_dc_list"]["documents"], [{"name": "DC-9", "date": ""}])
		self.assertFalse(groups["incomplete_transfer_dc_list"]["cancellable"])
		self.assertEqual(groups["stock_entry_list"]["documents"], [])

	def test_linked_documents_are_cancellable_only_with_doctype_cancel_permission(self):
		plan = make_plan(
			lot_transfer_list='{"LT-1": "2026-10-01 10:00:00"}',
			stock_entry_list='{"STE-1": "2026-10-01 10:00:00"}',
		)
		with self._permissions(denied={("SD YRP Lot Transfer", "cancel")}) as has_permission:
			groups = {group["key"]: group for group in self._workspace().get_linked_documents(plan)}
		self.assertFalse(groups["lot_transfer_list"]["cancellable"])
		self.assertTrue(groups["stock_entry_list"]["cancellable"])
		self.assertTrue(groups["ironing_excess_list"]["cancellable"])
		cancel_checks = [call.args[0] for call in has_permission.call_args_list]
		self.assertEqual(len(cancel_checks), len(set(cancel_checks)), "one cancel check per doctype")

	def test_cancel_linked_document_leaves_the_permission_check_to_the_document(self):
		plan = make_plan(lot_transfer_list='{"LT-1": "2026-10-01"}')
		with (
			patch("essdee_yrp.finishing.transactions.cancel_document") as cancel_document,
			patch.object(self._workspace(), "has_cancel_permission", return_value=False),
		):
			self._execute(plan, "cancel_linked_document", {"doctype": "SD YRP Lot Transfer", "name": "LT-1"})
		cancel_document.assert_called_once_with("SD YRP Lot Transfer", "LT-1")

	def _execute(self, plan, command, payload=None, expected_modified=None, roles=("Stock User",)):
		workspace = self._workspace()
		roles_patch, settings_patch = self._roles(*roles)
		with (
			self._permissions(),
			roles_patch,
			settings_patch,
			patch.object(frappe, "get_doc", return_value=plan),
			patch.object(workspace, "get_plan_workspace", return_value={"record": {"name": plan.name}}),
		):
			return workspace.execute_plan_command(
				plan.name, command, payload, expected_modified or plan.modified
			)

	def test_unknown_command_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._execute(make_plan(), "delete_everything")

	def test_stale_command_is_rejected(self):
		with self.assertRaises(frappe.TimestampMismatchError):
			self._execute(
				make_plan(fp_status="Dispatched"), "request_audit", expected_modified="2020-01-01 00:00:00"
			)

	def test_unavailable_command_is_rejected_on_the_server(self):
		with self.assertRaises(frappe.ValidationError):
			self._execute(make_plan(fp_status="Planned"), "request_audit")

	def test_request_audit_delegates_to_the_closure_service(self):
		with patch("essdee_yrp.finishing.closure.request_audit") as request_audit:
			result = self._execute(make_plan(fp_status="Dispatched"), "request_audit")
		request_audit.assert_called_once_with("FP-0001")
		self.assertEqual(result["record"], {"name": "FP-0001"})

	def test_cancel_linked_document_requires_plan_ownership(self):
		plan = make_plan(dc_list='{"DC-1": "2026-10-01"}')
		with patch("essdee_yrp.finishing.transactions.cancel_document") as cancel_document:
			with self.assertRaises(frappe.ValidationError):
				self._execute(
					plan, "cancel_linked_document", {"doctype": "YRP Delivery Challan", "name": "DC-OTHER"}
				)
			self._execute(plan, "cancel_linked_document", {"doctype": "YRP Delivery Challan", "name": "DC-1"})
		cancel_document.assert_called_once_with("YRP Delivery Challan", "DC-1")

	def test_unknown_tab_is_rejected(self):
		with (
			self._permissions(),
			patch.object(frappe, "get_doc", return_value=make_plan()),
			self.assertRaises(frappe.ValidationError),
		):
			self._workspace().get_plan_tab("FP-0001", "unknown")

	def test_tab_requires_plan_read_permission(self):
		with (
			patch.object(frappe, "get_doc", return_value=make_plan(denied=("read",))),
			self.assertRaises(frappe.PermissionError),
		):
			self._workspace().get_plan_tab("FP-0001", "details")

	def _tab(self, tab, plan=None, roles=("Stock User",)):
		"""Load a tab with every view builder stubbed; return the payload and the builders called."""
		context = {"primary_values": ["S", "M"], "is_set_item": 0, "set_attr": None}
		quantity = {key: {"key": key} for key in ("finishing_inward", "finishing_qty", "finishing_ironing", "pack_return")}
		results = {
			"get_ipd_context": context,
			"build_quantity_views": quantity,
			"build_inward_details": {"key": "inward_details"},
			"build_rework_details": {"key": "rework_details"},
			"build_rejection_details": {"key": "rejection_details"},
			"build_old_lot_matrices": {"old_lot_given_matrix": {"groups": []}, "old_lot_received_matrix": {"groups": []}},
			"get_packed_qty": {"sizes": {}},
		}
		called = []

		def stub(name):
			def builder(*args):
				called.append(name)
				return results[name]

			return builder

		roles_patch, settings_patch = self._roles(*roles)
		patches = [patch(f"essdee_yrp.finishing.views.{name}", side_effect=stub(name)) for name in results]
		patches.append(patch("essdee_yrp.finishing.views.build_plan_views", side_effect=AssertionError("full build")))
		with (
			self._permissions(),
			roles_patch,
			settings_patch,
			patch.object(frappe, "get_doc", return_value=plan or make_plan()),
			patch("essdee_yrp.finishing.web_workspace.get_source_entries", return_value=[]),
			patch("essdee_yrp.finishing.web_workspace.ocr.get_ocr_details", return_value={}),
			patch("essdee_yrp.finishing.web_workspace.transactions.get_primary_values", return_value=["S", "M"]),
			patch("essdee_yrp.finishing.web_workspace.packing.get_ipd_packing_config", return_value={}),
		):
			for item in patches:
				item.start()
			try:
				payload = self._workspace().get_plan_tab("FP-0001", tab)
			finally:
				for item in reversed(patches):
					item.stop()
		return payload, set(called)

	def test_details_tab_returns_the_desk_view_model(self):
		payload, _called = self._tab("details")
		self.assertEqual(
			payload,
			{
				"primary_values": ["S", "M"],
				"data": {"key": "finishing_inward"},
				"is_set_item": 0,
				"set_attr": None,
				"process": "Finishing",
			},
		)

	def test_each_tab_builds_only_its_own_view(self):
		context = {"get_ipd_context"}
		expected = {
			"details": context | {"build_quantity_views"},
			"item_details": context | {"build_quantity_views", "build_rework_details"},
			"inward": context | {"build_inward_details"},
			"ironing_excess": context | {"build_quantity_views"},
			"pack_return": context | {"build_quantity_views"},
			"old_lot": context | {"build_old_lot_matrices"},
			"ocr": context,
			"rejection": context | {"build_rejection_details"},
			"grn": {"get_packed_qty"},
		}
		for tab, builders in expected.items():
			with self.subTest(tab=tab):
				_payload, called = self._tab(tab, plan=make_plan(fp_status="OCR Completed"))
				self.assertEqual(called, builders)

	def test_tab_payloads_keep_the_desk_keys(self):
		self.assertEqual(self._tab("item_details")[0]["rework_details"], {"key": "rework_details"})
		self.assertEqual(self._tab("inward")[0]["data"], {"key": "inward_details"})
		self.assertEqual(self._tab("ironing_excess")[0]["data"], {"key": "finishing_ironing"})
		self.assertEqual(self._tab("ironing_excess")[0]["entries"], [])
		self.assertEqual(self._tab("pack_return")[0]["data"], {"key": "pack_return"})
		self.assertEqual(self._tab("rejection")[0], {"key": "rejection_details"})
		self.assertEqual(self._tab("ocr")[0], {"ocr_data": {}, "primary_values": ["S", "M"], "item": "TSHIRT"})

	def test_tabs_and_workspace_reuse_attribute_reads_within_one_request(self):
		from yrp.attribute_read_context import read_value

		loads = []

		def read_twice(*_args):
			for _ in range(2):
				read_value("p12-test", "key", lambda: loads.append(1) or {"value": 1})
			return {"print_inward": False, "create_entries": False}

		workspace = self._workspace()
		with (
			self._permissions(),
			patch.object(frappe, "get_doc", return_value=make_plan()),
			patch.dict(workspace.TAB_LOADERS, {"p12": read_twice}),
		):
			workspace.get_plan_tab("FP-0001", "p12")
		self.assertEqual(len(loads), 1)
		with (
			patch.object(workspace, "get_plan", return_value=make_plan()),
			patch.object(workspace, "get_plan_actions", side_effect=read_twice),
			patch.object(workspace, "get_document_print_formats", return_value=[]),
			patch.object(frappe, "has_permission", return_value=True),
		):
			workspace.get_plan_workspace("FP-0001")
		self.assertEqual(len(loads), 2)
		read_value("p12-test", "key", lambda: loads.append(1))
		self.assertEqual(len(loads), 3, "the scope must not outlive the request")

	def test_old_lot_tab_skips_available_balances_for_closed_plans(self):
		with patch("essdee_yrp.finishing.old_lot.fetch_from_old_lot") as fetch_from_old_lot:
			payload, _called = self._tab("old_lot", plan=make_plan(fp_status="OCR Completed"))
		fetch_from_old_lot.assert_not_called()
		self.assertIsNone(payload["available"])

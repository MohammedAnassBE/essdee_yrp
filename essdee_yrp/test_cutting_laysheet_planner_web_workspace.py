import json
from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting.planner_workspace import (
	_normalise_results,
	_normalise_values,
	_safe_error,
	get_editor,
	get_status,
	save,
	select_result,
	start_optimization,
)


DOCTYPE = "SD YRP Cutting Laysheet Planner"


def order_row(name="ORDER-1", size="S", qty=25):
	return frappe._dict(name=name, idx=1, size=size, qty=qty)


def planner_doc(status="Not Started", **values):
	doc = frappe._dict({
		"doctype": DOCTYPE,
		"name": "CLP-2026-00001",
		"modified": "2026-10-03 12:00:00",
		"docstatus": 0,
		"lot": "LOT-001",
		"item": "STYLE-001",
		"description": "October cutting plan",
		"max_plies": 100,
		"max_pieces": 12,
		"tolerance_pct": 3,
		"max_lays": 8,
		"tubular": 0,
		"order_details": [order_row(), order_row("ORDER-2", "M", 50)],
		"optimization_status": status,
		"optimization_started_on": None,
		"optimization_completed_on": None,
		"optimization_error": None,
		"optimization_input_json": None,
		"result_json": None,
		"selected_strategy": None,
		"total_lays": 0,
		"total_order": 0,
		"total_cut": 0,
		"overcut": 0,
		"overcut_pct": 0,
		"undercut": 0,
		"undercut_pct": 0,
		**values,
	})
	doc.get = lambda key, default=None: dict.get(doc, key, default)
	return doc


def planner_values():
	return {
		"lot": "LOT-001",
		"item": "STYLE-001",
		"description": "October cutting plan",
		"max_plies": 100,
		"max_pieces": 12,
		"tolerance_pct": 3,
		"max_lays": 8,
		"tubular": 0,
		"order_details": [
			{"name": "ORDER-1", "size": "S", "qty": 25},
			{"name": "ORDER-2", "size": "M", "qty": 50},
		],
	}


def result_payload():
	return {
		"input": {"order": {"S": 25, "M": 50}, "max_plies": 100, "max_pieces": 12, "tolerance_pct": 3, "max_lays": 8, "tubular": False},
		"optimizer_version": "4.1.0",
		"results": [{
			"strategy": "direct_integer_search",
			"strategy_description": "Direct search",
			"success": True,
			"status": "success",
			"summary": {"total_lays": 1, "unique_markers": 1, "avg_pieces_per_ply": 3, "total_order": 75, "total_cut": 75, "overcut": 0, "overcut_pct": 0, "undercut": 0, "undercut_pct": 0},
			"per_size": {"S": {"order": 25, "cut": 25, "diff": 0, "pct": 0}, "M": {"order": 50, "cut": 50, "diff": 0, "pct": 0}},
			"lays": [{"lay_no": 1, "plies": 25, "ratio": {"S": 1, "M": 2}, "pieces_per_ply": 3, "total_pieces": 75, "cut_per_size": {"S": 25, "M": 50}}],
		}],
		"failed": [{"strategy": "cp_sat", "success": False, "status": "timeout", "error": "Timed out"}],
	}


class TestCuttingLaySheetPlannerWebWorkspace(TestCase):
	def test_values_preserve_stable_rows_allow_zero_and_reject_invalid_inputs(self):
		doc = planner_doc()
		values = planner_values()
		values["order_details"][0]["qty"] = 0
		normalised = _normalise_values(values, doc)
		self.assertEqual(normalised["order_details"][0], {"name": "ORDER-1", "size": "S", "qty": 0})

		duplicate = deepcopy(values)
		duplicate["order_details"][1]["size"] = "S"
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(duplicate, doc)
		all_zero = deepcopy(values)
		all_zero["order_details"][1]["qty"] = 0
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(all_zero, doc)
		bad_limit = deepcopy(values)
		bad_limit["max_lays"] = 0
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(bad_limit, doc)
		unknown = deepcopy(values)
		unknown["order_details"][0]["name"] = "FOREIGN"
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(unknown, doc)
		with self.assertRaises(frappe.ValidationError):
			_normalise_values({**values, "optimization_status": "Completed"}, doc)

	def test_editor_defaults_and_active_input_lock_are_permission_aware(self):
		new_doc = planner_doc(name=None, order_details=[], tolerance_pct=None, max_lays=None)
		active = planner_doc(status="Running")
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.new_doc", return_value=new_doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
		):
			payload = get_editor()
		self.assertEqual(payload["record"]["tolerance_pct"], 3)
		self.assertEqual(payload["record"]["max_lays"], 8)
		self.assertTrue(payload["permissions"]["can_create"])
		self.assertTrue(payload["actions"]["can_edit_inputs"])

		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=active),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
		):
			payload = get_editor("CLP-2026-00001")
		self.assertFalse(payload["actions"]["can_edit_inputs"])
		self.assertFalse(payload["actions"]["can_optimize"])

	def test_save_creates_draft_and_rejects_active_or_stale_edit(self):
		new_doc = MagicMock()
		new_doc.name = "CLP-2026-00002"
		new_doc.order_details = []
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.planner_workspace.frappe.new_doc", return_value=new_doc),
			patch("essdee_yrp.cutting.planner_workspace.get_editor", return_value={"record": {"name": "CLP-2026-00002"}}),
		):
			payload = save({**planner_values(), "order_details": [{"size": "S", "qty": 25}]})
		new_doc.insert.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], "CLP-2026-00002")

		for doc, modified in [(planner_doc(status="Queued"), "2026-10-03 12:00:00"), (planner_doc(modified="newer"), "older")]:
			with self.subTest(status=doc.optimization_status):
				with (
					patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
					patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
				):
					with self.assertRaises((frappe.ValidationError, frappe.TimestampMismatchError)):
						save(planner_values(), "CLP-2026-00001", modified)

	def test_start_optimization_checks_staleness_permission_and_delegates_native(self):
		doc = planner_doc()
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.planner_workspace.native.optimize", return_value={"status": "Queued"}) as optimize,
			patch("essdee_yrp.cutting.planner_workspace.get_status", return_value={"status": "Queued"}),
		):
			payload = start_optimization("CLP-2026-00001", doc.modified)
		optimize.assert_called_once_with("CLP-2026-00001")
		self.assertEqual(payload["status"], "Queued")

		doc.optimization_status = "Running"
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.planner_workspace.native.optimize") as optimize,
		):
			with self.assertRaises(frappe.ValidationError):
				start_optimization("CLP-2026-00001", doc.modified)
		optimize.assert_not_called()

	def test_status_projects_safe_terminal_state_and_retry_flags(self):
		doc = planner_doc(status="Failed", optimization_error="Traceback (most recent call last):\n  File /secret/path.py")
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
		):
			payload = get_status("CLP-2026-00001")
		self.assertEqual(payload["error_message"], "Lay optimization failed. Review the inputs and try again.")
		self.assertTrue(payload["actions"]["can_retry"])
		self.assertFalse(payload["actions"]["should_poll"])

		doc.optimization_status = "Queued"
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
		):
			payload = get_status("CLP-2026-00001")
		self.assertTrue(payload["actions"]["should_poll"])
		self.assertFalse(payload["actions"]["can_optimize"])

	def test_result_projection_drops_unknown_sizes_and_sanitises_failures(self):
		payload = result_payload()
		payload["results"].append({
			**deepcopy(payload["results"][0]),
			"strategy": "injected",
			"per_size": {"XXL": {"order": 1, "cut": 1}},
		})
		payload["failed"].append({"strategy": "bad", "success": False, "error": "Traceback\n/private/file.py"})
		projected = _normalise_results(payload, ["S", "M"])
		self.assertEqual([row["strategy"] for row in projected["successful"]], ["direct_integer_search"])
		self.assertNotIn("/private", json.dumps(projected))

	def test_select_result_rejects_old_or_failed_strategy_and_delegates_valid(self):
		payload = result_payload()
		doc = planner_doc(
			status="Completed",
			result_json=json.dumps(payload),
			optimization_input_json=json.dumps(payload["input"], separators=(",", ":")),
		)
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.planner_workspace.native.select_strategy", return_value={"selected_strategy": "direct_integer_search"}) as select,
			patch("essdee_yrp.cutting.planner_workspace.get_editor", return_value={"record": {"selected_strategy": "direct_integer_search"}}),
		):
			result = select_result("CLP-2026-00001", "direct_integer_search", doc.modified)
		select.assert_called_once_with("CLP-2026-00001", "direct_integer_search")
		self.assertEqual(result["record"]["selected_strategy"], "direct_integer_search")

		for strategy in ("cp_sat", "missing"):
			with self.subTest(strategy=strategy):
				with (
					patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
					patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
				):
					with self.assertRaises(frappe.ValidationError):
						select_result("CLP-2026-00001", strategy, doc.modified)

		stale_payload = deepcopy(payload)
		stale_payload["input"]["order"]["S"] = 999
		doc.result_json = json.dumps(stale_payload)
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=True),
		):
			with self.assertRaises(frappe.ValidationError):
				select_result("CLP-2026-00001", "direct_integer_search", doc.modified)

	def test_direct_permission_denial_stops_native_optimization(self):
		with (
			patch("essdee_yrp.cutting.planner_workspace.frappe.get_doc", return_value=planner_doc()),
			patch("essdee_yrp.cutting.planner_workspace.frappe.has_permission", return_value=False),
			patch("essdee_yrp.cutting.planner_workspace.native.optimize") as optimize,
		):
			with self.assertRaises(frappe.PermissionError):
				start_optimization("CLP-2026-00001", "2026-10-03 12:00:00")
		optimize.assert_not_called()

	def test_safe_error_preserves_operator_message_but_not_traceback(self):
		self.assertEqual(_safe_error("No feasible lay plan was found."), "No feasible lay plan was found.")
		self.assertNotIn("Traceback", _safe_error("Traceback\nFile /tmp/private.py"))

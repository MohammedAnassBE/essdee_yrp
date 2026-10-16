from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.web_reports.layouts import get_report_layout, save_report_layout
from yrp.web_reports.registry import clear_web_report_cache, get_web_report

from essdee_yrp.planning.reports import desk_adapters as adapters
from essdee_yrp.planning.reports.production_quantities import authorize_filter_values


class TestPlanningDeskAdapters(TestCase):
	def test_unreadable_filter_stops_before_desk(self):
		with patch.object(adapters, "require_access"), patch.object(frappe, "get_list", return_value=[]), patch.object(adapters, "run_query_report") as run:
			with self.assertRaises(frappe.PermissionError):
				adapters.run_dispatch({"lot": ["DENIED"]})
			run.assert_not_called()

	def test_every_multi_filter_is_authorized(self):
		for runner, fields in ((adapters.run_dispatch, ("lot", "item")), (adapters.run_pending, tuple(adapters.MULTI_FILTERS))):
			for field in fields:
				with self.subTest(runner=runner.__name__, field=field), patch.object(adapters, "require_access"), patch.object(frappe, "get_list", return_value=["READABLE"]) as read, patch.object(adapters, "run_query_report", return_value={"columns": [], "result": []}) as run:
					runner({field: ["READABLE"]})
					read.assert_called_once_with(adapters.MULTI_FILTERS[field], filters={"name": ["in", ["READABLE"]]}, pluck="name", limit_page_length=0)
					self.assertEqual(run.call_args.kwargs["filters"], {field: ["READABLE"]})
					self.assertEqual(run.call_args.kwargs["user"], frappe.session.user)

	def test_json_and_large_lists_are_not_truncated(self):
		values = [f"LOT-{index}" for index in range(30)]
		with patch.object(frappe, "get_list", return_value=values):
			self.assertEqual(authorize_filter_values("SD YRP Lot", frappe.as_json(values)), values)

	def test_summary_uses_filtered_rows_excluding_desk_total(self):
		row = {"delivered_qty": 10, "received_qty": 8, "pending_quantity": 2}
		for rows, total, expected in (([row], False, [1, 10, 8, 2]), ([row, row], True, [1, 10, 8, 2]), ([], False, [0, 0, 0, 0])):
			with self.subTest(total=total, rows=rows), patch.object(adapters, "require_access"), patch.object(adapters, "run_query_report", return_value={"result": rows, "report_summary": [{"value": 999}], "add_total_row": total}):
				self.assertEqual([metric["value"] for metric in adapters.run_pending({})["report_summary"]], expected)

	def test_capability_and_execution_share_desk_and_read_gate(self):
		with patch.dict(frappe.session, {"user": "restricted@example.com"}), patch.object(adapters, "get_report_doc", return_value=frappe._dict(ref_doctype="YRP Work Order")) as report, patch.object(frappe, "has_permission", return_value=False) as permission:
			self.assertFalse(adapters.can_run_desk_report(adapters.WORK_ORDER))
			with self.assertRaises(frappe.PermissionError):
				adapters.require_work_order_access()
			permission.assert_called_with("YRP Work Order", "read")
			permission.return_value = True
			self.assertTrue(adapters.can_run_desk_report(adapters.WORK_ORDER))
			adapters.require_work_order_access()
			report.side_effect = frappe.PermissionError
			self.assertFalse(adapters.can_run_desk_report(adapters.WORK_ORDER))
			with self.assertRaises(frappe.PermissionError):
				adapters.require_work_order_access()

	def test_registry_refreshes_received_columns_from_settings(self):
		for settings in ("Accepted,Adas,Oil Mark,Rejected", "Rework"):
			with patch.object(frappe.db, "get_single_value", return_value=settings):
				clear_web_report_cache()
				try:
					entry = get_web_report("planning-work-order")
					for value in settings.split(","):
						self.assertIn(value.replace(" ", "_"), entry.base_columns)
					self.assertEqual("Accepted" in entry.base_columns, "Accepted" in settings)
				finally:
					clear_web_report_cache()


class TestPlanningDeskAdaptersLive(IntegrationTestCase):
	def test_administrator_adapters_return_columns(self):
		previous_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			for runner, filters in ((adapters.run_dispatch, {"percentage": 75}), (adapters.run_pending, {"from_date": "1900-01-01", "to_date": "1900-01-01"})):
				self.assertTrue(runner(filters)["columns"])
		finally:
			frappe.set_user(previous_user)

	def test_dynamic_columns_save_and_reload(self):
		previous_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			with patch.object(frappe.db, "get_single_value", return_value="Accepted,Adas,Oil Mark,Rejected"):
				clear_web_report_cache()
				columns = [{"kind": "base", "column_key": f"base:{field}", "visible": 1, "align": "right", "width": 120} for field in ("Accepted", "Adas", "Oil_Mark", "Rejected")]
				save_report_layout("planning-work-order", columns)
				clear_web_report_cache()
				layout = get_report_layout("planning-work-order")["layout"]
				self.assertEqual([column["column_key"] for column in layout], [column["column_key"] for column in columns])
		finally:
			frappe.set_user(previous_user)
			clear_web_report_cache()

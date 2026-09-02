import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_action_master.sd_yrp_action_master import (
	get_action_master_details,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action.sd_yrp_time_and_action import (
	get_update_rescheduled_date,
	get_t_and_a_preview_data,
	get_t_and_a_update_data,
	update_t_and_a,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_time_and_action_gantt_chart.sd_yrp_time_and_action_gantt_chart import (
	get_chart_data,
)
from essdee_yrp.time_and_action.reports import (
	execute_cumulative_time_and_action_delay,
	execute_live_time_and_action_delay,
	execute_time_and_action_delay_analysis,
	execute_time_and_action_department_performance,
	execute_time_and_action_dispatch_report,
	execute_time_and_action_pending_work,
	execute_time_and_action_report,
	execute_time_and_action_summary,
)
from essdee_yrp.time_and_action.tracking import (
	get_t_and_a_report_data,
	get_t_and_a_review_report_data,
)


class TestTimeAndActionBusinessLogic(FrappeTestCase):
	def test_preview_matches_production_calendar_fixture(self):
		preview = get_t_and_a_preview_data(
			"2026-08-18",
			[{"colour": "Test", "master": "Master-00001"}],
		)
		self.assertEqual(
			[str(row["rescheduled_date"]) for row in preview["Test"]],
			[
				"2026-08-19",
				"2026-08-21",
				"2026-08-22",
				"2026-08-23",
				"2026-08-25",
				"2026-09-04",
				"2026-09-08",
				"2026-09-09",
				"2026-09-11",
				"2026-09-11",
				"2026-09-18",
				"2026-09-21",
				"2026-09-22",
			],
		)

	def test_action_master_details_are_rebuilt_from_server_master(self):
		result = get_action_master_details(
			[{"colour": "Test", "master": "Master-00001"}]
		)
		master = frappe.get_doc('SD YRP Action Master', "Master-00001")
		self.assertEqual(
			[row["action"] for row in result["Test"]["details"]],
			[row.action for row in master.details],
		)

	def test_update_payload_contains_only_lot_linked_schedules(self):
		lot = "F0924-22"
		result = get_t_and_a_update_data(lot, frappe.db.get_value('SD YRP Lot', lot, "item"))
		returned = {
			row["t_and_a"]
			for master in result["data"][lot]["masters"].values()
			for row in master["datas"]
		}
		linked = set(
			frappe.get_all(
				'SD YRP Lot Time and Action Detail',
				filters={"parent": lot, "parenttype": 'SD YRP Lot'},
				pluck="time_and_action",
			)
		)
		self.assertTrue(returned)
		self.assertTrue(returned.issubset(linked))

	def test_update_rejects_tampered_action_definition(self):
		lot = "F0924-22"
		payload = get_t_and_a_update_data(
			lot, frappe.db.get_value('SD YRP Lot', lot, "item")
		)["data"]
		row = next(
			row
			for master in payload[lot]["masters"].values()
			for row in master["datas"]
		)
		row["actions"][0]["lead_time"] += 1
		with self.assertRaises(frappe.ValidationError):
			update_t_and_a(payload)

	def test_gantt_query_returns_only_readable_time_and_action_rows(self):
		row = frappe.get_all(
			'SD YRP Time and Action Detail',
			filters={"completed": 0},
			fields=["action"],
			limit=1,
		)[0]
		result = get_chart_data(row.action)
		self.assertTrue(all(set(item) == {"id", "name", "start", "end", "progress"} for item in result))

	def test_tracking_and_review_providers_return_expected_contracts(self):
		tracking = get_t_and_a_report_data()
		self.assertEqual(set(tracking), {"row_keys", "dates", "datas"})
		self.assertTrue({"item", "lot", "process_name", "qty"}.issubset(tracking["row_keys"]))
		self.assertIsInstance(get_t_and_a_review_report_data(), dict)

	def test_all_time_and_action_report_providers_execute(self):
		providers = (
			execute_cumulative_time_and_action_delay,
			execute_live_time_and_action_delay,
			execute_time_and_action_delay_analysis,
			execute_time_and_action_department_performance,
			execute_time_and_action_dispatch_report,
			execute_time_and_action_pending_work,
			execute_time_and_action_report,
			execute_time_and_action_summary,
		)
		for provider in providers:
			result = provider()
			self.assertIsInstance(result, tuple, provider.__name__)
			self.assertIsInstance(result[0], list, provider.__name__)
			self.assertIsInstance(result[1], list, provider.__name__)

	def test_rescheduled_preview_ignores_tampered_derived_values(self):
		lot = "F0924-22"
		payload = get_t_and_a_update_data(
			lot, frappe.db.get_value('SD YRP Lot', lot, "item")
		)["data"]
		master, master_data = next(iter(payload[lot]["masters"].items()))
		row = master_data["datas"][0]
		action = row["actions"][0]
		action["rescheduled_date"] = "2099-12-31"

		result = get_update_rescheduled_date(
			action.get("actual_date") or frappe.utils.nowdate(),
			"updated" if not action.get("actual_date") else "removed",
			action["action"],
			0,
			payload,
			0,
			lot,
			master,
		)
		location = next(
			data_row
			for data_row in result["total_data"][lot]["masters"][master]["datas"]
			if data_row["t_and_a"] == row["t_and_a"]
		)
		calculated = next(
			value for value in location["actions"] if value["action"] == action["action"]
		)
		self.assertNotEqual(str(calculated["rescheduled_date"]), "2099-12-31")

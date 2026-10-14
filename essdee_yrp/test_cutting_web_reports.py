from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.web_reports.background import needs_background
from yrp.web_reports.jobs import execute_report_job, get_report_job, run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_report

from essdee_yrp.cutting.reports import (
	build_daily_production_summary,
	calculate_completed,
	get_cutting_detail_report,
	get_daily_production_report,
	get_daily_production_summary_report,
)
from essdee_yrp.stock_dimensions import find_variant


class TestCuttingWebReports(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()
		self.jobs = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for job_name in self.jobs:
			for file_name in frappe.get_all(
				"File",
				filters={"attached_to_doctype": "YRP Report Job", "attached_to_name": job_name},
				pluck="name",
			):
				frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
			if frappe.db.exists("YRP Report Job", job_name):
				frappe.delete_doc("YRP Report Job", job_name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_cutting_dpr_uses_the_declared_background_boundaries(self):
		entry = get_web_report("cutting-dpr")
		self.assertFalse(needs_background(entry, _summary_filters("2026-01-01", "2026-01-11")))
		self.assertTrue(needs_background(entry, _summary_filters("2026-01-01", "2026-01-12")))
		self.assertFalse(
			needs_background(
				entry,
				{"mode": "daily", "date": "2026-01-01", "from_date": "", "to_date": ""},
			)
		)

	def test_summary_builder_accepts_either_date_boundary(self):
		self.assertEqual(build_daily_production_summary({"from_date": "2099-01-01"}), [])
		self.assertEqual(build_daily_production_summary({"to_date": "1900-01-01"}), [])

	def test_summary_runs_sync_at_10_days_and_background_at_11_days_with_progress(self):
		payload = [{"date": "2026-01-01", "report_data": [{"total_sum": 4}]}]

		def build(_filters, progress=None):
			if progress:
				progress(1, 2)
				progress(2, 2)
			return payload

		with patch("essdee_yrp.cutting.reports.build_daily_production_summary", side_effect=build):
			sync = run_web_report("cutting-dpr", _summary_filters("2026-01-01", "2026-01-11"))
			self.assertEqual((sync["mode"], sync["payload"]), ("sync", payload))

			with (
				patch("yrp.web_reports.jobs.frappe.enqueue"),
				patch("yrp.web_reports.jobs.get_workers", return_value=[object()]),
			):
				background = run_web_report(
					"cutting-dpr",
					_summary_filters("2026-01-01", "2026-01-12"),
					refresh=1,
				)
			self.jobs.append(background["job"]["name"])
			with patch("yrp.web_reports.jobs.frappe.publish_realtime") as publish:
				execute_report_job(background["job"]["name"])

		stored = get_report_job("cutting-dpr", background["job"]["name"], include_result=1)
		self.assertEqual((stored["job"]["status"], stored["payload"]), ("Completed", payload))
		events = [call.args[0] for call in publish.call_args_list]
		self.assertIn("yrp_report_progress", events)
		self.assertEqual(events[-1], "yrp_report_done")

	def test_summary_job_expires_after_cutting_plan_metadata_change(self):
		with (
			patch("essdee_yrp.cutting.reports.build_daily_production_summary", return_value=[]),
			patch("yrp.web_reports.jobs.frappe.enqueue"),
			patch("yrp.web_reports.jobs.get_workers", return_value=[object()]),
		):
			response = run_web_report("cutting-dpr", _summary_filters("2026-01-01", "2026-01-12"))
			self.jobs.append(response["job"]["name"])
			execute_report_job(response["job"]["name"])

		setter = frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"doc_type": "SD YRP Cutting Plan",
				"field_name": "work_order",
				"property": "permlevel",
				"property_type": "Int",
				"value": "1",
			}
		).insert(ignore_permissions=True)
		try:
			result = get_report_job("cutting-dpr", response["job"]["name"])
			self.assertTrue(result["expired"])
		finally:
			setter.delete(ignore_permissions=True)

	def test_find_variant_discards_attributes_and_uses_dependent_override(self):
		template = _variant_template(dependent_attribute="Stage", mapping="DEFAULT-MAPPING")
		requested = {"Stage": "Cut", "Colour": "Red", "Size": "M", "Panel": "Front"}
		normalized = {"Stage": "Cut", "Colour": "Red"}
		with (
			patch("essdee_yrp.stock_dimensions.frappe.get_cached_doc", return_value=template),
			patch(
				"essdee_yrp.stock_dimensions.build_variant_attributes",
				return_value=normalized,
			) as normalize,
			patch("essdee_yrp.stock_dimensions.frappe.db.get_value", return_value="VARIANT-CUT-RED") as get_value,
			patch("essdee_yrp.stock_dimensions._find_variant_by_attributes") as fallback,
			patch("essdee_yrp.stock_dimensions.frappe.db.set_value") as write,
		):
			result = find_variant("TEMPLATE", requested, dependent_attr="OVERRIDE-MAPPING")

		self.assertEqual(result, "VARIANT-CUT-RED")
		source = normalize.call_args.args[2]
		self.assertEqual((source.name, source.dependent_attribute_mapping), ("TEMPLATE", "OVERRIDE-MAPPING"))
		lookup_filters = get_value.call_args.args[1]
		self.assertEqual(
			lookup_filters["item_tuple_attribute"],
			str(tuple(sorted((key, value) for key, value in normalized.items()))),
		)
		fallback.assert_not_called()
		write.assert_not_called()

	def test_find_variant_falls_back_when_the_stored_tuple_is_stale(self):
		template = _variant_template()
		attributes = {"Colour": "Red", "Size": "M"}
		with (
			patch("essdee_yrp.stock_dimensions.frappe.get_cached_doc", return_value=template),
			patch("essdee_yrp.stock_dimensions.frappe.db.get_value", return_value=None),
			patch(
				"essdee_yrp.stock_dimensions._find_variant_by_attributes",
				return_value="VARIANT-STALE-TUPLE",
			) as fallback,
			patch("essdee_yrp.stock_dimensions.frappe.db.set_value") as write,
		):
			result = find_variant("TEMPLATE", attributes)

		self.assertEqual(result, "VARIANT-STALE-TUPLE")
		fallback.assert_called_once_with("TEMPLATE", attributes)
		write.assert_not_called()

	def test_find_variant_returns_none_for_a_valid_lookup_miss(self):
		template = _variant_template()
		attributes = {"Colour": "Ochre", "Size": "XS"}
		with (
			patch("essdee_yrp.stock_dimensions.frappe.get_cached_doc", return_value=template),
			patch("essdee_yrp.stock_dimensions.frappe.db.get_value", return_value=None),
			patch("essdee_yrp.stock_dimensions._find_variant_by_attributes", return_value=None) as fallback,
			patch("essdee_yrp.stock_dimensions.frappe.db.set_value") as write,
		):
			result = find_variant("TEMPLATE", attributes)

		self.assertIsNone(result)
		fallback.assert_called_once_with("TEMPLATE", attributes)
		write.assert_not_called()

	def test_cutting_report_reads_do_not_change_items(self):
		if not frappe.db.exists("SD YRP Cutting LaySheet", {"bundle_generated_date": "2026-08-01"}):
			self.skipTest("Migrated Cutting report oracle is unavailable")
		before = _item_state()

		daily = get_daily_production_report("2026-08-01", "")
		summary = get_daily_production_summary_report(
			from_date="2026-08-01",
			to_date="2026-08-01",
			location="",
		)
		detail = get_cutting_detail_report("2026-08-01", "2026-08-01", "")

		self.assertTrue(daily["report_data"])
		self.assertTrue(summary)
		self.assertTrue(detail["report_data"])
		self.assertEqual(_item_state(), before)

	def test_summary_matches_uncached_daily_composition(self):
		dates = frappe.get_all(
			"SD YRP Cutting LaySheet",
			filters={"status": "Label Printed", "bundle_generated_date": ("is", "set")},
			pluck="bundle_generated_date",
			order_by="bundle_generated_date desc",
			limit=2,
		)
		dates = sorted(set(dates), reverse=True)
		if not dates:
			self.skipTest("No labelled Cutting LaySheet dates are available")
		filters = _summary_filters(str(min(dates)), str(max(dates)))
		expected = []
		for date in dates:
			data = get_daily_production_report(str(date), "", only_label_printed=True)
			if data["report_data"]:
				expected.append({"date": str(date), **data})

		progress = []
		actual = build_daily_production_summary(filters, progress=lambda current, total: progress.append((current, total)))

		self.assertEqual(actual, expected)
		self.assertEqual(progress[-1], (len(dates), len(dates)))

	def test_unmapped_bundle_colour_is_ignored(self):
		completed = {
			"total_qty": {},
			"items": [{"attributes": {"Colour": "Off white"}, "values": {"M": 0}}],
		}
		incomplete = {
			"items": [
				{"attributes": {"Colour": "Off white"}, "values": {"M": {"Front": 0}}}
			],
		}
		bundle = frappe._dict(
			part="Front",
			size="M",
			quantity=3,
			set_combination='{"major_colour": "Blue"}',
		)
		detail = frappe._dict(is_set_item=0, packing_attribute="Colour")

		actual_completed, actual_incomplete = calculate_completed(
			[{"name": "CLS-1"}],
			detail,
			completed,
			incomplete,
			{"CLS-1": [bundle]},
		)

		self.assertEqual(actual_completed["items"][0]["values"]["M"], 0)
		self.assertEqual(actual_incomplete["items"][0]["values"]["M"]["Front"], 0)


def _summary_filters(from_date, to_date):
	return {
		"mode": "summary",
		"items": [],
		"lots": [],
		"location": "",
		"from_date": from_date,
		"to_date": to_date,
	}


def _item_state():
	return frappe.get_all(
		"Item",
		fields=["name", "modified", "item_tuple_attribute"],
		order_by="name",
		limit=0,
	)


def _variant_template(dependent_attribute=None, mapping=None):
	return frappe._dict(
		name="TEMPLATE",
		has_variants=1,
		variant_of="",
		dependent_attribute=dependent_attribute,
		dependent_attribute_mapping=mapping,
	)

from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.report.sd_yrp_finishing_plan_report import sd_yrp_finishing_plan_report as report


class TestFinishingReadQueries(TestCase):
	def test_report_reads_only_used_children_with_identical_rows(self):
		if not frappe.db.exists("SD YRP Finishing Plan", {"lot": "C1225-03"}):
			self.skipTest("Live Finishing Plan fixture is missing")
		actual = report.get_data({"lot": "C1225-03"})
		with patch.object(report, "_report_plans", side_effect=lambda names: {name: frappe.get_doc("SD YRP Finishing Plan", name) for name in names}):
			self.assertEqual(report.get_data({"lot": "C1225-03"}), actual)

	def test_batched_plan_rows_match_document_header_and_children(self):
		names = frappe.get_all("SD YRP Finishing Plan", pluck="name", limit_page_length=4)
		expected = {name: frappe.get_doc("SD YRP Finishing Plan", name) for name in names}
		with patch.object(frappe, "get_lazy_doc", side_effect=AssertionError("per-plan header load")):
			actual = report._report_plans(names)
		for name, doc in expected.items():
			for field in ("item", "lot", "pieces_per_box", "production_detail", "is_set_item", "work_order"):
				self.assertEqual(actual[name].get(field), doc.get(field))
			fields = ["finishing_old_lot_given_items"]
			if doc.is_set_item:
				fields += ["finishing_plan_details", "finishing_plan_reworked_details", "finishing_plan_grn_details"]
			for field in fields:
				self.assertEqual([r["name"] for r in actual[name][field]], [r.name for r in doc.get(field)])

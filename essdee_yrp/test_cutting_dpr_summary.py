import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.cutting import reports


class TestCuttingDprSummary(IntegrationTestCase):
	def test_plan_structures_build_once_per_report_run(self):
		plan = frappe._dict(name="CP-1")
		with patch.object(reports, "_cutting_plan_structures", return_value=("detail", {}, {})) as build:
			cache = {}
			first = reports._cached_cutting_plan_structures(plan, cache)
			second = reports._cached_cutting_plan_structures(plan, cache)
			reports._cached_cutting_plan_structures(plan, None)
		self.assertIs(first, second)
		self.assertEqual(build.call_count, 2)

	def test_shared_cache_matches_fresh_daily_reports(self):
		dates = self.get_plan_dates()
		cache = {}
		for date in dates:
			filters = {"date": str(date), "only_label_printed": True}
			shared = reports.build_daily_production_report(filters, document_cache=cache)
			fresh = reports.build_daily_production_report(filters)
			self.assertEqual(self.dump(shared), self.dump(fresh))

	def get_plan_dates(self):
		row = frappe.db.sql(
			"""
			SELECT laysheet.cutting_plan
			FROM `tabSD YRP Cutting LaySheet` laysheet
			JOIN `tabSD YRP Cutting Plan` plan ON plan.name = laysheet.cutting_plan
			WHERE laysheet.status = 'Label Printed' AND laysheet.bundle_generated_date IS NOT NULL
				AND IFNULL(plan.version, '') != 'V1'
			GROUP BY laysheet.cutting_plan
			HAVING COUNT(DISTINCT laysheet.bundle_generated_date) > 1
			ORDER BY MAX(laysheet.bundle_generated_date) DESC
			LIMIT 1
			"""
		)
		if not row:
			self.skipTest("No cutting plan with lay sheets on several days")
		dates = frappe.get_all(
			"SD YRP Cutting LaySheet",
			filters={"cutting_plan": row[0][0], "status": "Label Printed"},
			pluck="bundle_generated_date",
			distinct=True,
			order_by="bundle_generated_date desc",
			limit=3,
		)
		return dates

	def dump(self, value):
		return json.dumps(value, sort_keys=True, default=str)

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.essdee_yrp.report.sd_yrp_dc_report.sd_yrp_dc_report import get_data


class TestSDYRPDCReport(IntegrationTestCase):
	def get_recent_range(self):
		latest = frappe.db.get_value("YRP Delivery Challan", {"docstatus": 1}, "posting_date", order_by="posting_date desc")
		if not latest:
			self.skipTest("No submitted delivery challans")
		return {"from_date": frappe.utils.add_days(latest, -30), "to_date": latest}

	def test_parent_item_resolved_in_query(self):
		filters = self.get_recent_range()
		original_sql = frappe.db.sql
		with patch.object(frappe.db, "sql", wraps=original_sql) as sql:
			rows = get_data(filters)
		self.assertTrue(rows)
		self.assertEqual(sql.call_count, 1)
		for row in rows[:100]:
			self.assertEqual(row.item, get_parent_item(row.item_variant))

	def test_rows_follow_posting_order(self):
		rows = get_data(self.get_recent_range())
		challans = [row.delivery_challan for row in rows]
		dates = frappe._dict(frappe.get_all(
			"YRP Delivery Challan", filters={"name": ["in", list(set(challans))]},
			fields=["name", "posting_date"], as_list=True,
		))
		posting_dates = [dates[name] for name in challans]
		self.assertEqual(posting_dates, sorted(posting_dates))

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.essdee_yrp.report.sd_yrp_grn_report.sd_yrp_grn_report import get_data, get_parent_items


class TestSDYRPGRNReport(IntegrationTestCase):
	def get_recent_range(self):
		latest = frappe.db.get_value(
			"YRP Goods Received Note", {"docstatus": 1, "against": "YRP Work Order"}, "posting_date",
			order_by="posting_date desc",
		)
		if not latest:
			self.skipTest("No submitted work order GRNs")
		return {"from_date": frappe.utils.add_days(latest, -30), "to_date": latest}

	def test_parent_items_resolved_in_one_query(self):
		filters = self.get_recent_range()
		with patch(
			"essdee_yrp.essdee_yrp.report.sd_yrp_grn_report.sd_yrp_grn_report.get_parent_items",
			wraps=get_parent_items,
		) as batched:
			rows = get_data(filters)
		self.assertTrue(rows)
		batched.assert_called_once()
		for row in rows[:100]:
			self.assertEqual(row.item, get_parent_item(row.item_variant))

	def test_parent_items_skip_empty_and_missing_variants(self):
		self.assertEqual(get_parent_items({None, ""}), {})
		self.assertEqual(get_parent_items({"__missing_item__"}), {})

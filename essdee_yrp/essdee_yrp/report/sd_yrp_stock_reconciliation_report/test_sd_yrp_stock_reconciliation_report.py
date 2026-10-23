from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt

from essdee_yrp.essdee_yrp.report.sd_yrp_stock_reconciliation_report.sd_yrp_stock_reconciliation_report import (
	get_data,
)


class TestSDYRPStockReconciliationReport(IntegrationTestCase):
	def get_recent_range(self):
		latest = frappe.db.get_value(
			"YRP Stock Reconciliation", {"docstatus": 1}, "posting_date", order_by="posting_date desc"
		)
		if not latest:
			self.skipTest("No submitted stock reconciliations")
		return frappe._dict(from_date=add_days(latest, -30), to_date=latest)

	def get_previous_entry(self, row):
		entry = frappe.db.get_value(
			"YRP Stock Ledger Entry",
			{
				"voucher_type": "YRP Stock Reconciliation",
				"voucher_no": row.stock_reconciliation,
				"item": row.item_variant,
				"warehouse": row.supplier,
				"lot": row.lot,
			},
			"posting_datetime",
		)
		previous = frappe.db.sql(
			"""SELECT qty_after_transaction, valuation_rate FROM `tabYRP Stock Ledger Entry`
			WHERE item = %s AND warehouse = %s AND lot = %s AND posting_datetime < %s
			ORDER BY posting_datetime DESC, name LIMIT 1""",
			(row.item_variant, row.supplier, row.lot, entry),
			as_dict=True,
		)
		return previous[0] if previous else frappe._dict(qty_after_transaction=0, valuation_rate=None)

	def test_previous_values_come_from_the_latest_earlier_entry(self):
		rows = get_data(self.get_recent_range())
		self.assertTrue(rows)
		for row in rows[:50]:
			previous = self.get_previous_entry(row)
			self.assertEqual(flt(row.previous_quantity), flt(previous.qty_after_transaction))
			self.assertEqual(row.previous_rate, previous.valuation_rate)
			self.assertEqual(
				flt(row.difference), flt(row.updated_quantity) - flt(previous.qty_after_transaction)
			)

	def test_previous_entry_lookup_avoids_window_functions(self):
		filters = self.get_recent_range()
		original_sql = frappe.db.sql
		queries = []

		def sql(query, *args, **kwargs):
			if "YRP Stock Ledger Entry" in query:
				queries.append(query)
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=sql):
			get_data(filters)
		self.assertEqual(len(queries), 1)
		self.assertNotIn("LAG(", queries[0])

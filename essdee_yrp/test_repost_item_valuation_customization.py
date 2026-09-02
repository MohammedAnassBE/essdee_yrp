from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from yrp.stock.dimensions import (
	MANAGED_DIMENSION_FIELD_MARKER,
	STOCK_DOCTYPES,
	get_stock_dimensions,
)
from yrp.stock.stock_ledger import StockValuationPeriodClosedError


class TestRepostItemValuationCustomization(FrappeTestCase):
	def _transaction_repost(self, posting_date):
		return frappe.get_doc(
			{
				"doctype": 'YRP Repost Item Valuation',
				"based_on": "Transaction",
				"voucher_type": 'YRP Stock Entry',
				"voucher_no": "STE-U42-BOUNDARY-PROBE",
				"posting_date": posting_date,
			}
		)

	@patch(
		"yrp.stock.stock_ledger.get_last_stock_valuation_closing_date",
		return_value=getdate("2026-08-20"),
	)
	def test_transaction_repost_respects_stock_valuation_closing_boundary(self, _cutoff):
		with self.assertRaises(StockValuationPeriodClosedError):
			self._transaction_repost("2026-08-20").validate()

		# Validation must still allow an otherwise valid repost in the open period.
		self._transaction_repost("2026-08-21").validate()

	def test_via_landed_cost_voucher_is_essdee_owned(self):
		field = frappe.get_meta('YRP Repost Item Valuation', cached=False).get_field(
			"via_landed_cost_voucher"
		)

		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(field.default, "0")
		self.assertEqual(field.insert_after, "allow_negative_stock")
		self.assertTrue(
			frappe.db.exists(
				"Custom Field",
				{
					"dt": 'YRP Repost Item Valuation',
					"fieldname": "via_landed_cost_voucher",
					"module": "Essdee YRP",
				},
			)
		)

	def test_stock_dimensions_remain_base_yrp_managed(self):
		self.assertIn('YRP Repost Item Valuation', STOCK_DOCTYPES)
		meta = frappe.get_meta('YRP Repost Item Valuation', cached=False)

		for dimension in get_stock_dimensions():
			with self.subTest(fieldname=dimension.fieldname):
				field = meta.get_field(dimension.fieldname)
				self.assertIsNotNone(field)
				self.assertEqual(field.fieldtype, "Link")
				self.assertEqual(field.options, dimension.dimension_doctype)
				self.assertIn(MANAGED_DIMENSION_FIELD_MARKER, field.description or "")
				self.assertFalse(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": 'YRP Repost Item Valuation',
							"fieldname": dimension.fieldname,
							"module": "Essdee YRP",
						},
					)
				)

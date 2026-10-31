from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp import fabric_grn

PLAN = [
	{"item_variant": "40's GL Dyed Fabric New-Navy-19 Dia", "dimensions": {"lot": "F1"}, "stock_qty": 16.95}
]


class TestSupplierInputStockPrecision(UnitTestCase):
	def _validate(self, balance):
		with patch.object(fabric_grn, "_supplier_stock", return_value=(balance, 10)):
			fabric_grn.validate_supplier_input_stock(None, frappe._dict(), PLAN, {})

	def test_float_drift_in_the_balance_is_not_a_shortage(self):
		self._validate(16.949999)

	def test_real_shortage_is_reported(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Need: 16.95, Stock: 16.9, Short: 0.05"):
			self._validate(16.9)

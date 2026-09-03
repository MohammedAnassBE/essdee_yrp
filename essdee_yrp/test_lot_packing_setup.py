import unittest
from unittest.mock import patch

import frappe

from essdee_yrp import lot_packing_setup


class TestLotPackingSetup(unittest.TestCase):
	def test_legacy_copy_reads_the_retained_pre_namespace_table(self):
		legacy = [frappe._dict(parent="PO-1", lot="LOT-A", idx=1)]
		with (
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "sql", side_effect=[legacy, [], None]) as sql,
			patch.object(frappe.db, "exists", return_value=True),
		):
			result = lot_packing_setup.migrate_legacy_purchase_order_lot_rows()

		self.assertEqual(result, {"found": 1, "copied": 1, "skipped": 0})
		legacy_query = sql.call_args_list[0].args[0]
		self.assertIn("`tabPurchase Order Lot`", legacy_query)
		self.assertNotIn("`tabYRP Purchase Order Lot`", legacy_query)
		self.assertIn("'Purchase Order', 'YRP Purchase Order'", legacy_query)


if __name__ == "__main__":
	unittest.main()

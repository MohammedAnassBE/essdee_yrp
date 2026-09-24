from unittest import TestCase
from unittest.mock import patch

import frappe
from essdee_yrp.purchase_invoice import _unreceived_non_garment_return


class TestInvoiceMaterialReturns(TestCase):
	def test_only_unused_uncharged_other_item_is_excluded(self):
		wo = frappe._dict(item="Vest")
		row = frappe._dict(name="cloth-return", item_variant="Cloth-Blue", cost=0, qty=2, pending_quantity=2)
		with patch("frappe.get_cached_value", return_value="Cloth"):
			self.assertTrue(_unreceived_non_garment_return(wo, row, []))
			row.cost = 1
			self.assertFalse(_unreceived_non_garment_return(wo, row, []))
			row.cost = 0
			row.pending_quantity = 1
			self.assertFalse(_unreceived_non_garment_return(wo, row, []))
			row.pending_quantity = 2
			grn = frappe._dict(items=[frappe._dict(ref_docname=row.name, item_variant=row.item_variant)])
			self.assertFalse(_unreceived_non_garment_return(wo, row, [grn]))
		with patch("frappe.get_cached_value", return_value="Vest"):
			self.assertFalse(_unreceived_non_garment_return(wo, row, []))

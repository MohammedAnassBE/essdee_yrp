import unittest
from unittest.mock import patch

import frappe
from essdee_yrp.purchase_invoice import (
	_build_work_order_context,
	_inactive_legacy_receivable,
	_validate_selected_physical_quantities,
)


class LegacyInvoiceZeroRowsTest(unittest.TestCase):
	def test_zero_row_with_any_nonzero_receipt_is_not_ignored(self):
		r = frappe._dict(name="R0", item_variant="SIZE-S", qty=0)
		self.assertTrue(_inactive_legacy_receivable(r, []))
		for qty in (1, -1):
			for item in (dict(ref_docname="R0", item_variant="OTHER"), dict(item_variant="SIZE-S")):
				g = frappe._dict(items=[frappe._dict(quantity=qty, **item)])
				self.assertFalse(_inactive_legacy_receivable(r, [g]))
		r.qty = 1
		self.assertFalse(_inactive_legacy_receivable(r, []))

	def test_legacy_context_omits_only_inactive_allocation_rows(self):
		zero = frappe._dict(name="R0", item_variant="SIZE-S", qty=0, cost=5)
		active = frappe._dict(name="R1", item_variant="SIZE-L", qty=10, cost=5)
		wo = frappe._dict(name="WO-1", process_name="Sewing", production_detail=None,
			process_cost=None, lot="LOT-1", receivables=[zero, active],
			work_order_calculated_items=[frappe._dict(item_variant="SIZE-S", quantity=0),
				frappe._dict(item_variant="SIZE-L", quantity=10)],
			work_order_track_pieces=[frappe._dict(against="Goods Received Note", against_id="G1", item_variant="SIZE-S", received_qty=0),
				frappe._dict(against="Goods Received Note", against_id="G1", item_variant="SIZE-L", received_qty=1)])
		grn = frappe._dict(name="G1", lot="LOT-1", items=[frappe._dict(item_variant="SIZE-S", quantity=0),
			frappe._dict(item_variant="SIZE-L", quantity=1, ref_docname="R1", ref_doctype="YRP Work Order Receivables")])
		with patch("essdee_yrp.purchase_invoice.frappe.db.get_value", return_value="Billing"), \
			patch("essdee_yrp.purchase_invoice.get_or_create_variant", return_value="Billing"), \
			patch("essdee_yrp.purchase_invoice.resolve_item_uom", return_value=frappe._dict(uom="Nos")), \
			patch("essdee_yrp.purchase_invoice.get_variant_attributes", return_value={}):
			context = _build_work_order_context(wo, [grn], allow_missing_process_cost=True, allow_legacy_references=True)
		self.assertEqual(set(context["receivables_by_name"]), {"R1"})
		self.assertEqual(context["demands"][0]["selected_qty"], 1)
		_validate_selected_physical_quantities(context, [grn])
		self.assertEqual(len(wo.receivables), 2)

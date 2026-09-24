from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace

import frappe

from essdee_yrp.additional_grn import validate_receivables, validate_submit_role


class TestAdditionalGRN(TestCase):
	def test_exhausted_receivable_remains_valid_but_foreign_item_does_not(self):
		row = frappe._dict(idx=1, quantity=5, item_variant="ITEM")
		grn = SimpleNamespace(against="YRP Work Order", against_id="WO", items=[row], get=lambda key: None)
		target = frappe._dict(doctype="YRP Work Order Receivables", name="ROW", pending_quantity=0)
		with patch("essdee_yrp.additional_grn.frappe.get_doc", return_value=frappe._dict(receivables=[target])), patch(
			"essdee_yrp.additional_grn._find_matching_receivable", return_value=target
		) as match:
			validate_receivables(grn)
			self.assertEqual(row.ref_docname, "ROW")
			self.assertEqual(row.max_receivable_quantity, -1)
			match.return_value = None
			with self.assertRaises(frappe.ValidationError):
				validate_receivables(grn)

	def test_submit_requires_configured_role(self):
		with patch("essdee_yrp.additional_grn.frappe.db.get_single_value", return_value="Stock Manager"), patch(
			"essdee_yrp.additional_grn.frappe.get_roles", return_value=[]
		) as roles:
			with self.assertRaises(frappe.PermissionError):
				validate_submit_role()
			roles.return_value = ["Stock Manager"]
			validate_submit_role()

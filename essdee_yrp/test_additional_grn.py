from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.additional_grn import validate_receivables, validate_submit_role


class TestAdditionalGRN(TestCase):
	def test_exhausted_receivable_remains_valid_but_foreign_item_does_not(self):
		row = frappe._dict(idx=1, quantity=5, item_variant="ITEM")
		grn = SimpleNamespace(against="YRP Work Order", against_id="WO", items=[row], get=lambda key: None)
		target = frappe._dict(doctype="YRP Work Order Receivables", name="ROW", pending_quantity=0)
		with (
			patch(
				"essdee_yrp.additional_grn.frappe.get_doc", return_value=frappe._dict(receivables=[target])
			),
			patch("essdee_yrp.additional_grn._find_matching_receivable", return_value=target) as match,
		):
			validate_receivables(grn)
			self.assertEqual(row.ref_docname, "ROW")
			self.assertEqual(row.max_receivable_quantity, -1)
			match.return_value = None
			with self.assertRaises(frappe.ValidationError):
				validate_receivables(grn)

	def test_submit_requires_configured_role(self):
		with (
			patch("essdee_yrp.additional_grn.frappe.db.get_single_value", return_value="Stock Manager"),
			patch("essdee_yrp.additional_grn.frappe.get_roles", return_value=[]) as roles,
		):
			with self.assertRaises(frappe.PermissionError):
				validate_submit_role()
			roles.return_value = ["Stock Manager"]
			validate_submit_role()

	def test_receivable_rows_offer_every_received_type_like_a_regular_grn(self):
		from essdee_yrp.additional_grn import get_receivable_rows

		wo = frappe._dict(
			lot="LOT-1",
			receivables=[
				frappe._dict(
					doctype="YRP Work Order Receivables",
					name="WOR-1",
					item_variant="STYLE-S",
					uom="Nos",
					pending_quantity=0,
					table_index=0,
					row_index=0,
					set_combination="{}",
					cost=10,
				)
			],
		)
		existing = [frappe._dict(ref_docname="WOR-1", received_type="Rejected", quantity=4)]
		with (
			patch(
				"essdee_yrp.additional_grn._get_received_type_options",
				return_value=(["Accepted", "Rejected", "Rework"], "Accepted"),
			),
			patch("essdee_yrp.additional_grn._get_production_group_dimensions", return_value={}),
			patch("essdee_yrp.additional_grn.apply_dimension_defaults"),
			patch(
				"essdee_yrp.overrides.goods_received_note.normalize_cutting_grn_row_indexes",
				side_effect=lambda rows: rows,
			),
		):
			rows = get_receivable_rows(wo, existing)
		self.assertEqual([row.received_type for row in rows], ["Accepted", "Rejected", "Rework"])
		self.assertEqual([row.quantity for row in rows], [0, 4, 0])
		self.assertEqual({row.max_receivable_quantity for row in rows}, {-1})
		self.assertEqual(rows[1].row_index, "0::Rejected")

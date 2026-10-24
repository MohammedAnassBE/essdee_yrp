from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing import transactions
from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote

YRP_GRN = "yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note"


def receivable(name, pending, qty=10):
	return frappe._dict(
		name=name,
		item_variant="TEE-Pack-M",
		qty=qty,
		pending_quantity=pending,
		uom="Box",
		table_index=0,
		row_index="0",
		set_combination="{}",
	)


class TestFinishingPlanGrnItems(TestCase):
	def _build(self, receivables, quantity):
		work_order = frappe._dict(name="WO-1", receivables=receivables)
		ipd = frappe._dict(name="IPD-1", pack_out_stage="Pack", primary_item_attribute="Size")
		with (
			patch.object(transactions, "get_or_create_variant", return_value="TEE-Pack-M"),
			patch.object(transactions, "build_variant_attributes", return_value={}),
			patch.object(frappe.db, "get_single_value", return_value="Accepted"),
		):
			return transactions._build_packing_grn_items(
				work_order, ipd, "LOT-1", "TEE", {"M": quantity}, "Box"
			)

	def test_excess_over_receivables_is_received_on_the_last_receivable(self):
		items = self._build([receivable("REC-1", 2), receivable("REC-2", 0)], 5)

		self.assertEqual(
			[(row["ref_docname"], row["quantity"]) for row in items], [("REC-1", 2), ("REC-2", 3)]
		)

	def test_fully_received_receivable_still_takes_the_excess(self):
		items = self._build([receivable("REC-1", 0)], 4)

		self.assertEqual([(row["ref_docname"], row["quantity"]) for row in items], [("REC-1", 4)])

	def test_missing_receivable_still_fails(self):
		with self.assertRaisesRegex(frappe.ValidationError, "has no packing receivable"):
			self._build([], 4)


class TestFinishingPlanGrnPendingCap(TestCase):
	def _validate(self, flags, **values):
		target = receivable("REC-1", 0, qty=10)
		work_order = frappe._dict(name="WO-1", receivables=[target])
		row = frappe._dict(idx=1, item_variant="TEE-Pack-M", quantity=6, set_combination="{}")
		document = object.__new__(EssdeeGoodsReceivedNote)
		document.__dict__.update(
			{
				"against": "YRP Work Order",
				"against_id": "WO-1",
				"items": [row],
				"correction_items": [],
				"from_finishing": 1,
				"includes_packing": 1,
				"flags": frappe._dict(flags),
				**values,
			}
		)
		with (
			patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=False),
			patch.object(frappe, "get_doc", return_value=work_order),
			patch(f"{YRP_GRN}._wo_excess_percentage", return_value=0),
		):
			document.validate_against_work_order_pending()
		return row

	def test_finishing_plan_grn_skips_the_receivable_cap(self):
		row = self._validate({"finishing_plan_grn": True})

		self.assertEqual((row.ref_doctype, row.ref_docname), ("YRP Work Order Receivables", "REC-1"))
		self.assertEqual(row.pending_quantity, 0)

	def test_from_finishing_field_alone_keeps_the_cap(self):
		with self.assertRaisesRegex(frappe.ValidationError, "exceeds allowance"):
			self._validate({})

	def test_normal_work_order_grn_keeps_the_cap(self):
		with self.assertRaisesRegex(frappe.ValidationError, "exceeds allowance"):
			self._validate({"finishing_plan_grn": True}, from_finishing=0)

	def test_finishing_return_keeps_the_cap(self):
		with self.assertRaisesRegex(frappe.ValidationError, "exceeds allowance"):
			self._validate({"finishing_plan_grn": True}, is_return=1)

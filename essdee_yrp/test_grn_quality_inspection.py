from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.overrides.goods_received_note import validate_quality_inspection_passed

MODULE = "essdee_yrp.overrides.goods_received_note"
IPD = frappe._dict(
	is_set_item=0,
	packing_attribute="Colour",
	primary_item_attribute="Size",
	set_item_attribute=None,
	major_attribute_value=None,
)


class TestGrnQualityInspection(TestCase):
	def grn(self, **values):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="WO-1",
			is_return=0,
			lot="LOT-1",
			items=[
				frappe._dict(
					item_variant="TEE-Red-M", quantity=10, set_combination='{"major_colour": "Red"}'
				),
				frappe._dict(item_variant="LABEL", quantity=10, set_combination="{}"),
			],
		)
		grn.update(values)
		return grn

	def validate(self, grn, inspected, has_plan=True):
		attributes = {"TEE-Red-M": {"Colour": "Red", "Size": "M"}, "LABEL": {}}
		with (
			patch(f"{MODULE}.frappe.db.exists", return_value=has_plan),
			patch(f"{MODULE}.frappe.db.sql", return_value=inspected) as sql,
			patch(f"{MODULE}.frappe.db.get_value", side_effect=["IPD-1", IPD]),
			patch(f"{MODULE}.get_variant_attr_details", side_effect=attributes.get),
		):
			validate_quality_inspection_passed(grn)
		return sql

	def test_submitted_pass_inspection_for_the_colour_and_size_allows_the_grn(self):
		sql = self.validate(self.grn(), [frappe._dict(colour="Red", size="M")])

		self.assertIn("inspection.result = 'Pass'", sql.call_args.args[0])
		self.assertIn("inspection.docstatus = 1", sql.call_args.args[0])

	def test_missing_fail_or_hold_inspection_blocks_the_grn(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate(self.grn(), [frappe._dict(colour="Red", size="L")])

		self.assertIn("Red / M", str(raised.exception))
		self.assertIn("result Pass", str(raised.exception))

	def test_returns_and_work_orders_without_a_sewing_plan_are_exempt(self):
		self.assertFalse(self.validate(self.grn(is_return=1), []).called)
		self.assertFalse(self.validate(self.grn(), [], has_plan=False).called)

	def test_colour_falls_back_to_the_variant_when_the_row_has_no_major_colour(self):
		grn = self.grn()
		grn["items"][0].set_combination = "{}"
		with self.assertRaises(frappe.ValidationError) as raised:
			self.validate(grn, [])

		self.assertIn("Red / M", str(raised.exception))

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting import movement

MODULE = "essdee_yrp.cutting.movement"


def transaction(doctype="YRP Delivery Challan", **values):
	doc = frappe._dict(
		doctype=doctype, lot="LOT-1", items=[frappe._dict(item_variant="TB-S", delivered_quantity=2)]
	)
	doc.update(values)
	return doc


class TestCutPanelMovementRequired(UnitTestCase):
	def check(self, doc, *, cut_stage=True, tracking_disabled=False):
		with (
			patch(f"{MODULE}._bundle_tracking_disabled", return_value=tracking_disabled),
			patch(f"{MODULE}.has_cut_stage_items", return_value=cut_stage) as has_cut_stage,
		):
			movement.validate_movement_required(doc)
		return has_cut_stage

	def test_plain_delivery_challan_of_cut_panels_is_blocked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must move through a Cut Panel Movement"):
			self.check(transaction())

	def test_plain_goods_received_note_of_cut_panels_is_blocked(self):
		doc = transaction("YRP Goods Received Note", items=[frappe._dict(item_variant="TB-S", quantity=2)])
		with self.assertRaisesRegex(frappe.ValidationError, "Create this Goods Received Note"):
			self.check(doc)

	def test_cut_panel_movement_or_allow_non_bundle_passes(self):
		for values in ({"cut_panel_movement": "CPM-1"}, {"allow_non_bundle": 1}):
			self.check(transaction(**values)).assert_not_called()

	def test_grn_from_laysheet_return_or_packing_passes(self):
		for field in ("cutting_laysheet", "is_return", "includes_packing"):
			self.check(transaction("YRP Goods Received Note", **{field: 1})).assert_not_called()

	def test_lot_listed_in_mrp_settings_passes(self):
		self.check(transaction(), tracking_disabled=True).assert_not_called()

	def test_non_cut_stage_rows_pass(self):
		self.check(transaction(), cut_stage=False).assert_called_once()

	def test_zero_quantity_rows_are_ignored(self):
		doc = transaction(items=[frappe._dict(item_variant="TB-S", delivered_quantity=0, qty=0)])
		has_cut_stage = self.check(doc, cut_stage=False)
		self.assertEqual(has_cut_stage.call_args.args[0], [])

	def test_cut_stage_is_the_ipd_stitching_in_stage(self):
		with (
			patch(f"{MODULE}.attribute_db.get_value", side_effect=["IPD-1", ("Cut", "Stage")]),
			patch(f"{MODULE}.frappe.db.exists", return_value=True) as exists,
		):
			self.assertTrue(movement.has_cut_stage_items([{"item_variant": "TB-S"}], "LOT-1"))
		exists.assert_called_once_with(
			"Item Variant Attribute", {"parent": "TB-S", "attribute": "Stage", "attribute_value": "Cut"}
		)

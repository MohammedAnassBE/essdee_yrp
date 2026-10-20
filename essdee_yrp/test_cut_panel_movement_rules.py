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


class TestCutPanelMovementReceivedTypeRows(UnitTestCase):
	def overlay(self, source_rows, qty, target="YRP Delivery Challan"):
		qty_field = "quantity" if target == "YRP Goods Received Note" else "qty"
		moved = [
			frappe._dict(
				item_variant="TB-S", set_combination={}, table_index=0, row_index=0, **{qty_field: qty}
			)
		]
		return movement._overlay_source_rows(source_rows, moved, target_doctype=target)

	def rework_rows(self):
		return [
			frappe._dict(
				item_variant="TB-S", set_combination={}, received_type="Printing Mistake", pending_quantity=3
			),
			frappe._dict(
				item_variant="TB-S", set_combination={}, received_type="Oil Mark", pending_quantity=2
			),
		]

	def test_delivery_challan_fills_each_received_type_row_up_to_pending(self):
		rows = self.overlay(self.rework_rows(), 5)
		self.assertEqual(
			[(row.received_type, row.qty) for row in rows], [("Printing Mistake", 3), ("Oil Mark", 2)]
		)

	def test_delivery_challan_excess_stays_on_the_first_row(self):
		rows = self.overlay(self.rework_rows(), 6)
		self.assertEqual(
			[(row.received_type, row.qty) for row in rows], [("Printing Mistake", 4), ("Oil Mark", 2)]
		)

	def test_single_row_takes_the_whole_quantity(self):
		rows = self.overlay(
			[frappe._dict(item_variant="TB-S", set_combination={}, received_type="Accepted")], 4
		)
		self.assertEqual(
			[(row.received_type, row.qty, row.delivered_quantity) for row in rows], [("Accepted", 4, 4)]
		)

	def test_goods_received_note_keeps_the_first_matching_row(self):
		rows = self.overlay(self.rework_rows(), 5, target="YRP Goods Received Note")
		self.assertEqual([(row.received_type, row.quantity) for row in rows], [("Printing Mistake", 5)])

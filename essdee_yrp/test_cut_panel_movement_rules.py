from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting import movement

MODULE = "essdee_yrp.cutting.movement"


def transaction(doctype="YRP Delivery Challan", **values):
	doc = frappe._dict(
		doctype=doctype,
		lot="LOT-1",
		from_location="S-SOURCE",
		items=[frappe._dict(item_variant="TB-S", delivered_quantity=2)],
	)
	doc.update(values)
	return doc


class TestCutPanelMovementRequired(UnitTestCase):
	def check(self, doc, *, cut_stage=True, tracking_disabled=False, collapsed=()):
		with (
			patch(f"{MODULE}._bundle_tracking_disabled", return_value=tracking_disabled),
			patch(f"{MODULE}.has_cut_stage_items", return_value=cut_stage) as has_cut_stage,
			patch(f"{MODULE}.get_collapsed_panels", return_value=list(collapsed)),
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

	def test_collapsed_source_stock_asks_for_allow_non_bundle(self):
		with self.assertRaisesRegex(
			frappe.ValidationError, "S-SOURCE are collapsed stock. Tick Allow Non Bundle"
		):
			self.check(transaction(), collapsed=[{"panel": "Sleeve"}])

	def test_lot_listed_in_mrp_settings_passes(self):
		self.check(transaction(), tracking_disabled=True).assert_not_called()

	def test_non_cut_stage_rows_pass(self):
		self.check(transaction(), cut_stage=False).assert_called_once()

	def test_zero_quantity_rows_are_ignored(self):
		doc = transaction(items=[frappe._dict(item_variant="TB-S", delivered_quantity=0, qty=0)])
		has_cut_stage = self.check(doc, cut_stage=False)
		self.assertEqual(has_cut_stage.call_args.args[0], [])

	def test_correction_rows_are_checked_too(self):
		doc = transaction(
			items=[], correction_items=[frappe._dict(item_variant="TB-S", delivered_quantity=1)]
		)
		with self.assertRaisesRegex(frappe.ValidationError, "must move through a Cut Panel Movement"):
			self.check(doc)

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


class TestCutPanelMovementOwnsStockType(UnitTestCase):
	def link(self, doc, movement_json):
		cpm = frappe._dict(docstatus=1, against=None, against_id=None, cut_panel_movement_json=movement_json)
		with (
			patch(f"{MODULE}.frappe.db.get_value", return_value=cpm),
			patch(f"{MODULE}._get_active_root_transaction", return_value=None),
		):
			movement.validate_transaction_link(doc)
		return doc

	def test_collapsed_movement_ticks_allow_non_bundle(self):
		collapsed = '{"collapsed_details": [{"moved": 1, "move_qty": 2}]}'
		doc = self.link(transaction(cut_panel_movement="CPM-1", allow_non_bundle=0), collapsed)
		self.assertEqual(doc.allow_non_bundle, 1)

	def test_exact_movement_clears_allow_non_bundle(self):
		doc = self.link(transaction(cut_panel_movement="CPM-1", allow_non_bundle=1), '{"data": {}}')
		self.assertEqual(doc.allow_non_bundle, 0)


class TestReturnMovementScope(UnitTestCase):
	"""A return GRN built from a CPM carries every CPM panel in full, and nothing else."""

	def validate(self, returned_rows):
		ipd = frappe._dict(stiching_attribute="Panel")
		movement_rows = [
			{"item_variant": "TF-S", "quantity": 8, "set_combination": {"major_colour": "Green"}},
			{"item_variant": "SL-S", "quantity": 8, "set_combination": {"major_colour": "Green"}},
			{"item_variant": "LABEL", "quantity": 1, "set_combination": {}},
		]
		doc = transaction(
			"YRP Goods Received Note", is_return=1, cut_panel_movement="CPM-RET", items=returned_rows
		)
		panels = {
			"TF-S": {"Panel": "Top Front"},
			"SL-S": {"Panel": "Sleeve"},
			"TB-S": {"Panel": "Top Back"},
			"LABEL": {},
		}
		with (
			patch(
				f"{MODULE}.get_grouped_movement_rows",
				return_value=(frappe._dict(name="CPM-RET"), ipd, movement_rows),
			),
			patch(f"{MODULE}.get_variant_attr_details", side_effect=lambda variant: panels[variant]),
		):
			movement.validate_return_movement(doc)

	def row(self, variant, quantity):
		return frappe._dict(
			item_variant=variant, quantity=quantity, set_combination={"major_colour": "Green"}
		)

	def test_full_return_passes(self):
		self.validate([self.row("TF-S", 8), self.row("SL-S", 8)])

	def test_missing_panel_is_blocked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "TF-S: Cut Panel Movement 8.0, return 0"):
			self.validate([self.row("SL-S", 8)])

	def test_partial_quantity_is_blocked(self):
		with self.assertRaisesRegex(frappe.ValidationError, "SL-S: Cut Panel Movement 8.0, return 5.0"):
			self.validate([self.row("TF-S", 8), self.row("SL-S", 5)])

	def test_extra_panel_is_blocked(self):
		rows = [self.row("TF-S", 8), self.row("SL-S", 8), frappe._dict(item_variant="TB-S", quantity=2)]
		with self.assertRaisesRegex(frappe.ValidationError, "TB-S: Cut Panel Movement 0, return 2.0"):
			self.validate(rows)

	def test_forward_grn_and_plain_return_are_not_checked(self):
		with patch(f"{MODULE}.get_grouped_movement_rows") as grouped:
			movement.validate_return_movement(
				transaction("YRP Goods Received Note", cut_panel_movement="CPM-1")
			)
			movement.validate_return_movement(transaction("YRP Goods Received Note", is_return=1))
		grouped.assert_not_called()

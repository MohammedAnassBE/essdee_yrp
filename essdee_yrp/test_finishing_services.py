from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.finishing.state import (
	get_finishing_plan_dict,
	get_finishing_plan_list,
)
from essdee_yrp.finishing.grn import (
	apply_goods_received_note,
	_update_finishing_inward,
	_update_return_receipt,
)
from essdee_yrp.finishing.rebuild import _apply_rework_receipt_rows
from essdee_yrp.finishing.insights import fetch_rejected_quantity
from essdee_yrp.finishing.closure import complete_ocr
from essdee_yrp.finishing.old_lot import (
	_apply_lot_transfer_to_finishing,
	_record_split_history,
	_reverse_split_history,
)
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.reports import (
	apply_set_item_multiplier_to_packing_report,
)
from essdee_yrp.finishing.status import (
	compute_received_status,
	get_finishing_dispatch_totals,
	get_unaccountable_quantity,
)
from essdee_yrp.finishing.transactions import _normalize_dispatch_quantities
from essdee_yrp.finishing.packing_grn import _allocate_set_rows


class TestFinishingServices(IntegrationTestCase):
	@patch("essdee_yrp.finishing.rebuild.rebuild_finishing_plan")
	def test_legacy_fetch_rejected_button_uses_complete_authoritative_rebuild(
		self, rebuild
	):
		fetch_rejected_quantity("FP-1")

		rebuild.assert_called_once_with("FP-1", check_permission=True)

	@patch("essdee_yrp.finishing.rebuild.rebuild_finishing_plan")
	@patch("essdee_yrp.finishing.grn._is_finishing_inward_process", return_value=True)
	@patch("essdee_yrp.finishing.grn.frappe.db.get_value", return_value="FP-1")
	def test_rework_grn_uses_authoritative_rebuild_instead_of_new_inward(
		self, _get_value, _is_finishing, rebuild
	):
		grn = _doc(
			name="GRN-REWORK-1",
			against="Work Order",
			against_id="WO-REWORK-1",
			lot="LOT-1",
			process_name="Stitching",
			is_rework=1,
			includes_packing=0,
		)

		apply_goods_received_note(grn, cancelled=False)

		rebuild.assert_called_once_with("FP-1", check_permission=False)

	def test_rework_receipt_rows_clear_only_accepted_or_rejected_projection(self):
		key = ("VAR-1", (("major_colour", "Blue"),))
		items = {key: {"item_variant": "VAR-1"}}
		rework = {
			key: {"quantity": 5, "reworked_quantity": 1, "rejected_qty": 0}
		}
		rows = [
			_row(
				item_variant="VAR-1",
				quantity=3,
				received_type="Accepted",
				set_combination='{"major_colour":"Blue"}',
			),
			_row(
				item_variant="VAR-1",
				quantity=1,
				received_type="Rejected",
				set_combination='{"major_colour":"Blue"}',
			),
			_row(
				item_variant="VAR-1",
				quantity=1,
				received_type="Misstitch",
				set_combination='{"major_colour":"Blue"}',
			),
		]

		_apply_rework_receipt_rows(rows, items, rework, "Accepted", "Rejected")

		self.assertEqual(rework[key]["quantity"], 5)
		self.assertEqual(rework[key]["reworked_quantity"], 4)
		self.assertEqual(rework[key]["rejected_qty"], 1)

	def test_legacy_dispatch_grid_reads_only_positive_current_quantities(self):
		self.assertEqual(
			_normalize_dispatch_quantities(
				{
					"45 cm": {"packed": 4, "dispatched": 0, "cur_dispatch": 1},
					"50 cm": {"packed": 0, "dispatched": 0, "cur_dispatch": 0},
				}
			),
			{"45 cm": 1},
		)

	def test_legacy_packing_allocates_complete_sets_across_combinations(self):
		sepia = [
			_row(idx=1, set_combination='{"major_colour":"Sepia"}', delivered_quantity=12),
			_row(idx=2, set_combination='{"major_colour":"Sepia"}', delivered_quantity=12),
		]
		pista = [
			_row(idx=3, set_combination='{"major_colour":"Pista"}', delivered_quantity=12),
			_row(idx=4, set_combination='{"major_colour":"Pista"}', delivered_quantity=12),
		]

		allocations = _allocate_set_rows([*sepia, *pista], 20)

		self.assertEqual([quantity for _rows, quantity in allocations], [12, 8])
		self.assertTrue(all(len(rows) == 2 for rows, _quantity in allocations))

	def test_legacy_packing_does_not_reuse_a_combination_across_split_output_rows(self):
		red = [
			_row(name="RED-TOP", idx=1, set_combination='{"major_colour":"Red"}', delivered_quantity=12),
			_row(name="RED-BOTTOM", idx=2, set_combination='{"major_colour":"Red"}', delivered_quantity=12),
		]
		pista = [
			_row(name="PISTA-TOP", idx=3, set_combination='{"major_colour":"Pista"}', delivered_quantity=8),
			_row(name="PISTA-BOTTOM", idx=4, set_combination='{"major_colour":"Pista"}', delivered_quantity=8),
		]
		balances = {row.name: row.delivered_quantity for row in [*red, *pista]}

		first = _allocate_set_rows([*red, *pista], 10, balances)
		second = _allocate_set_rows([*red, *pista], 10, balances)

		self.assertEqual([quantity for _rows, quantity in first], [10])
		self.assertEqual([quantity for _rows, quantity in second], [2, 8])
		self.assertTrue(all(quantity == 0 for quantity in balances.values()))

	def test_legacy_double_encoded_set_combination_is_unwrapped(self):
		value = '"{\\"major_colour\\":\\"Green\\",\\"major_part\\":\\"Top\\"}"'

		self.assertEqual(
			json_object(value),
			{"major_colour": "Green", "major_part": "Top"},
		)

	def test_legacy_double_encoded_combination_builds_finishing_state(self):
		doc = _doc(
			finishing_plan_details=[
				_row(
					item_variant="VAR-1",
					set_combination='"{\\"major_colour\\":\\"Green\\"}"',
					accepted_qty=4,
				)
			]
		)

		indexed = get_finishing_plan_dict(doc)

		self.assertEqual(
			indexed[("VAR-1", (("major_colour", "Green"),))]["accepted_qty"],
			4,
		)

	@patch(
		"essdee_yrp.finishing.grn._received_type_defaults",
		return_value=("Accepted", "Rejected"),
	)
	def test_grn_finishing_inward_apply_and_cancel_are_symmetric(self, _defaults):
		doc = _doc(
			finishing_plan_details=[
				_row(item_variant="VAR-1", received_type_json='{"Accepted":2}')
			]
		)
		grn = _doc(
			items=[
				_row(item_variant="VAR-1", received_type="Accepted", quantity=3),
				_row(item_variant="VAR-1", received_type="Rejected", quantity=1),
			]
		)

		_update_finishing_inward(doc, grn, cancelled=False)
		row = doc.finishing_plan_details[0]
		self.assertEqual(row["delivered_quantity"], 4)
		self.assertEqual(row["accepted_qty"], 3)
		self.assertEqual(frappe.parse_json(row["received_type_json"]), {"Accepted": 5, "Rejected": 1})
		self.assertEqual(doc.finishing_plan_reworked_details[0]["quantity"], 1)

		_update_finishing_inward(doc, grn, cancelled=True)
		row = doc.finishing_plan_details[0]
		self.assertEqual(row["delivered_quantity"], 0)
		self.assertEqual(row["accepted_qty"], 0)
		self.assertEqual(frappe.parse_json(row["received_type_json"]), {"Accepted": 2, "Rejected": 0})
		self.assertEqual(doc.finishing_plan_reworked_details[0]["quantity"], 0)

	@patch(
		"essdee_yrp.finishing.grn._received_type_defaults",
		return_value=("Accepted", "Rejected"),
	)
	def test_finishing_return_updates_return_and_rework_buckets(self, _defaults):
		doc = _doc(
			finishing_plan_details=[
				_row(
					item_variant="VAR-1",
					accepted_qty=10,
					dc_qty=10,
				)
			]
		)
		grn = _doc(
			name="GRN-RETURN",
			is_pack=0,
			from_finishing=1,
			items=[
				_row(item_variant="VAR-1", received_type="Accepted", quantity=2),
				_row(item_variant="VAR-1", received_type="Rejected", quantity=1),
			],
		)

		_update_return_receipt(doc, grn, cancelled=False)
		row = doc.finishing_plan_details[0]
		self.assertEqual(row["return_qty"], 2)
		self.assertEqual(row["accepted_qty"], 9)
		self.assertEqual(row["dc_qty"], 7)
		self.assertEqual(doc.finishing_plan_reworked_details[0]["rejected_qty"], 1)

		_update_return_receipt(doc, grn, cancelled=True)
		row = doc.finishing_plan_details[0]
		self.assertEqual(row["return_qty"], 0)
		self.assertEqual(row["accepted_qty"], 10)
		self.assertEqual(row["dc_qty"], 10)
		self.assertEqual(doc.finishing_plan_reworked_details[0]["rejected_qty"], 0)

	def test_set_item_dpr_multiplies_pieces_but_not_physical_boxes(self):
		packing = _row(
			size_pieces={"S": 50, "M": 25},
			total_pieces=75,
			total_boxes=15,
			pieces_per_box=5,
		)
		ipd = _row(
			is_set_item=1,
			set_item_combination_details=[
				_row(set_item_attribute_value="Top"),
				_row(set_item_attribute_value="Bottom"),
			],
		)

		result = apply_set_item_multiplier_to_packing_report(packing, ipd)

		self.assertEqual(result.size_pieces, {"S": 100.0, "M": 50.0})
		self.assertEqual(result.total_pieces, 150.0)
		self.assertEqual(result.total_boxes, 15)
		self.assertEqual(result.pieces_per_box, 5)

	def test_detail_state_round_trip_preserves_business_quantities(self):
		doc = _doc(
			finishing_plan_details=[
				_row(
					item_variant="VAR-1",
					set_combination='{"major_colour":"Blue"}',
					received_type_json='{"Accepted":12}',
					cutting_qty=20,
					delivered_quantity=12,
					ironing_excess=2,
				)
			]
		)
		indexed = get_finishing_plan_dict(doc)
		rows = get_finishing_plan_list(indexed)

		self.assertEqual(rows[0]["item_variant"], "VAR-1")
		self.assertEqual(rows[0]["cutting_qty"], 20)
		self.assertEqual(rows[0]["delivered_quantity"], 12)
		self.assertEqual(rows[0]["ironing_excess"], 2)
		self.assertEqual(frappe.parse_json(rows[0]["received_type_json"]), {"Accepted": 12})

	@patch("essdee_yrp.finishing.old_lot.apply_auto_fp_status")
	@patch("essdee_yrp.finishing.old_lot.frappe.get_doc")
	def test_lot_transfer_submit_and_cancel_are_symmetric(self, get_doc, _status):
		plan = _doc(
			name="FP-1",
			lot_transfer_list="{}",
			finishing_plan_details=[
				_row(item_variant="VAR-1", set_combination='{"major_colour":"Blue"}')
			],
		)
		transfer = _doc(
			name="LT-1",
			finishing_plan="FP-1",
			items=[
				_row(
					item="VAR-1",
					qty=4,
					set_combination='{"major_colour":"Blue"}',
				)
			],
		)
		get_doc.return_value = plan

		_apply_lot_transfer_to_finishing(transfer, cancelled=False)
		self.assertEqual(plan.finishing_plan_details[0]["lot_transferred"], 4)
		self.assertIn("LT-1", frappe.parse_json(plan.lot_transfer_list))

		_apply_lot_transfer_to_finishing(transfer, cancelled=True)
		self.assertEqual(plan.finishing_plan_details[0]["lot_transferred"], 0)
		self.assertNotIn("LT-1", frappe.parse_json(plan.lot_transfer_list))

	@patch("essdee_yrp.finishing.old_lot.apply_auto_fp_status")
	@patch("essdee_yrp.finishing.old_lot.frappe.get_doc")
	def test_old_lot_history_submit_and_cancel_are_symmetric(self, get_doc, _status):
		available = _row(
			source_fp="FP-SOURCE",
			source_lot="LOT-OLD",
			warehouse="WH-1",
			item_variant="VAR-1",
			balance_loose_piece=5,
			balance_loose_piece_set=2,
			transfer_loose_piece=3,
			transfer_loose_piece_set=1,
			lot_transfer=None,
		)
		destination = _doc(
			name="FP-DEST",
			lot="LOT-NEW",
			finishing_old_lot_items=[available],
			finishing_old_lot_received_items=[],
		)
		source = _doc(
			name="FP-SOURCE",
			delivery_location="WH-1",
			finishing_old_lot_given_items=[],
		)
		transfer = _doc(name="LT-1", finishing_plan="FP-DEST")
		get_doc.side_effect = lambda _doctype, name: (
			destination if name == "FP-DEST" else source
		)
		contribution = {
			"source_fp": "FP-SOURCE",
			"source_lot": "LOT-OLD",
			"item_variant": "VAR-1",
			"colour": "Blue",
			"part": "Top",
			"set_combination": {"major_colour": "Blue", "major_part": "Top"},
			"size": "S",
			"loose_piece": 3,
			"loose_piece_set": 1,
		}

		_record_split_history(destination, transfer, [contribution])
		self.assertEqual(available.balance_loose_piece, 2)
		self.assertEqual(available.balance_loose_piece_set, 1)
		self.assertEqual(len(destination.finishing_old_lot_received_items), 1)
		self.assertEqual(len(source.finishing_old_lot_given_items), 1)

		_reverse_split_history(transfer)
		self.assertEqual(available.balance_loose_piece, 5)
		self.assertEqual(available.balance_loose_piece_set, 2)
		self.assertEqual(destination.finishing_old_lot_received_items, [])
		self.assertEqual(source.finishing_old_lot_given_items, [])

	@patch("essdee_yrp.finishing.closure.get_unaccountable_quantity", return_value=0)
	@patch("essdee_yrp.finishing.closure.frappe.get_doc")
	def test_complete_ocr_closes_only_a_zero_balance_plan(self, get_doc, _balance):
		plan = _doc(name="FP-1", fp_status="Fully Dispatched")
		get_doc.return_value = plan

		result = complete_ocr("FP-1")

		self.assertEqual(result, {"fp_status": "OCR Completed", "unaccountable": 0.0})
		self.assertEqual(plan.fp_status, "OCR Completed")

	@patch("essdee_yrp.finishing.status.get_set_item_parts_count", return_value=2)
	@patch("essdee_yrp.finishing.status.get_finishing_packing_summary")
	def test_legacy_set_dispatch_converts_boxes_to_component_pieces(
		self, packing_summary, _parts_count
	):
		packing_summary.return_value = frappe._dict(dynamic_ratio_packing=False)
		doc = _doc(
			pieces_per_box=5,
			finishing_plan_details=[_row(cutting_qty=200)],
			finishing_plan_grn_details=[_row(dispatched=10)],
		)

		totals = get_finishing_dispatch_totals(doc)

		self.assertEqual(totals.total_dispatched_pieces, 100)
		self.assertEqual(totals.dispatch_percentage, 50)

	def test_ocr_balance_accounts_for_rework_and_old_lot_transfers(self):
		doc = _doc(
			finishing_plan_details=[
				_row(
					delivered_quantity=100,
					lot_transferred=10,
					ironing_excess=2,
					transferred_qty=5,
					rejected_qty=2,
					return_qty=3,
					pack_return_qty=4,
				)
			],
			finishing_plan_reworked_details=[
				_row(quantity=7, reworked_quantity=4, rejected_qty=1)
			],
			finishing_old_lot_given_items=[
				_row(loose_piece_given=2, loose_piece_set_given=1)
			],
			finishing_old_lot_received_items=[
				_row(loose_piece_taken=1, loose_piece_set_taken=1)
			],
		)

		# 112 inward - 90 dispatched - 3 rejected - 2 pending - 5 transferred
		# - (3 - 2 + 1) loose - (4 - 1 + 1) loose-set = 6.
		self.assertEqual(get_unaccountable_quantity(doc, dispatched_pieces=90), 6)

	@patch("essdee_yrp.finishing.status.get_unaccountable_quantity", return_value=0)
	@patch("essdee_yrp.finishing.status.get_finishing_dispatch_totals")
	@patch("essdee_yrp.finishing.status.get_finishing_plan_total_cutting", return_value=100)
	@patch("essdee_yrp.finishing.status.frappe.get_cached_doc")
	def test_status_becomes_fully_dispatched_only_with_zero_ocr_balance(
		self, get_settings, _total_cutting, dispatch_totals, _unaccountable
	):
		get_settings.return_value = _row(
			partial_received_percentage=50,
			partially_dispatched_percentage=90,
		)
		dispatch_totals.return_value = _row(total_dispatched_pieces=98)
		doc = _doc(finishing_plan_details=[])

		self.assertEqual(compute_received_status(doc), "Fully Dispatched")


def _row(**values):
	defaults = {
		"cutting_qty": 0,
		"inward_quantity": 0,
		"delivered_quantity": 0,
		"accepted_qty": 0,
		"dc_qty": 0,
		"lot_transferred": 0,
		"ironing_excess": 0,
		"reworked": 0,
		"return_qty": 0,
		"pack_return_qty": 0,
		"return_dc_qty": 0,
		"pack_dc_qty": 0,
		"transferred_qty": 0,
		"rejected_qty": 0,
		"set_combination": "{}",
		"received_type_json": "{}",
		"item_variant": None,
		"dispatched": 0,
		"quantity": 0,
		"reworked_quantity": 0,
		"loose_piece_given": 0,
		"loose_piece_set_given": 0,
		"loose_piece_taken": 0,
		"loose_piece_set_taken": 0,
		"received_type": None,
		"item": None,
		"qty": 0,
	}
	defaults.update(values)
	return frappe._dict(defaults)


def _doc(**values):
	defaults = {
		"production_detail": None,
		"lot": None,
		"work_order": None,
		"pieces_per_box": 0,
		"finishing_plan_details": [],
		"finishing_plan_grn_details": [],
		"finishing_plan_reworked_details": [],
		"finishing_old_lot_given_items": [],
		"finishing_old_lot_received_items": [],
		"name": None,
		"is_pack": 0,
		"from_finishing": 0,
		"return_grn_list": "{}",
		"pack_return_list": "{}",
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.get = lambda key, default=None: doc[key] if key in doc else default
	doc.set = lambda key, value: doc.__setitem__(key, value)
	doc.append = lambda key, value: _append(doc, key, value)
	doc.save = lambda **_kwargs: doc
	doc.check_permission = lambda *_args, **_kwargs: None
	return doc


def _append(doc, key, value):
	row = _row(**value)
	doc.setdefault(key, []).append(row)
	return row

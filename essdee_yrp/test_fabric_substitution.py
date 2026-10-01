from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting_plan import (
	_split_required_weight,
	apply_lot_fabric_substitutions,
	expand_cutting_rows,
)
from essdee_yrp.fabric_program import SERVER_OWNED_TABLES
from essdee_yrp.fabric_substitution import (
	_advance_route_state,
	build_conversion_rows,
	build_lot_fabric_substitutions,
	resolve_process_conversion,
)
from essdee_yrp.hooks import override_whitelisted_methods
from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote
from yrp.yrp.doctype.goods_received_note.goods_received_note import GoodsReceivedNote


class TestFabricSubstitution(UnitTestCase):
	def test_split_actual_dias_are_grouped_under_one_planned_variant(self):
		lot = frappe._dict(
			name="LOT-1",
			lot_fabric_conversions=[
				_row(
					from_item="CLOTH-36-RED",
					to_item="CLOTH-30-RED",
					to_qty=5,
				),
				_row(
					from_item="CLOTH-36-RED",
					to_item="CLOTH-32-RED",
					to_qty=4,
				),
			],
		)
		with (
			patch(
				"essdee_yrp.fabric_substitution._selected_terminal_steps",
				return_value=[{
					"production_detail": "IPD-1", "process_name": "Washing",
				}],
			),
			patch(
				"essdee_yrp.fabric_substitution._variant_state",
				side_effect=lambda variant: {
					"variant": variant,
					"item": "CLOTH",
					"attrs": {
						"Dia": variant.split("-")[1], "Colour": "Red",
					},
				},
			),
		):
			result = build_lot_fabric_substitutions(lot)

		self.assertEqual(len(result["mappings"]), 1)
		mapping = result["mappings"][0]
		self.assertEqual(mapping["from_item_variant"], "CLOTH-36-RED")
		self.assertEqual(mapping["planned_qty"], 9)
		self.assertEqual(mapping["received_qty"], 9)
		self.assertTrue(mapping["is_substituted"])
		self.assertEqual(
			{row["item_variant"]: row["received_qty"] for row in mapping["actual"]},
			{"CLOTH-30-RED": 5, "CLOTH-32-RED": 4},
		)

	def test_cutting_generate_replaces_one_planned_row_with_actual_rows(self):
		rows = [{
			"cloth_item_variant": "CLOTH-36-RED",
			"cloth_type": "Body",
			"colour": "Red",
			"dia": "36 Dia",
			"required_weight": 9,
			"weight": 0,
			"used_weight": 0,
			"balance_weight": 0,
		}]
		index = {"CLOTH-36-RED": {"actual": [
			{
				"item_variant": "CLOTH-30-RED", "dia": "30 Dia",
				"colour": "Red", "received_qty": 5,
			},
			{
				"item_variant": "CLOTH-32-RED", "dia": "32 Dia",
				"colour": "Red", "received_qty": 4,
			},
		]}}

		expanded, changed = expand_cutting_rows(rows, index)

		self.assertEqual(changed, 1)
		self.assertEqual(
			[(row["cloth_item_variant"], row["required_weight"]) for row in expanded],
			[("CLOTH-30-RED", 5), ("CLOTH-32-RED", 4)],
		)
		self.assertEqual(sum(row["required_weight"] for row in expanded), 9)

	def test_cutting_split_preserves_total_after_rounding(self):
		result = _split_required_weight(7, [5, 4])
		self.assertEqual(result, [3.889, 3.111])
		self.assertEqual(round(sum(result), 3), 7)

	def test_unmapped_cutting_row_is_unchanged(self):
		row = {
			"cloth_item_variant": "CLOTH-36-RED",
			"required_weight": 9,
			"weight": 2,
		}
		expanded, changed = expand_cutting_rows([row], {})
		self.assertEqual(changed, 0)
		self.assertEqual(expanded, [row])

	def test_cutting_generate_api_is_overridden_in_essdee(self):
		self.assertEqual(
			override_whitelisted_methods[
				"production_api.production_api.doctype.cutting_plan.cutting_plan.get_cloth1"
			],
			"essdee_yrp.cutting_plan.get_cloth1",
		)

	def test_cutting_uses_all_lot_cloth_ipds_not_garment_ipd(self):
		doc = frappe._dict(
			name="CP-1",
			lot="LOT-1",
			production_detail="GARMENT-IPD",
			cutting_plan_cloth_details=[],
		)
		doc.get = lambda key, default=None: dict.get(doc, key, default)
		with (
			patch("essdee_yrp.cutting_plan.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting_plan.substitution_index", return_value={}) as index,
		):
			apply_lot_fabric_substitutions(doc.name)
		index.assert_called_once_with("LOT-1")

	def test_lot_conversion_is_a_server_owned_table(self):
		self.assertIn(
			("lot_fabric_conversions", "Lot Fabric Conversion"),
			SERVER_OWNED_TABLES,
		)

	def test_stale_conversion_never_coerces_exact_projection(self):
		with self.assertRaisesRegex(
			frappe.ValidationError, "Lot fabric conversion is out of date"
		):
			resolve_process_conversion(
				{("ROUTE", "PLAN"): {"ACTUAL-30": 5}},
				route_item="ROUTE",
				from_item="PLAN",
				projected_item="ACTUAL-32",
			)

	def test_identity_projection_preserves_all_variant_attributes(self):
		planned = {
			"variant": "CLOTH-36-RED-180GSM",
			"item": "CLOTH",
			"attrs": {"Dia": "36", "Colour": "Red", "GSM": "180"},
		}
		actual = {
			"variant": "CLOTH-32-RED-180GSM",
			"item": "CLOTH",
			"attrs": {"Dia": "32", "Colour": "Red", "GSM": "180"},
		}
		with (
			patch("essdee_yrp.api.work_order._step_kind", return_value="identity"),
			patch(
				"essdee_yrp.fabric_ipd.get_identity_process_row",
				return_value=frappe._dict(process_item="CLOTH"),
			),
		):
			result = _advance_route_state(
				frappe._dict(name="IPD-1"),
				{"process_name": "Washing"},
				"ROUTE",
				planned,
				actual,
			)
		self.assertEqual(result, [(planned, actual)])

	def test_grn_controller_updates_and_reverses_projection(self):
		doc = EssdeeGoodsReceivedNote({"doctype": "Goods Received Note"})
		with (
			patch.object(GoodsReceivedNote, "on_submit") as base_submit,
			patch.object(GoodsReceivedNote, "on_cancel") as base_cancel,
			patch.object(
				EssdeeGoodsReceivedNote,
				"_uses_essdee_deliverable_consumption",
				return_value=False,
			),
			patch("essdee_yrp.fabric_tracking.on_grn_submit") as project_submit,
			patch("essdee_yrp.fabric_tracking.on_grn_cancel") as project_cancel,
			patch(
				"essdee_yrp.fabric_substitution.rebuild_lot_fabric_conversions_for_grn"
			) as rebuild,
			patch.object(EssdeeGoodsReceivedNote, "_enqueue_repost"),
		):
			doc.on_submit()
			doc.on_cancel()

		base_submit.assert_called_once_with()
		base_cancel.assert_called_once_with()
		project_submit.assert_called_once_with(doc)
		project_cancel.assert_called_once_with(doc)
		self.assertEqual(rebuild.call_count, 2)

	def test_grn_public_lifecycle_locks_lot_before_frappe_parent_lock(self):
		doc = EssdeeGoodsReceivedNote({"doctype": "Goods Received Note"})
		calls = []
		with (
			patch(
				"essdee_yrp.fabric_substitution.lock_lot_for_default_knitting_grn",
				side_effect=lambda _doc: calls.append("lot"),
			),
			patch.object(
				GoodsReceivedNote,
				"submit",
				side_effect=lambda: calls.append("submit"),
			),
			patch.object(
				GoodsReceivedNote,
				"cancel",
				side_effect=lambda: calls.append("cancel"),
			),
		):
			doc.submit()
			doc.cancel()
		self.assertEqual(calls, ["lot", "submit", "lot", "cancel"])

	def test_conversion_rebuild_aggregates_multiple_grns_idempotently(self):
		receipts = [
			_receipt("GRN-1", 5),
			_receipt("GRN-2", 4),
		]

		def project(group, _process):
			return [{
				"production_detail": group["production_detail"],
				"route_item": group["route_item"],
				"source_from_item": group["planned_item_variant"],
				"source_to_item": group["actual_item_variant"],
				"stage_index": 1,
				"process_name": "Dyeing",
				"from_item": "CLOTH-36-NAVY",
				"to_item": "CLOTH-30-NAVY",
				"received_type": "Accepted",
				"stock_uom": "Kg",
				"to_qty": group["stock_qty"],
				"source_grns": group["source_grns"],
			}]

		with patch(
			"essdee_yrp.fabric_substitution._project_receipt_group",
			side_effect=project,
		):
			first = build_conversion_rows(receipts, "Knitting")
			second = build_conversion_rows(list(reversed(receipts)), "Knitting")

		self.assertEqual(first, second)
		self.assertEqual(first[0]["to_qty"], 9)
		self.assertEqual(first[0]["source_grn_count"], 2)


def _row(**values):
	defaults = {
		"production_detail": "IPD-1",
		"process_name": "Washing",
		"from_item": None,
		"to_item": None,
		"to_qty": 0,
		"received_type": "Accepted",
	}
	defaults.update(values)
	return frappe._dict(defaults)


def _receipt(source_grn, qty):
	return frappe._dict({
		"source_grn": source_grn,
		"source_grn_item": f"{source_grn}-ITEM",
		"production_detail": "IPD-1",
		"cloth_item": "CLOTH",
		"planned_item_variant": "CLOTH-36-GREIGE",
		"actual_item_variant": "CLOTH-30-GREIGE",
		"route_item": "CLOTH-36-NAVY",
		"received_type": "Accepted",
		"stock_uom": "Kg",
		"stock_qty": qty,
	})

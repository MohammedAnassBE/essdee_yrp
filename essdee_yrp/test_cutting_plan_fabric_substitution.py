from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp import fabric_substitution
from essdee_yrp.cutting.cloth_substitution import expand_cutting_rows, split_required_weight
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as cutting_plan

WHITE_14 = "ZZ TEST White-14 Dia"
WHITE_145 = "ZZ TEST White-14.5 Dia"


def cloth_row(**values):
	return {
		"cloth_item_variant": WHITE_14,
		"cloth_type": "Body",
		"colour": "White",
		"dia": "14",
		"required_weight": 100,
		"weight": 25,
		"used_weight": 5,
		"balance_weight": 20,
		**values,
	}


def split_index():
	return {WHITE_14: {"actual": [
		{"item_variant": WHITE_14, "dia": "14", "received_qty": 30},
		{"item_variant": WHITE_145, "dia": "14.5", "received_qty": 20},
	]}}


def conversion_row(stage, actual, quantity, **values):
	return {
		"production_detail": "ZZ TEST Cloth IPD",
		"process_stage_index": stage,
		"process_name": ("Knitting", "Dyeing", "Washing")[stage],
		"planned_item": WHITE_14,
		"actual_item": actual,
		"actual_quantity": quantity,
		"received_type": "Accepted",
		"route_item": "ZZ TEST Route",
		**values,
	}


class CuttingPlanStub:
	def __init__(self, lot="ZZ TEST Lot"):
		self.name = "ZZ TEST Cutting Plan"
		self.lot = lot
		self.cutting_plan_cloth_details = []
		self.cutting_plan_accessory_details = []
		self.add_comment = MagicMock()
		self.save = MagicMock()

	def set(self, fieldname, rows):
		setattr(self, fieldname, [frappe._dict(row) for row in rows])


@contextmanager
def generate_fixture(doc, index):
	def requirements(_doc):
		return [cloth_row(weight=0, used_weight=0, balance_weight=0)], [cloth_row(
			accessory="ZZ TEST Binding", required_weight=12, weight=0, used_weight=0, balance_weight=0
		)]

	with (
		patch.object(cutting_plan, "_get_submitted_cutting_plan", return_value=doc),
		patch.object(cutting_plan, "_build_cloth_requirement_rows", side_effect=requirements),
		patch.object(cutting_plan, "substitution_index", return_value=index) as substitutions,
	):
		yield substitutions


class TestCuttingPlanFabricSubstitution(TestCase):
	def test_expands_required_weight_by_receipts(self):
		source = cloth_row()
		original = deepcopy(source)
		rows, changed = expand_cutting_rows([source], split_index())
		self.assertEqual(changed, 1)
		self.assertEqual([row["cloth_item_variant"] for row in rows], [WHITE_14, WHITE_145])
		self.assertEqual([row["dia"] for row in rows], ["14", "14.5"])
		self.assertEqual([row["required_weight"] for row in rows], [60.000, 40.000])
		for row in rows:
			self.assertEqual(row["colour"], "White")
			self.assertEqual(row["cloth_type"], "Body")
			self.assertEqual([row[field] for field in ("weight", "used_weight", "balance_weight")], [0, 0, 0])
		self.assertEqual(source, original)

	def test_converging_substitutions_merge_required_weight(self):
		index = {WHITE_14: {"actual": [
			{"item_variant": WHITE_145, "dia": "14.5", "received_qty": 50},
		]}}
		planned = cloth_row()
		actual = cloth_row(cloth_item_variant=WHITE_145, dia="14.5")
		for sources in ([planned, actual], [actual, planned]):
			with self.subTest(sources=sources):
				original = deepcopy(sources)
				rows, changed = expand_cutting_rows(sources, index)
				self.assertEqual(changed, 1)
				self.assertEqual(rows, [cloth_row(
					cloth_item_variant=WHITE_145, dia="14.5", required_weight=200.0,
					weight=0, used_weight=0, balance_weight=0,
				)])
				self.assertEqual(sources, original)

	def test_merged_rows_keep_first_position_and_distinct_keys_unchanged(self):
		first = cloth_row(cloth_item_variant=WHITE_145, dia="14.5", required_weight=1.0004)
		others = [cloth_row(**values) for values in (
			{"cloth_item_variant": WHITE_145, "dia": "14.5", "cloth_type": "Rib"},
			{"cloth_item_variant": WHITE_145, "dia": "14.5", "colour": "Black"},
			{"cloth_item_variant": WHITE_145, "dia": "15"},
			{},
		)]
		rows, changed = expand_cutting_rows([first, *others, first, first], {})
		self.assertEqual(changed, 0)
		self.assertEqual(rows, [
			{**first, "required_weight": 3.001, "weight": 0, "used_weight": 0, "balance_weight": 0},
			*others,
		])

	def test_rounding_remainder_goes_to_last_actual_row(self):
		index = {WHITE_14: {"actual": [
			{"item_variant": f"ZZ TEST Actual {dia}", "dia": dia, "received_qty": 1}
			for dia in ("14", "14.5", "15")
		]}}
		rows, changed = expand_cutting_rows([cloth_row(required_weight=10)], index)
		weights = [row["required_weight"] for row in rows]
		self.assertEqual(changed, 1)
		self.assertEqual(weights, [3.333, 3.333, 3.334])
		self.assertEqual(sum(weights), 10)
		self.assertEqual(split_required_weight(10, []), [])
		self.assertEqual(split_required_weight(10, [0, -1]), [10, 0])

	def test_missing_or_nonpositive_receipts_leave_row_unchanged(self):
		for index in ({}, {WHITE_14: {"actual": [
			{"item_variant": WHITE_145, "received_qty": qty} for qty in (0, -2)
		]}}):
			with self.subTest(index=index):
				self.assertEqual(expand_cutting_rows([cloth_row()], index), ([cloth_row()], 0))

	def test_unchanged_dia_leaves_operational_values_unchanged(self):
		index = {WHITE_14: {"actual": [split_index()[WHITE_14]["actual"][0]]}}
		self.assertEqual(expand_cutting_rows([cloth_row()], index), ([cloth_row()], 0))

	def test_accessory_rows_never_expand(self):
		accessory = cloth_row(accessory="ZZ TEST Binding")
		self.assertEqual(expand_cutting_rows([accessory], split_index()), ([accessory], 0))
		doc = CuttingPlanStub()
		with generate_fixture(doc, split_index()):
			counts = cutting_plan.get_cloth1(doc.name)
		self.assertEqual(counts["cloth_requirements"], 2)
		self.assertEqual(counts["accessory_requirements"], 1)
		self.assertEqual(doc.cutting_plan_accessory_details, [cloth_row(
			accessory="ZZ TEST Binding", required_weight=12, weight=0, used_weight=0, balance_weight=0
		)])

	def test_terminal_washing_excludes_knitting_and_different_dyeing_quantities(self):
		greige = "ZZ TEST Greige-14 Dia"
		index = self.build_index([
			conversion_row(0, "ZZ TEST Greige-14.5 Dia", 500, planned_item=greige),
			conversion_row(1, WHITE_14, 5),
			conversion_row(1, WHITE_145, 95),
			conversion_row(2, WHITE_145, 20),
			conversion_row(2, WHITE_14, 30),
		])
		self.assertEqual(index, split_index())
		self.assertNotIn(greige, index)
		rows, changed = expand_cutting_rows([cloth_row()], index)
		self.assertEqual(changed, 1)
		self.assertEqual([row["required_weight"] for row in rows], [60, 40])

	def test_knitting_receipts_without_terminal_conversions_do_not_substitute(self):
		index = self.build_index([
			conversion_row(0, WHITE_14, 30),
			conversion_row(0, WHITE_145, 20),
		])
		self.assertNotIn(WHITE_14, index)
		self.assertEqual(expand_cutting_rows([cloth_row()], index), ([cloth_row()], 0))

	def test_ipd_without_fabric_steps_uses_stage_zero(self):
		index = self.build_index([
			conversion_row(0, WHITE_14, 30),
			conversion_row(0, WHITE_145, 20),
		], steps_by_ipd={"ZZ TEST Cloth IPD": []})
		self.assertEqual(index, split_index())

	def test_get_cloth1_comments_and_is_idempotent(self):
		doc = CuttingPlanStub()
		with generate_fixture(doc, split_index()) as substitutions:
			first_counts = cutting_plan.get_cloth1(doc.name)
			first_rows = deepcopy(doc.cutting_plan_cloth_details)
			second_counts = cutting_plan.get_cloth1(doc.name)
		self.assertEqual(first_counts, {"cloth_requirements": 2, "accessory_requirements": 1, "substituted_rows": 1})
		self.assertEqual(second_counts, first_counts)
		self.assertEqual(doc.cutting_plan_cloth_details, first_rows)
		self.assertEqual([row.required_weight for row in first_rows], [60, 40])
		self.assertEqual(substitutions.call_count, 2)
		self.assertEqual(doc.save.call_count, 2)
		comments = [call.kwargs["text"] for call in doc.add_comment.call_args_list]
		self.assertEqual(comments[1::2], ["Applied Lot fabric substitutions to 1 planned cloth row(s)."] * 2)
		self.assertTrue(all(text.startswith("Cloth Generated on ") for text in comments[::2]))

	def test_no_conversions_keeps_existing_generate_behavior(self):
		self.assertEqual(self.build_index([]), {})
		doc = CuttingPlanStub()
		doc.set("cutting_plan_cloth_details", [cloth_row()])
		with generate_fixture(doc, {}):
			counts = cutting_plan.get_cloth1(doc.name)
		self.assertEqual(counts, {"cloth_requirements": 1, "accessory_requirements": 1, "substituted_rows": 0})
		self.assertEqual(doc.cutting_plan_cloth_details, [cloth_row()])
		doc.add_comment.assert_called_once()
		self.assertTrue(doc.add_comment.call_args.kwargs["text"].startswith("Cloth Generated on "))
		self.assertRegex(doc.add_comment.call_args.kwargs["text"], r"^Cloth Generated on \d{2}-\d{2}-\d{4} \d{2}:\d{2} by ")

	def test_second_generate_preserves_actual_dia_operational_values(self):
		doc = CuttingPlanStub()
		with generate_fixture(doc, split_index()):
			cutting_plan.get_cloth1(doc.name)
			for row, weight, used in zip(doc.cutting_plan_cloth_details, [30, 20], [7, 3], strict=True):
				row.update(weight=weight, used_weight=used, balance_weight=weight - used)
			before = deepcopy(doc.cutting_plan_cloth_details)
			cutting_plan.get_cloth1(doc.name)
		self.assertEqual(doc.cutting_plan_cloth_details, before)
		self.assertEqual([row.weight for row in doc.cutting_plan_cloth_details], [30, 20])

	def test_child_documents_lose_metadata_without_mutating_source(self):
		metadata = {
			field: f"ZZ TEST {field}" for field in (
				"doctype", "name", "owner", "creation", "modified", "modified_by",
				"docstatus", "idx", "parent", "parentfield", "parenttype",
			)
		}
		source = {**cloth_row(), **metadata}
		child = SimpleNamespace(as_dict=lambda: source)
		for index in ({}, split_index()):
			with self.subTest(index=index):
				rows, _changed = expand_cutting_rows([child], index)
				for row in rows:
					self.assertTrue(metadata.keys().isdisjoint(row))
		self.assertEqual(source, {**cloth_row(), **metadata})

	def test_default_receipts_aggregate_routes_sort_and_preserve_precision(self):
		index = self.build_index([
			conversion_row(2, WHITE_145, 20),
			conversion_row(2, WHITE_14, 20.0004),
			conversion_row(2, WHITE_14, 9.9998, route_item="ZZ TEST Other Route"),
			conversion_row(2, WHITE_145, 800, received_type="Rejected"),
			conversion_row(2, WHITE_145, 900, received_type=""),
			conversion_row(2, WHITE_145, 0),
			conversion_row(2, WHITE_145, -10),
			conversion_row(2, WHITE_145, fabric_substitution.QTY_TOLERANCE),
		])
		expected = split_index()
		expected[WHITE_14]["actual"][0]["received_qty"] = 30.0002
		self.assertEqual(index, expected)

	def test_receipt_precision_is_preserved_until_required_weight_allocation(self):
		index = self.build_index([
			conversion_row(2, WHITE_14, 1.0004),
			conversion_row(2, WHITE_145, 1.0000),
		])
		rows, changed = expand_cutting_rows([cloth_row()], index)
		self.assertEqual(changed, 1)
		self.assertEqual([row["required_weight"] for row in rows], [50.01, 49.99])

	def test_small_positive_receipt_remains_available_for_substitution(self):
		index = self.build_index([conversion_row(2, WHITE_145, 0.0004)])
		self.assertEqual(index[WHITE_14]["actual"][0]["received_qty"], 0.0004)
		rows, changed = expand_cutting_rows([cloth_row()], index)
		self.assertEqual(changed, 1)
		self.assertEqual(rows, [cloth_row(
			cloth_item_variant=WHITE_145, dia="14.5", weight=0, used_weight=0, balance_weight=0
		)])

	def test_terminal_stage_is_selected_per_cloth_ipd(self):
		other = "ZZ TEST Other White"
		index = self.build_index([
			conversion_row(2, WHITE_145, 20),
			conversion_row(0, other, 900, production_detail="ZZ TEST Other IPD", planned_item=other),
			conversion_row(1, WHITE_14, 7, production_detail="ZZ TEST Other IPD", planned_item=other),
		], steps_by_ipd={
			"ZZ TEST Cloth IPD": [{"position": position} for position in range(3)],
			"ZZ TEST Other IPD": [{"position": position} for position in range(2)],
		})
		self.assertEqual(index[other], {"actual": [{"item_variant": WHITE_14, "dia": "14", "received_qty": 7}]})
		self.assertEqual(index[WHITE_14], {"actual": [{"item_variant": WHITE_145, "dia": "14.5", "received_qty": 20}]})

	def test_ineligible_terminal_receipts_never_fall_back_to_dyeing(self):
		for quantity, received_type in ((0, "Accepted"), (10, "Rejected")):
			with self.subTest(quantity=quantity, received_type=received_type):
				index = self.build_index([
					conversion_row(1, WHITE_145, 500),
					conversion_row(2, WHITE_145, quantity, received_type=received_type),
				])
				self.assertEqual(index, {})

	def test_no_lot_skips_substitution_lookup(self):
		doc = CuttingPlanStub(lot=None)
		with generate_fixture(doc, split_index()) as substitutions:
			counts = cutting_plan.get_cloth1(doc.name)
		substitutions.assert_not_called()
		self.assertEqual(counts["substituted_rows"], 0)
		self.assertEqual(doc.cutting_plan_cloth_details, [cloth_row(weight=0, used_weight=0, balance_weight=0)])

	def test_requirement_rebuild_without_preservation_still_expands(self):
		doc = CuttingPlanStub()
		with generate_fixture(doc, split_index()):
			counts = cutting_plan._generate_cloth_requirements(doc, preserve_operational_values=False)
		self.assertEqual(counts["substituted_rows"], 1)
		self.assertEqual([row.required_weight for row in doc.cutting_plan_cloth_details], [60, 40])
		self.assertEqual([row.weight for row in doc.cutting_plan_cloth_details], [0, 0])

	def build_index(self, rows, *, steps_by_ipd=None):
		if steps_by_ipd is None:
			steps_by_ipd = {"ZZ TEST Cloth IPD": [{"position": position} for position in range(3)]}
		with (
			patch.object(fabric_substitution.frappe, "get_all", return_value=rows) as get_all,
			patch.object(fabric_substitution.frappe, "get_cached_doc", side_effect=lambda doctype, name: SimpleNamespace(name=name)),
			patch.object(fabric_substitution, "get_fabric_steps", side_effect=lambda ipd: steps_by_ipd[ipd.name]),
			patch.object(fabric_substitution.frappe, "get_system_settings", return_value="Banker's Rounding"),
			patch.object(fabric_substitution, "_default_received_type", return_value="Accepted"),
			patch.object(fabric_substitution, "get_dia_attribute", return_value="Dia"),
			patch.object(fabric_substitution, "get_variant_attributes", side_effect=lambda item: {
				"Dia": {WHITE_14: "14", WHITE_145: "14.5"}[item], "Colour": "White"
			}),
		):
			index = fabric_substitution.substitution_index("ZZ TEST Lot")
		self.assertEqual(get_all.call_args.args, ("SD YRP Lot Fabric Conversion",))
		self.assertEqual(get_all.call_args.kwargs["filters"], {
			"parent": "ZZ TEST Lot", "parenttype": "SD YRP Lot", "parentfield": "lot_fabric_conversions"
		})
		return index

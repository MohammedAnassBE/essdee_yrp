import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import frappe

from essdee_yrp import fabric_substitution
from essdee_yrp.cutting_plan import _split_required_weight, expand_cutting_rows
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
	preserve_lot_fabric_conversions,
)


class TestLotFabricConversionSchema(unittest.TestCase):
	@patch.object(frappe.db, "add_index")
	def test_locking_queries_have_targeted_indexes(self, add_index):
		from essdee_yrp.patches import add_cloth_execution_lock_indexes

		add_cloth_execution_lock_indexes.execute()

		self.assertEqual(
			add_index.call_args_list,
			[
				call(
					"YRP Work Order",
					["lot", "process_name"],
					"cloth_execution_lot_process",
				),
				call(
					"YRP Goods Received Note",
					["against_id", "against", "docstatus"],
					"cloth_execution_against",
				),
			],
		)

	def test_lot_conversion_schema_uses_item_links_and_read_only_fields(self):
		path = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "essdee_yrp/doctype/sd_yrp_lot_fabric_conversion/sd_yrp_lot_fabric_conversion.json"
		)
		schema = json.loads(path.read_text(encoding="utf-8"))
		fields = {row["fieldname"]: row for row in schema["fields"]}

		for fieldname in (
			"planned_item",
			"actual_item",
			"route_item",
			"knitting_planned_item",
			"knitting_actual_item",
		):
			self.assertEqual(fields[fieldname]["fieldtype"], "Link")
			self.assertEqual(fields[fieldname]["options"], "Item")
		self.assertEqual(fields["received_type"]["options"], "YRP Received Type")
		self.assertTrue(all(row.get("read_only") for row in schema["fields"]))
		self.assertTrue(all(row.get("no_copy") for row in schema["fields"]))

	def test_conversion_table_is_server_owned_and_no_copy(self):
		path = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "essdee_yrp/doctype/sd_yrp_lot/sd_yrp_lot.json"
		)
		schema = json.loads(path.read_text(encoding="utf-8"))
		fields = {row["fieldname"]: row for row in schema["fields"]}
		table = fields["lot_fabric_conversions"]

		self.assertEqual(table["options"], "SD YRP Lot Fabric Conversion")
		self.assertEqual(table["fieldtype"], "Table")
		self.assertEqual(
			(table.get("hidden"), table.get("read_only"), table.get("no_copy")),
			(1, 1, 1),
		)

	@patch.object(frappe, "get_all", return_value=[])
	@patch.object(
		frappe.db,
		"sql",
		return_value=[frappe._dict(name="CONVERSION-1", actual_item="CLOTH-30")],
	)
	def test_stale_lot_save_reloads_conversions_with_current_read(self, current_read, _get_all):
		class LotDocument:
			name = "LOT-1"
			meta = SimpleNamespace(get_field=lambda _fieldname: True)

			def __init__(self):
				self.rows = []

			def is_new(self):
				return False

			def set(self, _fieldname, value):
				self.rows = value

			def append(self, _fieldname, value):
				row = frappe._dict(value)
				self.rows.append(row)
				return row

		lot = LotDocument()
		preserve_lot_fabric_conversions(lot)

		self.assertEqual([row.name for row in lot.rows], ["CONVERSION-1"])
		query = current_read.call_args.args[0]
		self.assertIn("FOR UPDATE", query)


class TestActualDiaAllocation(unittest.TestCase):
	@patch("essdee_yrp.fabric_substitution.get_supported_execution_route")
	@patch.object(frappe, "get_cached_doc")
	@patch.object(frappe.db, "exists", return_value=True)
	def test_standard_knitting_context_accepts_keyed_receivable_without_calculated_field(
		self, _exists, get_cached_doc, get_route
	):
		work_order = frappe._dict(
			name="WO-KNIT-1",
			lot="LOT-1",
			production_detail="IPD-1",
			item="CLOTH",
			process_name="Knitting",
			cloth_execution_version=1,
			receivables=[
				frappe._dict(
					additional_parameters='{"f":"fabric-key","m":"matrix-key"}'
				)
			],
		)
		ipd = frappe._dict(name="IPD-1")
		get_cached_doc.side_effect = [work_order, ipd]
		get_route.return_value = {
			"knitting": {"process_name": "Knitting"},
			"dyeing": {"process_name": "Dyeing"},
			"washing": {"process_name": "Washing"},
		}
		grn = frappe._dict(
			against="YRP Work Order",
			against_id=work_order.name,
			is_return=0,
			is_rework=0,
			additional_grn=0,
			includes_packing=0,
		)

		context = fabric_substitution.get_default_knitting_grn_context(grn)

		self.assertEqual(context.lot, "LOT-1")
		self.assertEqual(context.work_order, "WO-KNIT-1")
		get_route.assert_called_once_with(ipd)

	@patch("essdee_yrp.fabric_substitution.get_supported_execution_route")
	@patch.object(frappe, "get_cached_doc")
	@patch.object(frappe.db, "exists", return_value=True)
	def test_standard_knitting_context_rejects_incomplete_receivable_contracts(
		self, _exists, get_cached_doc, get_route
	):
		work_order = frappe._dict(
			name="WO-KNIT-1",
			lot="LOT-1",
			production_detail="IPD-1",
			item="CLOTH",
			process_name="Knitting",
			cloth_execution_version=1,
		)
		ipd = frappe._dict(name="IPD-1")
		get_route.return_value = {
			"knitting": {"process_name": "Knitting"},
			"dyeing": {"process_name": "Dyeing"},
			"washing": {"process_name": "Washing"},
		}
		grn = frappe._dict(
			against="YRP Work Order",
			against_id=work_order.name,
			is_return=0,
			is_rework=0,
			additional_grn=0,
			includes_packing=0,
		)

		for receivables in (
			[],
			[
				frappe._dict(additional_parameters='{"f":"fabric-key"}'),
				frappe._dict(additional_parameters=""),
			],
		):
			with self.subTest(receivables=receivables):
				work_order.receivables = receivables
				get_cached_doc.side_effect = [work_order, ipd]
				self.assertIsNone(
					fabric_substitution.get_default_knitting_grn_context(grn)
				)
		get_route.assert_called_with(ipd)

	@patch.object(frappe.db, "exists", side_effect=AssertionError("additional GRN queried a work order"))
	def test_additional_grn_is_not_standard_knitting_context(self, _exists):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="WO-KNIT-1",
			additional_grn=1,
		)

		self.assertIsNone(fabric_substitution.get_default_knitting_grn_context(grn))

	@patch("essdee_yrp.fabric_substitution._default_knitting_process", return_value="Knitting")
	@patch.object(frappe.db, "sql")
	def test_receipt_rebuild_query_excludes_additional_grns(self, sql, _process):
		sql.side_effect = [
			[frappe._dict(name="WO-KNIT-1", production_detail="IPD-1", item="CLOTH")],
			[],
		]

		self.assertEqual(fabric_substitution._fetch_default_knitting_receipts("LOT-1"), [])
		self.assertIn("IFNULL(additional_grn, 0) = 0", sql.call_args_list[1].args[0])

	@patch(
		"essdee_yrp.fabric_source._accepted_inspection_adjustments",
		return_value={"GRN-ITEM-ACCEPTED": -30, "GRN-ITEM-REJECTED": 15},
	)
	@patch("essdee_yrp.fabric_substitution._default_received_type", return_value="Accepted")
	@patch("essdee_yrp.fabric_substitution._default_knitting_process", return_value="Knitting")
	@patch.object(frappe.db, "sql")
	def test_lot_receipts_use_effective_accepted_inspection_quantity(
		self, sql, _process, _received_type, adjustments
	):
		def receipt(name, received_type, stock_qty):
			return frappe._dict(
				source_grn=f"GRN-{name}",
				source_grn_item=f"GRN-ITEM-{name}",
				actual_item=f"CLOTH-{name}",
				stock_qty=stock_qty,
				quantity=stock_qty,
				conversion_factor=1,
				uom="Kg",
				stock_uom="Kg",
				received_type=received_type,
				production_detail="IPD-1",
				cloth_item="CLOTH",
				planned_item="CLOTH-PLANNED",
				planned_qty=100,
				route_item="CLOTH-ROUTE",
				additional_parameters={"fabric_execution_key": f"fabric-{name}"},
			)

		sql.side_effect = [
			[frappe._dict(name="WO-KNIT-1", production_detail="IPD-1", item="CLOTH")],
			["GRN-ACCEPTED", "GRN-REJECTED"],
			[
				receipt("ACCEPTED", "Accepted", 100),
				receipt("REJECTED", "Rejected", 40),
			],
		]

		rows = fabric_substitution._fetch_default_knitting_receipts("LOT-1")

		self.assertEqual(
			[(row.source_grn_item, row.stock_qty, row.received_type) for row in rows],
			[
				("GRN-ITEM-ACCEPTED", 70, "Accepted"),
				("GRN-ITEM-REJECTED", 15, "Accepted"),
			],
		)
		adjustments.assert_called_once()
		self.assertTrue(adjustments.call_args.kwargs["for_update"])

	def test_knitting_conversion_rejects_parent_colour_extra_attribute_and_missing_dia(self):
		cases = (
			(
				{"item": "CLOTH", "attrs": {"Dia": "36", "Colour": "GREY"}},
				{"item": "OTHER", "attrs": {"Dia": "32", "Colour": "GREY"}},
				"must use planned Item template",
			),
			(
				{"item": "CLOTH", "attrs": {"Dia": "36", "Colour": "GREY"}},
				{"item": "CLOTH", "attrs": {"Dia": "32", "Colour": "RED"}},
				"changes Colour",
			),
			(
				{"item": "CLOTH", "attrs": {"Dia": "36", "Colour": "GREY"}},
				{
					"item": "CLOTH",
					"attrs": {"Dia": "32", "Colour": "GREY", "GSM": "180"},
				},
				"changes GSM",
			),
			(
				{"item": "CLOTH", "attrs": {"Dia": "36", "Colour": "GREY"}},
				{"item": "CLOTH", "attrs": {"Colour": "GREY"}},
				"has no Dia",
			),
		)
		for planned, actual, message in cases:
			with self.subTest(message=message), patch(
				"essdee_yrp.fabric_substitution._item_state",
				side_effect=[planned, actual],
			):
				with self.assertRaisesRegex(frappe.ValidationError, message):
					fabric_substitution._validate_knitting_variance("PLANNED", "ACTUAL")

	def test_route_allocation_preserves_fractional_total(self):
		rows = fabric_substitution.allocate_route_quantity(
			1,
			[
				{"actual_item": "CLOTH-A", "factor": 1 / 3},
				{"actual_item": "CLOTH-B", "factor": 1 / 3},
				{"actual_item": "CLOTH-C", "factor": 1 / 3},
			],
		)

		self.assertEqual([row["quantity"] for row in rows], [0.334, 0.333, 0.333])
		self.assertEqual(sum(row["quantity"] for row in rows), 1)

	def test_actual_dia_factors_preserve_short_exact_and_excess_receipts(self):
		for actual_rows, expected in (
			([("CLOTH-26", 60), ("CLOTH-30", 30)], [0.6, 0.3]),
			([("CLOTH-26", 60), ("CLOTH-30", 40)], [0.6, 0.4]),
			([("CLOTH-26", 60), ("CLOTH-30", 50)], [0.6, 0.5]),
		):
			factors = fabric_substitution.build_actual_dia_factors(
				[
					{"actual_item": item, "actual_quantity": quantity}
					for item, quantity in actual_rows
				],
				100,
			)
			self.assertEqual([row["factor"] for row in factors], expected)

	def test_split_actual_dias_group_under_one_planned_item(self):
		factors = fabric_substitution.build_actual_dia_factors(
			[
				{"actual_item": "CLOTH-30", "actual_quantity": 20},
				{"actual_item": "CLOTH-32", "actual_quantity": 30},
				{"actual_item": "CLOTH-30", "actual_quantity": 10},
			],
			100,
		)

		self.assertEqual(
			factors,
			[
				{"actual_item": "CLOTH-30", "actual_quantity": 30.0, "factor": 0.3},
				{"actual_item": "CLOTH-32", "actual_quantity": 30.0, "factor": 0.3},
			],
		)

	@patch("essdee_yrp.fabric_substitution._default_received_type", return_value="Accepted")
	@patch(
		"essdee_yrp.fabric_substitution.get_planned_knitting_output_totals",
		return_value={"CLOTH-36": 100},
	)
	@patch("essdee_yrp.fabric_substitution.get_parent_item", return_value="CLOTH")
	def test_lot_factors_use_saved_cloth_program_as_denominator(
		self, get_parent, planned_totals, _received_type
	):
		lot = frappe._dict(
			name="LOT-1",
			lot_fabric_conversions=[
				frappe._dict(
					production_detail="IPD-1",
					process_stage_index=0,
					planned_item="CLOTH-36",
					actual_item="CLOTH-30",
					actual_quantity=60,
					received_type="Accepted",
				),
				frappe._dict(
					production_detail="IPD-1",
					process_stage_index=0,
					planned_item="CLOTH-36",
					actual_item="CLOTH-32",
					actual_quantity=30,
					received_type="Accepted",
				),
			],
		)

		factors = fabric_substitution.get_actual_dia_factors(lot, "IPD-1", "CLOTH-36")

		self.assertEqual([row["factor"] for row in factors], [0.6, 0.3])
		self.assertEqual([row["actual_quantity"] for row in factors], [60.0, 30.0])
		get_parent.assert_called_once_with("CLOTH-36")
		planned_totals.assert_called_once_with(lot, "IPD-1", "CLOTH")


class TestLotFabricConversionRebuild(unittest.TestCase):
	@patch("essdee_yrp.fabric_substitution._default_knitting_process", return_value="Knitting")
	@patch.object(frappe.db, "sql")
	def test_inspection_lot_lock_uses_only_exact_keyed_grn_children(
		self, sql, _process
	):
		sql.side_effect = [
			[
				frappe._dict(
					source_grn_item="GRN-ITEM-2",
					lot="LOT-B",
					additional_parameters={"fabric_execution_key": "key-2"},
				),
				frappe._dict(
					source_grn_item="GRN-ITEM-1",
					lot="LOT-A",
					additional_parameters={"fabric_execution_key": "key-1"},
				),
				frappe._dict(
					source_grn_item="GRN-ITEM-LEGACY",
					lot="LOT-Z",
					additional_parameters={},
				),
			],
			[],
		]

		lots = fabric_substitution.lock_lots_for_default_knitting_grn_items(
			["GRN-ITEM-2", "GRN-ITEM-1", "GRN-ITEM-LEGACY"]
		)

		self.assertEqual(lots, ["LOT-A", "LOT-B"])
		discovery_query = sql.call_args_list[0].args[0]
		self.assertIn("tabYRP Goods Received Note", discovery_query)
		self.assertIn("tabYRP Goods Received Note Item", discovery_query)
		self.assertIn("tabYRP Work Order Receivables", discovery_query)
		self.assertIn("tabYRP Work Order", discovery_query)
		self.assertIn("wo.cloth_execution_version = 1", discovery_query)
		self.assertIn("IFNULL(grn.additional_grn, 0) = 0", discovery_query)
		self.assertEqual(
			sql.call_args_list[0].args[1]["grn_items"],
			("GRN-ITEM-1", "GRN-ITEM-2", "GRN-ITEM-LEGACY"),
		)
		lock_query = sql.call_args_list[1].args[0]
		self.assertIn("tabSD YRP Lot", lock_query)
		self.assertIn("ORDER BY name FOR UPDATE", lock_query)
		self.assertEqual(sql.call_args_list[1].args[1]["lots"], ("LOT-A", "LOT-B"))

	@patch("essdee_yrp.fabric_substitution._default_knitting_process", return_value="Knitting")
	@patch.object(frappe.db, "sql", return_value=[])
	def test_post_lock_grn_child_qualification_is_a_current_locking_read(
		self, sql, _process
	):
		fabric_substitution.get_default_knitting_lots_for_grn_items(
			["GRN-ITEM-1"],
			for_update=True,
		)

		query = sql.call_args.args[0]
		self.assertIn("ORDER BY item.name", query)
		self.assertRegex(query, r"ORDER BY item\.name\s+FOR UPDATE")

	@patch("essdee_yrp.fabric_substitution._project_receipt_group")
	@patch("essdee_yrp.fabric_substitution.frappe.get_cached_doc")
	def test_projection_is_deterministic_for_identical_receipts(self, get_cached_doc, project):
		get_cached_doc.return_value = frappe._dict(name="IPD-1")
		project.side_effect = lambda group, _ipd: [
			{
				"process_name": "KNITTING",
				"planned_item": group.planned_item,
				"actual_item": group.actual_item,
				"actual_quantity": group.stock_qty,
				"production_detail": group.production_detail,
				"process_stage_index": 0,
				"source_grn_count": len(group.source_grns),
			}
		]
		receipts = [
			frappe._dict(
				source_grn="GRN-2",
				fabric_execution_key="fabric-2",
				production_detail="IPD-1",
				planned_item="CLOTH-36",
				actual_item="CLOTH-32",
				stock_qty=40,
			),
			frappe._dict(
				source_grn="GRN-1",
				fabric_execution_key="fabric-1",
				production_detail="IPD-1",
				planned_item="CLOTH-36",
				actual_item="CLOTH-32",
				stock_qty=60,
			),
		]

		first = fabric_substitution.build_conversion_rows(receipts, "KNITTING")
		second = fabric_substitution.build_conversion_rows(receipts, "KNITTING")

		self.assertEqual(first, second)
		self.assertEqual(first[0]["actual_quantity"], 100)
		self.assertEqual(first[0]["source_grn_count"], 2)

	@patch("essdee_yrp.fabric_plan._route_bypasses_step", return_value=True)
	@patch("essdee_yrp.fabric_substitution._item_state")
	@patch("essdee_yrp.api.work_order._matrix_qty_rows", return_value=[])
	@patch("essdee_yrp.api.work_order._step_kind", return_value="swap")
	def test_direct_colour_route_can_bypass_dyeing(
		self, _step_kind, _matrix_rows, item_state, route_bypasses
	):
		item_state.side_effect = [
			{"item": "CLOTH", "attrs": {"Dia": "36", "Colour": "AMEL"}},
			{"item": "CLOTH", "attrs": {"Dia": "32", "Colour": "AMEL"}},
		]
		step = {"process_name": "DYEING", "shape": "swap", "attribute": "Colour"}

		result = fabric_substitution._project_stage_items(
			frappe._dict(name="IPD-1"),
			step,
			"FINISHED-ROUTE",
			"CLOTH-36-AMEL",
			"CLOTH-32-AMEL",
		)

		self.assertEqual(result, ("CLOTH-36-AMEL", "CLOTH-32-AMEL"))
		route_bypasses.assert_called_once()

	@patch("essdee_yrp.fabric_substitution._rebuild_lot_fabric_conversions")
	@patch("essdee_yrp.fabric_substitution.get_default_knitting_grn_context")
	def test_qualified_grn_rebuild_requires_pre_lifecycle_lot_lock(self, get_context, rebuild):
		get_context.return_value = frappe._dict(lot="LOT-1")
		grn = frappe._dict(name="GRN-1", flags=frappe._dict())

		with self.assertRaisesRegex(frappe.ValidationError, "lock.*Lot.*before"):
			fabric_substitution.rebuild_lot_fabric_conversions_for_grn(grn)

		rebuild.assert_not_called()

	@patch("essdee_yrp.fabric_substitution._lock_lot")
	@patch("essdee_yrp.fabric_substitution.get_default_knitting_grn_context")
	def test_repeated_lot_lock_returns_the_same_context_shape(self, get_context, lock_lot):
		context = frappe._dict(lot="LOT-1", production_detail="IPD-1")
		get_context.return_value = context
		grn = frappe._dict(flags=frappe._dict(cloth_execution_lot_locked="LOT-1"))

		result = fabric_substitution.lock_lot_for_default_knitting_grn(grn)

		self.assertEqual(result, context)
		lock_lot.assert_not_called()

	@patch("essdee_yrp.fabric_substitution._replace_conversion_rows")
	@patch("essdee_yrp.fabric_substitution.build_conversion_rows")
	@patch("essdee_yrp.fabric_substitution._fetch_default_knitting_receipts")
	@patch("essdee_yrp.fabric_substitution._lock_lot")
	def test_multiple_grn_rebuild_is_idempotent(self, lock_lot, fetch, build, replace):
		fetch.return_value = [frappe._dict(source_grn="GRN-1"), frappe._dict(source_grn="GRN-2")]
		build.return_value = [{"actual_item": "CLOTH-30", "actual_quantity": 100}]

		first = fabric_substitution._rebuild_lot_fabric_conversions("LOT-1")
		second = fabric_substitution._rebuild_lot_fabric_conversions("LOT-1")

		self.assertEqual(first, second)
		self.assertEqual(lock_lot.call_count, 2)
		self.assertEqual(replace.call_args_list, [
			call("LOT-1", build.return_value),
			call("LOT-1", build.return_value),
		])

	@patch("essdee_yrp.fabric_substitution._project_receipt_group")
	@patch("essdee_yrp.fabric_substitution.frappe.get_cached_doc")
	def test_unkeyed_historical_grn_is_ignored(self, get_cached_doc, project_receipt_group):
		get_cached_doc.return_value = frappe._dict(name="IPD-1")
		project_receipt_group.side_effect = lambda group, _ipd: [
			{
				"process_name": "KNITTING",
				"planned_item": group.planned_item,
				"actual_item": group.actual_item,
				"actual_quantity": group.stock_qty,
				"production_detail": group.production_detail,
				"process_stage_index": 0,
				"source_grn_count": len(group.source_grns),
			}
		]
		rows = fabric_substitution.build_conversion_rows(
			[
				frappe._dict(
					source_grn="GRN-OLD",
					fabric_execution_key=None,
					production_detail="IPD-1",
					planned_item="CLOTH-36",
					actual_item="CLOTH-30",
					stock_qty=50,
				),
				frappe._dict(
					source_grn="GRN-NEW",
					fabric_execution_key="fabric-new",
					production_detail="IPD-1",
					planned_item="CLOTH-36",
					actual_item="CLOTH-32",
					stock_qty=40,
				),
			],
			"KNITTING",
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["actual_item"], "CLOTH-32")

	@patch("essdee_yrp.fabric_substitution._validate_knitting_variance")
	@patch("essdee_yrp.fabric_substitution._project_stage_items")
	@patch("essdee_yrp.fabric_substitution.get_supported_execution_route")
	def test_rebuild_stops_projection_after_washing(
		self, supported_route, project_stage, validate_knitting_variance
	):
		supported_route.return_value = {
			"knitting": {"process_name": "KNITTING", "position": 0},
			"dyeing": {"process_name": "DYEING", "position": 1},
			"washing": {"process_name": "WASHING", "position": 2},
		}
		project_stage.side_effect = [
			("DYE-PLANNED", "DYE-ACTUAL"),
			("WASH-PLANNED", "WASH-ACTUAL"),
		]
		receipt = frappe._dict(
			production_detail="IPD-1",
			planned_item="KNIT-PLANNED",
			actual_item="KNIT-ACTUAL",
			stock_qty=10,
			received_type="Accepted",
			stock_uom="Kg",
			source_grn="GRN-1",
		)

		rows = fabric_substitution._project_receipt_group(receipt, frappe._dict(name="IPD-1"))

		self.assertEqual([row["process_name"] for row in rows], ["KNITTING", "DYEING", "WASHING"])
		self.assertEqual(project_stage.call_count, 2)
		validate_knitting_variance.assert_called_once_with("KNIT-PLANNED", "KNIT-ACTUAL")


class TestCuttingFabricSubstitutions(unittest.TestCase):
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


	def test_stale_conversion_never_coerces_exact_projection(self):
		with self.assertRaisesRegex(
			frappe.ValidationError, "Lot fabric conversion is out of date"
		):
			fabric_substitution.resolve_process_conversion(
				{("ROUTE", "PLAN"): {"ACTUAL-30": 5}},
				route_item="ROUTE",
				planned_item="PLAN",
				projected_item="ACTUAL-32",
			)

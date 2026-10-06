from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.test_cloth_program import _ensure_item
from essdee_yrp.api.work_order import _resolve_variant
from essdee_yrp import fabric_source
from essdee_yrp.fabric_source import (
	fill_from_source_grns,
	get_source_availability,
	get_source_process_options,
	validate_source_demands,
)


def _row(colour, target):
	return {
		"key": target,
		"input_specs": [
			{
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": colour},
				"qty": 1,
			}
		],
		"output_qty": 1,
		"out_attrs": {"Dia": "32 Dia", "Colour": target},
	}


class TestFabricSourceProcesses(TestCase):
	@patch("essdee_yrp.fabric_source.get_fabric_steps")
	def test_only_earlier_steps_are_offered_immediate_first(self, get_steps):
		get_steps.return_value = [
			{"position": 0, "process_name": "Knitting"},
			{"position": 1, "process_name": "White Wash"},
			{"position": 2, "process_name": "Dyeing"},
			{"position": 3, "process_name": "Washing"},
		]
		options = get_source_process_options(frappe._dict(name="Test IPD"), "Washing")
		self.assertEqual(
			[option["process_name"] for option in options],
			["Dyeing", "White Wash", "Knitting"],
		)


class TestExactFabricSourceBuckets(TestCase):
	def test_legacy_tolerance_remains_unchanged(self):
		self.assertEqual(fabric_source.QTY_TOLERANCE, 0.001)

	@patch.object(frappe.db, "sql", side_effect=[[], []])
	@patch.object(frappe.db, "has_column", return_value=True)
	@patch("essdee_yrp.fabric_source._legacy_source_allows_versioned_washing", return_value=False)
	def test_legacy_pool_excludes_versioned_source_receipts(
		self, _allows_washing, _has_column, sql
	):
		fabric_source._get_legacy_source_availability(
			lot="LOT-1",
			ipd="IPD-1",
			cloth_item="CLOTH",
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order="LEGACY-WO",
		)

		self.assertIn("cloth_execution_version", sql.call_args_list[0].args[0])
		self.assertIn("= 0", sql.call_args_list[0].args[0])
		self.assertIn("cloth_execution_version", sql.call_args_list[1].args[0])
		self.assertIn("= 0", sql.call_args_list[1].args[0])

	@patch.object(frappe.db, "sql", side_effect=[[], []])
	@patch.object(frappe.db, "has_column", return_value=True)
	def test_legacy_lock_excludes_versioned_source_receipts(self, _has_column, sql):
		fabric_source._lock_source_transactions("LOT-1", "CLOTH", "Knitting")

		self.assertNotIn("cloth_execution_version", sql.call_args_list[0].args[0])
		self.assertIn("cloth_execution_version", sql.call_args_list[1].args[0])
		self.assertIn("= 0", sql.call_args_list[1].args[0])

	@patch.object(frappe.db, "add_index")
	def test_exact_source_consumption_query_has_targeted_index(self, add_index):
		from essdee_yrp.patches import add_cloth_source_row_index

		add_cloth_source_row_index.execute()

		add_index.assert_called_once_with(
			"YRP Work Order Deliverables",
			["source_grn_item", "parent"],
			"cloth_source_grn_item",
		)

	def _receipt(self, name, qty, **values):
		return frappe._dict(
			{
				"source_grn": f"GRN-{name}",
				"source_grn_item": name,
				"source_grn_row": 1,
				"source_work_order": "WO-KNIT",
				"source_process": "Knitting",
				"item_variant": "CLOTH-32-GREY",
				"stock_qty": qty,
				"uom": "Kg",
				"received_type": "Accepted",
				"source_warehouse": "Fabric - E",
				"set_combination": "{}",
				"lot": "LOT-1",
				"cloth_execution_version": 1,
				"additional_parameters": {"fabric_execution_key": f"fabric-{name}"},
			},
			**values,
		)

	def _source_bucket_key(self, name):
		return fabric_source._bucket_key(
			name,
			None,
			item_variant="CLOTH-32-GREY",
			received_type="Accepted",
			warehouse="Fabric - E",
			set_combination="{}",
			dimensions={"lot": "LOT-1", "received_type": "Accepted"},
		)

	def test_exact_bucket_separates_source_grn_item_received_type_and_dimensions(self):
		buckets = fabric_source._build_source_buckets(
			[
				self._receipt("ROW-1", 30, batch_no="BATCH-A"),
				self._receipt("ROW-2", 40, batch_no="BATCH-B"),
				self._receipt("ROW-3", 50, received_type="Rejected", batch_no="BATCH-C"),
			],
			[],
			default_received_type="Accepted",
			dimension_fields=["lot", "received_type", "batch_no"],
			physical_knitting_source=True,
		)

		self.assertEqual(len(buckets), 2)
		self.assertEqual(len({row["key"] for row in buckets}), 2)
		self.assertEqual(
			[row["stock_dimensions"]["batch_no"] for row in buckets],
			["BATCH-A", "BATCH-B"],
		)
		self.assertTrue(all(row["received_type"] == "Accepted" for row in buckets))

	def test_source_receipts_are_classified_as_exact_legacy_or_mixed(self):
		exact = self._receipt("EXACT", 10)
		legacy = self._receipt(
			"LEGACY", 10, cloth_execution_version=0, additional_parameters={}
		)
		rejected = self._receipt("REJECTED", 10, received_type="Rejected")

		self.assertEqual(
			fabric_source._classify_source_receipts([exact, rejected], "Accepted"),
			"exact",
		)
		self.assertEqual(
			fabric_source._classify_source_receipts([legacy], "Accepted"),
			"legacy",
		)
		self.assertEqual(
			fabric_source._classify_source_receipts([exact, legacy], "Accepted"),
			"mixed",
		)

	@patch("essdee_yrp.fabric_source._build_source_buckets", return_value=[])
	@patch("yrp.stock.dimensions.assert_safe_fieldname")
	@patch(
		"yrp.stock.dimensions.get_dimension_fieldnames",
		return_value=["lot", "received_type"],
	)
	@patch.object(frappe.db, "get_single_value")
	@patch.object(frappe.db, "sql")
	def test_prepare_source_pool_uses_ordered_current_reads_after_lot_lock(
		self, sql, get_single, _dimensions, _safe_fieldname, build_buckets
	):
		get_single.side_effect = lambda doctype, fieldname: {
			("YRP Stock Settings", "default_received_type"): "Accepted",
			("SD YRP IPD Settings", "default_knitting_process"): "Knitting",
		}.get((doctype, fieldname))
		receipt = self._receipt("ROW-1", 100)

		def current_reads(query, _values=None, **kwargs):
			if kwargs.get("pluck"):
				return ["GRN-ROW-1"]
			if "tabYRP Goods Received Note Item" in query:
				return [receipt]
			if "tabYRP Work Order Deliverables" in query:
				return []
			return []

		sql.side_effect = current_reads
		with patch.object(frappe, "flags", frappe._dict()):
			fabric_source.prepare_source_pool(
				"LOT-1", "IPD-1", "Knitting", for_update=True
			)
			fabric_source.prepare_source_pool(
				"LOT-1", "IPD-1", "Knitting", for_update=True
			)

		queries = [entry.args[0] for entry in sql.call_args_list]
		self.assertIn("tabSD YRP Lot", queries[0])
		self.assertTrue(all("FOR UPDATE" in query for query in queries))
		self.assertIn("ORDER BY grn.name", queries[1])
		self.assertIn("ORDER BY grn.name, item.idx, item.name", queries[2])
		self.assertIn("ORDER BY item.parent, item.idx, item.name", queries[3])
		self.assertNotIn("JOIN `tabYRP Work Order` target_wo", queries[3])
		self.assertIn("item.docstatus", queries[3])
		self.assertIn("tabSD YRP Lot", queries[4])
		self.assertEqual(build_buckets.call_count, 2)

	@patch("essdee_yrp.fabric_source._build_source_buckets", return_value=[])
	@patch("yrp.stock.dimensions.assert_safe_fieldname")
	@patch(
		"yrp.stock.dimensions.get_dimension_fieldnames",
		return_value=["received_type"],
	)
	@patch.object(frappe.db, "get_single_value")
	@patch.object(frappe.db, "sql")
	def test_only_keyed_default_received_rows_enter_consumption_lookup(
		self, sql, get_single, _dimensions, _safe_fieldname, _build
	):
		get_single.side_effect = lambda doctype, fieldname: {
			("YRP Stock Settings", "default_received_type"): "Accepted",
			("SD YRP IPD Settings", "default_knitting_process"): "Knitting",
		}.get((doctype, fieldname))
		accepted = self._receipt("ACCEPTED", 10)
		rejected = self._receipt("REJECTED", 10, received_type="Rejected")

		def reads(query, values=None, **kwargs):
			if kwargs.get("pluck"):
				return ["GRN-ACCEPTED", "GRN-REJECTED"]
			if "tabYRP Goods Received Note Item" in query:
				return [accepted, rejected]
			if "tabYRP Work Order Deliverables" in query:
				self.assertEqual(values["source_items"], ("ACCEPTED",))
				return []
			return []

		sql.side_effect = reads
		pool = fabric_source.prepare_source_pool("LOT-1", "IPD-1", "Knitting")

		self.assertEqual(pool["source_mode"], "exact")

	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_submitted_exact_usage_requires_persisted_source_bucket_key(self, _factor):
		with self.assertRaisesRegex(frappe.ValidationError, "source bucket identity"):
			fabric_source._build_source_buckets(
				[self._receipt("ROW-1", 100)],
				[
					frappe._dict(
						source_grn_item="ROW-1",
						item_variant="CLOTH-32-GREY",
						qty=10,
						pending_quantity=0,
						stock_update=10,
						uom="Kg",
						docstatus=1,
					)
				],
				default_received_type="Accepted",
				dimension_fields=["lot", "received_type"],
				physical_knitting_source=True,
			)

	@patch("essdee_yrp.fabric_substitution.resolve_process_conversion", side_effect=lambda _i, **k: k["projected_item"])
	@patch("essdee_yrp.api.work_order._variant_attrs", return_value={"Dia": "32", "Colour": "Red"})
	@patch(
		"essdee_yrp.api.work_order._resolve_variant",
		side_effect=lambda _item, attrs: "CLOTH-32-RED" if attrs.get("Dia") == "32" else "CLOTH-36-RED",
	)
	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_factor_targets_do_not_reuse_one_grn_row_across_routes(
		self, _factor, _resolve, _attrs, _conversion
	):
		rows = [
			{
				"key": key,
				"matrix_key": key,
				"input_specs": [
					{
						"item": "CLOTH",
						"attrs": {"Dia": "36", "Colour": "Grey"},
						"qty": 1,
						"uom": "Kg",
					}
				],
				"output_item": "CLOTH",
				"output_qty": 1,
				"out_attrs": {"Dia": "36", "Colour": "Red"},
			}
			for key in ("ROUTE-RED-1", "ROUTE-RED-2")
		]
		bucket = {
			"key": "SOURCE-1",
			"source_grn": "GRN-1",
			"source_grn_item": "ROW-1",
			"item_variant": "CLOTH-32-GREY",
			"available_stock_qty": 100,
			"received_stock_qty": 100,
		}
		targets = {
			("ROUTE-RED-1", "CLOTH-32-GREY"): 60,
			("ROUTE-RED-2", "CLOTH-32-GREY"): 60,
		}

		fabric_source._project_receipt_buckets(
			rows,
			[bucket],
			{
				"CLOTH-32-GREY": {
					"item": "CLOTH",
					"attrs": {"Dia": "32", "Colour": "Grey"},
				}
			},
			route_targets=targets,
		)

		self.assertEqual([row["prefill"] for row in rows], [60, 40])
		self.assertEqual(sum(row["prefill"] for row in rows), 100)

	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_fully_exhausted_historical_rows_are_hidden(self, _factor):
		buckets = fabric_source._build_source_buckets(
			[self._receipt("ROW-1", 100)],
			[
				frappe._dict(
					source_grn_item="ROW-1",
					item_variant="CLOTH-32-GREY",
					qty=100,
					pending_quantity=0,
					stock_update=100,
					uom="Kg",
					docstatus=1,
					additional_parameters={
						"source_bucket_key": self._source_bucket_key("ROW-1")
					},
				)
			],
			default_received_type="Accepted",
			dimension_fields=["lot", "received_type"],
			physical_knitting_source=True,
		)

		self.assertEqual(buckets, [])

	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_draft_work_orders_do_not_reserve_but_submitted_dispatch_is_deducted(self, _factor):
		buckets = fabric_source._build_source_buckets(
			[self._receipt("ROW-1", 100)],
			[
				frappe._dict(
					source_grn_item="ROW-1",
					item_variant="CLOTH-32-GREY",
					qty=80,
					pending_quantity=80,
					stock_update=0,
					uom="Kg",
					docstatus=0,
				),
				frappe._dict(
					source_grn_item="ROW-1",
					item_variant="CLOTH-32-GREY",
					qty=40,
					pending_quantity=25,
					stock_update=15,
					uom="Kg",
					docstatus=1,
					additional_parameters={
						"source_bucket_key": self._source_bucket_key("ROW-1")
					},
				),
			],
			default_received_type="Accepted",
			dimension_fields=["lot", "received_type"],
			physical_knitting_source=True,
		)

		self.assertEqual(buckets[0]["reserved_stock_qty"], 15)
		self.assertEqual(buckets[0]["available_stock_qty"], 85)

	def test_default_received_type_is_the_only_normal_source(self):
		buckets = fabric_source._build_source_buckets(
			[
				self._receipt("ROW-1", 70, received_type="Accepted"),
				self._receipt("ROW-2", 30, received_type="Oil Mark"),
			],
			[],
			default_received_type="Accepted",
			dimension_fields=["received_type"],
			physical_knitting_source=True,
		)

		self.assertEqual(sum(row["received_stock_qty"] for row in buckets), 70)

	def test_actual_dia_carries_through_dyeing_and_identity_washing(self):
		dyeing = fabric_source.project_output_attributes(
			{"Dia": "32", "Colour": "Grey", "GSM": "180"},
			{"Dia": "36", "Colour": "Grey", "GSM": "180"},
			{"Dia": "36", "Colour": "Red", "GSM": "180"},
		)
		washing = fabric_source.project_output_attributes(
			dyeing,
			{"Dia": "36", "Colour": "Red", "GSM": "180"},
			{"Dia": "36", "Colour": "Red", "GSM": "180"},
		)

		self.assertEqual(dyeing, {"Dia": "32", "Colour": "Red", "GSM": "180"})
		self.assertEqual(washing, dyeing)

	@patch("essdee_yrp.fabric_substitution.resolve_process_conversion", side_effect=lambda _i, **k: k["projected_item"])
	@patch("essdee_yrp.api.work_order._variant_attrs", return_value={"Dia": "32", "Colour": "Red"})
	@patch("essdee_yrp.api.work_order._resolve_variant", return_value="CLOTH-32-RED")
	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_popup_prefill_rounds_down_without_overconsuming_source(
		self, _factor, _resolve, _attrs, _conversion
	):
		rows = [{
			"key": "ROUTE",
			"matrix_key": "ROUTE",
			"input_specs": [{
				"item": "CLOTH",
				"attrs": {"Dia": "32", "Colour": "Grey"},
				"qty": 1.07,
				"uom": "Kg",
			}],
			"output_item": "CLOTH",
			"output_qty": 1,
			"out_attrs": {"Dia": "32", "Colour": "Red"},
		}]
		bucket = {
			"key": "SOURCE",
			"source_grn": "GRN-1",
			"source_grn_item": "ROW-1",
			"item_variant": "CLOTH-32-GREY",
			"available_stock_qty": 100,
			"received_stock_qty": 100,
		}

		fabric_source._project_receipt_buckets(
			rows,
			[bucket],
			{"CLOTH-32-GREY": {"item": "CLOTH", "attrs": {"Dia": "32", "Colour": "Grey"}}},
		)

		self.assertEqual(rows[0]["prefill"], 93.457)
		self.assertLessEqual(rows[0]["prefill"] * 1.07, 100)

	def test_source_pool_rejects_changed_item_or_dimension(self):
		bucket = {
			"source_grn": "GRN-1",
			"source_grn_item": "ROW-1",
			"item_variant": "CLOTH-32-GREY",
			"received_type": "Accepted",
			"source_warehouse": "Fabric - E",
			"set_combination": "{}",
			"stock_dimensions": {"lot": "LOT-1", "received_type": "Accepted"},
		}
		for row, message in (
			(
				frappe._dict(
					source_grn="GRN-1",
					source_grn_item="ROW-1",
					item_variant="CLOTH-30-GREY",
					received_type="Accepted",
					lot="LOT-1",
				),
				"Item changed",
			),
			(
				frappe._dict(
					source_grn="GRN-1",
					source_grn_item="ROW-1",
					item_variant="CLOTH-32-GREY",
					received_type="Accepted",
					lot="LOT-2",
				),
				"stock dimension",
			),
		):
			with self.subTest(message=message), self.assertRaisesRegex(
				frappe.ValidationError, message
			):
				fabric_source._validate_source_bucket_identity(
					row, bucket, ["lot", "received_type"]
				)

	@patch("essdee_yrp.fabric_source._get_legacy_source_availability")
	@patch("essdee_yrp.fabric_source.is_versioned_cloth_work_order", return_value=False)
	def test_legacy_availability_response_is_unchanged(self, _is_versioned, legacy):
		legacy.return_value = {
			"received": {"CLOTH": 10},
			"reserved": {"CLOTH": 3},
			"net": {"CLOTH": 7},
		}
		result = get_source_availability(
			lot="LOT-1",
			ipd="IPD-1",
			cloth_item="CLOTH",
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order="LEGACY-WO",
		)

		self.assertEqual(result, legacy.return_value)

	@patch("essdee_yrp.fabric_source._get_legacy_source_availability")
	@patch("essdee_yrp.fabric_source.prepare_source_pool")
	@patch("essdee_yrp.fabric_source._uses_exact_source_pool", return_value=True)
	def test_new_versioned_work_order_can_preview_all_legacy_source(
		self, _uses_exact, prepare, legacy
	):
		prepare.return_value = {"source_mode": "legacy"}
		legacy.return_value = {
			"received": {"CLOTH": 10},
			"reserved": {},
			"net": {"CLOTH": 10},
		}

		result = get_source_availability(
			lot="LOT-1",
			ipd="IPD-1",
			cloth_item="CLOTH",
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order="NEW-WO",
		)

		self.assertEqual(result["source_mode"], "legacy")
		self.assertEqual(result["net"], {"CLOTH": 10})

	@patch("essdee_yrp.fabric_source._get_legacy_source_availability")
	@patch("essdee_yrp.fabric_source.prepare_source_pool")
	@patch("essdee_yrp.fabric_source._uses_exact_source_pool", return_value=True)
	def test_mixed_history_exposes_exact_and_legacy_pools_separately(
		self, _uses_exact, prepare, legacy
	):
		prepare.return_value = {
			"source_mode": "mixed",
			"default_received_type": "Accepted",
			"buckets": {"SOURCE": {
				"key": "SOURCE",
				"item_variant": "CLOTH-EXACT",
				"received_stock_qty": 8,
				"reserved_stock_qty": 0,
				"available_stock_qty": 8,
			}},
		}
		legacy.return_value = {
			"received": {"CLOTH-LEGACY": 5},
			"reserved": {},
			"net": {"CLOTH-LEGACY": 5},
		}

		result = get_source_availability(
			lot="LOT-1",
			ipd="IPD-1",
			cloth_item="CLOTH",
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order="NEW-WO",
		)

		self.assertEqual(result["source_mode"], "mixed")
		self.assertEqual(result["net"], {"CLOTH-EXACT": 8.0})
		self.assertEqual(
			result["legacy_availability"]["net"], {"CLOTH-LEGACY": 5}
		)

	@patch("essdee_yrp.fabric_source._conversion_factor", return_value=1)
	def test_submitted_rework_usage_does_not_poison_exact_bucket(self, _factor):
		buckets = fabric_source._build_source_buckets(
			[self._receipt("ROW-1", 100)],
			[frappe._dict(
				parent="REWORK-WO",
				source_grn_item="ROW-1",
				item_variant="CLOTH-32-GREY",
				qty=10,
				pending_quantity=0,
				stock_update=10,
				uom="Kg",
				docstatus=1,
				is_rework=True,
			)],
			default_received_type="Accepted",
			dimension_fields=["lot", "received_type"],
			physical_knitting_source=True,
		)

		self.assertEqual(buckets[0]["available_stock_qty"], 100)

	@patch.object(frappe.db, "sql", return_value=[frappe._dict(name="REWORK-WO", is_rework=1)])
	def test_locked_rework_parent_lookup_is_an_ordered_current_read(self, sql):
		rows = [frappe._dict(
			parent="REWORK-WO",
			docstatus=1,
			qty=10,
			pending_quantity=0,
			stock_update=10,
			additional_parameters={},
		)]

		fabric_source._mark_rework_consumption_rows(rows, for_update=True)

		query = sql.call_args.args[0]
		self.assertIn("ORDER BY name", query)
		self.assertIn("FOR UPDATE", query)
		self.assertTrue(rows[0].is_rework)

	@patch("essdee_yrp.fabric_source.prepare_source_pool")
	@patch("essdee_yrp.fabric_source.get_source_process_options", return_value=[{"value": "0::Knitting", "process_name": "Knitting"}])
	@patch.object(frappe, "get_cached_doc", return_value=frappe._dict(name="IPD-1", item="CLOTH"))
	def test_uncalculated_versioned_draft_does_not_lock_or_require_source(
		self, _get_cached_doc, _options, prepare
	):
		work_order = frappe._dict(
			name="WO-NEW",
			docstatus=0,
			is_rework=0,
			cloth_execution_version=1,
			lot="LOT-1",
			production_detail="IPD-1",
			process_name="Dyeing",
			deliverables=[],
			receivables=[],
		)

		fabric_source.validate_work_order_source_allocations(work_order)

		prepare.assert_not_called()

	@patch("essdee_yrp.fabric_source.get_source_process_options")
	def test_versioned_source_must_be_immediate_predecessor(self, options):
		options.return_value = [
			{"value": "1::Dyeing", "process_name": "Dyeing"},
			{"value": "0::Knitting", "process_name": "Knitting"},
		]
		with self.assertRaisesRegex(frappe.ValidationError, "immediate predecessor"):
			fabric_source._require_immediate_source(
				frappe._dict(name="IPD-1"),
				"Washing",
				{"value": "0::Knitting", "process_name": "Knitting"},
			)

	@patch("essdee_yrp.fabric_source._legacy_source_allows_versioned_washing", return_value=True)
	@patch.object(frappe.db, "sql", side_effect=[[], []])
	@patch.object(frappe.db, "has_column", return_value=True)
	def test_legacy_process_after_washing_can_still_read_washing_receipts(
		self, _has_column, sql, _allows_washing
	):
		fabric_source._get_legacy_source_availability(
			lot="LOT-1",
			ipd="IPD-1",
			cloth_item="CLOTH",
			source_process="Washing",
			source_step="2::Washing",
			current_process="Compacting",
			current_work_order="LEGACY-COMPACTING",
		)

		self.assertNotIn("source_wo.cloth_execution_version", sql.call_args_list[0].args[0])

	def test_version_zero_work_order_rejects_keyed_source_rows(self):
		work_order = frappe._dict(
			docstatus=0,
			is_rework=0,
			cloth_execution_version=0,
			deliverables=[frappe._dict(
				item_variant="CLOTH-32-GREY",
				qty=1,
				additional_parameters={"source_bucket_key": "SOURCE"},
			)],
			receivables=[],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "legacy Work Order"):
			fabric_source.validate_work_order_source_allocations(work_order)

	@patch("essdee_yrp.fabric_source._item_belongs_to_template", side_effect=lambda item, template: item.startswith("CLOTH"))
	@patch("essdee_yrp.fabric_source.prepare_source_pool")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	@patch("essdee_yrp.fabric_source.get_source_process_options")
	@patch.object(frappe, "get_cached_doc")
	def test_validator_ignores_bom_consumables_and_binds_key_to_route(
		self, get_cached_doc, options, resolve, prepare, _belongs
	):
		get_cached_doc.return_value = frappe._dict(name="IPD-1", item="CLOTH")
		options.return_value = [{"value": "0::Knitting", "process_name": "Knitting"}]
		resolve.return_value = {"value": "0::Knitting", "process_name": "Knitting"}
		bucket = {
			"key": "SOURCE",
			"source_grn": "GRN-1",
			"source_grn_item": "ROW-1",
			"item_variant": "CLOTH-32-GREY",
			"reference_item_variant": "ROUTE-ITEM",
			"received_stock_qty": 10,
			"available_stock_qty": 10,
			"remaining_stock_qty": 10,
			"stock_dimensions": {},
		}
		prepare.return_value = {
			"source_mode": "exact",
			"dimension_fields": [],
			"buckets": {"SOURCE": bucket},
		}
		execution_key = fabric_source._execution_key("SOURCE", "MATRIX", "ROUTE-ITEM")
		parameters = {
			"fabric_execution_key": execution_key,
			"matrix_key": "MATRIX",
			"source_bucket_key": "SOURCE",
		}
		work_order = frappe._dict(
			name="WO-1",
			docstatus=0,
			is_rework=0,
			cloth_execution_version=1,
			lot="LOT-1",
			production_detail="IPD-1",
			process_name="Dyeing",
			fabric_source_process="Knitting",
			fabric_source_process_step="0::Knitting",
			deliverables=[
				frappe._dict(
					item_variant="CLOTH-32-GREY",
					qty=10,
					uom="Kg",
					is_calculated=1,
					source_grn="GRN-1",
					source_grn_item="ROW-1",
					additional_parameters=parameters,
				),
				frappe._dict(
					item_variant="DYE-CHEMICAL",
					qty=1,
					uom="Kg",
					is_calculated=1,
				),
			],
			receivables=[frappe._dict(
				item_variant="CLOTH-32-RED",
				qty=10,
				is_calculated=1,
				additional_parameters=parameters,
			)],
		)
		with patch("essdee_yrp.fabric_source._conversion_factor", return_value=1):
			fabric_source.validate_work_order_source_allocations(work_order)

		work_order.deliverables[0].additional_parameters = {
			**parameters,
			"fabric_execution_key": "fabric-wrong-route",
		}
		bucket["remaining_stock_qty"] = 10
		with (
			patch("essdee_yrp.fabric_source._conversion_factor", return_value=1),
			self.assertRaisesRegex(frappe.ValidationError, "route identity"),
		):
			fabric_source.validate_work_order_source_allocations(work_order)


class TestFabricSourceFill(TestCase):
	def _fill(self, rows, availability, variants):
		with (
			patch(
				"essdee_yrp.fabric_source.resolve_source_process",
				return_value={
					"value": "0::Knitting",
					"process_name": "Knitting",
					"label": "Knitting",
				},
			),
			patch(
				"essdee_yrp.fabric_source.get_source_availability",
				return_value=availability,
			),
			patch(
				"essdee_yrp.fabric_source._variant_info",
				return_value=variants,
			),
		):
			return fill_from_source_grns(
				rows,
				lot="LOT-1",
				ipd=frappe._dict(name="IPD-1", item="Test Cloth"),
				current_process="Dyeing",
				current_work_order="WO-2",
				source_process="0::Knitting",
			)

	def test_shared_greige_is_not_split_between_final_colours(self):
		rows = [_row("Greige", "Red"), _row("Greige", "Navy")]
		availability = {
			"received": {"Greige-32": 150},
			"reserved": {},
			"net": {"Greige-32": 150},
		}
		variants = {
			"Greige-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Greige"},
			},
		}

		self._fill(rows, availability, variants)

		self.assertEqual([row["prefill"] for row in rows], [0, 0])
		self.assertTrue(all(row["source_shared"] for row in rows))
		self.assertEqual([row["source_available"] for row in rows], [150, 150])

	def test_dyed_yarn_knitting_outputs_fill_matching_colours(self):
		rows = [_row("Red", "Red"), _row("Navy", "Navy")]
		availability = {
			"received": {"Red-32": 90, "Navy-32": 60},
			"reserved": {},
			"net": {"Red-32": 90, "Navy-32": 60},
		}
		variants = {
			"Red-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Red"},
			},
			"Navy-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Navy"},
			},
		}

		self._fill(rows, availability, variants)

		self.assertEqual([row["prefill"] for row in rows], [90, 60])
		self.assertFalse(any(row["source_shared"] for row in rows))

	def test_no_compatible_popup_input_raises(self):
		rows = [_row("Red", "Red")]
		availability = {
			"received": {"Greige-32": 50},
			"reserved": {},
			"net": {"Greige-32": 50},
		}
		variants = {
			"Greige-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Greige"},
			},
		}

		with self.assertRaisesRegex(frappe.ValidationError, "no compatible input row"):
			self._fill(rows, availability, variants)

	@patch("essdee_yrp.fabric_source._uses_exact_source_pool", return_value=True)
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_calculate_rejects_only_a_mixed_submitted_selection(
		self, resolve, _uses_exact
	):
		resolve.return_value = {"value": "0::Knitting", "process_name": "Knitting"}
		with self.assertRaisesRegex(frappe.ValidationError, "mixed keyed and legacy"):
			validate_source_demands(
				[
					{"item_variant": "CLOTH-EXACT", "qty": 1, "source_bucket_key": "SOURCE"},
					{"item_variant": "CLOTH-LEGACY", "qty": 1},
				],
				lot="LOT-1",
				ipd=frappe._dict(name="IPD-1"),
				cloth_item="CLOTH",
				current_process="Dyeing",
				current_work_order="WO-NEW",
				source_process="0::Knitting",
			)

	@patch("essdee_yrp.fabric_source.prepare_source_pool")
	@patch("essdee_yrp.fabric_source._require_immediate_source")
	@patch("essdee_yrp.fabric_source._uses_exact_source_pool", return_value=True)
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_calculate_uses_exact_selection_even_when_lot_history_is_mixed(
		self, resolve, _uses_exact, _immediate, prepare
	):
		resolve.return_value = {"value": "0::Knitting", "process_name": "Knitting"}
		prepare.return_value = {"source_mode": "mixed", "buckets": {}}

		result = validate_source_demands(
			[{"item_variant": "CLOTH-EXACT", "qty": 1, "source_bucket_key": "SOURCE"}],
			lot="LOT-1",
			ipd=frappe._dict(name="IPD-1"),
			cloth_item="CLOTH",
			current_process="Dyeing",
			current_work_order="WO-NEW",
			source_process="0::Knitting",
		)

		self.assertEqual(result["source_mode"], "exact")
		prepare.assert_called_once()

	@patch("essdee_yrp.fabric_source._rows_in_stock_uom")
	@patch("essdee_yrp.fabric_source.get_source_availability")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_calculate_rechecks_stale_or_overallocated_quantity(self, resolve, availability, stock_rows):
		resolve.return_value = {
			"value": "0::Knitting",
			"process_name": "Knitting",
		}
		availability.return_value = {
			"received": {"Greige-32": 100},
			"reserved": {"Greige-32": 20},
			"net": {"Greige-32": 80},
		}
		stock_rows.return_value = {"Greige-32": 90}

		with self.assertRaisesRegex(frappe.ValidationError, "only 80.0 Kg remains available"):
			validate_source_demands(
				[{"item_variant": "Greige-32", "qty": 90, "uom": "Kg"}],
				lot="LOT-1",
				ipd=frappe._dict(name="IPD-1"),
				cloth_item="Test Cloth",
				current_process="Dyeing",
				current_work_order="WO-2",
				source_process="0::Knitting",
			)


class TestFabricSourceTransactions(IntegrationTestCase):
	"""Real parent/child transaction rows exercise the production SQL contract."""

	def _work_order(self, name, process, item, docstatus, source=None):
		doc = frappe.new_doc("YRP Work Order")
		doc.name = name
		doc.docstatus = docstatus
		doc.process_name = process
		doc.item = item
		doc.lot = self.lot
		doc.production_detail = self.ipd
		if source:
			doc.fabric_source_process = source
			doc.fabric_source_process_step = f"0::{source}"
		doc.db_insert()
		return doc

	def _source_receipt(self, suffix, qty, *, is_rework=0, is_return=0):
		wo = self._work_order(f"_Test Source WO {suffix}", "Knitting", self.item, 1)
		receivable = frappe.new_doc("YRP Work Order Receivables")
		receivable.name = f"_Test Source WOR {suffix}"
		receivable.parent = wo.name
		receivable.parenttype = "YRP Work Order"
		receivable.parentfield = "receivables"
		receivable.item_variant = self.variant
		receivable.qty = qty
		receivable.uom = "Kg"
		receivable.db_insert()

		grn = frappe.new_doc("YRP Goods Received Note")
		grn.name = f"_Test Source GRN {suffix}"
		grn.docstatus = 1
		grn.against = "YRP Work Order"
		grn.against_id = wo.name
		grn.is_rework = is_rework
		grn.is_return = is_return
		grn.db_insert()

		item = frappe.new_doc("YRP Goods Received Note Item")
		item.name = f"_Test Source GRNI {suffix}"
		item.parent = grn.name
		item.parenttype = "YRP Goods Received Note"
		item.parentfield = "items"
		item.item_variant = self.variant
		item.quantity = qty
		item.stock_qty = qty
		item.uom = "Kg"
		item.ref_doctype = "YRP Work Order Receivables"
		item.ref_docname = receivable.name
		item.db_insert()
		return grn

	def setUp(self):
		suffix = frappe.generate_hash(length=8)
		self.item = _ensure_item(f"_Test Source Cloth {suffix}")
		self.variant = _resolve_variant(self.item, {})
		self.lot = f"_Test Source Lot {suffix}"
		self.ipd = f"_Test Source IPD {suffix}"
		self.current = f"_Test Current WO {suffix}"
		self.suffix = suffix

	def test_submitted_grns_minus_same_source_work_order_reservations(self):
		self._source_receipt(self.suffix, 100)
		# Rework output is still physical input for a later process and therefore
		# remains selectable; only Lot-level cumulative counting was removed.
		self._source_receipt(f"{self.suffix}-RW", 20, is_rework=1)
		# Return GRNs are not positive source availability.
		self._source_receipt(f"{self.suffix}-RET", 10, is_return=1)

		target = self._work_order(
			f"_Test Reserved WO {self.suffix}",
			"Dyeing",
			self.item,
			0,
			source="Knitting",
		)
		reserved = frappe.new_doc("YRP Work Order Deliverables")
		reserved.name = f"_Test Reserved WOD {self.suffix}"
		reserved.parent = target.name
		reserved.parenttype = "YRP Work Order"
		reserved.parentfield = "deliverables"
		reserved.item_variant = self.variant
		reserved.qty = 35
		reserved.uom = "Kg"
		reserved.is_calculated = 1
		reserved.db_insert()

		# A different downstream process selecting the same Knitting pool must
		# reserve it too; otherwise Dyeing could reuse cloth already allocated to
		# White Wash.
		other_target = self._work_order(
			f"_Test Other Reserved WO {self.suffix}",
			"White Wash",
			self.item,
			0,
			source="Knitting",
		)
		other_reserved = frappe.new_doc("YRP Work Order Deliverables")
		other_reserved.name = f"_Test Other Reserved WOD {self.suffix}"
		other_reserved.parent = other_target.name
		other_reserved.parenttype = "YRP Work Order"
		other_reserved.parentfield = "deliverables"
		other_reserved.item_variant = self.variant
		other_reserved.qty = 25
		other_reserved.uom = "Kg"
		other_reserved.is_calculated = 1
		other_reserved.db_insert()

		# A Work Order consuming the same physical variant from another source
		# process belongs to a different pool and must not reduce Knitting.
		unrelated_target = self._work_order(
			f"_Test Unrelated Reserved WO {self.suffix}",
			"Washing",
			self.item,
			0,
			source="Dyeing",
		)
		unrelated_reserved = frappe.new_doc("YRP Work Order Deliverables")
		unrelated_reserved.name = f"_Test Unrelated Reserved WOD {self.suffix}"
		unrelated_reserved.parent = unrelated_target.name
		unrelated_reserved.parenttype = "YRP Work Order"
		unrelated_reserved.parentfield = "deliverables"
		unrelated_reserved.item_variant = self.variant
		unrelated_reserved.qty = 40
		unrelated_reserved.uom = "Kg"
		unrelated_reserved.is_calculated = 1
		unrelated_reserved.db_insert()

		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
		)
		self.assertEqual(available["received"], {self.variant: 120})
		self.assertEqual(available["reserved"], {self.variant: 60})
		self.assertEqual(available["net"], {self.variant: 60})

		# Cancelling the reserving WO releases the quantity without touching Lot.
		frappe.db.set_value("YRP Work Order", target.name, "docstatus", 2)
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
		)
		self.assertEqual(available["reserved"], {self.variant: 25})
		self.assertEqual(available["net"], {self.variant: 95})

		frappe.db.set_value("YRP Work Order", other_target.name, "docstatus", 2)
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
		)
		self.assertEqual(available["net"], {self.variant: 120})

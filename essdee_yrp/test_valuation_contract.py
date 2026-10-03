import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.mrp_stock_transfer import (
	_preflight_grn_stock_cancel,
	_validate_grn,
)
from essdee_yrp.api.work_order import _normalize_generated_uom_rows
from essdee_yrp.delivery_challan_hooks import validate_exact_source_limits
from essdee_yrp.fabric_grn import (
	QTY_TOLERANCE,
	_aggregate_rows,
	_calculate_saved_execution_inputs,
	_calculate_saved_work_order_inputs,
	_get_output_demands,
	_normalize_actual_dia_row_indexes,
	before_validate as prepare_fabric_grn,
	get_saved_actual_dia_rows,
	validate_actual_dia_rows,
)
from essdee_yrp.fabric_tracking import _apply_grn
from essdee_yrp.hooks import doc_events, override_doctype_class
from essdee_yrp.inspection_entry import _accepted_delta_by_source, convert_stock
from essdee_yrp.overrides.delivery_challan import EssdeeDeliveryChallan
from essdee_yrp.overrides.goods_received_note import (
	EssdeeGoodsReceivedNote,
	_guard_source_grn_allocations,
)
from essdee_yrp.work_order_hooks import validate_fabric_execution_immutable
from yrp.yrp.doctype.goods_received_note.goods_received_note import GoodsReceivedNote
from yrp.yrp.doctype.goods_received_note.goods_received_note import (
	_group_production_grn_receipts,
	_grn_receipt_stock_entries,
	make_production_grn_stock_ledger_entries,
)


class TestEssdeeValuationContract(UnitTestCase):
	def test_output_demand_keeps_one_row_per_physical_grn_item(self):
		receivable = frappe._dict(
			name="WOR-1",
			item_variant="CLOTH-26-GREIGE",
			qty=100,
			fabric_reference_allocations=json.dumps({
				"CLOTH-26-BLACK": 40,
				"CLOTH-26-NAVY": 60,
			}),
		)
		wo = frappe._dict(name="WO-1", receivables=[receivable])
		grn = frappe._dict(items=[frappe._dict(
			name="GRNI-1",
			ref_docname="WOR-1",
			item_variant="CLOTH-30-GREIGE",
			quantity=90,
		)])

		with patch(
			"essdee_yrp.fabric_grn._variant_attrs",
			return_value={"Dia": "30 Dia", "Colour": "Greige"},
		):
			demands = _get_output_demands(grn, wo)

		self.assertEqual(len(demands), 1)
		self.assertEqual(demands[0]["qty"], 90)
		self.assertEqual(
			demands[0]["reference_allocations"],
			{"CLOTH-26-BLACK": 36, "CLOTH-26-NAVY": 54},
		)

	def test_positive_receipt_sle_count_equals_physical_grn_item_count(self):
		for quantities in ([5], [5, 5]):
			doc = frappe.get_doc({
				"doctype": "Goods Received Note",
				"name": "GRN-PHYSICAL",
				"posting_date": "2026-10-03",
				"posting_time": "10:00:00",
				"items": [
					{
						"doctype": "Goods Received Note Item",
						"name": f"GRNI-{index}",
						"item_variant": f"CLOTH-{index}",
						"quantity": qty,
						"stock_qty": qty,
						"uom": "Kg",
						"stock_uom": "Kg",
						"rate": 10,
					}
					for index, qty in enumerate(quantities, 1)
				],
			})
			with patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=[],
			):
				entries = _grn_receipt_stock_entries(doc, "TARGET-WH")

			positive = [entry for entry in entries if entry["qty"] > 0]
			self.assertEqual(len(positive), len(quantities))
			self.assertEqual(
				[entry["voucher_detail_no"] for entry in positive],
				[f"GRNI-{index}" for index in range(1, len(quantities) + 1)],
			)

	def test_production_receipt_groups_identical_physical_outputs_into_one_sle(self):
		doc = frappe.get_doc({
			"doctype": "Goods Received Note",
			"name": "GRN-GROUPED-PHYSICAL",
			"posting_date": "2026-10-03",
			"posting_time": "10:00:00",
			"items": [
				{
					"doctype": "Goods Received Note Item",
					"name": "GRNI-1",
					"item_variant": "CLOTH-30-NAVY",
					"quantity": 10,
					"stock_qty": 10,
					"uom": "Kg",
					"stock_uom": "Kg",
					"rate": 12,
				},
				{
					"doctype": "Goods Received Note Item",
					"name": "GRNI-2",
					"item_variant": "CLOTH-30-NAVY",
					"quantity": 8,
					"stock_qty": 8,
					"uom": "Kg",
					"stock_uom": "Kg",
					"rate": 15,
				},
			],
		})
		with patch(
			"yrp.stock.dimensions.get_dimension_fieldnames",
			return_value=[],
		):
			groups = _group_production_grn_receipts(
				doc, "TARGET-WH", with_result_keys=True
			)

		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["item_rows"], ["GRNI-1", "GRNI-2"])
		self.assertEqual(groups[0]["entry"]["qty"], 18)
		self.assertAlmostEqual(
			groups[0]["entry"]["rate"],
			(10 * 12 + 8 * 15) / 18,
		)

	def test_managed_contract_rejects_appended_unkeyed_rows(self):
		parameters = '{"fabric_execution_key":"fabric-test"}'
		before = frappe._dict(
			lot="LOT-1", production_detail="IPD-1", process_name="Dyeing",
			item="CLOTH", supplier="SUP-1", delivery_location="LOC-1",
			fabric_source_process="Knitting",
			fabric_source_process_step="0::Knitting", open_status="Open",
			deliverables=[frappe._dict(
				name="WOD-1", item_variant="CLOTH-GREY", qty=5, uom="Kg",
				pending_quantity=5, stock_update=0,
				additional_parameters=parameters,
			)],
			receivables=[frappe._dict(
				name="WOR-1", item_variant="CLOTH-RED", qty=5, uom="Kg",
				pending_quantity=5, stock_update=0,
				additional_parameters=parameters,
			)],
		)
		current = frappe._dict(before.copy())
		current.deliverables = list(before.deliverables) + [frappe._dict(
			name="WOD-EXTRA", item_variant="YARN-EXTRA", qty=1, uom="Kg",
		)]
		current.receivables = list(before.receivables)
		current.flags = frappe._dict()
		current.get_doc_before_save = lambda: before
		with patch(
			"yrp.stock.dimensions.get_dimension_fieldnames",
			return_value=["received_type"],
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "only through Calculate"
			):
				validate_fabric_execution_immutable(current)

	def test_fabric_grn_quantity_tolerance_is_defined(self):
		self.assertEqual(QTY_TOLERANCE, 0.000001)

	def test_grn_uses_controller_without_lot_tracking_hooks(self):
		self.assertEqual(
			override_doctype_class["Goods Received Note"],
			"essdee_yrp.overrides.goods_received_note.EssdeeGoodsReceivedNote",
		)
		self.assertEqual(
			override_doctype_class["Delivery Challan"],
			"essdee_yrp.overrides.delivery_challan.EssdeeDeliveryChallan",
		)
		grn_events = doc_events["Goods Received Note"]
		self.assertIn(
			"essdee_yrp.fabric_grn.before_validate",
			grn_events["before_validate"],
		)
		self.assertNotIn(
			"essdee_yrp.fabric_tracking.on_grn_submit",
			grn_events.get("on_submit", []),
		)
		from essdee_yrp.hooks import override_whitelisted_methods

		self.assertEqual(
			override_whitelisted_methods[
				"yrp.yrp.doctype.inspection_entry.inspection_entry.convert_stock"
			],
			"essdee_yrp.inspection_entry.convert_stock",
		)
		self.assertNotIn(
			"essdee_yrp.fabric_tracking.on_grn_cancel",
			grn_events.get("on_cancel", []),
		)

	def test_grn_child_schema_contains_full_lineage_contract(self):
		path = Path(__file__).parent / (
			"essdee_yrp/doctype/yrp_grn_deliverable/yrp_grn_deliverable.json"
		)
		data = json.loads(path.read_text())
		fields = {row["fieldname"]: row for row in data["fields"]}
		for fieldname in (
			"goods_received_note_item",
			"received_item_variant",
			"material_value",
			"consumption_sle",
			"output_receipt_sle",
			"stock_dimensions",
		):
			self.assertIn(fieldname, fields)
		self.assertEqual(fields["work_order_deliverable"]["fieldtype"], "Link")
		self.assertTrue(fields["goods_received_note_item"]["reqd"])

	def test_grouped_grn_rows_are_named_before_lineage_is_calculated(self):
		"""The base grouped editor replaces items during before_validate."""
		doc = EssdeeGoodsReceivedNote({
			"doctype": "Goods Received Note",
			"docstatus": 1,
			"items": [{
				"doctype": "Goods Received Note Item",
				"item_variant": "CLOTH-22-DIA",
				"quantity": 6,
			}],
		})
		doc.items[0].name = None

		def calculated_plan(current):
			self.assertTrue(current.items[0].name)
			return [{"goods_received_note_item": current.items[0].name}]

		with (
			patch("essdee_yrp.fabric_grn.validate_actual_dia_rows"),
			patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
			patch(
				"essdee_yrp.fabric_grn.calculate_consumption_plan",
				side_effect=calculated_plan,
			),
			patch("essdee_yrp.fabric_grn.populate_grn_deliverables") as populate,
		):
			prepare_fabric_grn(doc)

		populate.assert_called_once_with(
			doc, [{"goods_received_note_item": doc.items[0].name}]
		)

	def test_draft_grn_does_not_validate_calculated_input_availability(self):
		doc = EssdeeGoodsReceivedNote({
			"doctype": "Goods Received Note",
			"docstatus": 0,
			"grn_deliverables": [{
				"goods_received_note_item": "OLD-GRN-ROW",
				"received_item_variant": "OLD-OUTPUT",
				"item_variant": "OLD-INPUT",
				"work_order_deliverable": "OLD-WOD",
				"quantity": 1,
				"uom": "Kg",
			}],
		})
		with (
			patch("essdee_yrp.fabric_grn.validate_actual_dia_rows"),
			patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
			patch("essdee_yrp.fabric_grn.calculate_consumption_plan") as calculate,
			patch("essdee_yrp.fabric_grn.populate_grn_deliverables") as populate,
		):
			prepare_fabric_grn(doc)

		calculate.assert_not_called()
		populate.assert_not_called()
		self.assertEqual(doc.get("grn_deliverables"), [])

	def test_non_fabric_grn_still_runs_base_submit_and_cancel_guards(self):
		doc = EssdeeGoodsReceivedNote({"doctype": "Goods Received Note"})
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.is_calculable_fabric_grn",
				return_value=False,
			),
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
			patch.object(GoodsReceivedNote, "before_cancel") as base_cancel,
		):
			doc.before_submit()
			doc.before_cancel()

		base_submit.assert_called_once_with()
		base_cancel.assert_called_once_with()

	def test_fabric_submit_populates_exact_plan_before_base_valuation(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": "Goods Received Note",
				"against": "Work Order",
				"against_id": "WO-TEST",
			}
		)
		plan = [{"goods_received_note_item": "GRN-ROW-1"}]
		locked_work_order = frappe._dict(name="WO-TEST", open_status="Open")
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.is_calculable_fabric_grn",
				return_value=True,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._get_locked_work_order",
				return_value=locked_work_order,
			) as get_locked_work_order,
			patch(
				"essdee_yrp.overrides.goods_received_note.calculate_consumption_plan",
				return_value=plan,
			) as calculate_consumption,
			patch(
				"essdee_yrp.overrides.goods_received_note.populate_grn_deliverables"
			) as populate,
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
		):
			doc.before_submit()

		get_locked_work_order.assert_called_once_with("WO-TEST")
		self.assertEqual(
			doc.flags.essdee_locked_work_order, locked_work_order
		)
		calculate_args = calculate_consumption.call_args
		self.assertEqual(calculate_args.kwargs["work_order_doc"], locked_work_order)
		populate.assert_called_once_with(doc, plan)
		base_submit.assert_called_once_with()
		self.assertEqual(doc.flags.essdee_deliverable_consumption, plan)

	def test_consumption_aggregation_never_blends_different_outputs(self):
		rows = [
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 2,
				"uom": "Kg",
				"reference_item_variant": "RED-CLOTH",
			},
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 1,
				"uom": "Kg",
				"reference_item_variant": "RED-CLOTH",
			},
			{
				"goods_received_note_item": "OUT-2",
				"received_item_variant": "BLUE-CLOTH",
				"item_variant": "GREIGE-CLOTH",
				"qty": 4,
				"uom": "Kg",
				"reference_item_variant": "BLUE-CLOTH",
			},
		]

		result = _aggregate_rows(rows)

		self.assertEqual(len(result), 2)
		self.assertEqual(
			{row["goods_received_note_item"]: row["qty"] for row in result},
			{"OUT-1": 3.0, "OUT-2": 4.0},
		)

	def test_multi_yarn_contract_scales_each_physical_actual_dia_output(self):
		wo = frappe._dict(
			receivables=[frappe._dict(
				qty=100,
				fabric_reference_allocations=json.dumps({"BLACK": 40, "NAVY": 60}),
			)],
			deliverables=[
				frappe._dict(
					item_variant="YARN-A", qty=59, uom="Kg", is_calculated=1,
					fabric_reference_allocations=json.dumps({"BLACK": 23.6, "NAVY": 35.4}),
				),
				frappe._dict(
					item_variant="YARN-B", qty=41, uom="Kg", is_calculated=1,
					fabric_reference_allocations=json.dumps({"BLACK": 16.4, "NAVY": 24.6}),
				),
			],
		)
		demands = [
			{
				"goods_received_note_item": "ACTUAL-22",
				"received_item_variant": "CLOTH-22",
				"qty": 60,
				"reference_allocations": {"BLACK": 24, "NAVY": 36},
			},
			{
				"goods_received_note_item": "ACTUAL-24",
				"received_item_variant": "CLOTH-24",
				"qty": 50,
				"reference_allocations": {"BLACK": 20, "NAVY": 30},
			},
		]

		rows = _calculate_saved_work_order_inputs(wo, demands)
		by_output = {}
		for row in rows:
			output = by_output.setdefault(row["goods_received_note_item"], {})
			output[row["item_variant"]] = (
				output.get(row["item_variant"], 0) + row["qty"]
			)

		self.assertEqual(by_output, {
			"ACTUAL-22": {"YARN-A": 35.4, "YARN-B": 24.6},
			"ACTUAL-24": {"YARN-A": 29.5, "YARN-B": 20.5},
		})

	def test_physical_output_value_distribution_keeps_last_remainder(self):
		class Meta:
			@staticmethod
			def get_field(_fieldname):
				return True

		outputs = [
			frappe._dict(
				name="OUT-22", doctype="Goods Received Note Item",
				item_variant="CLOTH-22", quantity=6, stock_qty=6,
				uom="Kg", stock_uom="Kg", rate=0, amount=0,
			),
			frappe._dict(
				name="OUT-24", doctype="Goods Received Note Item",
				item_variant="CLOTH-24", quantity=5, stock_qty=5,
				uom="Kg", stock_uom="Kg", rate=0, amount=0,
			),
		]
		rows = [
			frappe._dict(
				name="INPUT-22", idx=1, meta=Meta(),
				goods_received_note_item="OUT-22",
				item_variant="YARN-A", quantity=6, stock_qty=6,
				uom="Kg", stock_uom="Kg", stock_dimensions="{}",
			),
			frappe._dict(
				name="INPUT-24", idx=2, meta=Meta(),
				goods_received_note_item="OUT-24",
				item_variant="YARN-A", quantity=5, stock_qty=5,
				uom="Kg", stock_uom="Kg", stock_dimensions="{}",
			),
		]
		grn = frappe._dict(
			doctype="Goods Received Note", name="GRN-PHYSICAL-VALUE",
			against_id="WO-1", from_warehouse="SOURCE", posting_date="2026-10-03",
			posting_time="10:00:00", items=outputs, grn_deliverables=rows,
			flags=frappe._dict(), total_received_quantity=0, total=0,
		)
		grn.apply_freight_allocation = lambda: None
		grn.calculate_totals = lambda: None

		def ledger(entries, return_details=False, **_kwargs):
			if entries and entries[0]["qty"] < 0:
				return {"entries": {
					"grn-consumption-1": {"value": 100.000001, "sle": "SLE-IN"},
				}}
			return {"entries": {
				"grn-output:OUT-22": {"sle": "SLE-OUT-22"},
				"grn-output:OUT-24": {"sle": "SLE-OUT-24"},
			}}

		def persist(row, rate, value, consumption_sle=None, output_receipt_sle=None):
			row.valuation_rate = rate
			row.material_value = value
			if consumption_sle:
				row.consumption_sle = consumption_sle
			if output_receipt_sle:
				row.output_receipt_sle = output_receipt_sle

		with (
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=[]),
			patch("yrp.stock.stock_ledger.make_sl_entries", side_effect=ledger),
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note._persist_grn_deliverable_value", side_effect=persist),
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note.get_work_order_process_rate", return_value=2),
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note.frappe.get_doc", return_value=frappe._dict(name="WO-1")),
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note.frappe.db.set_value"),
			patch("yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.register_production_links") as register,
		):
			make_production_grn_stock_ledger_entries(grn, "TARGET")

		expected_first = 100.000001 / 11 * 6
		self.assertAlmostEqual(rows[0].material_value, expected_first, places=9)
		self.assertAlmostEqual(rows[1].material_value, 100.000001 - expected_first, places=9)
		self.assertAlmostEqual(outputs[0].rate, 2 + expected_first / 6, places=9)
		self.assertAlmostEqual(
			outputs[1].rate, 2 + (100.000001 - expected_first) / 5, places=9
		)
		links = register.call_args.args[2]
		self.assertEqual(
			{link["output_receipt_sle"] for link in links},
			{"SLE-OUT-22", "SLE-OUT-24"},
		)

	def test_physical_grn_cancel_reverses_posted_shape_without_recalculation(self):
		output = frappe._dict(
			name="OUT-22", item_variant="CLOTH-22", quantity=11, stock_qty=11,
			uom="Kg", stock_uom="Kg", rate=11,
		)
		row = frappe._dict(
			name="INPUT-1", goods_received_note_item="OUT-22",
			item_variant="YARN-A", quantity=11, stock_qty=11,
			uom="Kg", stock_uom="Kg", stock_dimensions="{}",
		)
		grn = frappe._dict(
			doctype="Goods Received Note", name="GRN-CANCEL-PHYSICAL",
			from_warehouse="SOURCE", posting_date="2026-10-03", posting_time="10:00:00",
			items=[output], grn_deliverables=[row],
		)

		with (
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=[]),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note.frappe.get_doc") as get_work_order,
			patch("yrp.yrp.doctype.goods_received_note.goods_received_note.get_work_order_process_rate") as process_rate,
			patch("yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.deactivate_production_links") as deactivate,
			patch("yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.register_production_links") as register,
		):
			make_production_grn_stock_ledger_entries(grn, "TARGET", cancel=True)

		entries = make_entries.call_args.args[0]
		self.assertEqual([entry["qty"] for entry in entries], [-11, 11])
		self.assertTrue(make_entries.call_args.kwargs["cancel"])
		deactivate.assert_called_once_with("Goods Received Note", "GRN-CANCEL-PHYSICAL")
		register.assert_not_called()
		get_work_order.assert_not_called()
		process_rate.assert_not_called()

	def test_consumption_aggregation_keeps_exact_work_order_inputs_separate(self):
		rows = [
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"work_order_deliverable": "WOD-GRN-A",
				"item_variant": "GREIGE-CLOTH",
				"qty": 2,
				"uom": "Kg",
			},
			{
				"goods_received_note_item": "OUT-1",
				"received_item_variant": "RED-CLOTH",
				"work_order_deliverable": "WOD-GRN-B",
				"item_variant": "GREIGE-CLOTH",
				"qty": 3,
				"uom": "Kg",
			},
		]

		result = _aggregate_rows(rows)

		self.assertEqual(len(result), 2)
		self.assertEqual(
			{row["work_order_deliverable"]: row["qty"] for row in result},
			{"WOD-GRN-A": 2.0, "WOD-GRN-B": 3.0},
		)

	def test_saved_execution_contract_scales_exact_inputs_for_actual_dia(self):
		parameters = '{"fabric_execution_key":"fabric-test"}'
		wo = frappe._dict({
			"receivables": [frappe._dict(qty=100, additional_parameters=parameters)],
			"deliverables": [
				frappe._dict(
					item_variant="YARN-A",
					qty=59,
					uom="Kg",
					is_calculated=1,
					additional_parameters=parameters,
				),
				frappe._dict(
					item_variant="YARN-B",
					qty=41,
					uom="Kg",
					is_calculated=1,
					additional_parameters=parameters,
				),
			],
		})
		demands = [{
			"goods_received_note_item": "ACTUAL-22-DIA-ROW",
			"received_item_variant": "CLOTH-22-DIA",
			"reference_item_variant": "CLOTH-18-DIA",
			"execution_key": "fabric-test",
			"qty": 40,
		}]

		rows = _calculate_saved_execution_inputs(wo, demands)

		self.assertEqual(
			{row["item_variant"]: row["qty"] for row in rows},
			{"YARN-A": 23.6, "YARN-B": 16.4},
		)
		self.assertTrue(all(row["received_item_variant"] == "CLOTH-22-DIA" for row in rows))

	def test_actual_dia_allows_only_dia_to_change_on_default_knitting(self):
		wo = frappe._dict(
			process_name="Knitting",
			receivables=[frappe._dict(name="WOR-1", item_variant="CLOTH-18-GREY")],
		)
		grn = frappe._dict(
			against="Work Order",
			against_id="WO-1",
			items=[frappe._dict(
				idx=1,
				ref_docname="WOR-1",
				item_variant="CLOTH-22-GREY",
			)],
		)
		with (
			patch("essdee_yrp.fabric_grn.frappe.db.exists", return_value=True),
			patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
			patch("essdee_yrp.fabric_grn.frappe.get_doc", return_value=wo),
			patch(
				"essdee_yrp.fabric_grn.frappe.db.get_single_value",
				return_value="Knitting",
			),
			patch(
				"essdee_yrp.fabric_grn.frappe.db.get_value",
				return_value="CLOTH",
			),
			patch(
				"essdee_yrp.fabric_grn._variant_attrs",
				side_effect=[
					{"Dia": "18 Dia", "Colour": "Grey"},
					{"Dia": "22 Dia", "Colour": "Grey"},
				],
			),
			patch(
				"essdee_yrp.fabric_grn.frappe.get_all",
				return_value=["18 Dia", "22 Dia"],
			),
		):
			validate_actual_dia_rows(grn)

	def test_actual_dia_splits_get_distinct_grouped_display_rows(self):
		grn = frappe._dict(items=[
			frappe._dict(
				ref_docname=None, item_variant="LEGACY-CLOTH",
				received_type="Accepted", row_index="0",
			),
			frappe._dict(
				ref_docname="WOR-1", item_variant="CLOTH-30",
				received_type="Accepted", row_index="fc-0",
			),
			frappe._dict(
				ref_docname="WOR-1", item_variant="CLOTH-32",
				received_type="Accepted", row_index="fc-0",
			),
			frappe._dict(
				ref_docname="WOR-1", item_variant="CLOTH-30",
				received_type="Rejected", row_index="fc-0",
			),
			frappe._dict(
				ref_docname="WOR-2", item_variant="CLOTH-22",
				received_type="Accepted", row_index="fc-1",
			),
		])

		_normalize_actual_dia_row_indexes(
			grn, {"WOR-1": frappe._dict(), "WOR-2": frappe._dict()}
		)

		self.assertEqual(
			[row.row_index for row in grn.get("items")],
			["0", "1", "2", "1", "3"],
		)

	def test_saved_actual_dia_helper_refreshes_current_source_limits(self):
		work_order = frappe._dict(
			name="WO-KNIT-1",
			receivables=[frappe._dict(
				name="WOR-1",
				item_variant="CLOTH-24-RED",
				qty=10,
				pending_quantity=8,
				cost=3,
			)],
		)
		grn = frappe._dict(items=[frappe._dict(
			name="GRNI-1",
			ref_docname="WOR-1",
			item_variant="CLOTH-26-RED",
			quantity=5,
			uom="Kg",
			row_index="1",
			received_type="Accepted",
		)])
		with patch(
			"yrp.yrp.doctype.goods_received_note.goods_received_note._wo_excess_percentage",
			return_value=10,
		):
			rows = get_saved_actual_dia_rows(grn, work_order)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_variant"], "CLOTH-26-RED")
		self.assertEqual(rows[0]["quantity"], 5)
		self.assertEqual(rows[0]["pending_quantity"], 8)
		self.assertEqual(rows[0]["max_receivable_quantity"], 9)
		self.assertEqual(rows[0]["rate"], 3)

	def test_draft_onload_merges_saved_actual_dia_once(self):
		work_order = frappe._dict(
			name="WO-KNIT-1",
			process_name="Knitting",
			receivables=[frappe._dict(
				name="WOR-1",
				item_variant="CLOTH-24-RED",
				qty=10,
				pending_quantity=8,
				cost=3,
			)],
		)
		doc = EssdeeGoodsReceivedNote({
			"doctype": "Goods Received Note",
			"docstatus": 0,
			"against": "Work Order",
			"against_id": work_order.name,
			"items": [{
				"doctype": "Goods Received Note Item",
				"name": "GRNI-1",
				"ref_docname": "WOR-1",
				"item_variant": "CLOTH-26-RED",
				"quantity": 5,
				"uom": "Kg",
				"row_index": "1",
				"received_type": "Accepted",
			}],
		})
		planned_row = {
			"ref_docname": "WOR-1",
			"item_variant": "CLOTH-24-RED",
			"quantity": 0,
			"uom": "Kg",
			"row_index": "0",
			"received_type": "Accepted",
		}

		def capture_grouped_rows(rows, _doctype):
			return [dict(row) for row in rows]

		with (
			patch.object(GoodsReceivedNote, "onload"),
			patch.object(
				EssdeeGoodsReceivedNote,
				"_uses_essdee_deliverable_consumption",
				return_value=True,
			),
			patch("frappe.get_doc", return_value=work_order),
			patch("frappe.db.get_single_value", return_value="Knitting"),
			patch(
				"yrp.yrp.doctype.goods_received_note.goods_received_note._wo_excess_percentage",
				return_value=10,
			),
			patch(
				"yrp.yrp.doctype.goods_received_note.goods_received_note._pending_receivable_rows",
				side_effect=lambda *_args, **_kwargs: [dict(planned_row)],
			),
			patch(
				"yrp.yrp.doctype.delivery_challan.delivery_challan._get_production_group_dimensions",
				return_value=[],
			),
			patch(
				"yrp.yrp.doctype.delivery_challan.delivery_challan._apply_dimension_values_to_rows"
			),
			patch("yrp.stock.dimensions.apply_dimension_defaults"),
			patch(
				"yrp.stock.save_stock_items.group_items_for_ui",
				side_effect=capture_grouped_rows,
			),
		):
			doc.onload()
			first = doc.get_onload("item_details")
			doc.onload()
			second = doc.get_onload("item_details")

		self.assertEqual(first, second)
		self.assertEqual(len(second), 1)
		self.assertEqual(
			[row["item_variant"] for row in second],
			["CLOTH-26-RED"],
		)
		self.assertEqual(second[0]["quantity"], 5)
		self.assertEqual(second[0]["max_receivable_quantity"], 9)
		self.assertEqual(len(doc.get("items")), 1)

	def test_actual_dia_is_rejected_for_excluded_grn_modes(self):
		wo = frappe._dict(
			process_name="Knitting",
			receivables=[frappe._dict(name="WOR-1", item_variant="CLOTH-18-GREY")],
		)
		grn = frappe._dict(
			against="Work Order",
			against_id="WO-1",
			is_rework=1,
			items=[frappe._dict(
				idx=1,
				ref_docname="WOR-1",
				item_variant="CLOTH-22-GREY",
			)],
		)
		with (
			patch("essdee_yrp.fabric_grn.frappe.db.exists", return_value=True),
			patch("essdee_yrp.fabric_grn.frappe.get_doc", return_value=wo),
			patch(
				"essdee_yrp.fabric_grn.frappe.db.get_single_value",
				return_value="Knitting",
			),
			patch(
				"essdee_yrp.fabric_grn.is_calculable_fabric_grn",
				return_value=False,
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "standard GRN"
			):
				validate_actual_dia_rows(grn)

	def test_source_grn_cancel_has_no_draft_work_order_reservation_guard(self):
		with patch(
			"essdee_yrp.overrides.goods_received_note.frappe.db.sql",
		) as sql:
			_guard_source_grn_allocations(frappe._dict(name="GRN-KNIT-1"))
		sql.assert_not_called()

	def test_delivery_challan_blocks_excess_against_exact_source_row(self):
		doc = frappe._dict(
			work_order="WO-DYE-1",
			docstatus=1,
			correction_items=[],
			items=[frappe._dict(
				ref_doctype="Work Order Deliverables",
				ref_docname="WOD-1",
				item_variant="CLOTH-1",
				uom="Kg",
				received_type="Accepted",
				delivered_quantity=12,
			)],
		)
		with patch(
			"essdee_yrp.delivery_challan_hooks.frappe.db.sql",
			return_value=[frappe._dict(
				name="WOD-1",
				source_grn_item="GRNI-1",
				pending_quantity=10,
				item_variant="CLOTH-1",
				uom="Kg",
				set_combination=None,
				received_type="Accepted",
			)],
		), patch(
			"yrp.stock.dimensions.get_dimension_fieldnames",
			return_value=["received_type"],
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "can dispatch only 10"
			):
				validate_exact_source_limits(doc)

	def test_delivery_challan_aggregates_submit_qty_by_exact_source_row(self):
		doc = frappe._dict(
			name="DC-DYE-1",
			work_order="WO-DYE-1",
			docstatus=1,
			correction_items=[],
			items=[
				frappe._dict(
					ref_doctype="Work Order Deliverables",
					ref_docname="WOD-1",
					item_variant="CLOTH-1",
					uom="Kg",
					delivered_quantity=6,
				),
				frappe._dict(
					ref_doctype="Work Order Deliverables",
					ref_docname="WOD-2",
					item_variant="CLOTH-1",
					uom="Kg",
					delivered_quantity=6,
				),
			],
		)
		targets = [
			frappe._dict(
				name=name,
				source_grn="GRN-1",
				source_grn_item="GRNI-1",
				pending_quantity=10,
				qty=10,
				item_variant="CLOTH-1",
				uom="Kg",
				set_combination=None,
				fabric_reference_variant=None,
				fabric_reference_allocations=None,
			)
			for name in ("WOD-1", "WOD-2")
		]
		work_order = frappe._dict(
			lot="LOT-1",
			production_detail="IPD-1",
			item="CLOTH",
			process_name="Dyeing",
			fabric_source_process="Knitting",
			fabric_source_process_step="0::Knitting",
			delivery_location="SUPPLIER-1",
		)
		pool = {
			"selected": {"process_name": "Knitting"},
			"physical_knitting_source": True,
			"buckets": {
				"GRNI-1::-": {
					"source_grn": "GRN-1",
					"source_grn_item": "GRNI-1",
					"item_variant": "CLOTH-1",
					"remaining_stock_qty": 10,
				}
			},
		}
		with (
			patch(
				"essdee_yrp.delivery_challan_hooks.frappe.db.get_value",
				return_value=work_order,
			),
			patch(
				"essdee_yrp.delivery_challan_hooks.frappe.get_cached_doc",
				return_value=frappe._dict(name="IPD-1", item="CLOTH"),
			),
			patch(
				"essdee_yrp.delivery_challan_hooks.frappe.db.sql",
				return_value=targets,
			),
			patch(
				"essdee_yrp.fabric_source.prepare_source_pool",
				return_value=pool,
			),
			patch(
				"essdee_yrp.fabric_source._conversion_factor",
				return_value=1,
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=[],
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "exact source GRN row.*only 4"
			):
				validate_exact_source_limits(doc)

	def test_delivery_challan_rejects_changed_exact_source_dimension(self):
		doc = frappe._dict(
			work_order="WO-DYE-1",
			docstatus=0,
			correction_items=[],
			items=[frappe._dict(
				ref_doctype="Work Order Deliverables",
				ref_docname="WOD-1",
				item_variant="CLOTH-1",
				uom="Kg",
				received_type="Rejected",
				delivered_quantity=2,
			)],
		)
		with (
			patch(
				"essdee_yrp.delivery_challan_hooks.frappe.db.sql",
				return_value=[frappe._dict(
					name="WOD-1",
					source_grn_item="GRNI-1",
					pending_quantity=10,
					item_variant="CLOTH-1",
					uom="Kg",
					set_combination=None,
					received_type="Accepted",
				)],
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["received_type"],
			),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "stock dimension"):
				validate_exact_source_limits(doc)

	def test_exact_source_dc_partial_updates_share_current_locked_counter(self):
		target = frappe._dict(
			name="WOD-1", item_variant="CLOTH-1", set_combination=None,
			pending_quantity=10, db_set=MagicMock(),
		)
		wo = frappe._dict(deliverables=[target])
		wo.set_status = MagicMock()
		wo.db_set = MagicMock()
		for qty in (3, 2):
			doc = EssdeeDeliveryChallan({
				"doctype": "Delivery Challan",
				"work_order": "WO-1",
				"items": [{
					"ref_doctype": "Work Order Deliverables",
					"ref_docname": "WOD-1",
					"item_variant": "CLOTH-1",
					"qty": qty,
					"delivered_quantity": qty,
				}],
			})
			doc.flags.essdee_locked_work_order = wo
			doc.update_work_order_deliverables()
		self.assertEqual(target.pending_quantity, 5)
		self.assertEqual(
			[target.db_set.call_args_list[0].args[1], target.db_set.call_args_list[1].args[1]],
			[7, 5],
		)

	def test_fabric_grn_partial_updates_share_current_locked_counter(self):
		target = frappe._dict(
			name="WOR-1", item_variant="CLOTH-1", set_combination=None,
			pending_quantity=10, db_set=MagicMock(),
		)
		wo = frappe._dict(receivables=[target])
		wo.set_status = MagicMock()
		wo.db_set = MagicMock()
		for qty in (3, 2):
			doc = EssdeeGoodsReceivedNote({
				"doctype": "Goods Received Note",
				"against_id": "WO-1",
				"items": [{
					"ref_doctype": "Work Order Receivables",
					"ref_docname": "WOR-1",
					"item_variant": "CLOTH-1",
					"quantity": qty,
				}],
			})
			doc.flags.essdee_locked_work_order = wo
			with patch.object(doc, "update_correction_receivables"):
				doc.update_work_order_receivables()
		self.assertEqual(target.pending_quantity, 5)
		self.assertEqual(
			[target.db_set.call_args_list[0].args[1], target.db_set.call_args_list[1].args[1]],
			[7, 5],
		)

	def test_default_knitting_grn_allows_physical_excess_and_negative_pending(self):
		target = frappe._dict(
			name="WOR-1",
			item_variant="CLOTH-1",
			qty=100,
			pending_quantity=100,
			set_combination=None,
			db_set=MagicMock(),
		)
		wo = frappe._dict(process_name="Knitting", receivables=[target])
		wo.set_status = MagicMock()
		wo.db_set = MagicMock()
		doc = EssdeeGoodsReceivedNote({
			"doctype": "Goods Received Note",
			"against_id": "WO-KNIT-1",
			"items": [{
				"ref_doctype": "Work Order Receivables",
				"ref_docname": "WOR-1",
				"item_variant": "CLOTH-1",
				"quantity": 110,
			}],
		})
		doc.flags.essdee_locked_work_order = wo

		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.db.get_single_value",
				return_value="Knitting",
			),
			patch.object(doc, "validate_against_correction_pending"),
		):
			doc.validate_against_work_order_pending()
		with patch.object(doc, "update_correction_receivables"):
			doc.update_work_order_receivables()

		self.assertEqual(target.pending_quantity, -10)
		self.assertIsNone(doc.items[0].get("max_receivable_quantity"))

	def test_standard_dyeing_grn_allows_physical_excess_and_negative_pending(self):
		target = frappe._dict(
			name="WOR-1",
			item_variant="CLOTH-1",
			qty=100,
			pending_quantity=100,
			set_combination=None,
			db_set=MagicMock(),
		)
		wo = frappe._dict(process_name="Dyeing", receivables=[target])
		wo.set_status = MagicMock()
		wo.db_set = MagicMock()
		doc = EssdeeGoodsReceivedNote({
			"doctype": "Goods Received Note",
			"against_id": "WO-DYE-1",
			"items": [{
				"ref_doctype": "Work Order Receivables",
				"ref_docname": "WOR-1",
				"item_variant": "CLOTH-1",
				"quantity": 110,
			}],
		})
		doc.flags.essdee_locked_work_order = wo

		with patch.object(doc, "validate_against_correction_pending"):
			doc.validate_against_work_order_pending()
		with patch.object(doc, "update_correction_receivables"):
			doc.update_work_order_receivables()

		self.assertEqual(target.pending_quantity, -10)
		self.assertIsNone(doc.items[0].get("max_receivable_quantity"))

	def test_inspection_accepted_delta_tracks_only_exact_grn_rows(self):
		doc = frappe._dict(items=[
			frappe._dict(
				ref_doctype="Goods Received Note Item",
				ref_docname="GRNI-1",
				received_type="Accepted",
				target_received_type="Rejected",
				qty=8,
			),
			frappe._dict(
				ref_doctype="Goods Received Note Item",
				ref_docname="GRNI-1",
				received_type="Rejected",
				target_received_type="Accepted",
				qty=3,
			),
			frappe._dict(
				ref_doctype="Stock Entry Detail",
				ref_docname="SED-1",
				received_type="Accepted",
				target_received_type="Rejected",
				qty=99,
			),
		])
		with patch(
			"essdee_yrp.inspection_entry.frappe.db.get_single_value",
			return_value="Accepted",
		):
			self.assertEqual(_accepted_delta_by_source(doc), {"GRNI-1": -5.0})

	def test_inspection_conversion_uses_current_locked_document_once(self):
		discovery = frappe._dict(against="Goods Received Note", items=[])
		locked = frappe._dict(
			docstatus=1,
			status="Submitted",
			is_converted=0,
			against="Goods Received Note",
			items=[],
			_build_sl_entries=MagicMock(return_value=[]),
			db_set=MagicMock(),
		)
		with (
			patch("essdee_yrp.inspection_entry._approver_role", return_value="Approver"),
			patch("essdee_yrp.inspection_entry.frappe.get_roles", return_value=["Approver"]),
			patch(
				"essdee_yrp.inspection_entry.frappe.get_doc",
				side_effect=[discovery, locked],
			) as get_doc,
			patch("essdee_yrp.inspection_entry._lock_source_grns"),
			patch(
				"essdee_yrp.fabric_substitution.lock_lots_for_default_knitting_grns",
				return_value=["LOT-1"],
			) as lock_lots,
			patch(
				"essdee_yrp.fabric_substitution._rebuild_lot_fabric_conversions"
			) as rebuild,
			patch("essdee_yrp.inspection_entry._guard_exact_fabric_allocations"),
			patch("yrp.stock.stock_ledger.enqueue_voucher_repost") as enqueue,
		):
			result = convert_stock("IE-1")
		self.assertEqual(result, {"status": "Converted", "is_converted": 1})
		self.assertEqual(
			get_doc.call_args_list[1].kwargs,
			{"for_update": True},
		)
		enqueue.assert_called_once_with(locked)
		self.assertEqual(locked.db_set.call_count, 2)
		lock_lots.assert_called_once_with([])
		rebuild.assert_called_once_with("LOT-1", already_locked=True)

	def test_delivery_challan_blocks_corrections_on_exact_source_work_order(self):
		doc = frappe._dict(
			work_order="WO-DYE-1",
			docstatus=0,
			items=[],
			correction_items=[frappe._dict(qty=1)],
		)
		with patch(
			"essdee_yrp.delivery_challan_hooks.frappe.db.get_value",
			return_value="Knitting",
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "Corrections cannot dispatch material"
			):
				validate_exact_source_limits(doc)

	def test_generated_rows_keep_physical_stock_qty_when_master_uom_changes(self):
		rows = [
			{
				"item_variant": "PACKED-ITEM",
				"qty": 20,
				"pending_quantity": 20,
				"stock_update": 10,
				"uom": "Piece",
			}
		]
		with (
			patch(
				"yrp.stock.uom.resolve_item_uom",
				return_value=frappe._dict(
					uom="Box", stock_uom="Piece", conversion_factor=10
				),
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"stock_uom": "Piece", "conversion_factor": 1},
			),
		):
			_normalize_generated_uom_rows(rows)

		self.assertEqual(rows[0]["uom"], "Box")
		self.assertEqual(rows[0]["qty"], 2)
		self.assertEqual(rows[0]["pending_quantity"], 2)
		self.assertEqual(rows[0]["stock_update"], 1)

	def test_mrp_transfer_rejects_return_grn_server_side(self):
		doc = frappe._dict(
			doctype="Goods Received Note",
			docstatus=1,
			against="Work Order",
			is_return=1,
		)
		with patch("frappe.has_permission"):
			with self.assertRaisesRegex(
				frappe.ValidationError, "Return Goods Received Notes"
			):
				_validate_grn(doc)

	def test_return_grn_does_not_increment_forward_fabric_tracking(self):
		grn = frappe._dict(
			against="Work Order",
			against_id="WO-TEST",
			is_return=1,
		)
		with patch("frappe.get_cached_doc") as get_cached_doc:
			_apply_grn(grn, 1)
		get_cached_doc.assert_not_called()

	def test_cross_site_cancel_preflights_period_and_valuation_ownership(self):
		doc = frappe._dict(
			doctype="Goods Received Note",
			name="GRN-TEST",
			posting_date="2026-08-24",
		)
		with (
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch(
				"yrp.stock.stock_ledger._validate_sl_entries_period"
			) as validate_period,
			patch(
				"yrp.stock.stock_ledger._lock_voucher_sles_for_cancel"
			) as lock_sles,
			patch(
				"yrp.stock.stock_ledger._validate_no_active_valuation_for_cancel"
			) as validate_ownership,
		):
			_preflight_grn_stock_cancel(doc)

		entry = {
			"voucher_type": "Goods Received Note",
			"voucher_no": "GRN-TEST",
			"posting_date": "2026-08-24",
		}
		validate_period.assert_called_once_with([entry])
		lock_sles.assert_called_once_with([entry], ["lot", "received_type"])
		validate_ownership.assert_called_once_with([entry])

import json
from pathlib import Path
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.work_order import _normalize_generated_uom_rows
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	calculate_cutting_consumption_plan,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel.sd_yrp_recut_and_print_panel import (
	RecutandPrintPanel,
)
from essdee_yrp.fabric_grn import (
	QTY_TOLERANCE,
	_aggregate_rows,
	_allocate_to_work_order_deliverables,
	_resolve_deliverable_source,
	is_calculable_fabric_grn,
)
from essdee_yrp.finishing.packing_grn import (
	_allocate_consumed_garments,
	_calculate_packing_inputs,
)
from essdee_yrp.garment_grn import (
	_find_deliverable,
	_find_receivable,
	_calculate_identity_accessory_plan,
	calculate_stitching_consumption_plan,
)
from essdee_yrp.hooks import override_doctype_class, override_whitelisted_methods
from essdee_yrp.overrides.goods_received_note import (
	EssdeeGoodsReceivedNote,
	_claim_mapped_stock_update_transition,
	_has_complete_mapped_consumption,
	_new_consumption_plan_kind,
	_set_dynamic_packing_piece_uom,
	_validate_mapped_consumption_ownership,
)
from essdee_yrp.patches.backfill_deterministic_valuation_lineage import (
	_has_base_compatible_production_posting_order,
	_get_owned_consumption_sle,
	_resolve_exact_work_order_deliverable,
)
from essdee_yrp.rework_work_order import (
	_subtract_direct_clearing,
	get_rework_source_rows,
)
from essdee_yrp.work_order_hooks import preserve_dynamic_packing_piece_uom
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import GoodsReceivedNote


class TestEssdeeValuationContract(UnitTestCase):
	@patch("essdee_yrp.rework_work_order.get_base_rework_source_rows")
	@patch("essdee_yrp.rework_work_order.frappe.has_permission")
	@patch("essdee_yrp.rework_work_order.frappe.get_doc")
	def test_rework_popup_requires_source_read_and_target_create_permission(
		self, get_doc, has_permission, get_base_rows
	):
		doc = Mock()
		get_doc.return_value = doc
		get_base_rows.return_value = []

		self.assertEqual(get_rework_source_rows("WO-1"), [])

		get_doc.assert_called_once_with('YRP Work Order', "WO-1")
		doc.check_permission.assert_called_once_with("read")
		has_permission.assert_called_once_with('YRP Work Order', "create", throw=True)
		get_base_rows.assert_called_once_with("WO-1")

	@patch("essdee_yrp.rework_work_order.get_base_rework_source_rows")
	@patch(
		"essdee_yrp.rework_work_order.frappe.has_permission",
		side_effect=frappe.PermissionError("Not permitted"),
	)
	@patch("essdee_yrp.rework_work_order.frappe.get_doc")
	def test_rework_popup_does_not_calculate_sources_without_create_permission(
		self, get_doc, _has_permission, get_base_rows
	):
		get_doc.return_value = Mock()

		with self.assertRaises(frappe.PermissionError):
			get_rework_source_rows("WO-1")

		get_base_rows.assert_not_called()

	def test_rework_popup_subtracts_essdee_direct_clearing(self):
		rows = [
			{
				"source_type": 'YRP Goods Received Note Item',
				"source_grn_item": "GRN-ITEM-OPEN",
				"available_qty": 5,
			},
			{
				"source_type": 'YRP Goods Received Note Item',
				"source_grn_item": "GRN-ITEM-COMPLETE",
				"available_qty": 5,
			},
			{
				"source_type": "Inspected GRN Stock",
				"source_grn_item": "GRN-ITEM-OPEN",
				"available_qty": 3,
			},
		]
		direct_rows = [
			frappe._dict(
				source_grn_item="GRN-ITEM-OPEN",
				quantity=5,
				reworked=1,
				completed=0,
			),
			frappe._dict(
				source_grn_item="GRN-ITEM-COMPLETE",
				quantity=5,
				reworked=1,
				completed=1,
			),
		]

		available = _subtract_direct_clearing(rows, direct_rows=direct_rows)

		self.assertEqual(len(available), 2)
		self.assertEqual(available[0]["available_qty"], 4)
		self.assertEqual(available[1]["source_type"], "Inspected GRN Stock")
		self.assertEqual(available[1]["available_qty"], 3)

	def test_rework_popup_api_is_overridden_only_at_the_essdee_boundary(self):
		self.assertEqual(
			override_whitelisted_methods[
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_rework_source_rows"
			],
			"essdee_yrp.rework_work_order.get_rework_source_rows",
		)

	def test_complete_mapped_grn_dispatch_uses_the_real_base_contract(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-1",
				"grn_deliverables": [
					{"goods_received_note_item": "GRN-ITEM-1"}
				],
			}
		)
		self.assertTrue(_has_complete_mapped_consumption(doc))

		doc.against = 'YRP Delivery Challan'
		self.assertFalse(_has_complete_mapped_consumption(doc))

	def test_fully_mapped_lineage_totals_do_not_raise_a_false_readiness_alert(self):
		from essdee_yrp.patches.backfill_deterministic_valuation_lineage import (
			_readiness_needs_review,
		)

		self.assertFalse(
			_readiness_needs_review(
				{
					"submitted_regular_work_order_grn_deliverables": 100,
					"fully_mapped_grn_deliverables": 100,
					"wholly_unmapped_grn_deliverables": 0,
					"partially_mapped_grn_deliverables": 0,
				}
			)
		)
		self.assertTrue(
			_readiness_needs_review(
				{"fully_mapped_grn_deliverables": 99, "partially_mapped_grn_deliverables": 1}
			)
		)

	def test_migration_runs_lineage_backfill_at_the_post_load_boundary(self):
		migration_source = (
			Path(__file__).parent / "migration" / "live.py"
		).read_text()
		self.assertIn('if mode == "migrate":', migration_source)
		self.assertIn(
			'result["valuation_lineage"] = backfill_deterministic_valuation_lineage()',
			migration_source,
		)
		self.assertIn('"backfill_deterministic_valuation_lineage.py"', migration_source)

	def test_historical_backfill_leaves_base_incompatible_f15_order_unmapped(self):
		output = frappe._dict(
			posting_datetime="2025-05-30 11:13:26",
			creation="2025-05-30 11:13:26.100000",
		)
		consumption = frappe._dict(
			posting_datetime="2025-05-30 11:13:26",
			creation="2025-05-30 11:13:26.200000",
		)
		self.assertFalse(
			_has_base_compatible_production_posting_order(output, consumption)
		)

		output.creation = "2025-05-30 11:13:26.300000"
		self.assertTrue(
			_has_base_compatible_production_posting_order(output, consumption)
		)

	def test_new_cutting_laysheet_uses_a_structured_empty_component_payload(self):
		app_path = Path(__file__).parent
		form_source = (
			app_path
			/ "essdee_yrp/doctype/sd_yrp_cutting_laysheet/sd_yrp_cutting_laysheet.js"
		).read_text()
		component_source = (
			app_path / "public/js/CuttingLaySheet/components/LaySheetCloths.vue"
		).read_text()
		self.assertIn(
			"load_data({ manual_items: {}, cloth_items: [] })", form_source
		)
		self.assertIn(
			"item_detail && !Array.isArray(item_detail) ? item_detail : {}",
			component_source,
		)
		self.assertIn("details.manual_items || {}", component_source)
		self.assertIn("details.cloth_items || []", component_source)

	def test_grn_override_is_the_single_new_transaction_controller(self):
		self.assertEqual(
			override_doctype_class['YRP Goods Received Note'],
			"essdee_yrp.overrides.goods_received_note.EssdeeGoodsReceivedNote",
		)

	def test_grn_child_lineage_is_complete_but_historical_links_are_optional(self):
		path = Path(__file__).parent / (
			"essdee_yrp/doctype/sd_yrp_yrp_grn_deliverable/"
			"sd_yrp_yrp_grn_deliverable.json"
		)
		fields = {
			row["fieldname"]: row
			for row in json.loads(path.read_text())["fields"]
		}
		for fieldname in (
			"goods_received_note_item",
			"received_item_variant",
			"material_value",
			"consumption_sle",
			"output_receipt_sle",
			"stock_dimensions",
		):
			self.assertIn(fieldname, fields)
		# Frappe child-table identities cannot be Link targets. Store their exact,
		# immutable child names as hidden Data and validate ownership server-side.
		self.assertEqual(fields["goods_received_note_item"]["fieldtype"], "Data")
		self.assertEqual(fields["work_order_deliverable"]["fieldtype"], "Data")
		self.assertFalse(fields["goods_received_note_item"].get("reqd"))
		self.assertFalse(fields["received_item_variant"].get("reqd"))

	def test_non_mapped_grn_still_runs_all_base_submit_and_cancel_guards(self):
		doc = EssdeeGoodsReceivedNote({"doctype": 'YRP Goods Received Note'})
		with (
			patch("essdee_yrp.overrides.goods_received_note.validate_sewing_plan_quantity"),
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
			patch.object(GoodsReceivedNote, "before_cancel") as base_cancel,
		):
			doc.before_submit()
			doc.before_cancel()

		base_submit.assert_called_once_with()
		base_cancel.assert_called_once_with()

	def test_work_order_lock_precedes_sewing_quantity_preflight(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-SEWING-1",
			}
		)
		events = []
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note._lock_work_order",
				side_effect=lambda _name: events.append("lock"),
			),
			patch(
				"essdee_yrp.overrides.goods_received_note.validate_sewing_plan_quantity",
				side_effect=lambda _doc: events.append("sewing-validation"),
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._new_consumption_plan_kind",
				return_value=None,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._has_complete_mapped_consumption",
				return_value=False,
			),
			patch.object(GoodsReceivedNote, "before_submit"),
		):
			doc.before_submit()

		self.assertEqual(events, ["lock", "sewing-validation"])

	def test_selected_new_planner_cannot_fall_back_with_an_empty_plan(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-1",
				"items": [{"item_variant": "OUTPUT-1", "quantity": 1}],
			}
		)
		with (
			patch("essdee_yrp.overrides.goods_received_note.validate_sewing_plan_quantity"),
			patch(
				"essdee_yrp.overrides.goods_received_note._new_consumption_plan_kind",
				return_value="fabric",
			),
			patch("essdee_yrp.overrides.goods_received_note._lock_work_order"),
			patch(
				"essdee_yrp.overrides.goods_received_note._calculate_new_consumption_plan",
				return_value=[],
			),
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
		):
			with self.assertRaisesRegex(frappe.ValidationError, "No deterministic fabric"):
				doc.before_submit()
		base_submit.assert_not_called()

	def test_cutting_plan_is_selected_before_generic_fabric_planner(self):
		doc = frappe._dict(
			against='YRP Work Order',
			against_id="WO-1",
			cutting_laysheet="CLS-1",
			is_return=0,
			is_rework=0,
			additional_grn=0,
		)
		self.assertEqual(_new_consumption_plan_kind(doc), "cutting")

	def test_identity_garment_grn_is_excluded_from_fabric_draft_planner(self):
		doc = frappe._dict(
			against='YRP Work Order',
			against_id="WO-IDENTITY-1",
			cutting_laysheet=None,
			is_return=0,
			is_rework=0,
			additional_grn=0,
			includes_packing=0,
			flags=frappe._dict(),
		)
		with (
			patch("essdee_yrp.fabric_grn.frappe.db.exists", return_value=True),
			patch(
				"essdee_yrp.garment_grn._is_identity_garment_grn",
				return_value=True,
			),
			patch("essdee_yrp.fabric_grn.frappe.get_cached_doc") as get_work_order,
		):
			self.assertFalse(is_calculable_fabric_grn(doc))
		get_work_order.assert_not_called()

	def test_stitching_plan_is_selected_before_identity_and_fabric(self):
		doc = frappe._dict(
			against='YRP Work Order',
			against_id="WO-STITCH-1",
			cutting_laysheet=None,
			is_return=0,
			is_rework=0,
			additional_grn=0,
			includes_packing=0,
		)
		with (
			patch(
				"essdee_yrp.garment_grn._is_stitching_garment_grn",
				return_value=True,
			),
			patch(
				"essdee_yrp.garment_grn._is_identity_garment_grn"
			) as identity,
		):
			self.assertEqual(_new_consumption_plan_kind(doc), "stitching")
		identity.assert_not_called()

	def test_stitching_garment_grn_is_excluded_from_fabric_draft_planner(self):
		doc = frappe._dict(
			against='YRP Work Order',
			against_id="WO-STITCH-1",
			cutting_laysheet=None,
			is_return=0,
			is_rework=0,
			additional_grn=0,
			includes_packing=0,
			flags=frappe._dict(),
		)
		with (
			patch("essdee_yrp.fabric_grn.frappe.db.exists", return_value=True),
			patch(
				"essdee_yrp.garment_grn._is_identity_garment_grn",
				return_value=False,
			),
			patch(
				"essdee_yrp.garment_grn._is_stitching_garment_grn",
				return_value=True,
			),
			patch("essdee_yrp.fabric_grn.frappe.get_cached_doc") as get_work_order,
		):
			self.assertFalse(is_calculable_fabric_grn(doc))
		get_work_order.assert_not_called()

	def test_stitching_receivable_requires_exact_owned_reference(self):
		receivables = {
			"WO-OUT-1": frappe._dict(
				name="WO-OUT-1",
				item_variant="GARMENT-S",
				uom="Pieces",
				set_combination='{"major_colour":"White"}',
				lot="LOT-1",
				received_type="Accepted",
			)
		}
		received = frappe._dict(
			idx=1,
			ref_doctype='YRP Work Order Receivables',
			ref_docname="WO-OUT-1",
			item_variant="GARMENT-M",
			uom="Pieces",
			set_combination='{"major_colour":"White"}',
			lot="LOT-1",
			received_type="Accepted",
		)
		with self.assertRaisesRegex(
			frappe.ValidationError, "does not match Work Order Receivable"
		):
			_find_receivable(receivables, received, "WO-STITCH-1")

	def test_stitching_receivable_allows_non_default_output_received_type(self):
		source = frappe._dict(
			name="WO-OUT-1",
			item_variant="GARMENT-S",
			uom="Pieces",
			set_combination='{"major_colour":"White"}',
			lot="LOT-1",
			received_type="Accepted",
		)
		received = frappe._dict(
			idx=1,
			ref_doctype='YRP Work Order Receivables',
			ref_docname="WO-OUT-1",
			item_variant="GARMENT-S",
			uom="Pieces",
			set_combination='{"major_colour":"White"}',
			lot="LOT-1",
			received_type="Misstitch",
		)

		self.assertIs(
			_find_receivable({source.name: source}, received, "WO-STITCH-1"),
			source,
		)

	def test_stitching_input_allocation_rejects_ambiguous_business_key(self):
		deliverables = [
			frappe._dict(
				name=f"WO-IN-{index}",
				idx=index,
				item_variant="PANEL-S",
				uom="Pieces",
				qty=10,
				pending_quantity=0,
				stock_update=0,
				is_calculated=1,
				set_combination='{"major_colour":"White"}',
			)
			for index in (1, 2)
		]
		work_order = frappe._dict(name="WO-STITCH-1", deliverables=deliverables)
		grn = frappe._dict(
			from_warehouse="SUPPLIER-WH",
			posting_date="2026-08-27",
			posting_time="12:00:00",
		)
		required = [
			{
				"goods_received_note_item": "GRN-OUT-1",
				"received_item_variant": "GARMENT-S",
				"item_variant": "PANEL-S",
				"qty": 1,
				"uom": "Pieces",
				"set_combination": '{"major_colour":"White"}',
			}
		]
		with (
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Pieces"},
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"essdee_yrp.fabric_reference.get_reference_allocations",
				return_value={},
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "matches 2 Work Order Deliverables"
			):
				_allocate_to_work_order_deliverables(
					required, work_order, grn, exact_business_key=True
				)

	def test_stitching_planner_preserves_each_received_output_identity(self):
		receivable = frappe._dict(
			name="WO-OUT-1",
			item_variant="GARMENT-S",
			uom="Pieces",
			pending_quantity=10,
			table_index=0,
			row_index="matrix-0000",
			set_combination='{"major_colour":"White"}',
			lot="LOT-1",
			received_type="Accepted",
		)
		work_order = frappe._dict(
			name="WO-STITCH-1",
			production_detail="IPD-1",
			lot="LOT-1",
			process_name="Stitching",
			receivables=[receivable],
		)
		received = frappe._dict(
			name="GRN-OUT-1",
			idx=1,
			quantity=4,
			item_variant="GARMENT-S",
			uom="Pieces",
			ref_doctype='YRP Work Order Receivables',
			ref_docname="WO-OUT-1",
			set_combination='{"major_colour":"White"}',
			lot="LOT-1",
			received_type="Accepted",
		)
		grn = frappe._dict(against_id="WO-STITCH-1", items=[received])
		ipd = frappe._dict(name="IPD-1")
		lot = frappe._dict(name="LOT-1")
		with (
			patch(
				"essdee_yrp.garment_grn._is_stitching_garment_grn",
				return_value=True,
			),
			patch("essdee_yrp.garment_grn.frappe.get_doc", return_value=work_order),
			patch(
				"essdee_yrp.garment_grn.frappe.get_cached_doc",
				side_effect=[ipd, lot],
			),
			patch(
				"yrp.utils.get_variant_attr_details",
				return_value={"Size": "S", "Stage": "Piece"},
			),
			patch(
				"essdee_yrp.garment_work_order.calculate_garment_process_rows",
				return_value=(
					[
						{
							"item_variant": "PANEL-S",
							"qty": 8,
							"uom": "Pieces",
							"set_combination": '{"major_colour":"White"}',
						}
					],
					[{"item_variant": "GARMENT-S", "qty": 4}],
				),
			) as calculate_rows,
			patch(
				"essdee_yrp.fabric_grn._allocate_to_work_order_deliverables",
				return_value=[{"mapped": True}],
			) as allocate,
		):
			self.assertEqual(
				calculate_stitching_consumption_plan(grn), [{"mapped": True}]
			)

		demand = calculate_rows.call_args.args[3][0]
		self.assertEqual(demand["item_variant"], "GARMENT-S")
		self.assertEqual(demand["qty"], 4)
		required = allocate.call_args.args[0]
		self.assertEqual(required[0]["goods_received_note_item"], "GRN-OUT-1")
		self.assertEqual(required[0]["received_item_variant"], "GARMENT-S")
		self.assertTrue(allocate.call_args.kwargs["exact_business_key"])

	def test_identity_deliverable_explicit_dimension_mismatch_never_broadens(self):
		deliverables = [
			frappe._dict(
				name="WO-D-1",
				item_variant="PANEL-M",
				uom="Piece",
				set_combination="{}",
				lot="LOT-A",
				received_type="Accepted",
			)
		]
		received = frappe._dict(
			item_variant="PANEL-M",
			uom="Piece",
			set_combination="{}",
			lot="LOT-B",
			received_type="Accepted",
		)

		with self.assertRaisesRegex(
			frappe.ValidationError, "is not a Deliverable"
		):
			_find_deliverable(deliverables, received, "WO-IDENTITY-1")

	def test_identity_accessory_is_mapped_to_its_exact_received_output(self):
		calculated = frappe._dict(
			item_variant="GARMENT-WINE-S",
			quantity=135,
			table_index=0,
			row_index="0",
			set_combination='{"major_colour":"Wine"}',
		)
		receivable = frappe._dict(
			name="WO-OUT-BACK-S",
			item_variant="PANEL-BACK-WINE-S",
			uom="Pieces",
			table_index=0,
			set_combination='{"major_colour":"Wine"}',
			lot="LOT-1",
		)
		work_order = frappe._dict(
			name="WO-YOLK-1",
			item="GARMENT",
			production_detail="IPD-1",
			lot="LOT-1",
			process_name="Yolk Fusing",
			work_order_calculated_items=[calculated],
			receivables=[receivable],
			deliverables=[
				frappe._dict(
					item_variant="PANEL-BACK-WINE-S", is_calculated=1
				),
				frappe._dict(item_variant="FUSING-STICKER-S", is_calculated=1),
			],
		)
		received = frappe._dict(
			name="GRN-OUT-1",
			idx=1,
			item_variant="PANEL-BACK-WINE-S",
			quantity=135,
			uom="Pieces",
			ref_doctype='YRP Work Order Receivables',
			ref_docname=receivable.name,
			set_combination='{"major_colour":"Wine"}',
			lot="LOT-1",
		)
		grn = frappe._dict(items=[received])
		with (
			patch(
				"essdee_yrp.garment_grn.frappe.db.get_value",
				side_effect=lambda doctype, name, field: {
					"PANEL-BACK-WINE-S": "GARMENT",
					"FUSING-STICKER-S": "FUSING-STICKER",
				}[name],
			),
			patch("essdee_yrp.garment_grn.frappe.get_cached_doc") as get_doc,
			patch(
				"yrp.utils.get_variant_attr_details",
				return_value={"Colour": "Wine", "Size": "S", "Stage": "Piece"},
			),
			patch(
				"essdee_yrp.garment_work_order.calculate_garment_process_rows",
				return_value=(
					[
						{"item_variant": "PANEL-BACK-WINE-S", "qty": 135, "uom": "Pieces"},
						{"item_variant": "FUSING-STICKER-S", "qty": 135, "uom": "Nos", "set_combination": "{}"},
					],
					[
						{
							"item_variant": "PANEL-BACK-WINE-S",
							"qty": 135,
							"uom": "Pieces",
							"table_index": 0,
							"set_combination": '{"major_colour":"Wine"}',
						}
					],
				),
			),
			patch(
				"essdee_yrp.fabric_grn._allocate_to_work_order_deliverables",
				return_value=[{"mapped": "sticker"}],
			) as allocate,
		):
			get_doc.side_effect = [frappe._dict(name="IPD-1"), frappe._dict(name="LOT-1")]
			self.assertEqual(
				_calculate_identity_accessory_plan(grn, work_order),
				[{"mapped": "sticker"}],
			)

		required = allocate.call_args.args[0]
		self.assertEqual(len(required), 1)
		self.assertEqual(required[0]["item_variant"], "FUSING-STICKER-S")
		self.assertEqual(required[0]["qty"], 135)
		self.assertEqual(required[0]["goods_received_note_item"], "GRN-OUT-1")
		self.assertTrue(allocate.call_args.kwargs["exact_business_key"])

	def test_identity_accessory_is_apportioned_across_process_outputs(self):
		calculated = frappe._dict(
			item_variant="GARMENT-S",
			quantity=100,
			table_index=0,
			row_index="0",
			set_combination="{}",
		)
		receivable = frappe._dict(
			name="WO-OUT-FRONT",
			item_variant="PANEL-FRONT-S",
			uom="Pieces",
			table_index=0,
			set_combination="{}",
			lot="LOT-1",
		)
		work_order = frappe._dict(
			name="WO-PRINT-1",
			item="GARMENT",
			production_detail="IPD-1",
			lot="LOT-1",
			process_name="Printing",
			work_order_calculated_items=[calculated],
			receivables=[receivable],
			deliverables=[
				frappe._dict(item_variant="PANEL-FRONT-S", is_calculated=1),
				frappe._dict(item_variant="INK-S", is_calculated=1),
			],
		)
		grn = frappe._dict(
			items=[
				frappe._dict(
					name="GRN-OUT-1",
					idx=1,
					item_variant="PANEL-FRONT-S",
					quantity=50,
					uom="Pieces",
					ref_doctype='YRP Work Order Receivables',
					ref_docname=receivable.name,
					set_combination="{}",
					lot="LOT-1",
				)
			]
		)
		with (
			patch(
				"essdee_yrp.garment_grn.frappe.db.get_value",
				side_effect=lambda doctype, name, field: (
					"GARMENT" if name.startswith("PANEL-") else "INK"
				),
			),
			patch(
				"essdee_yrp.garment_grn.frappe.get_cached_doc",
				side_effect=[frappe._dict(name="IPD-1"), frappe._dict(name="LOT-1")],
			),
			patch("yrp.utils.get_variant_attr_details", return_value={"Size": "S"}),
			patch(
				"essdee_yrp.garment_work_order.calculate_garment_process_rows",
				return_value=(
					[
						{"item_variant": "PANEL-FRONT-S", "qty": 100, "uom": "Pieces"},
						{"item_variant": "PANEL-BACK-S", "qty": 100, "uom": "Pieces"},
						{"item_variant": "INK-S", "qty": 20, "uom": "Nos", "set_combination": "{}"},
					],
					[
						{"item_variant": "PANEL-FRONT-S", "qty": 100, "table_index": 0, "set_combination": "{}"},
						{"item_variant": "PANEL-BACK-S", "qty": 100, "table_index": 0, "set_combination": "{}"},
					],
				),
			),
			patch(
				"essdee_yrp.fabric_grn._allocate_to_work_order_deliverables",
				return_value=[{"mapped": "ink"}],
			) as allocate,
		):
			_calculate_identity_accessory_plan(grn, work_order)

		self.assertEqual(allocate.call_args.args[0][0]["qty"], 5)

	def test_manual_identity_output_does_not_infer_unrelated_calculated_accessory(self):
		work_order = frappe._dict(
			name="WO-MANUAL-1",
			item="GARMENT",
			production_detail="IPD-1",
			lot="LOT-1",
			process_name="Yolk Fusing",
			work_order_calculated_items=[
				frappe._dict(
					item_variant="GARMENT-BACK-S",
					quantity=10,
					table_index=1,
					set_combination="{}",
				)
			],
			receivables=[
				frappe._dict(
					name="WO-OUT-MANUAL",
					item_variant="PANEL-FRONT-S",
					table_index=1,
					set_combination="{}",
				)
			],
			deliverables=[
				frappe._dict(item_variant="PANEL-FRONT-S", is_calculated=0),
				frappe._dict(item_variant="STICKER-S", is_calculated=1),
			],
		)
		grn = frappe._dict(
			items=[
				frappe._dict(
					name="GRN-OUT-MANUAL",
					idx=1,
					item_variant="PANEL-FRONT-S",
					quantity=10,
					ref_doctype='YRP Work Order Receivables',
					ref_docname="WO-OUT-MANUAL",
					set_combination="{}",
				)
			]
		)
		with (
			patch(
				"essdee_yrp.garment_grn.frappe.db.get_value",
				side_effect=lambda doctype, name, field: (
					"GARMENT" if name == "PANEL-FRONT-S" else "STICKER"
				),
			),
			patch(
				"essdee_yrp.garment_grn.frappe.get_cached_doc",
				side_effect=[frappe._dict(name="IPD-1"), frappe._dict(name="LOT-1")],
			),
			patch("yrp.utils.get_variant_attr_details", return_value={"Size": "S"}),
			patch(
				"essdee_yrp.garment_work_order.calculate_garment_process_rows",
				return_value=(
					[
						{"item_variant": "PANEL-BACK-S", "qty": 10},
						{"item_variant": "STICKER-S", "qty": 10},
					],
					[
						{
							"item_variant": "PANEL-BACK-S",
							"qty": 10,
							"table_index": 1,
							"set_combination": "{}",
						}
					],
				),
			),
		):
			self.assertEqual(
				_calculate_identity_accessory_plan(grn, work_order), []
			)

	def test_identity_output_with_no_accessory_keeps_its_empty_route(self):
		calculated = frappe._dict(
			item_variant="GARMENT-M",
			quantity=10,
			table_index=1,
			row_index="1",
			set_combination="{}",
		)
		receivable = frappe._dict(
			name="WO-OUT-M",
			item_variant="PANEL-M",
			uom="Pieces",
			table_index=1,
			set_combination="{}",
			lot="LOT-1",
		)
		work_order = frappe._dict(
			name="WO-EMB-1",
			item="GARMENT",
			production_detail="IPD-1",
			lot="LOT-1",
			process_name="Embellishment",
			work_order_calculated_items=[calculated],
			receivables=[receivable],
			deliverables=[
				frappe._dict(item_variant="PANEL-M", is_calculated=1),
				# A different demand in this Work Order owns this calculated
				# accessory; the current M route legitimately does not.
				frappe._dict(item_variant="ACCESSORY-S", is_calculated=1),
			],
		)
		grn = frappe._dict(
			items=[
				frappe._dict(
					name="GRN-OUT-M",
					idx=1,
					item_variant="PANEL-M",
					quantity=10,
					uom="Pieces",
					ref_doctype='YRP Work Order Receivables',
					ref_docname=receivable.name,
					set_combination="{}",
					lot="LOT-1",
				)
			]
		)
		with (
			patch(
				"essdee_yrp.garment_grn.frappe.db.get_value",
				side_effect=lambda doctype, name, field: (
					"GARMENT" if name == "PANEL-M" else "ACCESSORY"
				),
			),
			patch(
				"essdee_yrp.garment_grn.frappe.get_cached_doc",
				side_effect=[frappe._dict(name="IPD-1"), frappe._dict(name="LOT-1")],
			),
			patch("yrp.utils.get_variant_attr_details", return_value={"Size": "M"}),
			patch(
				"essdee_yrp.garment_work_order.calculate_garment_process_rows",
				return_value=(
					[{"item_variant": "PANEL-M", "qty": 10, "uom": "Pieces"}],
					[{"item_variant": "PANEL-M", "qty": 10, "table_index": 1, "set_combination": "{}"}],
				),
			),
		):
			self.assertEqual(
				_calculate_identity_accessory_plan(grn, work_order), []
			)

	def test_closed_sewing_receipt_keeps_its_specialized_stock_only_route(self):
		doc = frappe._dict(
			against='YRP Work Order',
			against_id="WO-1",
			from_closed_wo_sewing_details=1,
			is_return=0,
			is_rework=0,
			additional_grn=0,
		)
		self.assertIsNone(_new_consumption_plan_kind(doc))

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

	def test_generated_rows_preserve_physical_quantity_when_uom_changes(self):
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
		self.assertEqual(QTY_TOLERANCE, 0.000001)

	def test_recut_uses_stock_uom_rate_when_transaction_uom_differs(self):
		doc = RecutandPrintPanel(
			{
				"doctype": 'SD YRP Recut and Print Panel',
				"lot": "LOT-1",
				"supplier": "CUTTING-UNIT",
				"posting_date": "2026-08-26",
				"posting_time": "18:00:00",
				"recut_and_print_panel_details": [
					{
						"cloth_type": "MAIN",
						"dia": "60 Dia",
						"colour": "Red",
						"weight": 2,
					}
				],
			}
		)
		with (
			patch.object(doc, "_cloth_templates", return_value=("Colour", {"MAIN": "CLOTH"})),
			patch.object(doc, "_warehouse", return_value="CUT-WH"),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel.sd_yrp_recut_and_print_panel.get_or_create_variant",
				return_value="CLOTH-RED-60",
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel.sd_yrp_recut_and_print_panel.resolve_item_uom",
				return_value=frappe._dict(
					uom="Roll", stock_uom="Kg", conversion_factor=10
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel.sd_yrp_recut_and_print_panel.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch.object(
				frappe.db, "get_single_value", return_value="Accepted"
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel.sd_yrp_recut_and_print_panel.get_stock_balance",
				return_value=(20, 7),
			) as balance,
		):
			doc._set_cloth_variants_and_rates()

		row = doc.recut_and_print_panel_details[0]
		self.assertEqual(row.uom, "Roll")
		self.assertEqual(row.stock_uom, "Kg")
		self.assertEqual(row.rate, 7)
		self.assertNotIn("uom", balance.call_args.kwargs)

	def test_only_explicit_finishing_no_dc_return_uses_specialized_route(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-1",
				"is_return": 1,
				"from_finishing": 1,
			}
		)
		self.assertTrue(doc._is_essdee_return())
		doc.from_finishing = 0
		self.assertFalse(doc._is_essdee_return())

	def test_cutting_plan_conserves_each_input_across_exact_outputs(self):
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(
					name="WO-INPUT-1",
					item_variant="CLOTH-1",
					uom="Kg",
					qty=5,
					pending_quantity=0,
					stock_update=0,
					is_calculated=1,
					valuation_rate=0,
					rate=0,
				)
			],
		)
		grn = frappe._dict(
			cutting_laysheet="CLS-1",
			against_id="WO-1",
			from_warehouse="CUT-WH",
			posting_date="2026-08-25",
			posting_time="17:00:00",
			items=[
				frappe._dict(
					name="OUT-1",
					item_variant="PANEL-RED",
					stock_qty=1,
					quantity=1,
					set_combination="{}",
				),
				frappe._dict(
					name="OUT-2",
					item_variant="PANEL-BLUE",
					stock_qty=2,
					quantity=2,
					set_combination="{}",
				),
			],
		)
		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.get_doc",
				side_effect=lambda doctype, _name: (
					frappe._dict(name="CLS-1", cutting_plan="CP-1")
					if doctype == 'SD YRP Cutting LaySheet'
					else work_order
				),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.db.get_value",
				return_value="WO-1",
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet._cutting_grn_consumed_rows",
				return_value=[{"item_variant": "CLOTH-1", "uom": "Kg", "qty": 1}],
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Kg"},
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"yrp.stock.utils.get_stock_balance",
				return_value=(5, 20),
			),
		):
			plan = calculate_cutting_consumption_plan(grn)
			work_order.deliverables[0].pending_quantity = 5
			with self.assertRaisesRegex(
				frappe.ValidationError, "only 0.0 available for cutting input"
			):
				calculate_cutting_consumption_plan(grn)
			work_order.deliverables[0].pending_quantity = 0
			work_order.deliverables.append(
				frappe._dict(
					name="WO-INPUT-2",
					item_variant="CLOTH-1",
					uom="Kg",
					qty=5,
					pending_quantity=0,
					stock_update=0,
					is_calculated=1,
				)
			)
			with self.assertRaisesRegex(
				frappe.ValidationError, "matches multiple calculated Deliverables"
			):
				calculate_cutting_consumption_plan(grn)

		self.assertEqual(len(plan), 2)
		self.assertEqual(
			{row["goods_received_note_item"] for row in plan}, {"OUT-1", "OUT-2"}
		)
		self.assertTrue(all(row["work_order_deliverable"] == "WO-INPUT-1" for row in plan))
		self.assertAlmostEqual(sum(row["stock_qty"] for row in plan), 1, places=12)
		self.assertAlmostEqual(plan[0]["stock_qty"], 1 / 3, places=12)
		self.assertAlmostEqual(plan[1]["stock_qty"], 2 / 3, places=12)

	def test_cutting_plan_rejects_laysheet_from_a_different_work_order(self):
		grn = frappe._dict(
			cutting_laysheet="CLS-1",
			against_id="WO-EXPECTED",
		)
		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.get_doc",
				return_value=frappe._dict(name="CLS-1", cutting_plan="CP-1"),
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.db.get_value",
				return_value="WO-OTHER",
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "not GRN Work Order WO-EXPECTED"
			):
				calculate_cutting_consumption_plan(grn)

	def test_mapped_submit_and_cancel_apply_the_same_persisted_plan(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-1",
			}
		)
		plan = [{"work_order_deliverable": "WO-INPUT-1", "quantity": 2}]
		with (
			patch("essdee_yrp.overrides.goods_received_note.validate_sewing_plan_quantity"),
			patch(
				"essdee_yrp.overrides.goods_received_note._new_consumption_plan_kind",
				return_value="fabric",
			),
			patch("essdee_yrp.overrides.goods_received_note._lock_work_order") as lock,
			patch(
				"essdee_yrp.overrides.goods_received_note._calculate_new_consumption_plan",
				return_value=plan,
			),
			patch("essdee_yrp.fabric_grn.populate_grn_deliverables"),
			patch.object(GoodsReceivedNote, "before_submit") as base_submit,
		):
			doc.before_submit()

		lock.assert_called_once_with("WO-1")
		base_submit.assert_called_once_with()
		self.assertIs(doc.flags.essdee_mapped_consumption, plan)

		with (
			patch.object(GoodsReceivedNote, "on_submit") as base_submit_action,
			patch(
				"essdee_yrp.overrides.goods_received_note._claim_mapped_stock_update_transition",
				return_value=True,
			),
			patch("essdee_yrp.fabric_grn.apply_work_order_stock_update") as apply,
			patch.object(doc, "_enqueue_repost_if_mapped") as enqueue,
		):
			doc.on_submit()
		base_submit_action.assert_called_once_with()
		apply.assert_called_once_with("WO-1", plan)
		enqueue.assert_called_once_with()

		persisted_plan = [{"work_order_deliverable": "WO-INPUT-1", "quantity": 2}]
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note._has_complete_mapped_consumption",
				return_value=True,
			),
			patch("essdee_yrp.overrides.goods_received_note._lock_work_order"),
			patch(
				"essdee_yrp.overrides.goods_received_note._validate_mapped_consumption_ownership"
			) as validate_ownership,
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.db.get_value",
				return_value="Open",
			),
			patch(
				"essdee_yrp.fabric_grn.load_submitted_consumption_plan",
				return_value=persisted_plan,
			),
			patch.object(GoodsReceivedNote, "before_cancel") as base_cancel,
		):
			doc.before_cancel()
			base_cancel.assert_called_once_with()
			validate_ownership.assert_called_once_with(doc)
			self.assertIs(doc.flags.essdee_mapped_consumption, persisted_plan)

		with (
			patch.object(GoodsReceivedNote, "on_cancel") as base_cancel_action,
			patch(
				"essdee_yrp.overrides.goods_received_note._claim_mapped_stock_update_transition",
				return_value=True,
			),
			patch("essdee_yrp.fabric_grn.apply_work_order_stock_update") as apply,
			patch.object(doc, "_enqueue_repost_if_mapped") as enqueue,
		):
			doc.on_cancel()
		base_cancel_action.assert_called_once_with()
		apply.assert_called_once_with("WO-1", persisted_plan, cancel=True)
		enqueue.assert_called_once_with()

	def test_mapped_submit_retry_skips_base_and_work_order_side_effects(self):
		doc = EssdeeGoodsReceivedNote(
			{"doctype": 'YRP Goods Received Note', "against_id": "WO-1"}
		)
		doc.flags.essdee_mapped_consumption = [
			{"work_order_deliverable": "WO-D-1", "quantity": 1}
		]
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note._claim_mapped_stock_update_transition",
				return_value=False,
			),
			patch.object(GoodsReceivedNote, "on_submit") as base_submit,
			patch("essdee_yrp.fabric_grn.apply_work_order_stock_update") as apply,
		):
			doc.on_submit()

		base_submit.assert_not_called()
		apply.assert_not_called()

	def test_historical_mapped_state_zero_reverses_imported_work_order_counter(self):
		doc = EssdeeGoodsReceivedNote(
			{"doctype": 'YRP Goods Received Note', "name": "GRN-OLD", "against_id": "WO-1"}
		)
		doc.flags.essdee_mapped_consumption = [
			{"work_order_deliverable": "WO-D-1", "quantity": 1}
		]
		with (
			patch.object(frappe.db, "get_value", return_value=0),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(GoodsReceivedNote, "on_cancel") as base_cancel,
			patch("essdee_yrp.fabric_grn.apply_work_order_stock_update") as apply,
			patch.object(doc, "_enqueue_repost_if_mapped"),
		):
			doc.on_cancel()

		base_cancel.assert_called_once_with()
		apply.assert_called_once_with(
			"WO-1", doc.flags.essdee_mapped_consumption, cancel=True
		)
		set_value.assert_called_once_with(
			'YRP Goods Received Note',
			"GRN-OLD",
			"mapped_stock_update_state",
			-1,
			update_modified=False,
		)
		self.assertEqual(doc.mapped_stock_update_state, -1)

	def test_mapped_transition_state_contract(self):
		doc = frappe._dict(
			doctype='YRP Goods Received Note',
			name="GRN-STATE",
			mapped_stock_update_state=0,
		)
		cases = (
			(0, 1, True, True),
			(1, 1, False, False),
			(1, -1, True, True),
			(0, -1, True, True),
			(-1, -1, False, False),
		)
		for current, target, expected, writes in cases:
			with self.subTest(current=current, target=target):
				with (
					patch.object(frappe.db, "get_value", return_value=current),
					patch.object(frappe.db, "set_value") as set_value,
				):
					result = _claim_mapped_stock_update_transition(
						doc, target_state=target
					)
				self.assertEqual(result, expected)
				self.assertEqual(set_value.called, writes)

	def test_mapped_ownership_rejects_work_order_child_from_another_parent(self):
		output = frappe._dict(
			name="GRN-I-1", item_variant="OUTPUT-M", quantity=1, stock_qty=1
		)
		mapped = frappe._dict(
			idx=1,
			goods_received_note_item=output.name,
			received_item_variant=output.item_variant,
			work_order_deliverable="OTHER-WO-D-1",
			item_variant="INPUT-M",
			uom="Piece",
			stock_uom="Piece",
			quantity=1,
			stock_qty=1,
			conversion_factor=1,
			stock_dimensions='{"lot":"LOT-1","received_type":"Accepted"}',
			lot="LOT-1",
			received_type="Accepted",
		)
		grn = frappe._dict(
			against_id="WO-1", items=[output], grn_deliverables=[mapped]
		)
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(
					name="WO-D-1", item_variant="INPUT-M", uom="Piece"
				)
			],
		)
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_doc",
				return_value=work_order,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "not linked to a Deliverable owned"
			):
				_validate_mapped_consumption_ownership(grn)

	def test_direct_finishing_return_resolves_both_real_warehouses(self):
		doc = EssdeeGoodsReceivedNote(
			{
				"doctype": 'YRP Goods Received Note',
				"against": 'YRP Work Order',
				"against_id": "WO-1",
				"is_return": 1,
				"from_finishing": 1,
				"supplier": "FINISHING-UNIT",
				"delivery_location": "REWORK-UNIT",
			}
		)
		work_order = frappe._dict(
			process_name="Ironing and Packing",
			item="GARMENT",
			production_detail="IPD-1",
		)
		with (
			patch.object(GoodsReceivedNote, "set_missing_values"),
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_cached_doc",
				return_value=work_order,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._get_warehouse_for_supplier",
				side_effect=["FINISHING-WH", "REWORK-WH"],
			),
		):
			doc.set_missing_values()

		self.assertEqual(doc.from_warehouse, "FINISHING-WH")
		self.assertEqual(doc.to_warehouse, "REWORK-WH")
		self.assertEqual(doc.freight_charges, 0)

	def test_packing_plan_uses_all_configured_stock_dimensions(self):
		source = frappe._dict(
			name="WO-INPUT-1",
			item_variant="PANEL-M",
			uom="Box",
			set_combination="{}",
		)
		calculated = frappe._dict(
			name="CALC-1",
			idx=1,
			item_variant="PANEL-M",
			set_combination="{}",
			delivered_quantity=20,
			received_qty=0,
		)
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[source],
			work_order_calculated_items=[calculated],
		)
		grn = frappe._dict(
			from_warehouse="PACK-WH",
			posting_date="2026-08-25",
			posting_time="17:00:00",
			items=[
				frappe._dict(
					name="OUT-1",
					item_variant="PACK-M",
					stock_qty=20,
				)
			],
		)
		ipd = frappe._dict(primary_item_attribute="Size", is_set_item=0)
		dimensions = {
			"lot": "LOT-1",
			"received_type": "Accepted",
			"quality_grade": "A",
		}
		with (
			patch(
				"essdee_yrp.finishing.packing_grn.get_variant_attr_details",
				return_value={"Size": "M"},
			),
			patch(
				"essdee_yrp.finishing.packing_grn._find_deliverable",
				return_value=source,
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value=dimensions,
			),
			patch(
				"essdee_yrp.finishing.packing_grn.get_stock_balance",
				return_value=(20, 30),
			) as stock_balance,
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={
					"stock_uom": "Piece",
					"conversion_factor": 10,
				},
			),
		):
			plan = _allocate_consumed_garments(grn, work_order, ipd)

		stock_balance.assert_called_once_with(
			"PANEL-M",
			"PACK-WH",
			posting_date="2026-08-25",
			posting_time="17:00:00",
			with_valuation_rate=True,
			**dimensions,
		)
		self.assertEqual(plan[0]["dimensions"], dimensions)
		self.assertEqual(plan[0]["quantity"], 2)
		self.assertEqual(plan[0]["stock_qty"], 20)
		self.assertEqual(plan[0]["uom"], "Box")
		self.assertEqual(plan[0]["stock_uom"], "Piece")
		self.assertEqual(plan[0]["conversion_factor"], 10)

	def test_dynamic_packing_maps_garments_and_exact_bom_accessories(self):
		garment_s = frappe._dict(
			name="WO-GARMENT-S",
			item_variant="GARMENT-S-WHITE-TOP",
			uom="Pieces",
			qty=10,
			pending_quantity=0,
			stock_update=0,
			set_combination='{"major_colour":"White","major_part":"Top"}',
		)
		garment_m = frappe._dict(
			name="WO-GARMENT-M",
			item_variant="GARMENT-M-WHITE-TOP",
			uom="Pieces",
			qty=10,
			pending_quantity=0,
			stock_update=0,
			set_combination='{"major_colour":"White","major_part":"Top"}',
		)
		calculated_s = frappe._dict(
			name="CALC-S",
			idx=1,
			item_variant=garment_s.item_variant,
			set_combination=garment_s.set_combination,
			delivered_quantity=10,
			received_qty=0,
		)
		calculated_m = frappe._dict(
			name="CALC-M",
			idx=2,
			item_variant=garment_m.item_variant,
			set_combination=garment_m.set_combination,
			delivered_quantity=10,
			received_qty=0,
		)
		work_order = frappe._dict(
			name="WO-1",
			lot="LOT-1",
			process_name="Ironing and Packing",
			deliverables=[garment_s, garment_m],
			work_order_calculated_items=[calculated_s, calculated_m],
		)
		output_s = frappe._dict(
			name="OUT-S", item_variant="PACK-S", quantity=2, stock_qty=2
		)
		output_m = frappe._dict(
			name="OUT-M", item_variant="PACK-M", quantity=3, stock_qty=3
		)
		grn = frappe._dict(
			against='YRP Work Order',
			against_id=work_order.name,
			includes_packing=1,
			packing_calculation_version=2,
			lot="LOT-1",
			from_warehouse="PACK-WH",
			posting_date="2026-08-27",
			posting_time="18:00:00",
			items=[output_s, output_m],
			packing_batches=[
				frappe._dict(
					colour="White",
					box_quantity=1,
					ratio_json='{"S":2,"M":3}',
				)
			],
		)
		ipd = frappe._dict(
			name="IPD-1",
			primary_item_attribute="Size",
			packing_attribute="Colour",
			set_item_attribute="Part",
			is_set_item=1,
		)
		variant_attributes = {
			"GARMENT-S-WHITE-TOP": {"Size": "S", "Colour": "White", "Part": "Top"},
			"GARMENT-M-WHITE-TOP": {"Size": "M", "Colour": "White", "Part": "Top"},
			"PACK-S": {"Size": "S"},
			"PACK-M": {"Size": "M"},
		}
		accessory_requirements = [
			{
				"item_variant": "SIZE-TAG-S",
				"required_qty": 2,
				"uom": "Nos",
				"attrs": {"Size": "S"},
			},
			{
				"item_variant": "CARTON",
				"required_qty": 1,
				"uom": "Nos",
				"attrs": {},
			},
		]
		mapped_accessories = [{"item_variant": "ACCESSORY-MAPPED"}]
		with (
			patch(
				"essdee_yrp.finishing.packing_grn.get_variant_attr_details",
				side_effect=lambda variant: variant_attributes[variant],
			),
			patch(
				"essdee_yrp.finishing.packing_grn._find_deliverable",
				side_effect=[garment_s, garment_m],
			),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"stock_uom": "Pieces", "conversion_factor": 1},
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
			patch(
				"essdee_yrp.finishing.packing_grn.get_stock_balance",
				return_value=(10, 25),
			),
			patch(
				"essdee_yrp.finishing.packing_grn.frappe.get_cached_doc",
				return_value=frappe._dict(name="LOT-1"),
			),
			patch(
				"essdee_yrp.finishing.packing_grn.frappe.db.get_value",
				return_value=0,
			),
			patch(
				"essdee_yrp.finishing.packing_grn.calculate_essdee_accessory_bom",
				return_value=accessory_requirements,
			) as calculate_accessories,
			patch(
				"essdee_yrp.finishing.packing_grn._allocate_to_work_order_deliverables",
				return_value=mapped_accessories,
			) as allocate_accessories,
		):
			plan = _calculate_packing_inputs(grn, work_order, ipd)

		self.assertEqual(
			[(row["item_variant"], row["stock_qty"]) for row in plan[:2]],
			[(garment_s.item_variant, 2), (garment_m.item_variant, 3)],
		)
		self.assertEqual(plan[2:], mapped_accessories)
		self.assertEqual(
			calculate_accessories.call_args.args[1],
			[
				{"item_variant": garment_s.item_variant, "qty": 2},
				{"item_variant": garment_m.item_variant, "qty": 3},
			],
		)
		required = allocate_accessories.call_args.args[0]
		self.assertEqual(required[0]["goods_received_note_item"], output_s.name)
		self.assertEqual(required[0]["qty"], 2)
		self.assertEqual(required[1]["goods_received_note_item"], output_s.name)
		self.assertEqual(required[1]["qty"], 0.4)
		self.assertEqual(required[2]["goods_received_note_item"], output_m.name)
		self.assertEqual(required[2]["qty"], 0.6)
		self.assertEqual(_new_consumption_plan_kind(grn), "packing")

	def test_dynamic_packing_output_uses_physical_piece_uom(self):
		row = frappe._dict(
			item_variant="PACK-S",
			quantity=4,
			uom="Box",
			stock_uom="Pieces",
			conversion_factor=1,
			stock_qty=4,
			rate=175,
			amount=700,
		)
		grn = frappe._dict(
			lot="LOT-1",
			packing_calculation_version=2,
			items=[row],
		)
		with patch(
			"essdee_yrp.overrides.goods_received_note.frappe.db.get_value",
			return_value="Pieces",
		):
			_set_dynamic_packing_piece_uom(grn)

		self.assertEqual(row.uom, "Pieces")
		self.assertEqual(row.stock_uom, "Pieces")
		self.assertEqual(row.conversion_factor, 1)
		self.assertEqual(row.stock_qty, 4)
		self.assertEqual(row.amount, 700)

	def test_new_dynamic_packing_work_order_receivable_uses_piece_uom(self):
		packing_output = frappe._dict(item_variant="PACK-S", uom="Box")
		unrelated = frappe._dict(item_variant="CARTON", uom="Nos")
		work_order = frappe._dict(
			production_detail="IPD-1",
			lot="LOT-1",
			includes_packing=1,
			receivables=[packing_output, unrelated],
		)
		ipd = frappe._dict(
			item="GARMENT",
			based_on_other_attribute_mapping=1,
			packing_mode="Size Ratio Packing",
		)

		def get_value(doctype, name, fieldname):
			if doctype == 'SD YRP Lot':
				return "Pieces"
			if doctype == 'YRP Item Variant':
				return {"PACK-S": "GARMENT", "CARTON": "CARTON"}[name]
			raise AssertionError((doctype, name, fieldname))

		with (
			patch(
				"essdee_yrp.work_order_hooks.frappe.get_cached_doc",
				return_value=ipd,
			),
			patch(
				"essdee_yrp.work_order_hooks.frappe.db.get_value",
				side_effect=get_value,
			),
		):
			preserve_dynamic_packing_piece_uom(work_order)

		self.assertEqual(packing_output.uom, "Pieces")
		self.assertEqual(unrelated.uom, "Nos")

	def test_historical_backfill_requires_one_exact_work_order_input(self):
		child = frappe._dict(
			item_variant="CLOTH-1",
			uom="Kg",
			set_combination="{}",
			stock_dimensions='{"lot":"LOT-1","quality_grade":"A"}',
			lot="LOT-1",
			quality_grade="A",
		)
		rows = [
			frappe._dict(
				name="WO-INPUT-A",
				uom="Kg",
				set_combination="{}",
				lot="LOT-1",
				quality_grade="A",
			),
			frappe._dict(
				name="WO-INPUT-B",
				uom="Kg",
				set_combination="{}",
				lot="LOT-1",
				quality_grade="B",
			),
		]
		with patch(
			"essdee_yrp.patches.backfill_deterministic_valuation_lineage.frappe.get_all",
			return_value=rows,
		) as get_all:
			resolved = _resolve_exact_work_order_deliverable(
				"WO-1", child, ["lot", "quality_grade"]
			)
		self.assertEqual(resolved, "WO-INPUT-A")
		self.assertEqual(get_all.call_args.kwargs["limit_page_length"], 0)

		child.quality_grade = None
		child.stock_dimensions = '{"lot":"LOT-1"}'
		with patch(
			"essdee_yrp.patches.backfill_deterministic_valuation_lineage.frappe.get_all",
			return_value=rows,
		):
			resolved = _resolve_exact_work_order_deliverable(
				"WO-1", child, ["lot", "quality_grade"]
			)
		self.assertIsNone(resolved)

	def test_historical_backfill_accepts_only_the_exact_owned_consumption_sle(self):
		child = frappe._dict(
			name="GRN-DEL-1",
			item_variant="INPUT-1",
			consumption_sle="SLE-CLAIMED",
		)
		with patch.object(frappe, "get_all", return_value=[]) as get_all:
			self.assertIsNone(
				_get_owned_consumption_sle("GRN-1", child, ["lot", "received_type"])
			)

		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["name"], "SLE-CLAIMED")
		self.assertEqual(filters["voucher_type"], 'YRP Goods Received Note')
		self.assertEqual(filters["voucher_no"], "GRN-1")
		self.assertEqual(filters["voucher_detail_no"], "GRN-DEL-1")
		self.assertEqual(filters["item"], "INPUT-1")
		self.assertEqual(filters["qty"], ["<", 0])
		self.assertEqual(filters["is_cancelled"], 0)

	def test_legacy_grn_saved_work_order_link_cannot_contradict_its_input(self):
		source = frappe._dict(
			name="WO-D-1",
			item_variant="INPUT-OTHER",
			uom="Kg",
			set_combination="{}",
			lot="LOT-1",
			received_type="Accepted",
		)
		row = frappe._dict(
			item_variant="INPUT-EXPECTED",
			uom="Kg",
			work_order_deliverable=source.name,
			set_combination="{}",
			stock_dimensions='{"lot":"LOT-1","received_type":"Accepted"}',
		)
		work_order = frappe._dict(
			name="WO-1", lot="LOT-1", received_type="Accepted"
		)
		with (
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "LOT-1", "received_type": "Accepted"},
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError, "does not match linked Work Order Deliverable"
			):
				_resolve_deliverable_source(row, {source.name: source}, work_order)

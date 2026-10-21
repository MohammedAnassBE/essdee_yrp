import unittest
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.garment_grn import (
	_apply_calculated_receivable_quantities,
	_include_calculated_receivable_rows,
)
from essdee_yrp.garment_grn import (
	before_validate as calculate_garment_consumption,
)
from essdee_yrp.overrides.goods_received_note import (
	_only_default_received_type,
	_selected_draft_receivable_rows,
	aggregate_packing_grn_rows_for_ui,
	get_sewing_plan_remaining_quantities,
	get_work_order_defaults,
	normalize_cutting_grn_row_indexes,
	validate_sewing_plan_quantity,
)


class TestSewingPlanReceiptQuantities(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch("frappe.get_system_settings", return_value="Banker's Rounding (legacy)"))
		self.enterContext(
			patch("essdee_yrp.overrides.goods_received_note._", side_effect=lambda message: message)
		)

	def test_remaining_quantities_include_returns_and_exclude_current_grn(self):
		with patch("frappe.db", Mock()) as db:
			db.exists.side_effect = [True, False]
			db.get_single_value.return_value = "Checking Output"
			db.sql.side_effect = [
				[frappe._dict(variant="Red", qty=10), frappe._dict(variant="Blue", qty=5)],
				[
					frappe._dict(variant="Red", qty=4),
					frappe._dict(variant="Blue", qty=-2),
					frappe._dict(variant="Other", qty=3),
				],
			]
			self.assertEqual(
				get_sewing_plan_remaining_quantities("WO-1", "Unit", "GRN-1"),
				{"Red": 6, "Blue": 7, "Other": -3},
			)
		self.assertEqual(
			db.sql.call_args_list[0].args[1], {"work_order": "WO-1", "checking_type": "Checking Output"}
		)
		query, params = db.sql.call_args_list[1].args
		self.assertEqual(params, {"work_order": "WO-1", "grn_name": "GRN-1"})
		for clause in [
			"item.parent = grn.name",
			"grn.against_id = %(work_order)s",
			"grn.docstatus = 1",
			"grn.name != %(grn_name)s",
			"if(grn.is_return, -1, 1)",
			"group by item.item_variant",
		]:
			self.assertIn(clause, query)
		self.assertNotIn("received_type", query)

	def test_remaining_quantities_return_none_for_exempt_or_unplanned_work_orders(self):
		for exists, checking in [
			([False], "Checking Output"),
			([True, True], "Checking Output"),
			([True, False], None),
		]:
			with self.subTest(exists=exists, checking=checking), patch("frappe.db", Mock()) as db:
				db.exists.side_effect = exists
				db.get_single_value.return_value = checking
				self.assertIsNone(get_sewing_plan_remaining_quantities("WO-1", "Unit"))
				db.sql.assert_not_called()

	def test_no_checking_output_means_zero_remaining_and_new_grn_is_not_excluded(self):
		with patch("frappe.db", Mock()) as db:
			db.exists.return_value = True
			db.get_single_value.return_value = "Checking Output"
			db.sql.side_effect = [[], []]
			self.assertEqual(get_sewing_plan_remaining_quantities("WO-1", None), {})
			self.assertEqual(db.sql.call_args_list[1].args[1]["grn_name"], "")

	def test_submit_combines_received_types_and_preserves_mismatch_message(self):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="WO-1",
			name="GRN-1",
			items=[
				frappe._dict(item_variant="Red", received_type="Good", quantity=3),
				frappe._dict(item_variant="Red", received_type="Reject", quantity=4),
			],
		)
		allowed = [frappe._dict(variant="Red", qty=10)]
		with (
			patch("frappe.db", Mock()) as db,
			patch("frappe.throw", side_effect=frappe.ValidationError) as throw,
			self.assertRaises(frappe.ValidationError),
		):
			db.exists.return_value = True
			db.get_single_value.return_value = "Checking Output"
			db.sql.side_effect = [allowed, [frappe._dict(variant="Red", qty=4)], allowed]
			validate_sewing_plan_quantity(grn)
		throw.assert_called_once_with(
			"Red &mdash; Checking Output: 10, Already received: 4, This GRN: 7, Over by: 1",
			title="Sewing Plan Qty Mismatch",
		)

	def test_submit_preserves_three_decimal_comparison(self):
		for received, quantity, rejected in [(4, 6, False), (4.0008, 6, True), (4, 6.0004, False)]:
			allowed = [frappe._dict(variant="Red", qty=10.0004)]
			with (
				self.subTest(received=received, quantity=quantity),
				patch("frappe.db", Mock()) as db,
				patch("frappe.throw") as throw,
			):
				db.exists.return_value = True
				db.get_single_value.return_value = "Checking Output"
				db.sql.side_effect = [allowed, [frappe._dict(variant="Red", qty=received)], allowed]
				validate_sewing_plan_quantity(
					frappe._dict(
						against="YRP Work Order",
						against_id="WO-1",
						name="GRN-1",
						items=[frappe._dict(item_variant="Red", quantity=quantity)],
					)
				)
				self.assertEqual(throw.called, rejected)

	def test_submit_skips_returns_bypass_and_other_sources(self):
		for values in [
			{"is_return": 1},
			{"avoid_sewing_plan_qty": 1},
			{"against": "Purchase Order"},
			{"against_id": None},
		]:
			grn = frappe._dict(against="YRP Work Order", against_id="WO-1")
			grn.update(values)
			with self.subTest(values=values), patch("frappe.db", Mock()) as db:
				validate_sewing_plan_quantity(grn)
				db.exists.assert_not_called()


class TestGoodsReceivedNoteCustomization(FrappeTestCase):
	EXPECTED_FIELDS = {
		"additional_grn": ("Check", None),
		"allow_non_bundle": ("Check", None),
		"delivery_location_name": ("Data", None),
		"dc_no": ("Data", None),
		"cutting_laysheet": ("Link", "SD YRP Cutting LaySheet"),
		"mrp_material_issue_ref": ("Link", "YRP Stock Entry"),
		"is_pack": ("Check", None),
		"from_finishing": ("Check", None),
		"avoid_sewing_plan_qty": ("Check", None),
		"mapped_stock_update_state": ("Int", None),
		"rework_created": ("Check", None),
		"grn_date": ("Date", None),
		"actual_date": ("Date", None),
		"is_manual_entry": ("Check", None),
		"letter_head": ("Link", "Letter Head"),
		"cut_panel_movement": ("Link", "SD YRP Cut Panel Movement"),
		"includes_packing": ("Check", None),
		"supplier_document_date": ("Date", None),
		"freight_charge_per_product": ("Currency", None),
		"supplier_name": ("Data", None),
		"delivery_date": ("Date", None),
		"supplier_address": ("Link", "Address"),
		"supplier_address_display": ("Small Text", None),
		"contact_person": ("Link", "Contact"),
		"contact_display": ("Small Text", None),
		"contact_mobile": ("Small Text", None),
		"delivery_address": ("Link", "Address"),
		"delivery_address_display": ("Small Text", None),
		"total_receivable_cost": ("Currency", None),
		"packing_calculation_version": ("Int", None),
		"total_packing_boxes": ("Float", None),
		"total_packing_pieces": ("Float", None),
		"packing_batches": ("Table", "SD YRP GRN Packing Batch"),
		"items_json": ("JSON", None),
		"grn_excess_usage_items": ("Table", "SD YRP GRN Excess Usage Item"),
		"total_delivered_qty": ("Float", None),
		"total_tax": ("Currency", None),
		"grand_total": ("Currency", None),
		"in_words": ("Data", None),
		"approved_by": ("Link", "User"),
	}

	def test_desk_grn_calculate_uses_saved_work_order_calculation(self):
		from pathlib import Path

		source = (Path(frappe.get_app_path("essdee_yrp")) / "public/js/goods_received_note.js").read_text(
			encoding="utf-8"
		)
		self.assertIn("get_grn_calculation_context", source)
		self.assertIn("calculate_grn_receivables", source)
		self.assertIn('options: "YRP Received Type"', source)
		self.assertIn("essdee-grn-calc-qty", source)

	def test_desk_knitting_grn_exposes_server_guarded_actual_dia_split(self):
		from pathlib import Path

		source = (Path(frappe.get_app_path("essdee_yrp")) / "public/js/goods_received_note.js").read_text(
			encoding="utf-8"
		)
		self.assertIn("get_actual_dia_context", source)
		self.assertIn('__("Add Actual Dia")', source)
		self.assertIn("open_actual_dia_dialog", source)
		self.assertIn("allowExcess: true", source)
		self.assertIn("aggregatePhysicalRows: true", source)

	def test_grn_calculate_replaces_only_the_selected_received_type(self):
		rows = [
			frappe._dict(
				ref_docname="REC-1",
				received_type="Accepted",
				quantity=10,
				conversion_factor=1,
			),
			frappe._dict(
				ref_docname="REC-2",
				received_type="Accepted",
				quantity=5,
				conversion_factor=1,
			),
			frappe._dict(
				ref_docname="REC-2",
				received_type="Rejected",
				quantity=2,
				conversion_factor=1,
			),
		]

		result = _apply_calculated_receivable_quantities(rows, {"REC-1": 3}, "Accepted")

		self.assertEqual(
			[(row.ref_docname, row.received_type, row.quantity) for row in result],
			[
				("REC-1", "Accepted", 3),
				("REC-2", "Rejected", 2),
			],
		)

	def test_grn_calculate_can_save_selected_zero_pending_row_for_submit_validation(self):
		work_order = frappe._dict(
			receivables=[
				frappe._dict(
					name="REC-MINT-45",
					idx=1,
					item_variant="GARMENT-MINT-45",
					uom="Pieces",
					qty=100,
					pending_quantity=0,
					table_index=0,
					row_index="matrix-0000",
					set_combination="{}",
					cost=0,
				)
			]
		)

		rows = _include_calculated_receivable_rows([], work_order, {"REC-MINT-45": 5}, "Accepted")
		rows = _apply_calculated_receivable_quantities(rows, {"REC-MINT-45": 5}, "Accepted")

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].ref_docname, "REC-MINT-45")
		self.assertEqual(rows[0].pending_quantity, 0)
		self.assertEqual(rows[0].quantity, 5)
		self.assertEqual(rows[0].received_type, "Accepted")

	def test_calculated_input_availability_is_not_a_draft_save_hook(self):
		before_validate = frappe.get_hooks("doc_events")["YRP Goods Received Note"]["before_validate"]
		for method in (
			"essdee_yrp.finishing.packing_grn.before_validate",
			"essdee_yrp.fabric_grn.before_validate",
			"essdee_yrp.garment_grn.before_validate",
		):
			self.assertNotIn(method, before_validate)
		self.assertIn(
			"essdee_yrp.packing_hooks.set_grn_includes_packing",
			before_validate,
		)
		self.assertIn(
			"essdee_yrp.purchase_order_lots.validate_grn_lots",
			before_validate,
		)
		self.assertIn(
			"essdee_yrp.cutting.movement.validate_transaction_link",
			before_validate,
		)

	def test_fresh_grn_keeps_only_default_received_type(self):
		rows = [
			frappe._dict(item_variant="ITEM", received_type="Accepted"),
			frappe._dict(item_variant="ITEM", received_type="Rejected"),
			frappe._dict(item_variant="ITEM", received_type="Rework"),
		]
		with patch(
			"essdee_yrp.overrides.goods_received_note._default_received_type",
			return_value="Accepted",
		):
			filtered = _only_default_received_type(rows)
		self.assertEqual([row.received_type for row in filtered], ["Accepted"])

	def test_saved_draft_keeps_only_explicit_received_type_rows(self):
		existing = [
			frappe._dict(
				ref_docname="RECEIVABLE-1",
				item_variant="ITEM-S",
				received_type="Accepted",
			)
		]
		pending = [
			frappe._dict(
				ref_docname="RECEIVABLE-1",
				item_variant="ITEM-S",
				received_type=received_type,
			)
			for received_type in ("Accepted", "Rejected", "Rework")
		]
		grn = frappe._dict(against_id="WO-1", delivery_challan=None)
		with (
			patch.object(frappe, "get_doc", return_value=frappe._dict()),
			patch(
				"yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note._pending_receivable_rows",
				return_value=pending,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note._default_received_type",
				return_value="Accepted",
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_production_group_dimensions",
				return_value={},
			),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._apply_dimension_values_to_rows"
			),
			patch("yrp.stock.dimensions.apply_dimension_defaults"),
		):
			filtered = _selected_draft_receivable_rows(grn, existing)

		self.assertEqual([row.received_type for row in filtered], ["Accepted"])

	def test_approved_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("YRP Goods Received Note", cached=False)

		for fieldname, expected in self.EXPECTED_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), expected)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "YRP Goods Received Note",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta("YRP Goods Received Note", cached=False)

		self.assertEqual(meta.get_field("delivery_date").default, "Today")
		self.assertEqual(meta.get_field("delivery_date").reqd, 1)
		self.assertEqual(meta.get_field("supplier_address").reqd, 1)
		self.assertEqual(meta.get_field("delivery_address").reqd, 1)
		self.assertEqual(
			meta.get_field("delivery_location_name").fetch_from,
			"delivery_location.supplier_name",
		)
		self.assertEqual(
			meta.get_field("supplier_name").fetch_from,
			"supplier.supplier_name",
		)
		self.assertEqual(
			meta.get_field("is_manual_entry").fetch_from,
			"process_name.is_manual_entry_in_grn",
		)
		self.assertEqual(
			meta.get_field("includes_packing").fetch_from,
			"process_name.includes_packing",
		)
		self.assertEqual(meta.get_field("from_finishing").allow_on_submit, 1)
		self.assertEqual(meta.get_field("mrp_material_issue_ref").allow_on_submit, 1)
		self.assertEqual(meta.get_field("packing_batches").allow_on_submit, 1)
		self.assertEqual(meta.get_field("total_delivered_qty").allow_on_submit, 1)
		self.assertEqual(meta.get_field("avoid_sewing_plan_qty").permlevel, 1)
		self.assertEqual(meta.get_field("approved_by").no_copy, 1)

	def test_essdee_stock_entry_fields_are_packaged(self):
		meta = frappe.get_meta("YRP Goods Received Note", cached=False)
		for fieldname in ("essdee_yrp_stock_entry", "essdee_yrp_stock_entry_created"):
			self.assertIsNotNone(meta.get_field(fieldname))
			self.assertTrue(
				frappe.db.exists(
					"Custom Field",
					{
						"dt": "YRP Goods Received Note",
						"fieldname": fieldname,
						"module": "Essdee YRP",
					},
				)
			)

	def test_sewing_grn_is_blocked_without_checking_output(self):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="TEST-SEWING-WO",
			name="TEST-SEWING-GRN",
			items=[frappe._dict(item_variant="PIECE-RED-45", quantity=1)],
		)
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_single_value", return_value="Checking Output"),
			patch.object(frappe.db, "sql", side_effect=[[], [], []]),
			self.assertRaisesRegex(frappe.ValidationError, "Checking Output: 0"),
		):
			validate_sewing_plan_quantity(grn)

	def test_sewing_grn_accepts_only_remaining_checked_quantity(self):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="TEST-SEWING-WO",
			name="TEST-SEWING-GRN",
			items=[frappe._dict(item_variant="PIECE-RED-45", quantity=6)],
		)
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_single_value", return_value="Checking Output"),
			patch.object(
				frappe.db,
				"sql",
				side_effect=[
					[frappe._dict(variant="PIECE-RED-45", qty=10)],
					[frappe._dict(variant="PIECE-RED-45", qty=4)],
					[frappe._dict(variant="PIECE-RED-45", qty=10)],
				],
			),
		):
			validate_sewing_plan_quantity(grn)

	def test_configured_supplier_skips_sewing_quantity_validation(self):
		grn = frappe._dict(
			against="YRP Work Order",
			against_id="TEST-SEWING-WO",
			name="TEST-SEWING-GRN",
			supplier="EXEMPT-SEWING-UNIT",
			items=[frappe._dict(item_variant="PIECE-RED-45", quantity=99)],
		)
		with (
			patch.object(frappe.db, "exists", return_value=True) as exists,
			patch.object(frappe.db, "sql") as sql,
		):
			validate_sewing_plan_quantity(grn)

		self.assertEqual(exists.call_count, 2)
		sql.assert_not_called()

	def test_approved_base_yrp_fields_are_unchanged(self):
		meta = frappe.get_meta("YRP Goods Received Note", cached=False)

		delivery_location = meta.get_field("delivery_location")
		self.assertEqual(
			(
				delivery_location.options,
				delivery_location.reqd,
				delivery_location.fetch_from,
			),
			("Supplier", 0, "to_warehouse.supplier"),
		)

		freight_charges = meta.get_field("freight_charges")
		self.assertEqual(freight_charges.default, "0")
		self.assertFalse(freight_charges.depends_on)

		lot = meta.get_field("lot")
		self.assertEqual(
			(lot.fieldtype, lot.options, lot.reqd, lot.read_only, lot.mandatory_depends_on),
			("Link", "SD YRP Lot", 0, 0, "eval:doc.against!='Purchase Order'"),
		)

	def test_cutting_grn_sizes_share_one_logical_row(self):
		variants = {
			"FRONT-45": frappe._dict(
				name="FRONT-45",
				variant_of="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"FRONT-50": frappe._dict(
				name="FRONT-50",
				variant_of="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(name="Maze Capri Set R.N.S", primary_attribute="Size")

		def get_cached_doc(doctype, name):
			self.assertEqual(doctype, "Item")
			return variants.get(name, item)

		rows = [
			frappe._dict(
				item_variant=variant,
				lot="C0826-57",
				received_type="Accepted",
				set_combination={"major_part": "Top", "major_colour": "Red"},
			)
			for variant in variants
		]
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			normalized = normalize_cutting_grn_row_indexes(rows)
		self.assertEqual(len({row.row_index for row in normalized}), 1)

		changed_lot = frappe._dict(normalized[0])
		changed_lot.lot = "ANOTHER-LOT"
		changed_type = frappe._dict(normalized[0])
		changed_type.received_type = "Rejected"
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			separated = normalize_cutting_grn_row_indexes([normalized[0], changed_lot, changed_type])
		self.assertEqual(len({row.row_index for row in separated}), 3)

	def test_packing_grn_display_adds_split_receivable_rows_per_size(self):
		variants = {
			"PACK-45": frappe._dict(
				name="PACK-45",
				variant_of="PACKED-ITEM",
				attributes=[frappe._dict(attribute="Size", attribute_value="45 cm")],
			),
			"PACK-50": frappe._dict(
				name="PACK-50",
				variant_of="PACKED-ITEM",
				attributes=[frappe._dict(attribute="Size", attribute_value="50 cm")],
			),
		}
		item = frappe._dict(name="PACKED-ITEM", primary_attribute="Size")

		def get_cached_doc(doctype, name):
			self.assertEqual(doctype, "Item")
			return variants.get(name, item)

		rows = [
			frappe._dict(
				item_variant="PACK-45",
				quantity=2,
				stock_qty=10,
				amount=100,
				uom="Box",
				stock_uom="Pieces",
				conversion_factor=5,
				lot="LOT-1",
				received_type="Accepted",
				set_combination="{}",
			),
			frappe._dict(
				item_variant="PACK-45",
				quantity=3,
				stock_qty=15,
				amount=180,
				uom="Box",
				stock_uom="Pieces",
				conversion_factor=5,
				lot="LOT-1",
				received_type="Accepted",
				set_combination="{}",
			),
			frappe._dict(
				item_variant="PACK-50",
				quantity=4,
				stock_qty=20,
				amount=200,
				uom="Box",
				stock_uom="Pieces",
				conversion_factor=5,
				lot="LOT-1",
				received_type="Accepted",
				set_combination="{}",
			),
		]
		with (
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			aggregated = aggregate_packing_grn_rows_for_ui(rows)

		self.assertEqual(len(aggregated), 2)
		by_variant = {row.item_variant: row for row in aggregated}
		self.assertEqual(by_variant["PACK-45"].quantity, 5)
		self.assertEqual(by_variant["PACK-45"].stock_qty, 25)
		self.assertEqual(by_variant["PACK-45"].amount, 280)
		self.assertAlmostEqual(by_variant["PACK-45"].rate, 11.2)
		self.assertEqual(
			by_variant["PACK-45"].row_index,
			by_variant["PACK-50"].row_index,
		)

	def test_fresh_work_order_grn_defaults_normalize_migrated_size_indexes(self):
		variants = {
			"FRONT-45": frappe._dict(
				name="FRONT-45",
				variant_of="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"FRONT-50": frappe._dict(
				name="FRONT-50",
				variant_of="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(name="Maze Capri Set R.N.S", primary_attribute="Size")
		base_defaults = {
			"items": [
				frappe._dict(
					item_variant=name,
					row_index=f"legacy-{index}",
					lot="C0826-57",
					received_type="Accepted",
					set_combination={"major_part": "Top", "major_colour": "Red"},
				)
				for index, name in enumerate(variants)
			],
			"item_details": ["stale"],
		}

		def get_cached_doc(doctype, name):
			self.assertEqual(doctype, "Item")
			return variants.get(name, item)

		with (
			patch(
				"yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.get_work_order_defaults",
				return_value=base_defaults,
			),
			patch(
				"essdee_yrp.overrides.goods_received_note.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch(
				"yrp.stock.save_stock_items.group_items_for_ui",
				return_value=["grouped"],
			) as group_items,
		):
			defaults = get_work_order_defaults("YRP-WO-TEST")

		normalized = defaults["items"]
		self.assertEqual(len({row.row_index for row in normalized}), 1)
		self.assertEqual(defaults["item_details"], ["grouped"])
		group_items.assert_called_once_with(normalized, "YRP Goods Received Note")

	def test_non_group_garment_process_consumes_each_received_panel(self):
		variant = "GARMENT-BOTTOM-LEFT-DARK-GREY-45"
		combination = {"major_colour": "Airforce", "major_part": "Top"}
		grn = frappe.get_doc(
			{
				"doctype": "YRP Goods Received Note",
				"against": "YRP Work Order",
				"against_id": "TEST-PRINTING-WO",
				"process_name": "Printing",
				"items": [
					{
						"item_variant": variant,
						"quantity": 9,
						"uom": "Pieces",
						"lot": "TEST-LOT",
						"received_type": "Accepted",
						"set_combination": combination,
					}
				],
			}
		)
		deliverable = frappe._dict(
			name="TEST-DELIVERABLE",
			item_variant=variant,
			uom="Pieces",
			lot="TEST-LOT",
			received_type="Accepted",
			set_combination=combination,
			# Migrated/manual submitted Work Order rows may not carry this UI
			# provenance flag.  They remain authoritative Deliverables.
			is_calculated=0,
			valuation_rate=2,
			qty=9,
			pending_quantity=0,
			stock_update=0,
			rate=2,
		)
		work_order = frappe._dict(
			name="TEST-PRINTING-WO",
			production_detail="TEST-IPD",
			process_name="Printing",
			lot="TEST-LOT",
			deliverables=[deliverable],
		)
		ipd = frappe._dict(
			is_cloth_item=0,
			cutting_process="Cutting",
			stiching_process="Stitching",
			packing_process="Packing",
			ipd_processes=[frappe._dict(process_name="Printing", in_stage="Cut", out_stage="Cut")],
		)

		def get_cached_doc(doctype, name):
			return work_order if doctype == "YRP Work Order" else ipd

		original_get_value = frappe.db.get_value

		def get_value(doctype, filters, fieldname, *args, **kwargs):
			if doctype == "YRP Process" and filters == "Printing" and fieldname == "is_group":
				return 0
			return original_get_value(doctype, filters, fieldname, *args, **kwargs)

		with (
			patch("essdee_yrp.garment_grn.frappe.get_cached_doc", side_effect=get_cached_doc),
			patch("essdee_yrp.garment_grn.frappe.get_doc", return_value=work_order),
			patch("essdee_yrp.garment_grn.frappe.db.get_value", side_effect=get_value),
			patch(
				"yrp.stock.utils.get_conversion_factor",
				return_value={"conversion_factor": 1, "stock_uom": "Pieces"},
			),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "TEST-LOT", "received_type": "Accepted"},
			),
			patch("yrp.stock.utils.get_stock_balance", return_value=(9, 2)),
		):
			calculate_garment_consumption(grn)

		self.assertEqual(len(grn.grn_deliverables), 1)
		consumed = grn.grn_deliverables[0]
		self.assertEqual(consumed.item_variant, variant)
		self.assertEqual(consumed.quantity, 9)
		self.assertEqual(consumed.stock_qty, 9)
		self.assertEqual(consumed.work_order_deliverable, deliverable.name)
		self.assertEqual(consumed.goods_received_note_item, grn.items[0].name)
		self.assertEqual(consumed.received_item_variant, variant)
		self.assertEqual(consumed.set_combination, combination)


class TestDefaultKnittingActualDia(unittest.TestCase):
	def setUp(self):
		self.enterContext(patch("essdee_yrp.fabric_grn.get_dia_attribute", return_value="Dia"))
		self.enterContext(patch("essdee_yrp.fabric_grn._configured_dia_values", return_value=["14", "14.5"]))
		self.enterContext(patch("essdee_yrp.fabric_grn.get_parent_item", return_value="Greige"))
		self.enterContext(patch.object(frappe.db, "exists", return_value=True))
		self.enterContext(patch.object(frappe.db, "get_single_value", return_value="Knitting"))
		self.work_order = frappe._dict(
			name="WO-1", process_name="Knitting", production_detail="IPD-1",
			cloth_execution_version=0, check_permission=Mock(),
			receivables=[frappe._dict(name="REC-1", item_variant="Greige-14")],
		)
		self.enterContext(patch.object(frappe, "get_doc", return_value=self.work_order))

	def test_actual_dia_context_uses_default_knitting_and_production_detail(self):
		from essdee_yrp.fabric_grn import get_actual_dia_context

		self.assertEqual(get_actual_dia_context("WO-1"), {"enabled": True, "attribute": "Dia", "dia_options": ["14", "14.5"]})
		self.work_order.process_name = "Dyeing"
		self.assertFalse(get_actual_dia_context("WO-1")["enabled"])
		self.work_order.process_name = "Knitting"
		self.work_order.production_detail = None
		self.assertFalse(get_actual_dia_context("WO-1")["enabled"])

	def test_actual_dia_validation_rejects_colour_and_unconfigured_dia(self):
		from essdee_yrp.fabric_grn import validate_actual_dia_rows

		for attributes, message in (({"Colour": "Blue", "Dia": "14.5"}, "only Dia may differ"), ({"Colour": "Greige", "Dia": "99"}, "not a valid Dia value")):
			with (
				self.subTest(attributes=attributes),
				patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
				patch("essdee_yrp.fabric_grn._variant_attrs", side_effect=[{"Colour": "Greige", "Dia": "14"}, attributes]),
			):
				row = frappe._dict(idx=1, ref_docname="REC-1", item_variant="ACTUAL")
				with self.assertRaisesRegex(frappe.ValidationError, message):
					validate_actual_dia_rows(frappe._dict(against="YRP Work Order", against_id="WO-1", items=[row]))

	def test_unversioned_actual_dia_split_gets_distinct_row_indexes(self):
		from essdee_yrp.fabric_grn import validate_actual_dia_rows

		rows = [
			frappe._dict(idx=1, ref_docname="REC-1", item_variant="Greige-14", row_index="0"),
			frappe._dict(idx=2, ref_docname="REC-1", item_variant="Greige-14.5", row_index="0"),
		]
		with (
			patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
			patch("essdee_yrp.fabric_grn._variant_attrs", side_effect=[{"Colour": "Greige", "Dia": "14"}, {"Colour": "Greige", "Dia": "14.5"}]),
		):
			validate_actual_dia_rows(frappe._dict(against="YRP Work Order", against_id="WO-1", items=rows))
		self.assertNotEqual(rows[0].row_index, rows[1].row_index)

	def test_saved_actual_rows_have_pending_without_receipt_cap(self):
		from essdee_yrp.fabric_grn import get_saved_actual_dia_rows

		self.work_order.receivables[0].update(pending_quantity=50, cost=10)
		rows = get_saved_actual_dia_rows(frappe._dict(items=[frappe._dict(item_variant="Greige-14.5", ref_docname="REC-1", quantity=60)]), self.work_order)
		self.assertEqual(rows[0]["pending_quantity"], 50)
		self.assertIsNone(rows[0]["max_receivable_quantity"])

	def test_saved_actual_rows_preserve_operator_quantities_and_quantity_basis(self):
		from essdee_yrp.fabric_grn import get_saved_actual_dia_rows

		self.work_order.receivables[0].update(pending_quantity=50, cost=20, uom="Kg")
		for secondary_qty in (0, 3):
			with self.subTest(secondary_qty=secondary_qty):
				saved = frappe._dict(
					name="ACTUAL", item_variant="Greige-14.5", ref_docname="REC-1",
					received_type="Accepted", quantity=20, secondary_uom="Roll", secondary_qty=secondary_qty,
					uom="Pound", stock_uom="Gram", conversion_factor=453.592, stock_qty=9071.84,
				)
				# Base _pending_receivable_rows emits no secondary UOM or quantity.
				planned = frappe._dict(
					ref_docname="REC-1", received_type="Accepted", quantity=30,
					uom="Kg", stock_uom="Kg", conversion_factor=1,
				)
				actual = get_saved_actual_dia_rows(
					frappe._dict(items=[saved]), self.work_order, planned_rows=[planned]
				)[0]
				for field in ("quantity", "secondary_qty", "uom", "stock_uom", "conversion_factor", "stock_qty"):
					self.assertEqual(actual[field], saved[field], field)
				self.assertEqual(actual.get("secondary_uom"), "Roll" if secondary_qty else None)
				self.assertEqual(actual["item_variant"], "Greige-14.5")
				self.assertEqual(actual["rate"], 20)
				self.assertEqual(saved.secondary_uom, "Roll", "display rebuild must not mutate saved rows")

	def test_saved_actual_rows_backfill_only_missing_secondary_uom(self):
		from essdee_yrp.fabric_grn import get_saved_actual_dia_rows

		self.work_order.receivables[0].update(pending_quantity=50, cost=20, secondary_uom="Roll")
		for saved_uom, planned_rows, expected in (
			(None, [frappe._dict(ref_docname="REC-1", received_type="Accepted", secondary_uom="Bundle", secondary_qty=2)], "Bundle"),
			("Roll", [frappe._dict(ref_docname="REC-1", received_type="Accepted", secondary_uom="Bundle", secondary_qty=2)], "Roll"),
			(None, [], "Roll"),
			("Roll", [], "Roll"),
		):
			with self.subTest(saved_uom=saved_uom, planned_rows=planned_rows):
				saved = frappe._dict(item_variant="Greige-14.5", ref_docname="REC-1",
					received_type="Accepted", quantity=20, secondary_uom=saved_uom, secondary_qty=3)
				actual = get_saved_actual_dia_rows(
					frappe._dict(items=[saved]), self.work_order, planned_rows=planned_rows
				)[0]
				self.assertEqual(actual["secondary_uom"], expected)
				self.assertEqual(actual["secondary_qty"], 3)

	def test_reopened_draft_orders_receivables_before_actual_dia_splits(self):
		from itertools import product

		from yrp.stock.save_stock_items import ungroup_items_from_ui

		from essdee_yrp.fabric_store.documents.goods_received_note import _merge_authoritative_rows
		from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote

		self.work_order.receivables = [
			frappe._dict(name="A", item_variant="Greige-19", pending_quantity=30, cost=20),
			frappe._dict(name="B", item_variant="Greige-14", pending_quantity=50, cost=20),
		]
		for planned_quantity, secondary_qty in product((30, 0), (0, 3)):
			with self.subTest(planned_quantity=planned_quantity, secondary_qty=secondary_qty):
				saved = [
					frappe._dict(item_variant=variant, row_index=index, ref_docname=ref,
						quantity=quantity, received_type="Accepted", secondary_uom="Roll", secondary_qty=0)
					for index, (variant, ref, quantity) in enumerate([
						("Greige-19", "A", 40), ("Greige-14", "B", planned_quantity), ("Greige-14.5", "B", 20),
					])
				]
				saved[-1].update(secondary_qty=secondary_qty, uom="Pound", stock_uom="Gram", conversion_factor=453.592)
				# No planned row is persisted if only the actual Dia has quantity.
				if not planned_quantity:
					saved.pop(1)
				document = object.__new__(EssdeeGoodsReceivedNote)
				document.__dict__.update(
					docstatus=0, against="YRP Work Order", against_id="WO-1",
					items=saved, delivery_challan=None,
					__onload=frappe._dict(),
				)
				planned = [
					frappe._dict(item_variant=variant, row_index=f"{index}::Accepted", ref_docname=ref,
						quantity=quantity, received_type="Accepted", uom="Kg")
					for index, (variant, ref, quantity) in enumerate([
						("Greige-19", "A", 40), ("Greige-14", "B", planned_quantity),
					])
				]
				def get_doc(doctype, name):
					if doctype == "YRP Work Order":
						return self.work_order
					return frappe._dict(attributes=[
						frappe._dict(attribute="Colour", attribute_value="Greige"),
						frappe._dict(attribute="Dia", attribute_value=name.split("-")[-1]),
					])

				config = {
					"item_field": "item_variant", "qty_field": "quantity",
					"value_fields": ["ref_docname", "received_type", "secondary_uom", "secondary_qty"],
				}
				with (
					patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.GoodsReceivedNote.onload"),
					patch.object(frappe, "get_doc", side_effect=get_doc),
					patch("essdee_yrp.overrides.goods_received_note._default_received_type", return_value="Accepted"),
					patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note._pending_receivable_rows", return_value=planned),
					patch("yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_production_group_dimensions", return_value={}),
					patch("yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._apply_dimension_values_to_rows"),
					patch("yrp.stock.dimensions.apply_dimension_defaults"),
					patch("yrp.stock.save_stock_items._get_map_config", return_value=config),
					patch("yrp.stock.save_stock_items._get_entry_fields", return_value=["stock_uom", "conversion_factor"]),
					patch("yrp.stock.save_stock_items.get_dimension_fieldnames", return_value=[]),
					patch("yrp.stock.save_stock_items._resolve_or_create_variant", side_effect=lambda parent, attrs: f"{parent}-{attrs['Dia']}"),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames", return_value=()),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._", side_effect=lambda text: text),
					patch("yrp.yrp.doctype.yrp_item.yrp_item.get_parent_item", return_value="Greige"),
					patch("yrp.yrp.doctype.yrp_item.yrp_item.get_attribute_details", return_value={
						"attributes": ["Colour"], "primary_attribute": "Dia",
						"primary_attribute_values": ["14", "14.5", "19"],
					}),
				):
					document.onload()
					matrix = document.get_onload("item_details")
					browser_rows = ungroup_items_from_ui(matrix, "YRP Goods Received Note")
					merged = _merge_authoritative_rows(saved, browser_rows)
				matrix = document.get_onload("item_details")
				order = [
					(dia, value["ref_docname"], value["qty"])
					for group in matrix for row in group["items"] for dia, value in row["values"].items()
					if value.get("ref_docname")
				]
				self.assertEqual(order, [("19", "A", 40), ("14", "B", planned_quantity), ("14.5", "B", 20)])
				self.assertEqual([row.row_index for row in saved], [0, 1, 2] if planned_quantity else [0, 2])
				actual_entry = next(row for group in matrix for row in group["items"] if row["values"].get("14.5", {}).get("ref_docname"))
				self.assertEqual(actual_entry["values"]["14.5"]["secondary_qty"], secondary_qty)
				self.assertEqual(actual_entry["values"]["14.5"].get("secondary_uom"), "Roll" if secondary_qty else None)
				self.assertEqual(actual_entry["default_uom"], "Pound")
				self.assertEqual(actual_entry["stock_uom"], "Gram")
				self.assertEqual(actual_entry["conversion_factor"], 453.592)
				actual = next(row for row in merged if row["item_variant"] == "Greige-14.5")
				for field in ("quantity", "secondary_qty", "secondary_uom", "uom", "stock_uom", "conversion_factor"):
					self.assertEqual(actual[field], saved[-1][field], field)


class TestFabricReceiptExcess(unittest.TestCase):
	def test_standard_receipt_excess_links_and_updates_negative_pending(self):
		from essdee_yrp.overrides.goods_received_note import (
			EssdeeGoodsReceivedNote,
			_update_versioned_cloth_receivables,
		)

		for version in (0, 1):
			with self.subTest(version=version):
				target = frappe._dict(name="REC-1", item_variant="Greige-14", qty=50, pending_quantity=50, db_set=Mock())
				work_order = frappe._dict(name="WO-1", production_detail="CLOTH-IPD", cloth_execution_version=version, receivables=[target])
				row = frappe._dict(idx=1, item_variant="Greige-14.5", quantity=60, ref_doctype="YRP Work Order Receivables", ref_docname="REC-1")
				document = Mock(against_id="WO-1")
				document.get.side_effect = {"items": [row]}.get
				with (
					patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
					patch.object(frappe, "get_doc", return_value=work_order),
					patch.object(frappe.db, "get_value", return_value=1),
					patch("essdee_yrp.overrides.goods_received_note._wo_excess_percentage", return_value=0),
					patch("essdee_yrp.overrides.goods_received_note._update_work_order_status"),
				):
					EssdeeGoodsReceivedNote.validate_against_work_order_pending(document)
					self.assertEqual(row.ref_docname, "REC-1")
					self.assertEqual(row.pending_quantity, 50)
					self.assertIsNone(row.max_receivable_quantity)
					document.validate_against_correction_pending.assert_called_once_with(0)
					_update_versioned_cloth_receivables(document, work_order)
				self.assertEqual(target.pending_quantity, -10)
				target.db_set.assert_called_once_with("pending_quantity", -10, update_modified=False)

	def test_only_cloth_ipd_receipts_skip_process_allowance(self):
		from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote

		for cloth, process, excess_pct in (
			(0, "Printing", 20), (0, "Embroidery", 10), (0, "Cutting", 300),
			(1, "Knitting", 0), (1, "Dyeing", 0),
		):
			with self.subTest(cloth=cloth, process=process):
				target = frappe._dict(name="REC-1", item_variant="ITEM", qty=50, pending_quantity=50)
				work_order = frappe._dict(name="WO-1", production_detail="IPD-1", process_name=process, receivables=[target])
				document = object.__new__(EssdeeGoodsReceivedNote)
				row = frappe._dict(idx=1, item_variant="ITEM", quantity=50 * (1 + excess_pct / 100) + 10,
					ref_doctype="YRP Work Order Receivables", ref_docname="REC-1")
				document.__dict__.update(against_id="WO-1", items=[row], correction_items=[])
				with (
					patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=True),
					patch.object(frappe, "get_doc", return_value=work_order),
					patch.object(frappe.db, "get_value", return_value=cloth) as get_value,
					patch("essdee_yrp.overrides.goods_received_note._wo_excess_percentage", return_value=excess_pct),
					patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note._wo_excess_percentage", return_value=excess_pct),
				):
					if cloth:
						document.validate_against_work_order_pending()
						self.assertIsNone(row.max_receivable_quantity)
					else:
						with self.assertRaisesRegex(frappe.ValidationError, "exceeds allowance"):
							document.validate_against_work_order_pending()
					get_value.assert_called_once_with("YRP Item Production Detail", "IPD-1", "is_cloth_item")

	def test_return_and_rework_keep_base_pending_checks(self):
		from essdee_yrp.overrides.goods_received_note import EssdeeGoodsReceivedNote

		for field in ("is_return", "is_rework"):
			with self.subTest(field=field):
				document = object.__new__(EssdeeGoodsReceivedNote)
				document.__dict__.update({field: 1, "flags": frappe._dict()})
				with (
					patch("essdee_yrp.fabric_grn.is_calculable_fabric_grn", return_value=False),
					patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.GoodsReceivedNote.validate_against_work_order_pending", side_effect=frappe.ValidationError("pending cap")) as validate,
					self.assertRaisesRegex(frappe.ValidationError, "pending cap"),
				):
					document.validate_against_work_order_pending()
				validate.assert_called_once()

	def test_correction_still_rejects_excess(self):
		from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import GoodsReceivedNote

		target = frappe._dict(name="CORR-REC", item_variant="Greige-14", qty=50, pending_quantity=50)
		correction = frappe._dict(work_order="WO-1", receivables=[target])
		row = frappe._dict(idx=1, item_variant="Greige-14", quantity=60, work_order_correction="CORR-1")
		document = Mock(against_id="WO-1")
		document.get.return_value = [row]
		with patch.object(frappe, "get_doc", return_value=correction), self.assertRaisesRegex(frappe.ValidationError, "exceeds allowance"):
			GoodsReceivedNote.validate_against_correction_pending(document, 0)

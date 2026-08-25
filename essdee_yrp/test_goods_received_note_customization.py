from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.garment_grn import before_validate as calculate_garment_consumption
from essdee_yrp.overrides.goods_received_note import (
	aggregate_packing_grn_rows_for_ui,
	get_work_order_defaults,
	normalize_cutting_grn_row_indexes,
	validate_sewing_plan_quantity,
)


class TestGoodsReceivedNoteCustomization(FrappeTestCase):
	EXPECTED_FIELDS = {
		"additional_grn": ("Check", None),
		"allow_non_bundle": ("Check", None),
		"delivery_location_name": ("Data", None),
		"dc_no": ("Data", None),
		"cutting_laysheet": ("Link", "Cutting LaySheet"),
		"mrp_material_issue_ref": ("Link", "Stock Entry"),
		"is_return": ("Check", None),
		"is_pack": ("Check", None),
		"from_finishing": ("Check", None),
		"avoid_sewing_plan_qty": ("Check", None),
		"rework_created": ("Check", None),
		"grn_date": ("Date", None),
		"actual_date": ("Date", None),
		"is_manual_entry": ("Check", None),
		"letter_head": ("Link", "Letter Head"),
		"cut_panel_movement": ("Link", "Cut Panel Movement"),
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
		"packing_batches": ("Table", "GRN Packing Batch"),
		"items_json": ("JSON", None),
		"grn_excess_usage_items": ("Table", "GRN Excess Usage Item"),
		"total_delivered_qty": ("Float", None),
		"total_tax": ("Currency", None),
		"grand_total": ("Currency", None),
		"in_words": ("Data", None),
		"approved_by": ("Link", "User"),
	}

	def test_approved_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

		for fieldname, expected in self.EXPECTED_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), expected)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Goods Received Note",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

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

	def test_obsolete_essdee_stock_entry_fields_are_excluded(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)
		self.assertIsNone(meta.get_field("essdee_yrp_stock_entry"))
		self.assertIsNone(meta.get_field("essdee_yrp_stock_entry_created"))

	def test_sewing_grn_is_blocked_without_checking_output(self):
		grn = frappe._dict(
			against="Work Order",
			against_id="TEST-SEWING-WO",
			name="TEST-SEWING-GRN",
			items=[frappe._dict(item_variant="PIECE-RED-45", quantity=1)],
		)
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_single_value", return_value="Checking Output"),
			patch.object(frappe.db, "sql", side_effect=[[], []]),
			self.assertRaisesRegex(frappe.ValidationError, "Checking Output: 0"),
		):
			validate_sewing_plan_quantity(grn)

	def test_sewing_grn_accepts_only_remaining_checked_quantity(self):
		grn = frappe._dict(
			against="Work Order",
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
				],
			),
		):
			validate_sewing_plan_quantity(grn)

	def test_approved_base_yrp_fields_are_unchanged(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

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
			(lot.fieldtype, lot.options, lot.reqd, lot.read_only),
			("Link", "Lot", 1, 0),
		)

	def test_cutting_grn_sizes_share_one_logical_row(self):
		variants = {
			"FRONT-45": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"FRONT-50": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(primary_attribute="Size")

		def get_cached_doc(doctype, name):
			return variants[name] if doctype == "Item Variant" else item

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
			separated = normalize_cutting_grn_row_indexes(
				[normalized[0], changed_lot, changed_type]
			)
		self.assertEqual(len({row.row_index for row in separated}), 3)

	def test_packing_grn_display_adds_split_receivable_rows_per_size(self):
		variants = {
			"PACK-45": frappe._dict(
				item="PACKED-ITEM",
				attributes=[frappe._dict(attribute="Size", attribute_value="45 cm")],
			),
			"PACK-50": frappe._dict(
				item="PACKED-ITEM",
				attributes=[frappe._dict(attribute="Size", attribute_value="50 cm")],
			),
		}
		item = frappe._dict(primary_attribute="Size")

		def get_cached_doc(doctype, name):
			return variants[name] if doctype == "Item Variant" else item

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
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"FRONT-50": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Front"),
					frappe._dict(attribute="Colour", attribute_value="Red"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(primary_attribute="Size")
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
			return variants[name] if doctype == "Item Variant" else item

		with (
			patch(
				"yrp.yrp.doctype.goods_received_note.goods_received_note.get_work_order_defaults",
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
		group_items.assert_called_once_with(normalized, "Goods Received Note")

	def test_non_group_garment_process_consumes_each_received_panel(self):
		variant = "GARMENT-BOTTOM-LEFT-DARK-GREY-45"
		combination = {"major_colour": "Airforce", "major_part": "Top"}
		grn = frappe.get_doc(
			{
				"doctype": "Goods Received Note",
				"against": "Work Order",
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
			return work_order if doctype == "Work Order" else ipd

		original_get_value = frappe.db.get_value

		def get_value(doctype, filters, fieldname, *args, **kwargs):
			if doctype == "Process" and filters == "Printing" and fieldname == "is_group":
				return 0
			return original_get_value(doctype, filters, fieldname, *args, **kwargs)

		with (
			patch("essdee_yrp.garment_grn.frappe.get_cached_doc", side_effect=get_cached_doc),
			patch("essdee_yrp.garment_grn.frappe.db.get_value", side_effect=get_value),
			patch(
				"essdee_yrp.garment_grn._stock_uom_values",
				return_value={"conversion_factor": 1, "stock_uom": "Pieces", "stock_qty": 9},
			),
		):
			calculate_garment_consumption(grn)

		self.assertEqual(len(grn.grn_deliverables), 1)
		consumed = grn.grn_deliverables[0]
		self.assertEqual(consumed.item_variant, variant)
		self.assertEqual(consumed.quantity, 9)
		self.assertEqual(consumed.stock_qty, 9)
		self.assertEqual(consumed.work_order_deliverable, deliverable.name)
		self.assertEqual(consumed.set_combination, combination)

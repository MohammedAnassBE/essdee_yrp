import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from essdee_yrp.stock_entry_hooks import (
	_normalize_completion_row_indexes,
	preserve_dynamic_packing_completion_piece_uom,
	preserve_dynamic_packing_dispatch_piece_uom,
)


class TestStockEntryCustomization(FrappeTestCase):
	EXPECTED_PURPOSES = (
		"Material Issue\n"
		"Material Receipt\n"
		"Send to Warehouse\n"
		"Receive at Warehouse\n"
		"Material Consumed\n"
		"Stock Dispatch\n"
		"DC Completion\n"
		"GRN Completion"
	)

	def test_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Stock Entry", cached=False)
		expected = {
			"cut_panel_movement": ("Link", "Cut Panel Movement"),
			"dispatch_colour_details": ("Long Text", None),
			"includes_packing": ("Check", None),
			"packing_batch_dispatch_json": ("JSON", None),
			"packing_slip": ("Data", None),
			"transfer_supplier": ("Link", "Supplier"),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), definition)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Stock Entry",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta("Stock Entry", cached=False)

		packing_slip = meta.get_field("packing_slip")
		self.assertEqual(packing_slip.depends_on, "eval:doc.purpose == 'Stock Dispatch'")
		self.assertEqual(
			packing_slip.mandatory_depends_on,
			"eval:doc.purpose == 'Stock Dispatch'",
		)
		self.assertEqual(meta.get_field("cut_panel_movement").allow_on_submit, 1)
		self.assertEqual(meta.get_field("includes_packing").default, "0")
		self.assertEqual(meta.get_field("dispatch_colour_details").no_copy, 1)
		self.assertEqual(meta.get_field("dispatch_colour_details").read_only, 1)
		self.assertEqual(meta.get_field("packing_batch_dispatch_json").read_only, 1)

	def test_approved_property_customizations(self):
		meta = frappe.get_meta("Stock Entry", cached=False)

		self.assertEqual(meta.get_field("purpose").options, self.EXPECTED_PURPOSES)
		self.assertEqual(
			meta.get_field("additional_amount").read_only_depends_on,
			"eval: doc.purpose != 'Send to Warehouse'",
		)
		for name in (
			"Stock Entry-additional_amount-read_only_depends_on",
			"Stock Entry-purpose-options",
		):
			self.assertTrue(frappe.db.exists("Property Setter", name))

	def test_base_terms_and_condition_behavior_is_unchanged(self):
		field = frappe.get_meta("Stock Entry", cached=False).get_field(
			"terms_and_condition"
		)
		self.assertEqual(field.fetch_from, "to_supplier.po_terms_and_condition")
		self.assertEqual(field.fetch_if_empty, 1)
		self.assertEqual(field.allow_on_submit, 0)

	def test_completion_rows_receive_distinct_vue_group_indexes(self):
		doc = frappe.new_doc("Stock Entry")
		doc.purpose = "DC Completion"
		for index in range(4):
			doc.append(
				"items",
				{
					"item": f"TEST-VARIANT-{index}",
					"qty": 1,
					"row_index": 0,
				},
			)

		self.assertTrue(_normalize_completion_row_indexes(doc))
		self.assertEqual([row.row_index for row in doc.items], [0, 1, 2, 3])
		self.assertFalse(_normalize_completion_row_indexes(doc))

	def test_normal_stock_entry_indexes_are_not_rewritten(self):
		doc = frappe.new_doc("Stock Entry")
		doc.purpose = "Material Receipt"
		for index in (0, 0):
			doc.append(
				"items",
				{"item": "TEST-VARIANT", "qty": 1, "row_index": index},
			)

		self.assertFalse(_normalize_completion_row_indexes(doc))
		self.assertEqual([row.row_index for row in doc.items], [0, 0])

	def test_dynamic_packing_grn_completion_preserves_physical_piece_uom(self):
		doc = frappe.new_doc("Stock Entry")
		doc.update(
			{
				"purpose": "GRN Completion",
				"against": "Goods Received Note",
				"against_id": "TEST-DYNAMIC-PACKING-GRN",
			}
		)
		row = doc.append(
			"items",
			{
				"item": "TEST-PACKED-VARIANT",
				"qty": 4,
				"uom": "Box",
				"stock_uom": "Pieces",
				"conversion_factor": 12,
				"stock_qty": 48,
				"rate": 175,
				"amount": 700,
				"against_id_detail": "TEST-GRN-ITEM",
			},
		)
		grn = frappe._dict(
			name="TEST-DYNAMIC-PACKING-GRN",
			packing_calculation_version=2,
			includes_packing=1,
			from_finishing=1,
			lot="TEST-LOT",
			items=[
				frappe._dict(
					name="TEST-GRN-ITEM",
					item_variant="TEST-PACKED-VARIANT",
					uom="Pieces",
					stock_uom="Pieces",
				)
			],
		)
		with (
			patch("essdee_yrp.stock_entry_hooks.frappe.get_doc", return_value=grn),
			patch("essdee_yrp.stock_entry_hooks.frappe.db.get_value", return_value="Pieces"),
		):
			self.assertTrue(preserve_dynamic_packing_completion_piece_uom(doc))

		self.assertEqual(row.uom, "Pieces")
		self.assertEqual(row.stock_uom, "Pieces")
		self.assertEqual(row.conversion_factor, 1)
		self.assertEqual(row.qty, 4)
		self.assertEqual(row.stock_qty, 4)
		self.assertEqual(row.amount, 700)
		self.assertEqual(doc.total_amount, 700)

	def test_legacy_packing_completion_keeps_base_uom(self):
		doc = frappe.new_doc("Stock Entry")
		doc.update(
			{
				"purpose": "GRN Completion",
				"against": "Goods Received Note",
				"against_id": "TEST-LEGACY-PACKING-GRN",
			}
		)
		row = doc.append(
			"items",
			{
				"item": "TEST-PACKED-VARIANT",
				"qty": 2,
				"uom": "Box",
				"stock_uom": "Pieces",
				"conversion_factor": 12,
				"stock_qty": 24,
				"rate": 100,
				"against_id_detail": "TEST-GRN-ITEM",
			},
		)
		grn = frappe._dict(
			name="TEST-LEGACY-PACKING-GRN",
			packing_calculation_version=1,
		)
		with patch("essdee_yrp.stock_entry_hooks.frappe.get_doc", return_value=grn):
			self.assertFalse(preserve_dynamic_packing_completion_piece_uom(doc))

		self.assertEqual(row.uom, "Box")
		self.assertEqual(row.conversion_factor, 12)
		self.assertEqual(row.stock_qty, 24)

	def test_dynamic_packing_dispatch_routes_preserve_physical_piece_uom(self):
		for against, against_id, finishing_plan in (
			("Finishing Plan", "TEST-FP", None),
			("Finishing Plan Dispatch", "TEST-FPD", "TEST-FP"),
		):
			with self.subTest(against=against):
				doc = frappe.new_doc("Stock Entry")
				doc.update(
					{
						"purpose": "Material Issue",
						"against": against,
						"against_id": against_id,
						"packing_batch_dispatch_json": frappe.as_json(
							[
								{
									"finishing_plan": finishing_plan,
									"packing_calculation_version": 2,
									"stock_uom": "Pieces",
									"stock_quantities": {"S": 4, "M": 6},
								}
							]
						),
					}
				)
				for item, quantity in (("TEST-PACKED-S", 4), ("TEST-PACKED-M", 6)):
					doc.append(
						"items",
						{
							"item": item,
							"lot": "TEST-LOT",
							"qty": quantity,
							"uom": "Box",
							"stock_uom": "Pieces",
							"conversion_factor": 12,
							"stock_qty": quantity * 12,
							"rate": 175,
						},
					)

				def get_value(doctype, name, fieldname):
					if (doctype, name, fieldname) == ("Finishing Plan", "TEST-FP", "lot"):
						return "TEST-LOT"
					if (doctype, name, fieldname) == ("Lot", "TEST-LOT", "packing_uom"):
						return "Pieces"
					raise AssertionError((doctype, name, fieldname))

				with patch(
					"essdee_yrp.stock_entry_hooks.frappe.db.get_value",
					side_effect=get_value,
				):
					self.assertTrue(preserve_dynamic_packing_dispatch_piece_uom(doc))

				self.assertEqual([row.uom for row in doc.items], ["Pieces", "Pieces"])
				self.assertEqual([row.stock_uom for row in doc.items], ["Pieces", "Pieces"])
				self.assertEqual([row.conversion_factor for row in doc.items], [1, 1])
				self.assertEqual([row.stock_qty for row in doc.items], [4, 6])

	def test_legacy_packing_dispatch_keeps_base_uom(self):
		doc = frappe.new_doc("Stock Entry")
		doc.update(
			{
				"purpose": "Material Issue",
				"against": "Finishing Plan",
				"against_id": "TEST-FP",
				"packing_batch_dispatch_json": frappe.as_json(
					[
						{
							"packing_calculation_version": 1,
							"stock_uom": "Pieces",
							"stock_quantities": {"S": 24},
						}
					]
				),
			}
		)
		row = doc.append(
			"items",
			{
				"item": "TEST-PACKED-S",
				"lot": "TEST-LOT",
				"qty": 2,
				"uom": "Box",
				"stock_uom": "Pieces",
				"conversion_factor": 12,
				"stock_qty": 24,
			},
		)

		self.assertFalse(preserve_dynamic_packing_dispatch_piece_uom(doc))
		self.assertEqual(row.uom, "Box")
		self.assertEqual(row.conversion_factor, 12)
		self.assertEqual(row.stock_qty, 24)

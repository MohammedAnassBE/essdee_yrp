import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
from essdee_yrp.stock_entry_hooks import (
	onload as stock_entry_onload,
	preserve_dynamic_packing_completion_piece_uom,
	preserve_dynamic_packing_dispatch_piece_uom,
)
from essdee_yrp.stock_reconciliation_hooks import onload as stock_reconciliation_onload


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
		meta = frappe.get_meta('YRP Stock Entry', cached=False)
		expected = {
			"cut_panel_movement": ("Link", 'SD YRP Cut Panel Movement'),
			"dispatch_colour_details": ("Long Text", None),
			"includes_packing": ("Check", None),
			"packing_batch_dispatch_json": ("JSON", None),
			"packing_slip": ("Data", None),
			"transfer_supplier": ("Link", 'YRP Supplier'),
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
							"dt": 'YRP Stock Entry',
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta('YRP Stock Entry', cached=False)

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
		meta = frappe.get_meta('YRP Stock Entry', cached=False)

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
		field = frappe.get_meta('YRP Stock Entry', cached=False).get_field(
			"terms_and_condition"
		)
		self.assertEqual(field.fetch_from, "to_supplier.po_terms_and_condition")
		self.assertEqual(field.fetch_if_empty, 1)
		self.assertEqual(field.allow_on_submit, 0)

	def test_stock_entry_onload_uses_logical_item_matrix_projection(self):
		doc = frappe.new_doc('YRP Stock Entry')
		doc.purpose = "Material Receipt"
		for index in (11, 12):
			doc.append(
				"items",
				{"item": f"TEST-VARIANT-{index}", "qty": 1, "row_index": index},
			)

		projected = [frappe._dict(item="TEST-VARIANT-11", row_index="matrix-0000")]
		grouped = [{"primary_attribute": "Size", "items": [{"name": "TEST"}]}]
		with (
			patch(
				"essdee_yrp.item_matrix.normalize_item_matrix_row_indexes",
				return_value=projected,
			) as normalize,
			patch(
				"yrp.stock.save_stock_items.group_items_for_ui",
				return_value=grouped,
			) as group,
		):
			stock_entry_onload(doc)

		normalize.assert_called_once()
		self.assertIs(normalize.call_args.args[0][0], doc.items[0])
		group.assert_called_once_with(projected, 'YRP Stock Entry')
		self.assertEqual(doc.get_onload("item_details"), grouped)
		self.assertEqual([row.row_index for row in doc.items], [11, 12])

	def test_stock_reconciliation_onload_uses_same_logical_projection(self):
		doc = frappe.new_doc('YRP Stock Reconciliation')
		doc.append(
			"items",
			{"item": "TEST-VARIANT", "qty": 1, "row_index": 7},
		)
		projected = [frappe._dict(item="TEST-VARIANT", row_index="matrix-0000")]
		grouped = [{"primary_attribute": "Size", "items": [{"name": "TEST"}]}]
		with (
			patch(
				"essdee_yrp.item_matrix.normalize_item_matrix_row_indexes",
				return_value=projected,
			) as normalize,
			patch(
				"yrp.stock.save_stock_items.group_items_for_ui",
				return_value=grouped,
			) as group,
		):
			stock_reconciliation_onload(doc)

		normalize.assert_called_once()
		self.assertIs(normalize.call_args.args[0][0], doc.items[0])
		group.assert_called_once_with(projected, 'YRP Stock Reconciliation')
		self.assertEqual(doc.get_onload("item_details"), grouped)
		self.assertEqual(doc.items[0].row_index, 7)

	def test_stock_reconciliation_projection_keeps_warehouse_bucket_separate(self):
		variants = {
			"TEST-CUT-45": frappe._dict(
				item="TEST-CUT",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Top Front"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"TEST-CUT-50": frappe._dict(
				item="TEST-CUT",
				attributes=[
					frappe._dict(attribute="Panel", attribute_value="Top Front"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(primary_attribute="Size")

		def get_cached_doc(doctype, name):
			return variants[name] if doctype == 'YRP Item Variant' else item

		rows = [
			frappe._dict(
				item="TEST-CUT-45",
				warehouse="WAREHOUSE-A",
				lot="TEST-LOT",
				received_type="Accepted",
			),
			frappe._dict(
				item="TEST-CUT-50",
				warehouse="WAREHOUSE-A",
				lot="TEST-LOT",
				received_type="Accepted",
			),
			frappe._dict(
				item="TEST-CUT-45",
				warehouse="WAREHOUSE-B",
				lot="TEST-LOT",
				received_type="Accepted",
			),
		]
		with (
			patch(
				"essdee_yrp.item_matrix.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"essdee_yrp.item_matrix.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			normalized = normalize_item_matrix_row_indexes(rows)

		self.assertEqual(normalized[0].row_index, normalized[1].row_index)
		self.assertNotEqual(normalized[0].row_index, normalized[2].row_index)

	def test_dynamic_packing_grn_completion_preserves_physical_piece_uom(self):
		doc = frappe.new_doc('YRP Stock Entry')
		doc.update(
			{
				"purpose": "GRN Completion",
				"against": 'YRP Goods Received Note',
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
		doc = frappe.new_doc('YRP Stock Entry')
		doc.update(
			{
				"purpose": "GRN Completion",
				"against": 'YRP Goods Received Note',
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
			('SD YRP Finishing Plan', "TEST-FP", None),
			('SD YRP Finishing Plan Dispatch', "TEST-FPD", "TEST-FP"),
		):
			with self.subTest(against=against):
				doc = frappe.new_doc('YRP Stock Entry')
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
					if (doctype, name, fieldname) == ('SD YRP Finishing Plan', "TEST-FP", "lot"):
						return "TEST-LOT"
					if (doctype, name, fieldname) == ('SD YRP Lot', "TEST-LOT", "packing_uom"):
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
		doc = frappe.new_doc('YRP Stock Entry')
		doc.update(
			{
				"purpose": "Material Issue",
				"against": 'SD YRP Finishing Plan',
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

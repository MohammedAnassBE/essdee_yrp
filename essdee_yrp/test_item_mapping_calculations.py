from unittest import TestCase
from unittest.mock import patch

import frappe
from yrp.attribute_values import ensure_value_master, get_mapping_values
from yrp.stock.test_uom import _attribute, _ensure_uom, _india_compliance_item_fields, _item_group
from yrp.yrp.doctype.yrp_item.yrp_item import ensure_global_attribute_values
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	calculate_major_deliverables,
)
from yrp.yrp.utils.ipd_engine import calculate_bom_for_variant_demands

from essdee_yrp.api.work_order import _resolve_variant
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import calculate_bom
from essdee_yrp.garment_work_order import _cutting_inputs


class TestItemMappingCalculations(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.savepoint = "mapping_calculation_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(self.savepoint)
		self.suffix = frappe.generate_hash(length=8)
		self.attribute = "_Test Calculation Colour " + self.suffix
		self.outside_value = "Blue " + self.suffix
		mapping = _attribute(self.attribute, "Red " + self.suffix)
		ensure_global_attribute_values(self.attribute, [self.outside_value], check_permission=False)
		mapping_doc = frappe.get_doc("YRP Item Item Attribute Mapping", mapping)
		mapping_doc.append("values", {"attribute_value": self.outside_value})
		mapping_doc.save(ignore_permissions=True)
		self.input_item = self._item(
			"Input",
			has_variants=1,
			attributes=[
				{
					"attribute": self.attribute,
					"mapping": mapping,
				}
			],
		)
		self.mapping = frappe.get_doc("Item", self.input_item).attributes[0].mapping
		mapping_doc = frappe.get_doc("YRP Item Item Attribute Mapping", self.mapping)
		mapping_doc.set("values", mapping_doc.values[:1])
		mapping_doc.save(ignore_permissions=True)
		self.output_item = self._item("Output")
		self.process = "_Test Calculation Process " + self.suffix
		self.ipd = self._persist(
			{
				"doctype": "YRP Item Production Detail",
				"name": "_Test Calculation IPD " + self.suffix,
				"item": self.output_item,
			}
		)
		self.matrix = self._persist(
			{
				"doctype": "YRP IPD Process Matrix",
				"name": "_Test Calculation Matrix " + self.suffix,
				"ipd": self.ipd.name,
				"process_name": self.process,
				"reference_item_variant": self.output_item,
				"input_item": self.input_item,
				"output_item": self.output_item,
				"combinations": [
					{"group_index": 0, "side": "Input", "combo_index": 0, "quantity": 2, "uom": "Piece"},
					{"group_index": 0, "side": "Output", "combo_index": 0, "quantity": 1, "uom": "Piece"},
				],
				"combination_attributes": [
					{
						"group_index": 0,
						"side": "Input",
						"combo_index": 0,
						"attribute": self.attribute,
						"attribute_value": ensure_value_master(self.attribute, self.outside_value),
					}
				],
			}
		)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)

	def test_matrix_bom_accepts_value_removed_from_item_picklist(self):
		result = calculate_bom_for_variant_demands(
			self.ipd.name,
			[
				{
					"item_variant": self.output_item,
					"qty": 3,
				}
			],
		)

		self._assert_input(result["major_deliverables"][0], 6)

	def test_matrix_bom_keeps_empty_picklist_unrestricted(self):
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", self.mapping)
		mapping.set("values", [])
		mapping.save(ignore_permissions=True)

		result = calculate_bom_for_variant_demands(
			self.ipd.name,
			[
				{
					"item_variant": self.output_item,
					"qty": 4,
				}
			],
		)

		self._assert_input(result["major_deliverables"][0], 8)

	def test_lot_calculate_bom_accepts_value_removed_from_item_picklist(self):
		lot = frappe.get_doc(
			{
				"doctype": "SD YRP Lot",
				"name": "_Test Calculation Lot " + self.suffix,
				"production_detail": self.ipd.name,
				"docstatus": 0,
				"total_order_quantity": 3,
				"uom": "Piece",
				"lot_order_details": [{"item_variant": self.output_item, "quantity": 3}],
			}
		)
		get_doc = frappe.get_doc

		def load_doc(doctype, name=None, *args, **kwargs):
			if doctype == "SD YRP Lot" and name == lot.name:
				return lot
			if name is None:
				return get_doc(doctype, *args, **kwargs)
			return get_doc(doctype, name, *args, **kwargs)

		with (
			patch.object(frappe, "get_doc", side_effect=load_doc),
			patch.object(lot, "save", return_value=lot),
		):
			result = calculate_bom(lot.name)

		self.assertEqual(len(result["bom_summary"]), 1)
		row = result["bom_summary"][0]
		self.assertEqual(row["required_qty"], 6)
		self._assert_variant(row["item_name"])
		self.assertEqual(lot.bom_summary[0].required_qty, 6)

	def test_cutting_work_order_accepts_value_removed_from_item_picklist(self):
		rows = _cutting_inputs(
			self.ipd,
			self.process,
			[
				{
					"item_variant": self.output_item,
					"qty": 5,
				}
			],
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["qty"], 10)
		self._assert_variant(rows[0]["item_variant"])

	def test_core_deliverable_calculator_accepts_value_removed_from_item_picklist(self):
		rows = calculate_major_deliverables(
			self.ipd.name,
			[
				{
					"item_variant": self.output_item,
					"qty": 7,
				}
			],
			process_names=[self.process],
		)

		self.assertEqual(len(rows), 1)
		self._assert_input(rows[0], 14)

	def test_fabric_work_order_accepts_value_removed_from_item_picklist(self):
		variant = _resolve_variant(self.input_item, {self.attribute: self.outside_value})

		self._assert_variant(variant)

	def _assert_input(self, row, quantity):
		self.assertEqual(row["required_qty"], quantity)
		self.assertEqual(row["attrs"], {self.attribute: self.outside_value})
		self._assert_variant(row["item_variant"])

	def _assert_variant(self, name):
		variant = frappe.get_doc("Item", name)
		self.assertEqual(variant.variant_of, self.input_item)
		self.assertEqual(variant.attributes[0].display_name, self.outside_value)
		self.assertNotIn(self.outside_value, get_mapping_values(self.mapping))

	def _item(self, label, **fields):
		code = "_Test Calculation " + label + " " + self.suffix
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": _item_group(),
					"stock_uom": _ensure_uom("Piece"),
					"is_stock_item": 1,
					**_india_compliance_item_fields(),
					**fields,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _persist(self, data):
		doc = frappe.get_doc(data)
		doc.db_insert()
		for child in doc.get_all_children():
			child.db_insert()
		return doc

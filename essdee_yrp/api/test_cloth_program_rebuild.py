"""Rebuilds preserve GRN actual-Dia receipts and synced excess ownership."""

from unittest.mock import call, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.attribute_links import value as _attribute_value

from essdee_yrp import fabric_tracking
from essdee_yrp.api import cloth_program
from essdee_yrp.api.test_cloth_program import (
	_ensure_iav,
	_ensure_item,
	_ensure_process,
	_reset_cpd,
)


class TestClothProgramRebuild(IntegrationTestCase):
	def setUp(self):
		self.dia14 = _ensure_iav("Dia", "ZZ TEST 14 Dia")
		self.actual_dia = _ensure_iav("Dia", "ZZ TEST 14.5 Dia")
		self.dia19 = _ensure_iav("Dia", "ZZ TEST 19 Dia")
		self.white = _ensure_iav("Colour", "ZZ TEST White")
		self.greige = _ensure_iav("Colour", "ZZ TEST Greige")
		self.yarn = _ensure_item("ZZ TEST Rebuild Yarn")
		self.cloth = _ensure_item("ZZ TEST Rebuild Cloth")
		cloth_item = frappe.get_doc("Item", self.cloth)
		if not cloth_item.has_variants:
			cloth_item.has_variants = 1
			cloth_item.variant_based_on = "Item Attribute"
			cloth_item.set(
				"attributes",
				[
					{"attribute": "Dia"},
					{"attribute": "Colour"},
				],
			)
			cloth_item.save(ignore_permissions=True)
		frappe.db.set_value("Item", self.cloth, "is_cloth_item", 1)
		frappe.db.delete(
			"SD YRP Item Yarn Ratio",
			{
				"parent": self.cloth,
				"parenttype": "Item",
				"parentfield": "yarn_ratio_details",
			},
		)
		frappe.clear_document_cache("Item", self.cloth)
		_reset_cpd(self.cloth)
		self.selection = {
			"cloth_item": self.cloth,
			"yarn_item": self.yarn,
			"knitting_process": _ensure_process("ZZ TEST Rebuild Knit", is_item_conversion=1),
			"dyeing_process": _ensure_process("ZZ TEST Rebuild Dye"),
			"compacting_process": None,
			"cloth_per_kg_yarn": 3.0,
			"greige_colour": self.greige,
		}
		self.lot = frappe.get_doc(
			{
				"doctype": "SD YRP Lot",
				"lot_name": f"ZZ TEST {self._testMethodName}",
				"cloth_excess_percentage": 0,
			}
		).insert(ignore_permissions=True)
		demand = {
			(self.cloth, self.dia14, self.white): 496,
			(self.cloth, self.dia19, self.white): 327.6,
		}
		self.enterContext(patch.object(cloth_program, "compute_cloth_demand", return_value=demand))
		cloth_program.build_cloth_programs(self.lot.name, [self.selection])
		self.assertEqual(
			{dia: flt(row.weight) for dia, row in self._rows().items()},
			{self.dia14: 496, self.dia19: 328},
		)

	def _rows(self):
		return {
			_attribute_value(row.dia): row
			for row in frappe.get_all(
				"SD YRP Lot Fabric Program",
				filters={"parent": self.lot.name},
				fields=["name", "dia", "reference_item_variant", "weight", "received_weight"],
			)
		}

	def _receive(self, received19=30):
		self.lot.reload()
		rows = self._rows()
		ref14 = rows[self.dia14].reference_item_variant
		ref19 = rows[self.dia19].reference_item_variant
		self.assertTrue(ref14)
		self.assertTrue(ref19)
		fabric_tracking._bump_program_rows(
			self.lot,
			"lot_fabric_programs",
			"SD YRP Lot Fabric Program",
			self.cloth,
			{
				(_attribute_value(self.dia14), ref14): 30,
				(_attribute_value(self.actual_dia), ref14): 20,
				(_attribute_value(self.dia19), ref19): received19,
			},
			1,
			"received_weight",
		)
		actual = self._rows()[self.actual_dia]
		self.assertEqual((actual.reference_item_variant, flt(actual.weight)), (ref14, 0))

	def _assert_program(self, weight14, weight19, received19=30):
		rows = self._rows()
		self.assertEqual(
			{dia: (flt(row.weight), flt(row.received_weight)) for dia, row in rows.items()},
			{
				self.dia14: (weight14, 30),
				self.actual_dia: (0, 20),
				self.dia19: (weight19, received19),
			},
		)
		self.assertEqual(sum(flt(row.weight) for row in rows.values()), weight14 + weight19)

	def test_rebuild_preserves_actual_dia_receipts(self):
		self._receive()
		cloth_program.build_cloth_programs(self.lot.name, [self.selection])
		self._assert_program(496, 328)

	def test_recalculate_preserves_actual_dia_receipts(self):
		self._receive()
		cloth_program.recalculate_cloth_program(self.lot.name)
		self._assert_program(496, 328)

	def test_rebuild_reseeds_unreceived_rows_with_changed_excess(self):
		self._receive(received19=0)
		old_name = self._rows()[self.dia19].name
		cloth_program.build_cloth_programs(self.lot.name, [self.selection], excess_percentage=10)
		self._assert_program(546, 360, received19=0)
		self.assertNotEqual(self._rows()[self.dia19].name, old_name)
		self.assertFalse(frappe.db.exists("SD YRP Lot Fabric Program", old_name))

	def test_popup_excess_does_not_replace_synced_excess(self):
		self._receive()
		cloth_program.build_cloth_programs(self.lot.name, [self.selection], excess_percentage=5)
		self._assert_program(521, 344)
		self.lot.reload()
		self.assertEqual(flt(self.lot.cloth_excess_percentage), 0)

	def test_recalculate_uses_synced_excess(self):
		self._receive()
		cloth_program.build_cloth_programs(self.lot.name, [self.selection], excess_percentage=5)
		frappe.db.set_value("SD YRP Lot", self.lot.name, "cloth_excess_percentage", 7.5)
		cloth_program.recalculate_cloth_program(self.lot.name)
		self._assert_program(533, 352)
		self.lot.reload()
		self.assertEqual(flt(self.lot.cloth_excess_percentage), 7.5)

	def test_route_additions_are_not_duplicated_on_actual_dia(self):
		self._receive()
		frappe.db.set_value(
			"SD YRP Lot",
			self.lot.name,
			"cloth_program_additions",
			frappe.as_json(
				{
					"routes": [
						{
							"cloth_item": self.cloth,
							"dia": self.dia14,
							"colour": self.white,
							"additional_weight": 4,
						}
					]
				}
			),
		)
		cloth_program.build_cloth_programs(self.lot.name, [self.selection], excess_percentage=5)
		self._assert_program(525, 344)
		frappe.db.set_value("SD YRP Lot", self.lot.name, "cloth_excess_percentage", 5)
		cloth_program.recalculate_cloth_program(self.lot.name)
		self._assert_program(525, 344)

	def test_final_pass_keeps_seeded_dia_changes_and_rows_without_reference(self):
		ref14 = self._rows()[self.dia14].reference_item_variant
		rows = [
			frappe._dict(
				name="seeded-dia-change",
				cloth_item=self.cloth,
				dia=self.actual_dia,
				reference_item_variant=ref14,
				weight=496,
			),
			frappe._dict(
				name="no-reference",
				cloth_item=self.cloth,
				dia=self.dia19,
				colour=self.white,
				reference_item_variant=None,
				weight=0,
			),
		]
		with (
			patch.object(self.lot, "save"),
			patch.object(cloth_program.attribute_db, "get_all", return_value=rows),
			patch.object(cloth_program.attribute_db, "set_value") as set_value,
		):
			cloth_program._update_cloth_program_quantities(
				self.lot,
				{self.cloth: {(self.dia14, self.white): 496, (self.dia19, self.white): 327.6}},
				10,
				{},
			)
		self.assertEqual(
			set_value.call_args_list,
			[
				call("SD YRP Lot Fabric Program", "seeded-dia-change", "weight", 546, update_modified=False),
				call("SD YRP Lot Fabric Program", "no-reference", "weight", 360, update_modified=False),
			],
		)

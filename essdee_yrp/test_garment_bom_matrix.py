from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import garment_bom_matrix
from essdee_yrp.garment_bom_matrix import _build_matrix


class TestGarmentBomMatrix(TestCase):
	def test_matrix_keeps_cloth_inputs_and_finished_variant_output(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Finished Item",
			cutting_process="_Test Cutting",
			dependent_attribute="Stage",
			item_attributes=[
				frappe._dict(attribute="Colour"),
				frappe._dict(attribute="Size"),
				frappe._dict(attribute="Stage"),
			],
		)
		cloth_item = frappe._dict(
			attributes=[
				frappe._dict(attribute="Colour"),
				frappe._dict(attribute="Dia"),
			]
		)
		rows = [
			{
				"item": "_Test Cloth",
				"attrs": {"Colour": "Red", "Dia": "20"},
				"quantity": 0.25,
				"uom": "Kg",
			}
		]

		real_get_value = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			if doctype == "Item":
				return "Pieces"
			return real_get_value(doctype, *args, **kwargs)

		with (
			patch.object(frappe, "get_cached_doc", return_value=cloth_item),
			patch.object(frappe.db, "get_value", side_effect=get_value),
		):
			matrix = _build_matrix(
				ipd,
				"_Test Finished Variant",
				{"Colour": "Red", "Size": "M", "Stage": "Packed"},
				"_Test Cloth",
				rows,
			)

		self.assertEqual(matrix.reference_item_variant, "_Test Finished Variant")
		self.assertEqual(matrix.input_item, "_Test Cloth")
		self.assertEqual(matrix.output_item, "_Test Finished Item")
		self.assertEqual(matrix.combinations[0].side, "Input")
		self.assertEqual(matrix.combinations[0].quantity, 0.25)
		self.assertEqual(matrix.combinations[1].side, "Output")
		self.assertEqual(matrix.combinations[1].quantity, 1)
		self.assertEqual(
			{row.attribute for row in matrix.output_attributes},
			{"Colour", "Size"},
		)

	def test_output_only_matrix_supports_an_ipd_without_bom_cloth(self):
		ipd = frappe._dict(
			name="_Test Accessory Only IPD",
			item="_Test Finished Item",
			cutting_process="_Test Cutting",
			dependent_attribute="Stage",
			item_attributes=[frappe._dict(attribute="Colour")],
		)

		real_get_value = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			if doctype == "Item":
				return "Pieces"
			return real_get_value(doctype, *args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=get_value):
			matrix = _build_matrix(
				ipd,
				"_Test Finished Variant",
				{"Colour": "Red", "Stage": "Packed"},
				None,
				[],
			)

		self.assertFalse(matrix.input_item)
		self.assertEqual(len(matrix.combinations), 1)
		self.assertEqual(matrix.combinations[0].side, "Output")


class TestEnsureGarmentBomMatrices(TestCase):
	def ensure(self, existing, on_demand=True):
		with (
			patch.object(garment_bom_matrix, "is_on_demand_garment_ipd", return_value=on_demand),
			patch.object(frappe.db, "get_value", return_value="_Test Cutting") as get_value,
			patch.object(frappe, "get_all", return_value=existing) as get_all,
			patch.object(
				garment_bom_matrix, "regenerate_garment_bom_matrices", return_value=["M-NEW"]
			) as regenerate,
		):
			result = garment_bom_matrix.ensure_garment_bom_matrices("IPD-1", ["V-1", "V-2", "V-1"])
		return result, get_value, get_all, regenerate

	def test_generates_only_variants_without_a_matrix(self):
		result, get_value, get_all, regenerate = self.ensure(["V-1"])
		self.assertEqual(result, ["M-NEW"])
		regenerate.assert_called_once_with("IPD-1", ["V-2"])
		get_value.assert_called_once_with("YRP Item Production Detail", "IPD-1", "cutting_process")
		self.assertEqual(get_all.call_args.kwargs["filters"]["process_name"], "_Test Cutting")

	def test_keeps_existing_matrices(self):
		result, _get_value, _get_all, regenerate = self.ensure(["V-1", "V-2"])
		self.assertEqual(result, [])
		regenerate.assert_not_called()

	def test_skips_cloth_or_incomplete_ipds(self):
		result, get_value, get_all, regenerate = self.ensure([], on_demand=False)
		self.assertEqual(result, [])
		get_value.assert_not_called()
		get_all.assert_not_called()
		regenerate.assert_not_called()


class TestUnbuildableVariants(TestCase):
	def test_reports_failing_and_empty_variants_without_leaking_messages(self):
		ipd = frappe._dict(cloth_detail=[frappe._dict(is_bom_item=1)])

		def cloth_rows(_ipd, variant):
			if variant == "V-BAD":
				frappe.throw("Missing mapping")
			return ([{"item": "Cloth"}] if variant == "V-OK" else []), {}

		frappe.local.message_log = []
		with (
			patch.object(garment_bom_matrix, "_validate_garment_ipd"),
			patch.object(garment_bom_matrix, "_get_variant_cloth_rows", side_effect=cloth_rows),
		):
			skipped = garment_bom_matrix.get_unbuildable_variants(ipd, ["V-OK", "V-BAD", "V-EMPTY"])

		self.assertEqual(
			skipped,
			[
				{"item_variant": "V-BAD", "reason": "Missing mapping"},
				{"item_variant": "V-EMPTY", "reason": "No BOM cloth requirement was generated."},
			],
		)
		self.assertEqual(frappe.message_log, [])


class TestOnDemandGarmentMatricesOnMigratedData(IntegrationTestCase):
	"""Migrated Lot C0126-05 (garment IPD, Open, draft) builds its Cutting matrices on first use."""

	lot = "C0126-05"

	def setUp(self):
		self.ipd = frappe.db.get_value("SD YRP Lot", self.lot, "production_detail")
		if not self.ipd or not garment_bom_matrix.is_on_demand_garment_ipd(self.ipd):
			self.skipTest(f"Migration oracle {self.lot} is unavailable")
		garment_bom_matrix.clear_generated_matrices(frappe.get_doc("YRP Item Production Detail", self.ipd))
		self.variants = frappe.get_all(
			"SD YRP Lot Order Detail",
			filters={"parent": self.lot, "quantity": [">", 0]},
			pluck="item_variant",
		)

	def matrix_count(self):
		return frappe.db.count("YRP IPD Process Matrix", {"ipd": self.ipd})

	def test_first_use_builds_once_and_ipd_update_clears(self):
		self.assertEqual(self.matrix_count(), 0)
		created = garment_bom_matrix.ensure_garment_bom_matrices(self.ipd, self.variants)
		self.assertTrue(created)
		self.assertEqual(self.matrix_count(), len(created))
		self.assertEqual(garment_bom_matrix.ensure_garment_bom_matrices(self.ipd, self.variants), [])
		self.assertEqual(self.matrix_count(), len(created))
		garment_bom_matrix.clear_generated_matrices(frappe.get_doc("YRP Item Production Detail", self.ipd))
		self.assertEqual(self.matrix_count(), 0)

	def test_lot_calculate_bom_starts_from_no_matrix(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import calculate_bom
		from essdee_yrp.merch.lot_workspace import get_bom_block

		self.assertEqual(get_bom_block(frappe.get_doc("SD YRP Lot", self.lot)), "")
		result = calculate_bom(self.lot)
		self.assertTrue(result["bom_summary"])
		self.assertGreater(self.matrix_count(), 0)

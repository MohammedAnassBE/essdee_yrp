# Copyright (c) 2024, Essdee and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.lot.lot import calculate_bom, get_ocr_details


class TestLot(FrappeTestCase):
	def test_calculate_bom_uses_shared_matrix_engine_and_saves_lot(self):
		lot = frappe._dict(
			name="_Test Matrix Lot",
			production_detail="_Test Matrix IPD",
			docstatus=0,
			total_order_quantity=10,
			uom="Nos",
			lot_order_details=[
				frappe._dict(item_variant="_Test Finished Variant", quantity=10),
			],
		)
		lot.check_permission = lambda *_args, **_kwargs: None
		lot.set = lambda fieldname, value: setattr(lot, fieldname, value)
		lot.save = lambda *_args, **_kwargs: None
		calculation = {
			"major_deliverables": [
				{
					"item_variant": "_Test Cloth Variant",
					"process_name": "_Test Cutting",
					"uom": "Kg",
					"required_qty": 2.5,
				},
			],
			"accessories": [
				{
					"item_variant": "_Test Thread Variant",
					"process_name": "_Test Stitching",
					"uom": "Kg",
					"required_qty": 0.5,
				},
			],
		}

		with (
			patch.object(frappe, "get_doc", return_value=lot),
			patch(
				"essdee_yrp.essdee_yrp.doctype.lot.lot.calculate_bom_for_variant_demands",
				return_value=calculation,
			) as shared_calculator,
			patch(
				"essdee_yrp.essdee_yrp.doctype.lot.lot.calculate_essdee_accessory_bom",
				return_value=calculation["accessories"],
			) as essdee_accessory_calculator,
			patch(
				"essdee_yrp.essdee_yrp.doctype.lot.lot.now_datetime",
				return_value="2026-08-14 12:00:00",
			),
		):
			result = calculate_bom(lot.name)

		shared_calculator.assert_called_once_with(
			"_Test Matrix IPD",
			[{"item_variant": "_Test Finished Variant", "qty": 10.0}],
		)
		essdee_accessory_calculator.assert_called_once_with(
			"_Test Matrix IPD",
			[{"item_variant": "_Test Finished Variant", "qty": 10.0}],
			lot,
		)
		self.assertEqual(len(lot.bom_summary), 2)
		self.assertEqual(lot.bom_summary[0]["item_name"], "_Test Cloth Variant")
		self.assertEqual(lot.bom_summary_json["_Test Cloth Variant"][3], 0.25)
		self.assertEqual(result["last_calculated_time"], "2026-08-14 12:00:00")

	def test_ocr_details_does_not_require_f15_plan_doctypes(self):
		def get_all(doctype, *args, **kwargs):
			if doctype == "Work Order":
				return ["_Test OCR Work Order"]
			if doctype == "Goods Received Note":
				return []
			self.fail(f"Unexpected DocType query: {doctype}")

		work_order = frappe._dict(
			includes_packing=0,
			process_name="_Test OCR Process",
			work_order_calculated_items=[],
		)
		grn_meta = frappe._dict(has_field=lambda _fieldname: False)

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(
				frappe,
				"get_value",
				side_effect=[
					("_Test OCR IPD", "_Test OCR Item"),
					("_Test OCR Sewing", "Size", 1),
				],
			),
			patch.object(frappe, "get_doc", return_value=work_order),
			patch.object(frappe, "get_meta", return_value=grn_meta),
		):
			result = get_ocr_details("_Test OCR Lot")

		self.assertEqual(
			result["processes"]["_Test OCR Process"]["cp_list"],
			[],
		)

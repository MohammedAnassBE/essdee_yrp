# Copyright (c) 2024, Essdee and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.lot.lot import calculate_bom, get_ocr_details
from essdee_yrp.fabric_program import SERVER_OWNED_TABLES, refresh_server_owned_tables


class TestLot(FrappeTestCase):
	def test_server_owned_refresh_locks_lot_before_reading_children(self):
		lot = frappe._dict(name="LOT-1")
		lot.flags = frappe._dict()
		lot.is_new = lambda: False
		lot.set = lambda fieldname, value: dict.__setitem__(lot, fieldname, value)
		lot.append = lambda _fieldname, _value: None
		with (
			patch("essdee_yrp.fabric_program.frappe.db.sql") as lock,
			patch(
				"essdee_yrp.fabric_program.frappe.db.get_values", return_value=[]
			) as get_values,
		):
			refresh_server_owned_tables(lot)
			refresh_server_owned_tables(lot)

		lock.assert_called_once_with(
			"SELECT name FROM `tabLot` WHERE name = %s FOR UPDATE",
			("LOT-1",),
		)
		self.assertEqual(get_values.call_count, len(SERVER_OWNED_TABLES) * 2)
		self.assertTrue(all(
			call.kwargs.get("for_update") is True
			for call in get_values.call_args_list
		))

	def test_stale_lot_save_preserves_server_owned_fabric_conversions(self):
		suffix = frappe.generate_hash(length=8)
		lot = frappe.get_doc({
			"doctype": "Lot",
			"lot_name": f"_Test Conversion Refresh {suffix}",
		}).insert(ignore_permissions=True)
		stale = frappe.get_doc("Lot", lot.name)

		row = frappe.new_doc("Lot Fabric Conversion")
		row.parent = lot.name
		row.parenttype = "Lot"
		row.parentfield = "lot_fabric_conversions"
		row.idx = 1
		row.process_name = f"_Test Process {suffix}"
		row.from_item = f"_Test Planned {suffix}"
		row.to_item = f"_Test Actual {suffix}"
		row.to_qty = 7
		row.db_insert()

		# Simulate a form opened before the GRN-side direct child insert. The Lot
		# hook must reload the server-owned table before Frappe syncs children.
		stale.flags.ignore_links = True
		stale.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value(
				"Lot Fabric Conversion",
				{
					"parent": lot.name,
					"parentfield": "lot_fabric_conversions",
				},
				"to_qty",
			),
			7,
		)

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

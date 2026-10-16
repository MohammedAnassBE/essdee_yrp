# Copyright (c) 2024, Essdee and Contributors
# See license.txt

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.fabric_program import SERVER_OWNED_TABLES, refresh_server_owned_tables
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import Lot, calculate_bom, get_ocr_details


class TestLot(FrappeTestCase):
	def test_actual_dia_conversion_fields_are_read_only_desk_state(self):
		path = Path(__file__).with_name("sd_yrp_lot.json")
		schema = json.loads(path.read_text(encoding="utf-8"))
		fields = {row["fieldname"]: row for row in schema["fields"]}

		self.assertEqual(fields["actual_dia_conversion_tab"]["fieldtype"], "Tab Break")
		self.assertEqual(fields["actual_dia_conversion_html"]["fieldtype"], "HTML")
		self.assertEqual(fields["lot_fabric_conversions"]["options"], "SD YRP Lot Fabric Conversion")
		self.assertTrue(fields["lot_fabric_conversions"]["hidden"])
		self.assertTrue(fields["lot_fabric_conversions"]["read_only"])

	def test_piece_quantities_derive_read_only_box_quantities(self):
		lot = SimpleNamespace(
			production_detail="_Test Packing IPD",
			lot_order_details=[
				frappe._dict(item_variant="PIECE-S", quantity=25),
				frappe._dict(item_variant="PIECE-M", quantity=12),
			],
			items=[
				frappe._dict(item_variant="BOX-S", qty=99),
				frappe._dict(item_variant="BOX-M", qty=99),
			],
			flags=frappe._dict(),
		)
		ipd = frappe._dict(
			packing_combo=12,
			is_set_item=0,
			primary_item_attribute="Size",
		)
		attributes = {
			"PIECE-S": {"Size": "S"},
			"PIECE-M": {"Size": "M"},
			"BOX-S": {"Size": "S"},
			"BOX-M": {"Size": "M"},
		}
		with (
			patch.object(frappe, "get_cached_doc", return_value=ipd),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_variant_attr_details",
				side_effect=lambda variant: attributes[variant],
			),
		):
			Lot.derive_items_from_order_details(lot)

		self.assertEqual([row.qty for row in lot.items], [3, 1])
		self.assertTrue(lot.flags.items_derived)

	def test_box_table_does_not_expose_edit_actions(self):
		source = (
			Path(frappe.get_app_path("essdee_yrp")) / "public/js/Lot/components/LotOrder.vue"
		).read_text(encoding="utf-8")
		self.assertNotIn(">Edit<", source)
		self.assertNotIn('@click="edit_item', source)
		self.assertNotIn('@click="delete_item', source)

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
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.calculate_bom_for_variant_demands",
				return_value=calculation,
			) as shared_calculator,
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.calculate_essdee_accessory_bom",
				return_value=calculation["accessories"],
			) as essdee_accessory_calculator,
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.now_datetime",
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

	def test_ocr_details_uses_migrated_cutting_and_finishing_plans(self):
		def get_all(doctype, *args, **kwargs):
			if doctype == "YRP Work Order":
				return ["_Test OCR Work Order"]
			if doctype == "SD YRP Cutting Plan":
				return ["_Test OCR Cutting Plan"]
			if doctype == "YRP Goods Received Note":
				return ["_Test OCR GRN"]
			if doctype == "SD YRP Finishing Plan":
				return ["_Test OCR Finishing Plan"]
			self.fail(f"Unexpected DocType query: {doctype}")

		work_order = frappe._dict(
			includes_packing=1,
			process_name="_Test OCR Process",
			work_order_calculated_items=[
				frappe._dict(item_variant="_Test OCR Variant", delivered_quantity=12, received_qty=10),
			],
		)
		packing_grn = SimpleNamespace(
			packing_calculation_version=2,
			items=[frappe._dict(item_variant="_Test OCR Variant", quantity=10)],
		)
		packing_grn.get = lambda fieldname: getattr(packing_grn, fieldname, None)
		lot = SimpleNamespace(name="_Test OCR Lot", checked_permissions=[])
		lot.check_permission = lot.checked_permissions.append
		finishing_plan = frappe._dict(
			work_order="_Test OCR Packing Work Order",
			pieces_per_box=10,
			finishing_plan_grn_details=[
				frappe._dict(item_variant="_Test OCR Variant", dispatched=3),
			],
		)
		grn_meta = frappe._dict(has_field=lambda _fieldname: False)
		documents = {
			"_Test OCR Lot": lot,
			"_Test OCR Work Order": work_order,
			"_Test OCR GRN": packing_grn,
			"_Test OCR Finishing Plan": finishing_plan,
		}

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(
				frappe,
				"get_value",
				side_effect=[
					("_Test OCR IPD", "_Test OCR Item"),
					("_Test OCR Sewing", "Size", 10),
				],
			),
			patch.object(frappe, "get_doc", side_effect=lambda _doctype, name: documents[name]),
			patch.object(frappe, "get_meta", return_value=grn_meta),
			patch.object(frappe.db, "exists", return_value=False),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_variant_attr_details",
				return_value={"Size": "S"},
			),
		):
			result = get_ocr_details("_Test OCR Lot")

		self.assertEqual(result["sizes"], ["S"])
		self.assertEqual(lot.checked_permissions, ["read"])
		self.assertEqual(result["processes"]["_Test OCR Process"]["cp_list"], ["_Test OCR Cutting Plan"])
		self.assertEqual(result["processes"]["_Test OCR Process"]["total_received"], 10)
		self.assertEqual(result["finishing_plan_list"], ["_Test OCR Finishing Plan"])
		self.assertEqual(result["dispatch_detail"], {"S": 30})
		self.assertEqual(result["total_dispatch"], 30)

	def test_ocr_details_keeps_finishing_data_without_a_submitted_work_order(self):
		lot = SimpleNamespace(name="_Test Finishing Only Lot", checked_permissions=[])
		lot.check_permission = lot.checked_permissions.append
		finishing_plan = frappe._dict(
			work_order=None,
			pieces_per_box=10,
			finishing_plan_grn_details=[
				frappe._dict(item_variant="_Test Finishing Variant", dispatched=2),
			],
		)

		def get_all(doctype, *args, **kwargs):
			if doctype == "YRP Work Order":
				return []
			if doctype == "SD YRP Finishing Plan":
				return ["_Test Finishing Plan"]
			self.fail(f"Unexpected DocType query: {doctype}")

		def get_doc(_doctype, name):
			return lot if name == lot.name else finishing_plan

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(
				frappe,
				"get_value",
				side_effect=[
					("_Test Finishing IPD", "_Test Finishing Item"),
					("_Test Sewing", "Size", 10),
				],
			),
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.get_variant_attr_details",
				return_value={"Size": "M"},
			),
		):
			result = get_ocr_details(lot.name)

		self.assertEqual(lot.checked_permissions, ["read"])
		self.assertEqual(result["processes"], {})
		self.assertEqual(result["sizes"], ["M"])
		self.assertEqual(result["finishing_plan_list"], ["_Test Finishing Plan"])
		self.assertEqual(result["dispatch_detail"], {"M": 20})
		self.assertEqual(result["total_dispatch"], 20)

	def test_ocr_details_rejects_an_unreadable_lot(self):
		lot = SimpleNamespace(check_permission=Mock(side_effect=frappe.PermissionError))
		with patch.object(frappe, "get_doc", return_value=lot):
			with self.assertRaises(frappe.PermissionError):
				get_ocr_details("_Test Restricted Lot")
		lot.check_permission.assert_called_once_with("read")

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
			"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE",
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
			"doctype": "SD YRP Lot",
			"lot_name": f"_Test Conversion Refresh {suffix}",
		}).insert(ignore_permissions=True)
		stale = frappe.get_doc("SD YRP Lot", lot.name)

		row = frappe.new_doc("SD YRP Lot Fabric Conversion")
		row.parent = lot.name
		row.parenttype = "SD YRP Lot"
		row.parentfield = "lot_fabric_conversions"
		row.idx = 1
		row.process_name = f"_Test Process {suffix}"
		row.planned_item = f"_Test Planned {suffix}"
		row.actual_item = f"_Test Actual {suffix}"
		row.actual_quantity = 7
		row.db_insert()

		# Simulate a form opened before the GRN-side direct child insert. The Lot
		# hook must reload the server-owned table before Frappe syncs children.
		stale.flags.ignore_links = True
		stale.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value(
				"SD YRP Lot Fabric Conversion",
				{
					"parent": lot.name,
					"parentfield": "lot_fabric_conversions",
				},
				"actual_quantity",
			),
			7,
		)

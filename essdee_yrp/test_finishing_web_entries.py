import copy
from importlib import import_module
from importlib.util import find_spec
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.test_finishing_web_workspace import make_plan

MODULE = "essdee_yrp.finishing.web_entries"
WORKSPACE = "essdee_yrp.finishing.web_workspace"


def quantity_block(*fields):
	values = {size: {field: 0 for field in fields} for size in ("S", "M")}
	return {
		"data": {
			"Red": {
				"values": copy.deepcopy(values),
				"colour": "Red",
				"part": None,
				"check_value": True,
				"set_combination": {"major_colour": "Red"},
				"colour_total": {},
			}
		}
	}


def plan_views():
	return {
		"primary_values": ["S", "M"],
		"is_set_item": 0,
		"set_attr": None,
		"finishing_qty": quantity_block("accepted", "balance", "balance_dc", "return_qty", "pack_return"),
		"finishing_ironing": quantity_block("ironing", "ironing_dc"),
		"pack_return": quantity_block("pack_returned_qty", "pack_return"),
	}


class TestFinishingWebEntries(TestCase):
	def _entries(self):
		self.assertIsNotNone(find_spec(MODULE), "Finishing web entry commands must exist")
		return import_module(MODULE)

	def _run(self, command, payload, plan=None, services=None):
		self._entries()
		workspace = import_module(WORKSPACE)
		plan = plan or make_plan(delivery_location="S-UNIT", fp_status="Dispatched")
		patches = [
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_roles", return_value=["Stock User"]),
			patch.object(frappe.db, "get_single_value", return_value=None),
			patch.object(frappe, "get_doc", return_value=plan),
			patch("essdee_yrp.finishing.views.build_plan_views", side_effect=lambda _doc: plan_views()),
			patch.object(workspace, "get_plan_workspace", return_value={"record": {"name": plan.name}}),
		]
		services = services or {}
		for target, value in services.items():
			patches.append(patch(target, return_value=value))
		started = [item.start() for item in patches]
		mocks = {
			target.rsplit(".", 1)[-1]: mock
			for target, mock in zip(services, started[len(started) - len(services) :], strict=True)
		}
		try:
			result = workspace.execute_plan_command(plan.name, command, payload, plan.modified)
		finally:
			for item in reversed(patches):
				item.stop()
		return result, mocks

	def test_create_delivery_challan_overlays_quantities_on_server_view_model(self):
		result, mocks = self._run(
			"create_delivery_challan",
			{
				"from_location": "S-FROM",
				"actual_date": "2026-10-09",
				"selected_type": "balance",
				"quantities": {"Red": {"checked": True, "sizes": {"S": 4}}},
			},
			services={"essdee_yrp.finishing.transactions.create_delivery_challan": "DC-1"},
		)
		args = mocks["create_delivery_challan"].call_args.args
		row = args[0]["items"]["data"]["data"]["Red"]
		self.assertEqual(args[0]["selected_type"], "balance")
		self.assertEqual(row["values"]["S"]["balance_dc"], 4)
		self.assertEqual(row["values"]["M"]["balance_dc"], 0)
		self.assertTrue(row["check_value"])
		self.assertEqual(args[1:], ("TSHIRT", "WO-1", "LOT-1", "S-FROM", "NA", "FP-0001", "2026-10-09"))
		self.assertEqual(result["result"], {"doctype": "YRP Delivery Challan", "name": "DC-1"})

	def test_quantities_must_be_non_negative_numbers(self):
		for value in (-1, "abc"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				self._run(
					"create_delivery_challan",
					{
						"from_location": "S",
						"actual_date": "2026-10-09",
						"selected_type": "balance",
						"quantities": {"Red": {"checked": True, "sizes": {"S": value}}},
					},
					services={"essdee_yrp.finishing.transactions.create_delivery_challan": "DC-1"},
				)

	def test_unknown_colour_or_size_is_rejected(self):
		for quantities in ({"Blue": {"sizes": {"S": 1}}}, {"Red": {"sizes": {"XXL": 1}}}):
			with self.subTest(quantities=quantities), self.assertRaises(frappe.ValidationError):
				self._run(
					"return_items",
					{"received_type": "Accepted", "quantities": quantities},
					services={"essdee_yrp.finishing.transactions.return_items": "GRN-1"},
				)

	def test_delivery_challan_type_must_be_a_frappe_15_option(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"create_delivery_challan",
				{
					"from_location": "S",
					"actual_date": "2026-10-09",
					"selected_type": "accepted",
					"quantities": {},
				},
				services={"essdee_yrp.finishing.transactions.create_delivery_challan": "DC-1"},
			)

	def test_return_items_uses_plan_location_and_requires_received_type(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"return_items",
				{"quantities": {}},
				services={"essdee_yrp.finishing.transactions.return_items": "GRN-1"},
			)
		result, mocks = self._run(
			"return_items",
			{"received_type": "Rework", "quantities": {"Red": {"sizes": {"M": 2}}}},
			services={"essdee_yrp.finishing.transactions.return_items": "GRN-1"},
		)
		args = mocks["return_items"].call_args.args
		self.assertEqual(args[0]["data"]["data"]["Red"]["values"]["M"]["return_qty"], 2)
		self.assertEqual(args[1:4], ("WO-1", "LOT-1", "TSHIRT"))
		self.assertEqual(
			args[4],
			{
				"from_location": "S-UNIT",
				"delivery_location": "S-UNIT",
				"vehicle_no": "NA",
				"received_type": "Rework",
			},
		)
		self.assertEqual(result["result"]["doctype"], "YRP Goods Received Note")

	def test_convert_to_loose_piece_opens_the_created_delivery_challan(self):
		result, mocks = self._run(
			"convert_to_loose_piece",
			{"from_location": "S-FROM", "quantities": {"Red": {"sizes": {"S": 1}}}},
			services={
				"essdee_yrp.finishing.transactions.convert_to_loose_piece_items": {
					"delivery_challan": "DC-9",
					"goods_received_note": "GRN-9",
				}
			},
		)
		args = mocks["convert_to_loose_piece_items"].call_args.args
		self.assertEqual(args[0]["data"]["data"]["Red"]["values"]["S"]["return_qty"], 1)
		self.assertEqual(args[1:], ("WO-1", "LOT-1", "TSHIRT", "S-FROM"))
		self.assertEqual(
			result["result"],
			{
				"doctype": "YRP Delivery Challan",
				"name": "DC-9",
				"related": {"doctype": "YRP Goods Received Note", "name": "GRN-9"},
			},
		)

	def test_make_grn_sends_box_quantities_and_batches(self):
		result, mocks = self._run(
			"create_grn",
			{
				"delivery_location": "S-UNIT",
				"actual_date": "2026-10-09",
				"quantities": {"S": 3},
				"packing_batches": [{"colour": "Red", "box_quantity": 1, "ratio": {"S": 5}}],
				"request_id": "req-1",
			},
			services={
				"essdee_yrp.finishing.transactions.get_primary_values": ["S", "M"],
				"essdee_yrp.finishing.transactions.create_grn": "GRN-2",
			},
		)
		kwargs = mocks["create_grn"].call_args.kwargs
		self.assertEqual(kwargs["data"], {"S": 3, "M": 0})
		self.assertEqual(kwargs["packing_batches"], [{"colour": "Red", "box_quantity": 1, "ratio": {"S": 5}}])
		self.assertEqual(
			(kwargs["work_order"], kwargs["lot"], kwargs["item_name"], kwargs["request_id"]),
			("WO-1", "LOT-1", "TSHIRT", "req-1"),
		)
		self.assertEqual(result["result"]["name"], "GRN-2")

	def test_dispatch_box_sends_legacy_cur_dispatch_shape(self):
		result, mocks = self._run(
			"dispatch_box",
			{
				"from_location": "S-UNIT",
				"to_location": "S-TO",
				"goods_value": 100,
				"vehicle_no": "TN01",
				"quantities": {"M": 2},
				"colour_details": {},
				"packing_batch_dispatches": [],
			},
			services={
				"essdee_yrp.finishing.transactions.get_primary_values": ["S", "M"],
				"essdee_yrp.finishing.transactions.create_stock_entry": "STE-1",
			},
		)
		kwargs = mocks["create_stock_entry"].call_args.kwargs
		self.assertEqual(kwargs["data"], {"S": {"cur_dispatch": 0}, "M": {"cur_dispatch": 2}})
		self.assertEqual(
			(kwargs["doc_name"], kwargs["to_location"], kwargs["vehicle_no"]), ("FP-0001", "S-TO", "TN01")
		)
		self.assertEqual(result["result"], {"doctype": "YRP Stock Entry", "name": "STE-1"})

	def test_dispatch_box_requires_frappe_15_mandatory_fields(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"dispatch_box",
				{
					"from_location": "S-UNIT",
					"to_location": "",
					"goods_value": 100,
					"vehicle_no": "TN01",
					"quantities": {},
				},
				services={
					"essdee_yrp.finishing.transactions.get_primary_values": ["S", "M"],
					"essdee_yrp.finishing.transactions.create_stock_entry": "STE-1",
				},
			)

	def test_ironing_excess_uses_plan_ipd_and_location(self):
		_result, mocks = self._run(
			"add_ironing_excess",
			{"quantities": {"Red": {"sizes": {"S": 5}}}},
			services={"essdee_yrp.finishing.transactions.create_material_receipt": "STE-2"},
		)
		args = mocks["create_material_receipt"].call_args.args
		self.assertEqual(args[0]["data"]["data"]["Red"]["values"]["S"]["ironing_dc"], 5)
		self.assertEqual(args[1:], ("TSHIRT", "LOT-1", "IPD-1", "FP-0001", "S-UNIT"))

	def test_return_pack_uses_accepted_pack_return(self):
		_result, mocks = self._run(
			"return_pack",
			{"quantities": {"Red": {"sizes": {"M": 1}}}},
			services={"essdee_yrp.finishing.transactions.return_items": "GRN-3"},
		)
		call = mocks["return_items"].call_args
		self.assertEqual(call.args[0]["data"]["data"]["Red"]["values"]["M"]["pack_return"], 1)
		self.assertEqual(call.args[4]["received_type"], "Accepted")
		self.assertTrue(call.kwargs["is_pack"])

	def test_lot_transfer_overlays_server_balances_and_checks_set_colour(self):
		available = {
			"colours": ["Red"],
			"data": [
				{
					"source_fp": "FP-0002",
					"lot": "LOT-2",
					"warehouse": "WH-1",
					"old_lot_inward": {
						"data": {
							"Red": {
								"set_combination": None,
								"part": None,
								"values": {
									"S": {
										"balance_loose_piece": 3,
										"balance_loose_piece_set": 0,
										"transfer_loose_piece": 0,
										"transfer_loose_piece_set": 0,
									}
								},
							}
						}
					},
				}
			],
		}
		payload = {
			"transfers": [
				{
					"source_fp": "FP-0002",
					"lot": "LOT-2",
					"warehouse": "WH-1",
					"colours": {"Red": {"set_combination": "Red", "sizes": {"S": {"loose_piece": 2}}}},
				}
			]
		}
		_result, mocks = self._run(
			"lot_transfer",
			payload,
			services={
				"essdee_yrp.finishing.old_lot.fetch_from_old_lot": available,
				"essdee_yrp.finishing.old_lot.create_lot_transfer": "LT-1",
			},
		)
		data = mocks["create_lot_transfer"].call_args.args[0]
		self.assertEqual(data[0]["old_lot_inward"]["data"]["Red"]["values"]["S"]["transfer_loose_piece"], 2)
		self.assertEqual(data[0]["old_lot_inward"]["data"]["Red"]["set_combination"], "Red")
		self.assertEqual(
			mocks["create_lot_transfer"].call_args.args[1:], ("TSHIRT", "IPD-1", "LOT-1", "FP-0001")
		)
		payload["transfers"][0]["colours"]["Red"]["sizes"]["S"]["loose_piece"] = 4
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"lot_transfer",
				payload,
				services={
					"essdee_yrp.finishing.old_lot.fetch_from_old_lot": available,
					"essdee_yrp.finishing.old_lot.create_lot_transfer": "LT-1",
				},
			)

	def test_alternative_plan_requires_a_listed_alternative_item(self):
		payload = {
			"lot_source": "New Lot",
			"lot_name": "LOT-1A",
			"alternative_item": "OTHER",
			"production_detail": "IPD-9",
			"quantities": {"Red": {"checked": True, "sizes": {"S": 1}}},
		}
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"create_alternative_plan",
				payload,
				services={
					"essdee_yrp.finishing.alternative.check_is_alternative_item": ["ALT"],
					"essdee_yrp.finishing.alternative.create_alternative_fp": {},
				},
			)
		payload["alternative_item"] = "ALT"
		result, mocks = self._run(
			"create_alternative_plan",
			payload,
			services={
				"essdee_yrp.finishing.alternative.check_is_alternative_item": ["ALT"],
				"essdee_yrp.finishing.alternative.create_alternative_fp": {
					"work_order": "WO-9",
					"lot": "LOT-1A",
				},
			},
		)
		kwargs = mocks["create_alternative_fp"].call_args.kwargs
		self.assertEqual(kwargs["qty_details"]["data"]["data"]["Red"]["values"]["S"]["conversion_qty"], 1)
		self.assertEqual(
			(kwargs["lot_source"], kwargs["lot_name"], kwargs["doc_name"]), ("new", "LOT-1A", "FP-0001")
		)
		self.assertEqual(result["result"], {"doctype": "YRP Work Order", "name": "WO-9"})

	def test_update_quantity_requires_an_alternate_lot(self):
		payload = {"target_lot": "LOT-X", "quantities": {"Red": {"checked": True, "sizes": {"S": 1}}}}
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"update_alternative_quantity",
				payload,
				services={
					"essdee_yrp.finishing.alternative.get_fp_alternate_lots": ["LOT-2"],
					"essdee_yrp.finishing.alternative.update_alternative_lot_quantity": "WO-5",
				},
			)
		payload["target_lot"] = "LOT-2"
		result, _mocks = self._run(
			"update_alternative_quantity",
			payload,
			services={
				"essdee_yrp.finishing.alternative.get_fp_alternate_lots": ["LOT-2"],
				"essdee_yrp.finishing.alternative.update_alternative_lot_quantity": "WO-5",
			},
		)
		self.assertEqual(result["result"], {"doctype": "YRP Work Order", "name": "WO-5"})

	def test_locked_plan_rejects_entry_commands(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(
				"return_pack",
				{"quantities": {}},
				plan=make_plan(fp_status="OCR Completed", delivery_location="S-UNIT"),
				services={"essdee_yrp.finishing.transactions.return_items": "GRN-3"},
			)

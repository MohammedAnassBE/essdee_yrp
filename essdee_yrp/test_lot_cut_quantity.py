import json
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe

import essdee_yrp.fabric_store.web_workspace as workspace
import essdee_yrp.purchase.lot_cut_quantity as report


class TestLotCutQuantity(TestCase):
	def test_empty_lots_are_rejected(self):
		for lots in ([], "[]", ["", "  "]):
			with self.subTest(lots=lots), self.assertRaises(frappe.ValidationError):
				report.get_lot_cut_quantity(lots)

	def test_more_than_twenty_lots_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			report.get_lot_cut_quantity([f"LOT-{index}" for index in range(21)])

	def test_report_role_is_required(self):
		with patch.object(frappe, "get_roles", return_value=["All", "Desk User"]):
			with self.assertRaises(frappe.PermissionError):
				report.get_lot_cut_quantity(["LOT-1"])

	def test_report_role_is_checked_before_input_is_parsed(self):
		with (
			patch.object(frappe, "get_roles", return_value=["All", "Desk User"]),
			patch.object(frappe, "parse_json") as parse_json,
			self.assertRaises(frappe.PermissionError),
		):
			report.get_lot_cut_quantity("not-json")

		parse_json.assert_not_called()

	def test_each_lot_requires_record_read_permission(self):
		lot = MagicMock(name="LOT-1")
		with (
			patch.object(frappe, "get_roles", return_value=["Purchase User"]),
			patch.object(frappe, "get_doc", return_value=lot),
			patch.object(frappe, "has_permission", return_value=False) as permission,
			patch.object(frappe, "get_all") as get_all,
			self.assertRaises(frappe.PermissionError),
		):
			report.get_lot_cut_quantity(["LOT-1"])

		permission.assert_called_once_with("SD YRP Lot", "read", doc=lot)
		get_all.assert_not_called()

	def test_unknown_lot_raises_does_not_exist(self):
		with (
			patch.object(frappe, "get_roles", return_value=["Purchase Manager"]),
			patch.object(frappe, "get_doc", side_effect=frappe.DoesNotExistError("Missing Lot")),
			self.assertRaises(frappe.DoesNotExistError),
		):
			report.get_lot_cut_quantity(["MISSING"])

	def test_payload_is_allowlisted_ordered_and_uses_stored_completed_json(self):
		stored_groups = [{
			"attributes": ["Colour"],
			"primary_attribute_values": ["S", "M"],
			"items": [{"attributes": {"Colour": "Navy"}, "values": {"S": 4, "M": 5}, "completed": False}],
		}]
		available = {
			"LOT-B": [
				{
					"name": "CP-CANCELLED",
					"item": "ITEM-B",
					"version": "V1",
					"docstatus": 2,
					"creation": "2026-01-01 08:00:00",
					"completed_items_json": "[]",
				},
				{
					"name": "CP-B-1",
					"item": "ITEM-B",
					"version": "V3",
					"docstatus": 1,
					"creation": "2026-01-01 09:00:00",
					"completed_items_json": json.dumps(stored_groups),
				},
				{
					"name": "CP-B-2",
					"item": "ITEM-B",
					"version": "V2",
					"docstatus": 0,
					"creation": "2026-01-01 10:00:00",
					"completed_items_json": None,
				},
			],
			"LOT-A": [],
		}

		def get_all(doctype, filters, fields, order_by):
			self.assertEqual(doctype, "SD YRP Cutting Plan")
			self.assertEqual(filters["docstatus"], ["<", 2])
			self.assertEqual(
				fields,
				["name", "item", "version", "docstatus", "completed_items_json"],
			)
			self.assertEqual(order_by, "creation asc, name asc")
			return [
				row for row in sorted(available[filters["lot"]], key=lambda row: (row["creation"], row["name"]))
				if row["docstatus"] < 2
			]

		with (
			patch.object(frappe, "get_roles", return_value=["Purchase User"]),
			patch.object(frappe, "get_doc", side_effect=lambda _doctype, name: frappe._dict(name=name)),
			patch.object(frappe, "has_permission", return_value=True) as permission,
			patch.object(frappe, "get_all", side_effect=get_all),
		):
			payload = report.get_lot_cut_quantity('[" LOT-B ", "LOT-A", "LOT-B"]')

		self.assertEqual([lot["lot"] for lot in payload["lots"]], ["LOT-B", "LOT-A"])
		self.assertEqual(
			[plan["name"] for plan in payload["lots"][0]["cutting_plans"]],
			["CP-B-1", "CP-B-2"],
		)
		self.assertEqual(
			payload["lots"][0]["cutting_plans"][0]["completed_items"],
			stored_groups,
		)
		self.assertEqual(payload["lots"][0]["cutting_plans"][1]["completed_items"], {})
		self.assertEqual(set(payload), {"lots"})
		self.assertEqual(set(payload["lots"][0]), {"lot", "cutting_plans"})
		for plan in payload["lots"][0]["cutting_plans"]:
			self.assertEqual(set(plan), {"name", "item", "version", "completed_items"})
		self.assertEqual(
			permission.call_args_list,
			[
				call("SD YRP Lot", "read", doc=frappe._dict(name="LOT-B")),
				call("SD YRP Lot", "read", doc=frappe._dict(name="LOT-A")),
			],
		)

	def test_capabilities_include_report_for_permitted_role(self):
		with (
			patch.object(workspace, "_capability", return_value={"can_read": False}),
			patch.object(workspace, "_permission_flags", return_value={}),
			patch.object(workspace, "can_run_report", return_value=False),
			patch.object(workspace, "can_view_lot_cut_quantity", return_value=True),
			patch.object(workspace.frappe, "has_permission", return_value=True),
		):
			payload = workspace.get_capabilities()

		self.assertEqual(
			payload["sections"]["reports"]["reports"]["lot_cut_quantity"],
			{
				"label": "Lot Cut Quantity",
				"can_read": True,
				"can_read_cutting_plan": True,
			},
		)

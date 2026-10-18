from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
	build_order_item_details,
	fetch_order_item_details,
)
from essdee_yrp.purchase import lot_workspace as workspace


class TestLotWorkspace(TestCase):
	def setUp(self):
		permissions = patch.object(workspace, "permission_flags", return_value={"can_write": True, "can_create": True})
		self.permission_flags = permissions.start()
		self.addCleanup(permissions.stop)

	def _doc(self, **values):
		return frappe._dict(
			{
				"name": "LOT-1",
				"modified": "2026-10-14 10:00:00",
				"status": "Open",
				"meta": SimpleNamespace(
					get_label=lambda field: field,
					get_field=lambda field: SimpleNamespace(fieldtype="Data"),
				),
				"check_permission": Mock(),
				**values,
			}
		)

	def _patch_builders(self, stack):
		return [
			stack.enter_context(patch.object(workspace, method))
			for method in (
				"fetch_item_details",
				"build_order_item_stages",
				"get_ocr_details",
				"fetch_fabric_program_details",
			)
		]

	def test_rejects_unreadable_lot(self):
		doc = SimpleNamespace(check_permission=Mock(side_effect=frappe.PermissionError))
		with ExitStack() as stack:
			builders = self._patch_builders(stack)
			stack.enter_context(patch.object(frappe, "get_doc", return_value=doc))
			with self.assertRaises(frappe.PermissionError):
				workspace.get_lot_workspace("private-lot")
			doc.check_permission.assert_called_once_with("read")
			for builder in builders:
				builder.assert_not_called()

	def test_sparse_lot_returns_header_only(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.lot_name = "legacy-shell"
		doc.name = doc.lot_name
		doc.status = "Open"
		with ExitStack() as stack:
			builders = self._patch_builders(stack)
			permission = stack.enter_context(patch.object(doc, "check_permission"))
			stack.enter_context(patch.object(frappe, "get_doc", return_value=doc))
			payload = workspace.get_lot_workspace(doc.name)
			permission.assert_called_once_with("read")
			self.assertEqual(payload["header"], [])
			self.assertEqual(payload["details"], [])
			self.assertEqual(payload["fabrics"], [])
			self.assertEqual(payload["other_conversions"], [])
			for key in ("order_items", "order_details", "bom", "ocr"):
				self.assertIsNone(payload[key])
			for builder in builders:
				builder.assert_not_called()

	def test_sparse_lot_keeps_packing_and_bom_facts_without_tables(self):
		values = {
			"pack_in_stage": "IAV-Stitched",
			"pack_out_stage": "IAV-Packed",
			"packing_uom": "Box",
			"total_order_quantity": 120,
			"total_quantity": 100,
			"last_calculated_time": "2026-10-14 10:00:00",
		}
		doc = self._doc(**values)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(workspace, "_attribute_value", side_effect=lambda value: value),
		):
			payload = workspace.get_lot_workspace(doc.name)
		self.assertIsNone(payload["order_details"])
		self.assertIsNone(payload["bom"])
		self.assertEqual({field["fieldname"]: field["value"] for field in payload["details"]}, values)
		self.assertFalse(set(values).intersection(field["fieldname"] for field in payload["header"]))

	def test_header_facts_follow_desk_order_and_drop_empty(self):
		doc = self._doc(
			production_order="PPO-1",
			item="Item",
			assigned_person="person@example.test",
			assigned_person_name="Person",
			pack_out_stage="IAV-Pack",
			capacity_planning=0,
			cloth_excess_percentage=0,
		)
		facts = workspace.get_facts(doc, workspace.HEADER_FIELDS)
		self.assertEqual(
			[r["fieldname"] for r in facts],
			[
				"production_order",
				"item",
				"assigned_person",
			],
		)
		self.assertEqual([r["value"] for r in facts], ["PPO-1", "Item", "Person"])

	def _stage_group(self, small, large):
		return [
			{
				"attributes": ["Colour"],
				"primary_attribute": "Size",
				"primary_attribute_values": ["S", "L"],
				"items": [
					{
						"attributes": {"Colour": "Blue"},
						"is_set_item": False,
						"values": {"S": {"qty": small}, "L": {"qty": large}},
						"total_qty": small + large,
					}
				],
				"size_wise_total": {"S": small, "L": large},
				"total_sum": small + large,
			}
		]

	def test_order_details_merges_stages_and_hides_empty_stage(self):
		doc = self._doc(production_detail="IPD-1", lot_order_details=[frappe._dict(quantity=3)])
		fixtures = [
			self._stage_group(2, 3),
			self._stage_group(1, 2),
			self._stage_group(0, 1),
			self._stage_group(0, 0),
		]
		with (
			patch.object(frappe, "get_cached_doc", return_value=frappe._dict(name="IPD-1")),
			patch.object(workspace, "build_order_item_stages", return_value=dict(zip(("quantity", "cut_qty", "stich_qty", "pack_qty"), fixtures))) as builder,
			patch.object(workspace, "get_colour_attribute", return_value="Colour"),
		):
			payload = workspace.get_order_details(doc)
		self.assertEqual([stage["label"] for stage in payload["stages"]], ["Order", "Cut", "Stitched"])
		self.assertEqual(
			builder.call_args.args[2],
			("quantity", "cut_qty", "stich_qty", "pack_qty"),
		)
		group = payload["groups"][0]
		self.assertEqual(group["items"][0]["values"]["L"], {"quantity": 3, "cut_qty": 2, "stich_qty": 1})
		self.assertEqual(group["items"][0]["totals"], {"quantity": 5, "cut_qty": 3, "stich_qty": 1})
		self.assertEqual(group["totals"], {"quantity": 5, "cut_qty": 3, "stich_qty": 1})
		self.assertEqual(group["size_totals"]["cut_qty"], {"S": 1, "L": 2})
		self.assertNotIn("facts", payload)

	def test_colour_note_only_for_v2_set_items(self):
		row = {
			"is_set_item": True,
			"set_attr": "Part",
			"major_attr_value": "Top",
			"attributes": {"Part": "Bottom"},
			"item_keys": {"major_colour": "Blue"},
		}
		self.assertIsNone(workspace.colour_note(self._doc(version="V1"), row))
		self.assertEqual(workspace.colour_note(self._doc(version="V2"), row), "Blue")
		self.assertEqual(workspace.colour_note(self._doc(version="V3"), row), "Blue")
		self.assertIsNone(workspace.colour_note(self._doc(version="V2"), {**row, "is_set_item": False}))
		self.assertIsNone(
			workspace.colour_note(self._doc(version="V2"), {**row, "attributes": {"Part": "Top"}})
		)

	def _fabric_doc(self):
		return self._doc(
			lot_fabric_details=[
				frappe._dict(
					cloth_item="Cloth", production_detail="IPD-1", plan_status="Built", plan_error="Error"
				),
				frappe._dict(cloth_item="Shell", production_detail=None, plan_status=""),
			],
			lot_fabric_conversions=[
				frappe._dict(idx=2, production_detail="IPD-1", actual_item="Actual-2"),
				frappe._dict(idx=1, production_detail="IPD-1", actual_item="Actual-1"),
				frappe._dict(idx=3, production_detail="IPD-other", actual_item="Other"),
			],
		)

	def test_fabric_cards_attach_conversions_and_drop_editor_keys(self):
		doc = self._fabric_doc()
		entry = {
			"cloth_item": "Cloth",
			"production_detail": "IPD-1",
			"program": [{"dia": "20"}],
			"fabric_routes": ["private"],
			"final_options": {"private": True},
		}
		with patch.object(workspace, "fetch_fabric_program_details", return_value=[entry]):
			cards = workspace.get_fabrics(doc)
		self.assertEqual([r["actual_item"] for r in cards[0]["conversions"]], ["Actual-1", "Actual-2"])
		self.assertEqual(cards[0]["plan_error"], "Error")
		self.assertEqual(cards[1]["cloth_item"], "Shell")
		for key in ("program", "requirement", "steps", "dyed_yarn_colours"):
			self.assertEqual(cards[1][key], [])
		for card in cards:
			self.assertNotIn("fabric_routes", card)
			self.assertNotIn("final_options", card)
		self.assertEqual([r["actual_item"] for r in workspace.get_other_conversions(doc)], ["Other"])

	def test_ocr_hidden_without_movement(self):
		doc = self._doc(item="Item", production_detail="IPD-1")
		payload = {"sizes": ["S"], "processes": {}, "total_dispatch": 0}
		with patch.object(workspace, "get_ocr_details", return_value=payload) as ocr:
			self.assertIsNone(workspace.get_ocr(doc))
			payload["processes"] = {"Cutting": {"total_sent": 2}}
			self.assertIs(workspace.get_ocr(doc), payload)
			payload["processes"] = {}
			payload["total_dispatch"] = 2
			self.assertIs(workspace.get_ocr(doc), payload)
			ocr.reset_mock()
			self.assertIsNone(workspace.get_ocr(self._doc(item="Item")))
			ocr.assert_not_called()

	def test_order_items_and_bom_drop_hidden_fields(self):
		doc = self._doc(production_detail="IPD-1", items=[frappe._dict(qty=2)])
		details = {
			"item": "Item",
			"default_uom": "Box",
			"primary_attribute": None,
			"items": [{"attributes": {}, "values": {"qty": 2}, "dependent_attribute_details": {}}],
		}
		with patch.object(workspace, "fetch_item_details", return_value=details):
			payload = workspace.get_order_items(doc)
		self.assertEqual(
			payload,
			{
				"item": "Item",
				"uom": "Box",
				"sizes": [],
				"attributes": [],
				"items": [{"attributes": {}, "values": {"qty": 2}}],
			},
		)
		row = frappe._dict(
			item_name="Thread", process_name="Sewing", required_qty="2.5", uom="Kg", available_stock=10
		)
		meta = Mock()
		meta.get_field.return_value.precision = "6"
		with patch.object(frappe, "get_meta", return_value=meta) as get_meta:
			bom = workspace.get_bom(self._doc(bom_summary=[row]))
		get_meta.assert_called_once_with("SD YRP Lot BOM")
		meta.get_field.assert_called_once_with("required_qty")
		self.assertEqual(bom["precision"], 6)
		self.assertEqual(
			bom["summary"], [{"item": "Thread", "process_name": "Sewing", "required_qty": 2.5, "uom": "Kg"}]
		)
		self.assertEqual(bom["additional"], [])
		self.assertNotIn("facts", bom)

	def test_scoped_workspace_keeps_positional_argument_validation(self):
		from essdee_yrp.purchase.lot_workspace import get_lot_workspace

		with patch.object(frappe, "get_doc", side_effect=AssertionError("Unexpected document read")):
			with self.assertRaises(frappe.FrappeTypeError):
				get_lot_workspace([])



class TestLiveLotWorkspace(TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user(self.previous_user)

	def _live_lot(self, name):
		if not frappe.db.exists("SD YRP Lot", name):
			self.skipTest(f"Live fixture {name} is missing")
		return frappe.get_doc("SD YRP Lot", name)

	def test_fetch_order_item_details_matches_builder(self):
		doc = self._live_lot("C1225-03")
		ipd_doc = frappe.get_doc("YRP Item Production Detail", doc.production_detail)
		self.assertEqual(
			fetch_order_item_details(doc.lot_order_details, doc.production_detail),
			build_order_item_details(doc.lot_order_details, ipd_doc, "quantity"),
		)

	def test_live_lots_smoke(self):
		self._live_lot("C1225-03")
		self._live_lot("F0926-49")
		garment = workspace.get_lot_workspace("C1225-03")
		self.assertEqual(len(garment["order_items"]["sizes"]), 8)
		self.assertEqual(len(garment["order_items"]["items"]), 1)
		self.assertTrue(garment["order_details"]["groups"])
		self.assertEqual(len(garment["bom"]["summary"]), 33)
		self.assertTrue(garment["ocr"]["processes"])
		cloth = workspace.get_lot_workspace("F0926-49")
		self.assertEqual(len(cloth["fabrics"]), 1)
		for key in ("steps", "program", "conversions"):
			self.assertTrue(cloth["fabrics"][0][key])

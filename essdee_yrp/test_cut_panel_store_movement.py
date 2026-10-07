from copy import deepcopy
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cut_panel_store.movement_workspace import (
	_authoritative_selection,
	_movement_context,
	get_movement_editor,
	save_movement,
)


class TestCutPanelStoreMovementWorkspace(UnitTestCase):
	def setUp(self):
		super().setUp()
		self.available = {
			"panels": ["Front"],
			"is_set_item": 0,
			"data": {
				"Navy": {
					"part": None,
					"data": [{
						"lay_no": 1,
						"bundle_no": 2,
						"size": "M",
						"shade": "A",
						"set_combination": {},
						"Front": 10,
						"Front_moved": False,
						"bundle_moved": False,
					}],
				}
			},
			"collapsed_details": [{
				"colour": "Navy",
				"size": "L",
				"panel": "Back",
				"shade": "A",
				"lay_no": 3,
				"bundle_no": 4,
				"set_combination": {},
				"quantity": 6,
				"moved": False,
				"move_qty": 0,
			}],
			"accessory_data": [{
				"cloth_name": "TAPE",
				"cloth_type": "Tape",
				"colour": "Navy",
				"dia": "10 mm",
				"shade": "A",
				"weight": 4,
				"moved_weight": 0,
			}],
		}

	def selected_payload(self):
		selected = deepcopy(self.available)
		selected["data"]["Navy"]["data"][0]["Front"] = 999
		selected["data"]["Navy"]["data"][0]["Front_moved"] = True
		selected["collapsed_details"][0].update({"moved": True, "move_qty": 2})
		selected["accessory_data"][0]["moved_weight"] = 1.25
		return selected

	def test_new_editor_returns_empty_defaults_without_generating_stock(self):
		context = frappe._dict(
			lot="LOT-1",
			item="ITEM-1",
			production_detail="IPD-1",
			source_supplier="CUT-PANEL-STORE",
			source_warehouse="WH-1",
		)
		with (
			patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context", return_value=context),
			patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cut_panel_store.movement_workspace.get_cut_bundle_unmoved_data") as generator,
		):
			payload = get_movement_editor(source={"lot": "LOT-1", "from_warehouse": "CUT-PANEL-STORE"})

		generator.assert_not_called()
		self.assertIsNone(payload["record"])
		self.assertEqual(payload["context"]["item"], "ITEM-1")
		self.assertEqual(payload["movement_data"]["data"], {})
		self.assertTrue(payload["permissions"]["can_create"])

	def test_context_derives_item_from_lot_and_resolves_supplier_warehouse(self):
		lot = MagicMock(item="ITEM-AUTH", production_detail="IPD-AUTH")
		lot.check_permission = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc", return_value=lot),
			patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.db.exists", return_value="CUT-STORE"),
			patch("essdee_yrp.cut_panel_store.movement_workspace._get_warehouse_for_supplier", return_value="CUT-WH"),
		):
			context = _movement_context(source={
				"lot": "LOT-AUTH",
				"item": "SPOOFED",
				"from_warehouse": "CUT-STORE",
			})

		lot.check_permission.assert_called_once_with("read")
		self.assertEqual(context.item, "ITEM-AUTH")
		self.assertEqual(context.production_detail, "IPD-AUTH")
		self.assertEqual(context.source_supplier, "CUT-STORE")
		self.assertEqual(context.source_warehouse, "CUT-WH")

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_cut_bundle_unmoved_data")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context")
	def test_authoritative_selection_keeps_server_quantities_for_all_row_types(self, context, generator):
		context.return_value = frappe._dict(lot="LOT-1", item="ITEM-1", source_supplier="CUT-STORE", movement_from_cutting=0, cutting_plan=None)
		generator.return_value = deepcopy(self.available)

		result = _authoritative_selection({
			"lot": "LOT-1",
			"from_warehouse": "CUT-STORE",
			"posting_date": "2026-10-07",
			"posting_time": "10:30:00",
			"movement_data": self.selected_payload(),
		})

		row = result["data"]["Navy"]["data"][0]
		self.assertEqual(row["Front"], 10)
		self.assertTrue(row["Front_moved"])
		self.assertEqual(result["collapsed_details"][0]["move_qty"], 2)
		self.assertEqual(result["accessory_data"][0]["moved_weight"], 1.25)
		generator.assert_called_once_with(
			"CUT-STORE",
			"LOT-1",
			"2026-10-07",
			"10:30:00",
			0,
			cutting_plan=None,
			get_collapsed=True,
		)

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_cut_bundle_unmoved_data")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context")
	def test_authoritative_selection_rejects_forged_exact_rows(self, context, generator):
		context.return_value = frappe._dict(lot="LOT-1", item="ITEM-1", source_supplier="CUT-STORE", movement_from_cutting=0, cutting_plan=None)
		generator.return_value = deepcopy(self.available)
		selected = self.selected_payload()
		selected["data"]["Navy"]["data"].append({
			"lay_no": 99,
			"bundle_no": 99,
			"size": "M",
			"shade": "A",
			"set_combination": {},
			"Front_moved": True,
		})

		with self.assertRaisesRegex(frappe.ValidationError, "Stock changed"):
			_authoritative_selection({
				"lot": "LOT-1",
				"from_warehouse": "CUT-STORE",
				"movement_data": selected,
			})

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_cut_bundle_unmoved_data")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context")
	def test_authoritative_selection_rejects_collapsed_and_accessory_overdraw(self, context, generator):
		context.return_value = frappe._dict(lot="LOT-1", item="ITEM-1", source_supplier="CUT-STORE", movement_from_cutting=0, cutting_plan=None)
		generator.return_value = deepcopy(self.available)
		selected = self.selected_payload()
		selected["collapsed_details"][0]["move_qty"] = 7
		with self.assertRaisesRegex(frappe.ValidationError, "Collapsed move qty"):
			_authoritative_selection({"lot": "LOT-1", "from_warehouse": "CUT-STORE", "movement_data": selected})

		selected = self.selected_payload()
		selected["accessory_data"][0]["moved_weight"] = 5
		with self.assertRaisesRegex(frappe.ValidationError, "Accessory moving weight"):
			_authoritative_selection({"lot": "LOT-1", "from_warehouse": "CUT-STORE", "movement_data": selected})

	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_payload")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._authoritative_selection")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_existing_save_rejects_stale_modified_value(self, get_doc, context, authoritative, payload):
		doc = frappe._dict(
			name="CPM-1",
			doctype="SD YRP Cut Panel Movement",
			docstatus=0,
			modified="2026-10-07 10:00:00",
			movement_from_cutting=0,
		)
		doc.check_permission = MagicMock()
		get_doc.return_value = doc
		context.return_value = frappe._dict(lot="LOT-1", item="ITEM-1", source_supplier="CUT-STORE")

		with self.assertRaisesRegex(frappe.TimestampMismatchError, "changed"):
			save_movement(
				{"lot": "LOT-1", "from_warehouse": "CUT-STORE", "movement_data": {}},
				name="CPM-1",
				expected_modified="2026-10-07 09:00:00",
			)

		authoritative.assert_not_called()
		payload.assert_not_called()

	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_payload")
	@patch("essdee_yrp.cut_panel_store.movement_workspace._movement_context")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_plan_created_movement_can_be_read_without_rewriting_its_identity(self, get_doc, context, payload):
		doc = frappe._dict(
			name="CPM-CUTTING",
			docstatus=1,
			movement_from_cutting=1,
			cutting_plan="CP-1",
			lot="LOT-1",
			item="ITEM-1",
			from_warehouse="CUTTING-SUPPLIER",
			cut_panel_movement_json=self.available,
		)
		doc.check_permission = MagicMock()
		get_doc.return_value = doc
		context.return_value = frappe._dict(lot="LOT-1", item="ITEM-1", source_supplier="CUTTING-SUPPLIER")
		payload.return_value = {"name": doc.name, "movement_from_cutting": 1, "cutting_plan": "CP-1"}

		result = get_movement_editor(name="CPM-CUTTING")

		doc.check_permission.assert_called_once_with("read")
		self.assertEqual(result["record"]["movement_from_cutting"], 1)
		self.assertEqual(result["record"]["cutting_plan"], "CP-1")

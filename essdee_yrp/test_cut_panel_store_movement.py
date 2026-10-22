from copy import deepcopy
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cut_panel_store.movement_workspace import (
	_authoritative_selection,
	_movement_context,
	_transaction_record,
	create_movement_transaction,
	get_movement_linked_documents,
	get_movement_work_orders,
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

	def test_transaction_flags_for_user_without_cancel_show_no_permission_message(self):
		stock_entry = frappe.get_doc({"doctype": "YRP Stock Entry", "name": "STE-QUIET", "docstatus": 1})
		frappe.local.message_log = []
		frappe.set_user("Guest")
		try:
			with patch("frappe.permissions.get_doc_permissions", return_value={"read": 1, "cancel": 0, "print": 0}):
				permissions = _transaction_record(stock_entry)["permissions"]
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(permissions["can_cancel"])
		self.assertFalse(permissions["can_print"])
		self.assertEqual(frappe.local.message_log, [], "a permission flag must not pop up Frappe's access message")

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

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_active_root_transactions")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_list")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.has_permission")
	def test_linked_documents_are_permission_filtered_and_keep_cancelled_history(
		self, has_permission, get_list, get_doc, active_roots
	):
		movement = frappe._dict(name="CPM-1", docstatus=1, lot="LOT-1", modified="2026-10-07")
		movement.check_permission = MagicMock()
		readable = frappe._dict(
			doctype="YRP Stock Entry",
			name="STE-1",
			docstatus=2,
			posting_date="2026-10-07",
			posting_time="12:00:00",
			modified="2026-10-07 12:01:00",
			purpose="Material Transfer",
		)
		unreadable = frappe._dict(
			doctype="YRP Delivery Challan",
			name="DC-HIDDEN",
			docstatus=1,
			posting_date="2026-10-07",
			posting_time="12:02:00",
			modified="2026-10-07 12:03:00",
		)
		get_doc.side_effect = lambda doctype, name: movement if doctype == "SD YRP Cut Panel Movement" else {
			"STE-1": readable,
			"DC-HIDDEN": unreadable,
		}[name]
		has_permission.side_effect = lambda doctype, ptype="read", doc=None, **_kwargs: (
			doctype != "YRP Goods Received Note" and doc is not unreadable
		)
		get_list.side_effect = lambda doctype, **_kwargs: {
			"YRP Stock Entry": ["STE-1"],
			"YRP Delivery Challan": ["DC-HIDDEN"],
		}.get(doctype, [])
		active_roots.return_value = []

		payload = get_movement_linked_documents("CPM-1")

		self.assertEqual([row["name"] for row in payload["sections"]["stock_entries"]], ["STE-1"])
		self.assertEqual(payload["sections"]["delivery_challans"], [])
		self.assertNotIn("goods_received_notes", payload["sections"])
		self.assertTrue(payload["actions"]["stock_entry"]["eligible"])
		self.assertEqual(payload["sections"]["stock_entries"][0]["status"], "Cancelled")

	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_list")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_work_order_choices_are_submitted_and_same_lot(self, get_doc, get_list):
		movement = frappe._dict(name="CPM-1", docstatus=1, lot="LOT-1")
		movement.check_permission = MagicMock()
		get_doc.return_value = movement
		get_list.return_value = [frappe._dict(name="WO-1", supplier="SUP-1", item="ITEM-1")]

		rows = get_movement_work_orders("CPM-1", txt="WO")

		self.assertEqual(rows[0]["name"], "WO-1")
		filters = get_list.call_args.kwargs["filters"]
		self.assertEqual(filters["docstatus"], 1)
		self.assertEqual(filters["lot"], "LOT-1")
		self.assertEqual(filters["name"], ["like", "%WO%"])

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_movement_linked_documents")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.build_stock_entry_defaults")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_active_root_transactions")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.new_doc")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_stock_entry_creation_uses_authoritative_defaults(
		self, get_doc, new_doc, active_roots, build_defaults, linked_documents
	):
		movement = frappe._dict(name="CPM-1", docstatus=1, lot="LOT-1")
		movement.check_permission = MagicMock()
		get_doc.return_value = movement
		active_roots.return_value = []
		build_defaults.return_value = {"purpose": "Material Transfer", "from_warehouse": "WH-1"}
		doc = MagicMock()
		doc.doctype = "YRP Stock Entry"
		doc.name = "STE-NEW"
		doc.docstatus = 0
		doc.get.side_effect = lambda fieldname: {"modified": "now"}.get(fieldname)
		new_doc.return_value = doc
		linked_documents.return_value = {"sections": {}}

		result = create_movement_transaction(
			"CPM-1", "stock_entry", {"to_warehouse": "WH-2"}, submit=True
		)

		build_defaults.assert_called_once_with("CPM-1")
		doc.update.assert_called_once_with(build_defaults.return_value)
		self.assertEqual(doc.to_warehouse, "WH-2")
		doc.insert.assert_called_once()
		doc.submit.assert_called_once()
		self.assertEqual(result["record"]["name"], "STE-NEW")

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_active_root_transactions")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_concurrent_root_transaction_is_rejected_clearly(self, get_doc, active_roots):
		movement = frappe._dict(name="CPM-1", docstatus=1, lot="LOT-1")
		movement.check_permission = MagicMock()
		get_doc.return_value = movement
		active_roots.return_value = [frappe._dict(doctype="YRP Delivery Challan", name="DC-1")]

		with self.assertRaisesRegex(frappe.ValidationError, "already used by active YRP Delivery Challan DC-1"):
			create_movement_transaction("CPM-1", "stock_entry", {"to_warehouse": "WH-2"})

	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_movement_linked_documents")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.build_goods_received_note_defaults")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.build_delivery_challan_defaults")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.get_active_root_transactions")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.new_doc")
	@patch("essdee_yrp.cut_panel_store.movement_workspace.frappe.get_doc")
	def test_dc_and_grn_creation_validate_same_lot_work_order_and_use_builders(
		self, get_doc, new_doc, active_roots, build_dc, build_grn, linked_documents
	):
		movement = frappe._dict(name="CPM-1", docstatus=1, lot="LOT-1")
		movement.check_permission = MagicMock()
		work_order = frappe._dict(name="WO-1", docstatus=1, lot="LOT-1")
		work_order.check_permission = MagicMock()
		get_doc.side_effect = lambda doctype, _name: movement if doctype == "SD YRP Cut Panel Movement" else work_order
		active_roots.return_value = []
		build_dc.return_value = {"work_order": "WO-1", "items": [{"item": "ITEM-1"}]}
		build_grn.return_value = {"against": "YRP Work Order", "against_id": "WO-1", "items": [{"item": "ITEM-1"}]}
		linked_documents.return_value = {"sections": {}}

		created = []
		for doctype, name in (("YRP Delivery Challan", "DC-NEW"), ("YRP Goods Received Note", "GRN-NEW")):
			doc = MagicMock()
			doc.doctype = doctype
			doc.name = name
			doc.docstatus = 0
			doc.get.side_effect = lambda fieldname: {"modified": "now"}.get(fieldname)
			created.append(doc)
		new_doc.side_effect = created

		dc = create_movement_transaction("CPM-1", "delivery_challan", {"work_order": "WO-1"})
		grn = create_movement_transaction("CPM-1", "goods_received_note", {"work_order": "WO-1"})

		build_dc.assert_called_once_with("CPM-1", "WO-1")
		build_grn.assert_called_once_with("CPM-1", "WO-1")
		self.assertEqual(dc["record"]["name"], "DC-NEW")
		self.assertEqual(grn["record"]["name"], "GRN-NEW")
		self.assertEqual(created[0].update.call_args.args[0], build_dc.return_value)
		self.assertEqual(created[1].update.call_args.args[0], build_grn.return_value)


class TestCutPanelMovementDeliveryChallanAddress(UnitTestCase):
	MODULE = "essdee_yrp.cutting.movement"

	def build(self, linked):
		cpm = frappe._dict(
			name="CPM-1", lot="LOT-1", from_warehouse="S-0170", posting_date="2026-10-20",
			posting_time="10:00:00", cut_panel_movement_json="{}",
		)
		work_order = MagicMock(docstatus=1, open_status="Open", lot="LOT-1")
		work_order.name = "WO-1"
		work_order.meta.get_field.return_value = True
		work_order.get.side_effect = {"delivery_address": "Sewing-Billing"}.get
		with (
			patch(f"{self.MODULE}._require_create_permission"),
			patch(f"{self.MODULE}.get_grouped_movement_rows", return_value=(cpm, None, [])),
			patch(f"{self.MODULE}.frappe.get_doc", return_value=work_order),
			patch(f"{self.MODULE}.get_dc_work_order_defaults", return_value={"items": []}),
			patch(f"{self.MODULE}._overlay_source_rows", return_value=[]),
			patch(f"{self.MODULE}.group_items_for_ui", return_value=[]),
			patch(f"{self.MODULE}._movement_uses_collapsed", return_value=False),
			patch(f"{self.MODULE}.frappe.db.exists", return_value=linked),
			patch(f"{self.MODULE}.get_default_address", return_value="S-0170-Billing"),
			patch(f"{self.MODULE}.get_address_display", return_value="Cut Panel Store"),
			patch(
				"yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan._get_warehouse_for_supplier",
				return_value="S-0170",
			),
		):
			from essdee_yrp.cutting.movement import build_delivery_challan_defaults

			return build_delivery_challan_defaults("CPM-1", "WO-1")

	def test_from_address_belongs_to_the_movement_source_location(self):
		defaults = self.build(linked=False)

		self.assertEqual(defaults["from_location"], "S-0170")
		self.assertEqual(defaults["from_address"], "S-0170-Billing")
		self.assertEqual(defaults["from_address_details"], "Cut Panel Store")

	def test_work_order_delivery_address_is_kept_when_it_belongs_to_the_source(self):
		self.assertEqual(self.build(linked=True)["from_address"], "Sewing-Billing")

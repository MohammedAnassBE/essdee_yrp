from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe

from essdee_yrp.fabric_store.documents.delivery_challan import (
	_merge_authoritative_rows,
	_validate_and_sync_party_dependencies,
	execute_delivery_challan_command,
	get_delivery_challan_workspace,
	preview_delivery_challan_source,
	save_delivery_challan,
)
from essdee_yrp.fabric_store.web_workspace import (
	create_delivery_challan_return,
	get_delivery_challan_return_editor,
)


class TestFabricStoreDeliveryChallan(TestCase):
	def test_party_dependencies_reject_a_warehouse_owned_by_another_location(self):
		doc = self.make_document()
		with patch(
			"essdee_yrp.fabric_store.documents.delivery_challan._warehouse_party",
			return_value="UNIT-OTHER",
		):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"From Warehouse Stores - E.*From Location UNIT-1",
			):
				_validate_and_sync_party_dependencies(doc)

	def test_party_dependencies_reject_an_address_not_linked_to_the_location(self):
		doc = self.make_document()
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._warehouse_party",
				side_effect=["UNIT-1", "SUPPLIER-1"],
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.frappe.db.exists",
				return_value=False,
			),
		):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"From Address ADDR-FROM.*UNIT-1",
			):
				_validate_and_sync_party_dependencies(doc)

	def test_party_dependencies_rebuild_address_details_from_selected_links(self):
		doc = self.make_document()
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._warehouse_party",
				side_effect=["UNIT-1", "SUPPLIER-1"],
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.frappe.db.exists",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_address_display",
				side_effect=["Fresh sender address", "Fresh receiver address"],
			),
		):
			_validate_and_sync_party_dependencies(doc)

		self.assertEqual(doc.from_address_details, "Fresh sender address")
		self.assertEqual(doc.supplier_address_details, "Fresh receiver address")

	def test_padded_zero_quantity_cell_does_not_create_a_forged_row(self):
		merged = _merge_authoritative_rows(
			[],
			[{"item_variant": "ITEM-S", "qty": 0, "secondary_qty": 0}],
		)
		self.assertEqual(merged, [])

	def test_duplicate_workspace_is_unsaved_and_keeps_entered_groups(self):
		source = self.make_document(docstatus=1)
		duplicate = self.make_document()
		duplicate.name = None
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=source),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.new_doc", return_value=duplicate),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._onload_matrices", return_value=([{"copy": "items"}], [{"copy": "corrections"}])),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_stock_dimensions_for_ui", return_value=[]),
		):
			workspace = get_delivery_challan_workspace(source={"duplicate_from": source.name})

		self.assertIsNone(workspace["record"]["name"])
		self.assertEqual(workspace["values"]["comments"], source.comments)
		self.assertEqual(workspace["matrices"]["items"], [{"copy": "items"}])

	def test_special_source_delivery_challan_cannot_be_duplicated(self):
		source = self.make_document(docstatus=1, cut_panel_movement="CPM-1")
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=source),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "source-managed"):
				get_delivery_challan_workspace(source={"duplicate_from": source.name})

	def make_document(
		self,
		*,
		docstatus=0,
		is_internal_unit=0,
		transfer_complete=0,
		cut_panel_movement=None,
		includes_packing=1,
	):
		doc = frappe._dict(
			doctype="YRP Delivery Challan",
			name="DC-1",
			docstatus=docstatus,
			modified="2026-10-06 10:00:00",
			naming_series="DC-.YYYY.-",
			work_order="WO-1",
			posting_date="2026-10-06",
			posting_time="10:00:00",
			edit_posting_date_and_time=0,
			process_name="Cutting",
			item="STYLE-1",
			production_detail="IPD-1",
			lot="LOT-1",
			from_location="UNIT-1",
			from_warehouse="Stores - E",
			to_warehouse="Supplier - E",
			supplier="SUPPLIER-1",
			vehicle_no="TN01AB1234",
			comments="Dispatch",
			from_address="ADDR-FROM",
			from_address_details="From address",
			supplier_address="ADDR-TO",
			supplier_address_details="To address",
			includes_packing=includes_packing,
			cut_panel_movement=cut_panel_movement,
			cutting_bulk_lay_sheet=None,
			cutting_bulk_lay_sheet_detail=None,
			from_finishing=0,
			loose_piece_dc=0,
			pack_piece_dc=0,
			allow_non_bundle=0,
			additional_goods_value=25,
			is_internal_unit=is_internal_unit,
			transfer_complete=transfer_complete,
			ste_transferred=0,
			ste_transferred_percent=0,
			total_delivered_qty=7,
			stock_value=350,
			total_value=375,
			items=[
				frappe._dict(
					name="DCI-1",
					item_variant="RAW-S",
					qty=5,
					delivered_quantity=5,
					uom="Kg",
					ref_doctype="YRP Work Order Deliverables",
					ref_docname="WOD-1",
					row_index="0",
					set_combination='{"colour":"Red"}',
				),
			],
			correction_items=[
				frappe._dict(
					name="DCC-1",
					item_variant="RAW-M",
					qty=2,
					delivered_quantity=2,
					uom="Kg",
					ref_doctype="YRP Work Order Deliverables",
					ref_docname="WOD-C1",
					work_order_correction="WOC-1",
					row_index="0",
					set_combination='{"colour":"Blue"}',
				),
			],
		)
		doc.check_permission = MagicMock()
		doc.has_permission = MagicMock(return_value=True)
		doc.update = MagicMock(side_effect=lambda values: dict.update(doc, values))
		doc.set = MagicMock(
			side_effect=lambda fieldname, value: dict.__setitem__(
				doc,
				fieldname,
				[
					frappe._dict(row) if isinstance(row, dict) else row
					for row in value
				]
				if isinstance(value, list)
				else value,
			)
		)
		doc.insert = MagicMock()
		doc.save = MagicMock()
		doc.submit = MagicMock()
		doc.cancel = MagicMock()
		doc.amend = MagicMock()
		doc.get_onload = MagicMock(
			return_value={
				"item_details": [{"kind": "normal", "items": []}],
				"correction_item_details": [{"kind": "correction", "items": []}],
			}
		)
		doc.run_method = MagicMock()
		doc.meta = MagicMock()
		doc.meta.get_field.side_effect = lambda fieldname: frappe._dict(
			fieldname=fieldname,
			label=fieldname.replace("_", " ").title(),
			fieldtype="Currency" if "value" in fieldname else "Data",
			hidden=0,
			read_only=0,
			reqd=0,
			options="",
		)
		return doc

	def workspace_base(self, doc, **kwargs):
		permissions = {
			"can_read": True,
			"can_create": True,
			"can_write": doc.docstatus == 0,
			"can_submit": doc.docstatus == 0,
			"can_cancel": doc.docstatus == 1,
			"can_amend": doc.docstatus == 2,
			"can_print": True,
		}
		capabilities = {
			name: {key: value for key, value in spec.items() if key not in {"eligible", "permission"}}
			for name, spec in kwargs["capabilities"].items()
			if spec.get("eligible", True)
			and (not spec.get("permission") or permissions.get(f"can_{spec['permission']}", False))
		}
		return {
			"record": {
				"doctype": doc.doctype,
				"name": doc.name,
				"docstatus": doc.docstatus,
				"modified": doc.modified,
			},
			"fields": [{"fieldname": fieldname, "value": doc.get(fieldname)} for fieldname in kwargs["fieldnames"]],
			"totals": [{"fieldname": fieldname, "value": doc.get(fieldname)} for fieldname in kwargs["totals"]],
			"permissions": permissions,
			"capabilities": capabilities,
			"print_formats": [],
		}

	def test_workspace_exposes_base_custom_fields_authoritative_matrices_and_totals(self):
		doc = self.make_document(docstatus=1)
		doc.received_type = "Accepted"
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._return_context",
				return_value={"items": [{"delivery_challan_item": "DCI-1"}]},
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._related_documents",
				return_value={"returns": [], "completion_entries": []},
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_stock_dimensions_for_ui",
				return_value=[
					{
						"fieldname": "received_type",
						"label": "Received Type",
						"options": "YRP Received Type",
						"mandatory": 1,
					}
				],
			),
		):
			workspace = get_delivery_challan_workspace(doc.name)

		fieldnames = {field["fieldname"] for field in workspace["fields"]}
		self.assertTrue(
			{
				"work_order",
				"from_warehouse",
				"from_address",
				"includes_packing",
				"additional_goods_value",
			}
			<= fieldnames
		)
		self.assertEqual(workspace["matrices"]["items"][0]["kind"], "normal")
		self.assertEqual(workspace["matrices"]["correction_items"][0]["kind"], "correction")
		self.assertEqual(
			[field["fieldname"] for field in workspace["totals"]],
			["total_delivered_qty", "stock_value", "additional_goods_value", "total_value"],
		)
		self.assertTrue(workspace["return_context"]["variants"]["whole_bundle"])
		self.assertIn("return", workspace["capabilities"])
		self.assertEqual(
			workspace["dimensions"],
			[
				{
					"fieldname": "received_type",
					"label": "Received Type",
					"options": "YRP Received Type",
					"mandatory": 1,
					"fieldtype": "Link",
					"reqd": True,
					"value": "Accepted",
					"locked": True,
				}
			],
		)
		doc.run_method.assert_called_once_with("onload")

	def test_workspace_only_exposes_transfer_when_submitted_internal_and_incomplete(self):
		eligible = self.make_document(docstatus=1, is_internal_unit=1)
		complete = self.make_document(docstatus=1, is_internal_unit=1, transfer_complete=1)
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._return_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._related_documents", return_value={}),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", side_effect=[eligible, complete]),
		):
			first = get_delivery_challan_workspace(eligible.name)
			second = get_delivery_challan_workspace(complete.name)

		self.assertIn("complete_transfer", first["capabilities"])
		self.assertNotIn("complete_transfer", second["capabilities"])

	def test_workspace_omits_notifications_without_raw_write_permission(self):
		doc = self.make_document(docstatus=1)

		def has_permission(doctype, ptype=None, **kwargs):
			if doctype == "YRP Delivery Challan" and ptype == "write":
				return False
			return True

		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_workspace_base",
				side_effect=self.workspace_base,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._return_context",
				return_value={},
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._related_documents",
				return_value={},
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission",
				side_effect=has_permission,
			),
		):
			workspace = get_delivery_challan_workspace(doc.name)

		self.assertNotIn("prepare_sms", workspace["capabilities"])
		self.assertNotIn("prepare_whatsapp", workspace["capabilities"])

	def test_workspace_values_and_record_follow_effective_readable_fields(self):
		doc = self.make_document(docstatus=1, cut_panel_movement="CPM-SECRET")

		def restricted_base(document, **kwargs):
			workspace = self.workspace_base(document, **kwargs)
			workspace["fields"] = [
				{"fieldname": "work_order", "label": "Work Order", "value": document.work_order}
			]
			return workspace

		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_workspace_base",
				side_effect=restricted_base,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._return_context",
				return_value={},
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._related_documents",
				return_value={},
			),
		):
			workspace = get_delivery_challan_workspace(doc.name)

		self.assertEqual(workspace["values"], {"work_order": "WO-1"})
		self.assertEqual(workspace["record"]["work_order"], "WO-1")
		self.assertNotIn("supplier", workspace["record"])
		self.assertNotIn("markers", workspace["special_source"])
		self.assertNotIn("CPM-SECRET", frappe.as_json(workspace["special_source"]))

	def test_source_preview_uses_essdee_defaults_and_preserves_only_editable_headers(self):
		defaults = {
			"work_order": "WO-1",
			"from_location": "",
			"from_warehouse": "",
			"supplier": "SUPPLIER-1",
			"items": [{"item_variant": "RAW-S", "qty": 5, "ref_docname": "WOD-1", "row_index": "0"}],
			"item_details": [{"kind": "authoritative"}],
			"correction_items": [],
			"correction_item_details": [],
		}
		with patch(
			"essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_defaults",
			return_value=defaults,
		) as loader:
			preview = preview_delivery_challan_source(
				"WO-1",
				{"vehicle_no": "TN-NEW", "supplier": "FORGED", "work_order": "WO-X"},
			)

		self.assertEqual(preview["values"]["vehicle_no"], "TN-NEW")
		self.assertEqual(preview["values"]["supplier"], "SUPPLIER-1")
		self.assertEqual(preview["values"]["work_order"], "WO-1")
		self.assertEqual(preview["matrices"]["items"], [{"kind": "authoritative"}])
		self.assertIn("fields", preview)
		self.assertEqual(
			[field["fieldname"] for field in preview["totals"]],
			["total_delivered_qty", "stock_value", "additional_goods_value", "total_value"],
		)
		loader.assert_called_once_with("WO-1")

	def test_new_save_merges_only_quantities_onto_authoritative_normal_and_correction_rows(self):
		doc = self.make_document()
		doc.name = "DC-NEW"
		defaults = {
			"work_order": "WO-1",
			"supplier": "SUPPLIER-1",
			"items": [
				{
					"item_variant": "RAW-S",
					"qty": 5,
					"secondary_qty": 5,
					"secondary_uom": "Roll",
					"ref_docname": "WOD-1",
					"row_index": "0",
					"uom": "Kg",
				}
			],
			"correction_items": [
				{
					"item_variant": "RAW-M",
					"qty": 2,
					"ref_docname": "WOD-C1",
					"work_order_correction": "WOC-1",
					"row_index": "0",
					"uom": "Kg",
				}
			],
		}
		browser_items = [
			{
				"item_variant": "RAW-S",
				"qty": 3,
				"secondary_qty": 7,
				"secondary_uom": "FORGED-UOM",
				"ref_docname": "FORGED",
				"row_index": "0",
			}
		]
		browser_corrections = [
			{
				"item_variant": "RAW-M",
				"qty": 1,
				"ref_docname": "FORGED-C",
				"work_order_correction": "WOC-1",
				"row_index": "0",
			}
		]
		refreshed = {"record": {"name": "DC-NEW"}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._validate_and_sync_party_dependencies"),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._validated_purchase_order_source", return_value="PO-1") as validate_po,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_defaults", return_value=defaults),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_items_from_ui", return_value=browser_items),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.ungroup_correction_items_from_ui",
				return_value=browser_corrections,
			),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value=refreshed),
		):
			result = save_delivery_challan(
				{
					"work_order": "WO-1",
					"purchase_order": "PO-1",
					"vehicle_no": "TN-NEW",
					"supplier": "FORGED",
					"item_details": [{"browser": "normal"}],
					"correction_item_details": [{"browser": "correction"}],
				},
				submit=True,
			)

		self.assertEqual(result, refreshed)
		self.assertEqual(doc.supplier, "SUPPLIER-1")
		self.assertEqual(doc.vehicle_no, "TN-NEW")
		self.assertEqual(doc.purchase_order, "PO-1")
		validate_po.assert_called_once_with("PO-1")
		self.assertEqual(doc["items"][0].qty, 3)
		self.assertEqual(doc["items"][0].secondary_qty, 7)
		self.assertEqual(doc["items"][0].secondary_uom, "Roll")
		self.assertEqual(doc["items"][0].ref_docname, "WOD-1")
		self.assertEqual(doc.correction_items[0].qty, 1)
		self.assertEqual(doc.correction_items[0].ref_docname, "WOD-C1")
		doc.insert.assert_called_once_with()
		doc.submit.assert_called_once_with()

	def test_save_rejects_browser_rows_not_in_authoritative_source(self):
		doc = self.make_document()
		defaults = {
			"work_order": "WO-1",
			"items": [{"item_variant": "RAW-S", "qty": 5, "ref_docname": "WOD-1", "row_index": "0"}],
			"correction_items": [],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._validate_and_sync_party_dependencies"),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_defaults", return_value=defaults),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_items_from_ui", return_value=[
				{"item_variant": "RAW-S", "qty": 5, "row_index": "0"},
				{"item_variant": "FORGED", "qty": 99, "row_index": "9"},
			]),
		):
			with self.assertRaises(frappe.ValidationError):
				save_delivery_challan({"work_order": "WO-1", "item_details": [{}]})

		doc.insert.assert_not_called()

	def test_existing_save_persists_only_configured_stock_dimensions(self):
		doc = self.make_document()
		doc.received_type = "Accepted"
		refreshed = {"record": {"name": doc.name}, "values": {"received_type": "Rejected"}}
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._validate_and_sync_party_dependencies"),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_stock_dimensions_for_ui",
				return_value=[{"fieldname": "lot"}, {"fieldname": "received_type"}],
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace",
				return_value=refreshed,
			),
		):
			result = save_delivery_challan(
				{
					"received_type": "Rejected",
					"lot": "FORGED-LOT",
					"forged_dimension": "FORGED",
				},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result, refreshed)
		self.assertEqual(doc.received_type, "Rejected")
		self.assertEqual(doc.lot, "LOT-1")
		self.assertNotIn("forged_dimension", doc)
		doc.save.assert_called_once_with()

	def test_submitted_save_updates_allow_on_submit_item_tables_only(self):
		doc = self.make_document(docstatus=1)
		original_get_field = doc.meta.get_field.side_effect
		doc.meta.fields = [
			frappe._dict(fieldname="items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="correction_items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="vehicle_no", fieldtype="Data", allow_on_submit=0, hidden=0, read_only=0),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			original_get_field(fieldname),
		)
		browser_items = [dict(doc["items"][0], qty=4)]
		browser_corrections = [dict(doc.correction_items[0], qty=1)]
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["items", "correction_items", "vehicle_no"]),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_items_from_ui", return_value=browser_items),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_correction_items_from_ui", return_value=browser_corrections),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value={"record": {"name": doc.name}}),
		):
			result = save_delivery_challan(
				{"item_details": [{"browser": True}], "correction_item_details": [{"browser": True}]},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result["record"]["name"], doc.name)
		self.assertEqual(doc["items"][0].qty, 4)
		self.assertEqual(doc.correction_items[0].qty, 1)
		doc.save.assert_called_once_with()

	def test_submitted_save_rejects_non_allow_on_submit_header(self):
		doc = self.make_document(docstatus=1)
		doc.meta.fields = [
			frappe._dict(fieldname="items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="vehicle_no", fieldtype="Data", allow_on_submit=0, hidden=0, read_only=0),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["items", "vehicle_no"]),
			self.assertRaisesRegex(frappe.ValidationError, "Allow on Submit"),
		):
			save_delivery_challan({"vehicle_no": "TN-FORGED"}, name=doc.name, expected_modified=doc.modified)
		doc.save.assert_not_called()

	def test_existing_special_source_ignores_browser_quantity_changes(self):
		doc = self.make_document(cut_panel_movement="CPM-1")
		doc.cutting_bulk_lay_sheet = "CBLS-1"
		doc.cutting_bulk_lay_sheet_detail = "CBLSD-1"
		doc.pack_piece_dc = 1
		doc["items"][0].ref_docname = "CPM-ROW-1"
		browser_items = [
			{
				"item_variant": "RAW-S",
				"qty": 4,
				"row_index": "0",
				"set_combination": '{"colour":"Red"}',
			}
		]
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._validate_and_sync_party_dependencies"),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_defaults") as defaults,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_items_from_ui", return_value=browser_items),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.ungroup_correction_items_from_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value=refreshed),
		):
			save_delivery_challan(
				{"vehicle_no": "TN-SPECIAL", "item_details": [{}], "correction_item_details": []},
				name=doc.name,
				expected_modified=doc.modified,
			)

		defaults.assert_not_called()
		self.assertEqual(doc.cut_panel_movement, "CPM-1")
		self.assertEqual(doc.cutting_bulk_lay_sheet_detail, "CBLSD-1")
		self.assertEqual(doc.pack_piece_dc, 1)
		self.assertEqual(doc["items"][0].ref_docname, "CPM-ROW-1")
		self.assertEqual(doc["items"][0].qty, 5)
		self.assertEqual(doc["items"][0].delivered_quantity, 5)
		doc.save.assert_called_once_with()

	def test_return_command_uses_essdee_wrapper_and_preserves_cut_panel_link(self):
		doc = self.make_document(docstatus=1, cut_panel_movement="CPM-1")
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._load_return_movement",
				return_value=frappe._dict(name="CPM-RETURN-1", lot=doc.lot),
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn",
				return_value="GRN-RET-1",
			) as create_return,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value=refreshed),
		):
			result = execute_delivery_challan_command(
				doc.name,
				"return",
				{
					"items": [{"delivery_challan_item": "DCI-1", "return_quantity": 1}],
					"received_type": "Good",
					"return_whole_bundles": True,
					"cut_panel_movement": "CPM-RETURN-1",
				},
				expected_modified=doc.modified,
			)

		create_return.assert_called_once_with(
			doc.name,
			[{"delivery_challan_item": "DCI-1", "return_quantity": 1}],
			"Good",
			"CPM-RETURN-1",
		)
		self.assertEqual(result["created"], {"doctype": "YRP Goods Received Note", "name": "GRN-RET-1"})
		self.assertEqual(result["workspace"], refreshed)

	def test_forged_return_and_transfer_commands_are_rejected_before_delegation(self):
		draft = self.make_document(docstatus=0, is_internal_unit=1)
		unauthorized = self.make_document(docstatus=1, is_internal_unit=1)
		incomplete_transfer = self.make_document(docstatus=1, is_internal_unit=1)
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				side_effect=[draft, unauthorized, incomplete_transfer],
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission",
				side_effect=[True, False, True],
			),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn") as create_return,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.make_dc_completion") as complete_transfer,
		):
			with self.assertRaises(frappe.ValidationError):
				execute_delivery_challan_command(draft.name, "return", {"items": []})
			with self.assertRaises(frappe.PermissionError):
				execute_delivery_challan_command(unauthorized.name, "complete_transfer")
			with self.assertRaises(frappe.ValidationError):
				execute_delivery_challan_command(incomplete_transfer.name, "return", {"items": []})

		create_return.assert_not_called()
		complete_transfer.assert_not_called()

	def test_whole_bundle_return_requires_an_explicit_return_movement(self):
		doc = self.make_document(docstatus=1, cut_panel_movement="CPM-SOURCE")
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn"
			) as create_return,
		):
			with self.assertRaises(frappe.ValidationError):
				execute_delivery_challan_command(
					doc.name,
					"return",
					{"items": [], "return_whole_bundles": True},
				)

		create_return.assert_not_called()

	def test_whole_bundle_return_rejects_a_movement_from_another_lot(self):
		doc = self.make_document(docstatus=1)
		movement = frappe._dict(name="CPM-WRONG-LOT", lot="LOT-OTHER")
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._load_return_movement",
				return_value=movement,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn"
			) as create_return,
		):
			with self.assertRaises(frappe.ValidationError):
				execute_delivery_challan_command(
					doc.name,
					"return",
					{
						"items": [],
						"return_whole_bundles": True,
						"cut_panel_movement": movement.name,
					},
				)

		create_return.assert_not_called()

	def test_whole_bundle_return_rejects_a_linked_movement(self):
		doc = self.make_document(docstatus=1)
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._load_return_movement",
				side_effect=frappe.ValidationError("already linked"),
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn"
			) as create_return,
		):
			with self.assertRaises(frappe.ValidationError):
				execute_delivery_challan_command(
					doc.name,
					"return",
					{
						"items": [],
						"return_whole_bundles": True,
						"cut_panel_movement": "CPM-LINKED",
					},
				)

		create_return.assert_not_called()

	def test_normal_return_does_not_reuse_the_source_delivery_movement(self):
		doc = self.make_document(docstatus=1, cut_panel_movement="CPM-SOURCE")
		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission",
				return_value=True,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.create_essdee_return_grn",
				return_value="GRN-NORMAL-1",
			) as create_return,
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			execute_delivery_challan_command(
				doc.name,
				"return",
				{"items": [{"delivery_challan_item": "DCI-1", "return_quantity": 1}]},
			)

		create_return.assert_called_once_with(
			doc.name,
			[{"delivery_challan_item": "DCI-1", "return_quantity": 1}],
			None,
			None,
		)

	def test_complete_transfer_delegates_only_after_authoritative_eligibility_checks(self):
		doc = self.make_document(docstatus=1, is_internal_unit=1)
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.make_dc_completion", return_value="STE-1") as complete,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value=refreshed),
		):
			result = execute_delivery_challan_command(doc.name, "complete_transfer")

		complete.assert_called_once_with(doc.name)
		self.assertEqual(result["created"], {"doctype": "YRP Stock Entry", "name": "STE-1"})

	def test_complete_transfer_reopens_existing_draft_completion(self):
		doc = self.make_document(docstatus=1, is_internal_unit=1)
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan._target_create_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_draft_completion_stock_entry", return_value="STE-DRAFT") as find_draft,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.make_dc_completion") as complete,
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value={}),
		):
			result = execute_delivery_challan_command(doc.name, "complete_transfer")

		find_draft.assert_called_once_with("YRP Delivery Challan", doc.name)
		complete.assert_not_called()
		self.assertEqual(result["created"], {"doctype": "YRP Stock Entry", "name": "STE-DRAFT"})

	def test_lifecycle_and_notification_commands_are_server_authorized(self):
		doc = self.make_document(docstatus=0)
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.get_delivery_challan_workspace", return_value=refreshed),
		):
			self.assertEqual(execute_delivery_challan_command(doc.name, "submit"), refreshed)
		doc.submit.assert_called_once_with()

		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("yrp.notification.get_flow_sms_context", return_value={"templates": ["SMS-1"]}) as sms,
		):
			context = execute_delivery_challan_command(doc.name, "prepare_notification", {"channel": "sms"})
		self.assertEqual(context, {"channel": "sms", "context": {"templates": ["SMS-1"]}})
		sms.assert_called_once_with("YRP Delivery Challan", doc.name, "supplier")

	def test_notification_context_requires_raw_write_permission(self):
		doc = self.make_document(docstatus=1)

		def deny_write(doctype, ptype=None, throw=False, **kwargs):
			if throw:
				raise frappe.PermissionError
			return False

		with (
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan",
				return_value=doc,
			),
			patch(
				"essdee_yrp.fabric_store.documents.delivery_challan.frappe.has_permission",
				side_effect=deny_write,
			),
			patch("yrp.notification.get_flow_sms_context") as sms,
		):
			with self.assertRaises(frappe.PermissionError):
				execute_delivery_challan_command(
					doc.name,
					"prepare_notification",
					{"channel": "sms"},
				)

		sms.assert_not_called()

	def test_notification_send_delegates_to_existing_logged_service(self):
		doc = self.make_document(docstatus=1)
		payload = {"template_name": "Dispatch", "mobile_no": "9944405056", "params": {"name": doc.name}}
		sent = {"channel": "sms", "result": {"ok": True}}
		with (
			patch("essdee_yrp.fabric_store.documents.delivery_challan._get_delivery_challan", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.delivery_challan.send_supplier_notification", return_value=sent) as send,
		):
			self.assertEqual(
				execute_delivery_challan_command(doc.name, "send_sms", payload, doc.modified),
				sent,
			)

		send.assert_called_once_with(doc, "YRP Delivery Challan", "sms", payload)

	def test_compatibility_return_defaults_to_normal_and_exposes_explicit_variants(self):
		doc = self.make_document(docstatus=1, cut_panel_movement="CPM-SOURCE")
		return_data = {"items": [{"delivery_challan_item": "DCI-1"}]}
		with (
			patch(
				"essdee_yrp.fabric_store.web_workspace._get_supported_document",
				return_value=doc,
			),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.web_workspace.get_return_delivery_items",
				return_value=return_data,
			),
		):
			editor = get_delivery_challan_return_editor(doc.name)

		self.assertTrue(editor["variants"]["normal"])
		self.assertTrue(editor["variants"]["whole_bundle"])

		with (
			patch(
				"essdee_yrp.fabric_store.web_workspace._get_supported_document",
				return_value=doc,
			),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.web_workspace.create_return_grn",
				return_value="GRN-NORMAL",
			) as create_return,
			patch(
				"essdee_yrp.fabric_store.web_workspace.get_document",
				return_value={"record": {"name": "GRN-NORMAL"}},
			),
		):
			create_delivery_challan_return(
				doc.name,
				[{"delivery_challan_item": "DCI-1", "return_quantity": 1}],
			)

		create_return.assert_called_once_with(
			doc.name,
			[{"delivery_challan_item": "DCI-1", "return_quantity": 1}],
			None,
		)

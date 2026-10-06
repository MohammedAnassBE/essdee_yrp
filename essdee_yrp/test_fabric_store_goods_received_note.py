from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.garment_grn import _allocate_calculated_receivables

from essdee_yrp.fabric_store.documents.goods_received_note import (
	_merge_authoritative_rows,
	_merge_inspection_sources,
	calculate_goods_received_note,
	execute_goods_received_note_command,
	get_goods_received_note_calculation,
	get_goods_received_note_workspace,
	preview_goods_received_note_source,
	save_goods_received_note,
	save_goods_received_note_inspection,
)


class TestFabricStoreGoodsReceivedNote(TestCase):
	def test_padded_zero_quantity_cell_does_not_create_a_forged_row(self):
		with patch(
			"essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames",
			return_value=(),
		):
			merged = _merge_authoritative_rows(
				[],
				[{"item_variant": "ITEM-S", "quantity": 0, "secondary_qty": 0}],
			)

		self.assertEqual(merged, [])

	def test_duplicate_workspace_is_unsaved_and_keeps_entered_groups(self):
		source = self.make_document(docstatus=1)
		duplicate = self.make_document()
		duplicate.name = None
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=source),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=duplicate),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._onload_matrices", return_value=([{"copy": "items"}], [{"copy": "corrections"}])),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[]),
		):
			workspace = get_goods_received_note_workspace(source={"duplicate_from": source.name})

		self.assertIsNone(workspace["record"]["name"])
		self.assertEqual(workspace["values"]["comments"], source.comments)
		self.assertEqual(workspace["matrices"]["items"], [{"copy": "items"}])

	def test_special_source_grn_cannot_be_duplicated_as_an_ordinary_receipt(self):
		source = self.make_document(docstatus=1)
		source.additional_grn = 1
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=source),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "source-managed"):
				get_goods_received_note_workspace(source={"duplicate_from": source.name})

	def test_calculated_output_is_allocated_across_duplicate_receivable_rows(self):
		work_order = frappe._dict(
			receivables=[
				frappe._dict(name="WOR-1", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=1),
				frappe._dict(name="WOR-2", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=2),
				frappe._dict(name="WOR-3", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=3),
			]
		)

		allocations = _allocate_calculated_receivables(
			work_order,
			{"item_variant": "FABRIC-GREY", "set_combination": "{}", "qty": 50.4},
		)

		self.assertEqual(
			[(row.name, quantity) for row, quantity in allocations],
			[("WOR-1", 33.6), ("WOR-2", 16.8)],
		)

	def test_calculated_output_above_combined_pending_quantity_is_rejected_clearly(self):
		work_order = frappe._dict(
			name="WO-1",
			receivables=[
				frappe._dict(name="WOR-1", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=10, idx=1),
				frappe._dict(name="WOR-2", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=5, idx=2),
			],
		)

		with self.assertRaisesRegex(frappe.ValidationError, "Only 15.*pending"):
			_allocate_calculated_receivables(
				work_order,
				{"item_variant": "FABRIC-GREY", "set_combination": "{}", "qty": 16},
			)

	def make_document(
		self,
		*,
		docstatus=0,
		is_internal_unit=0,
		transfer_complete=0,
		is_return=0,
		is_rework=0,
		additional_grn=0,
	):
		doc = frappe._dict(
			doctype="YRP Goods Received Note",
			name="GRN-1",
			docstatus=docstatus,
			modified="2026-10-06 10:00:00",
			naming_series="YRP-GRN-.YYYY.-",
			against="YRP Work Order",
			against_id="WO-1",
			delivery_challan="DC-1",
			is_return=is_return,
			is_rework=is_rework,
			additional_grn=additional_grn,
			includes_packing=0,
			cutting_laysheet=None,
			cut_panel_movement=None,
			from_closed_wo_sewing_details=0,
			allow_non_bundle=0,
			posting_date="2026-10-06",
			posting_time="10:00:00",
			edit_posting_date_and_time=0,
			process_name="Stitching",
			item="STYLE-1",
			production_detail="IPD-1",
			supplier="SUPPLIER-1",
			delivery_location="UNIT-1",
			from_warehouse="Supplier - E",
			to_warehouse="Stores - E",
			freight_charges=25,
			comments="Receipt",
			is_internal_unit=is_internal_unit,
			transfer_complete=transfer_complete,
			ste_transferred=0,
			ste_transferred_percent=0,
			total_received_quantity=8,
			total=400,
			grand_total=425,
			items=[
				frappe._dict(
					name="GRNI-1",
					item_variant="STYLE-S",
					quantity=5,
					secondary_qty=2,
					uom="Nos",
					rate=50,
					ref_doctype="YRP Work Order Receivables",
					ref_docname="WOR-1",
					row_index="0::Accepted",
					received_type="Accepted",
					lot="LOT-1",
					set_combination='{"colour":"Red"}',
				),
				frappe._dict(
					name="GRNI-2",
					item_variant="STYLE-S",
					quantity=3,
					uom="Nos",
					rate=50,
					ref_doctype="YRP Work Order Receivables",
					ref_docname="WOR-1",
					row_index="0::Rejected",
					received_type="Rejected",
					lot="LOT-1",
					set_combination='{"colour":"Red"}',
				),
			],
			correction_items=[
				frappe._dict(
					name="GRNC-1",
					item_variant="STYLE-M",
					quantity=1,
					uom="Nos",
					rate=60,
					ref_docname="WOR-C1",
					work_order_correction="WOC-1",
					row_index="1",
					received_type="Accepted",
					lot="LOT-1",
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
		doc.run_method = MagicMock()
		doc.get_onload = MagicMock(
			return_value={
				"item_details": [{"kind": "normal"}],
				"correction_item_details": [{"kind": "correction"}],
			}
		)
		doc.meta = MagicMock()
		doc.meta.get_field.side_effect = lambda fieldname: frappe._dict(
			fieldname=fieldname,
			label=fieldname.replace("_", " ").title(),
			fieldtype="Currency" if fieldname in {"total", "grand_total", "freight_charges"} else "Data",
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

	def test_workspace_exposes_calculate_matrices_dimensions_and_special_context(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value={"inspection_entries": [], "completion_entries": []}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[{"fieldname": "received_type", "label": "Received Type", "options": "YRP Received Type", "mandatory": 1}]),
		):
			workspace = get_goods_received_note_workspace(doc.name)

		self.assertEqual(workspace["matrices"]["items"], [{"kind": "normal"}])
		self.assertEqual(workspace["matrices"]["correction_items"], [{"kind": "correction"}])
		self.assertIn("calculate", workspace["capabilities"])
		self.assertFalse(workspace["special_source"]["active"])
		self.assertEqual(workspace["dimensions"][0]["fieldtype"], "Link")
		self.assertTrue(workspace["dimensions"][0]["locked"])

	def test_workspace_hides_calculate_for_new_or_special_modes(self):
		doc = self.make_document(additional_grn=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value={}),
		):
			workspace = get_goods_received_note_workspace(doc.name)
		self.assertNotIn("calculate", workspace["capabilities"])
		self.assertTrue(workspace["special_source"]["read_only"])

	def test_work_order_preview_uses_essdee_defaults(self):
		defaults = {
			"supplier": "SUPPLIER-1",
			"items": [{"item_variant": "STYLE-S", "quantity": 5}],
			"item_details": [{"kind": "wo"}],
			"correction_items": [],
			"correction_item_details": [],
		}
		with patch(
			"essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults",
			return_value=defaults,
		) as loader:
			workspace = preview_goods_received_note_source(
				{"against": "YRP Work Order", "against_id": "WO-1", "delivery_challan": "DC-1"}
			)
		self.assertEqual(workspace["values"]["supplier"], "SUPPLIER-1")
		self.assertEqual(workspace["matrices"]["items"], [{"kind": "wo"}])
		loader.assert_called_once_with("WO-1", "DC-1")

	def test_purchase_order_preview_uses_base_defaults(self):
		defaults = {
			"supplier": "SUPPLIER-PO",
			"items": [{"item_variant": "FABRIC-1", "quantity": 2}],
			"item_details": [{"kind": "po"}],
		}
		with patch(
			"essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults",
			return_value=defaults,
		) as loader:
			workspace = preview_goods_received_note_source(
				{"purchase_order": "PO-1", "comments": "Kept"}
			)
		self.assertEqual(workspace["record"]["against"], "Purchase Order")
		self.assertEqual(workspace["values"]["comments"], "Kept")
		loader.assert_called_once_with("PO-1")

	def test_existing_save_uses_saved_rows_and_preserves_other_types_corrections_and_special_rows(self):
		doc = self.make_document(additional_grn=1)
		browser_rows = [
			{
				"item_variant": "STYLE-S",
				"quantity": 4,
				"rate": 999,
				"ref_docname": "WOR-1",
				"row_index": "0::Accepted",
				"received_type": "Accepted",
				"lot": "FORGED",
				"set_combination": '{"colour":"Red"}',
			},
			{
				"item_variant": "STYLE-S",
				"quantity": 3,
				"ref_docname": "WOR-1",
				"row_index": "0::Rejected",
				"received_type": "Rejected",
				"lot": "LOT-1",
				"set_combination": '{"colour":"Red"}',
			},
		]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_rows),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={"record": {"name": doc.name}}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults") as defaults,
		):
			result = save_goods_received_note(
				{
					"comments": "Updated",
					"supplier": "FORGED",
					"item_details": [{"browser": True}],
				},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result["record"]["name"], doc.name)
		self.assertEqual(doc.supplier, "SUPPLIER-1")
		self.assertEqual(doc["items"][0].quantity, 5, "special prepared rows stay untouched")
		self.assertEqual(doc["items"][1].received_type, "Rejected")
		self.assertEqual(doc.correction_items[0].name, "GRNC-1")
		defaults.assert_not_called()

	def test_existing_save_rejects_delivery_challan_relink_without_rebuilding_rows(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaisesRegex(frappe.ValidationError, "Delivery Challan cannot be changed"),
		):
			save_goods_received_note(
				{"delivery_challan": "DC-FORGED"},
				name=doc.name,
				expected_modified=doc.modified,
			)
		doc.save.assert_not_called()

	def test_ordinary_existing_save_merges_quantity_but_rejects_forged_lineage(self):
		doc = self.make_document()
		browser_rows = [
			# The common matrix ungrouping helper renumbers logical rows. Saved
			# Received-Type suffixes therefore cannot be trusted as browser identity.
			dict(doc["items"][0], quantity=4, rate=999, row_index=0),
			dict(doc["items"][1], quantity=2, row_index=1),
		]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_rows),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			save_goods_received_note({"item_details": [{}]}, name=doc.name)
		self.assertEqual(doc["items"][0].quantity, 4)
		self.assertEqual(doc["items"][0].rate, 50)
		self.assertEqual(doc["items"][0].lot, "LOT-1")

		forged = [dict(doc["items"][0], ref_docname="WOR-FORGED", quantity=4)]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=forged),
			self.assertRaises(frappe.ValidationError),
		):
			save_goods_received_note({"item_details": [{}]}, name=doc.name)

	def test_new_save_keeps_authoritative_source_and_delegates_freight_and_submit_to_controller(self):
		doc = self.make_document()
		doc.name = "GRN-NEW"
		doc.items = []
		doc.correction_items = []
		defaults = {
			"supplier": "SUPPLIER-1",
			"from_warehouse": "Supplier - E",
			"to_warehouse": "Stores - E",
			"items": [dict(self.make_document()["items"][0])],
			"correction_items": [],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", return_value=defaults),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=[dict(defaults["items"][0], quantity=4)]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			save_goods_received_note(
				{
					"against": "YRP Work Order",
					"against_id": "WO-1",
					"supplier": "FORGED",
					"freight_charges": 100,
					"item_details": [{}],
				},
				submit=True,
			)
		self.assertEqual(doc.supplier, "SUPPLIER-1")
		self.assertEqual(doc.freight_charges, 100)
		doc.insert.assert_called_once()
		doc.submit.assert_called_once()

	def test_calculate_delegates_selected_type_and_returns_refreshed_workspace(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified") as stale,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables", return_value={"received_type": "Rejected"}) as calculate,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={"record": {"name": doc.name}}),
		):
			result = calculate_goods_received_note(
				doc.name,
				[{"source_row": "WOCI-1", "qty": 3}],
				"Rejected",
				doc.modified,
			)
		stale.assert_called_once_with(doc, doc.modified)
		calculate.assert_called_once_with(doc.name, [{"source_row": "WOCI-1", "qty": 3}], "Rejected", doc.modified)
		self.assertEqual(result["calculation"]["received_type"], "Rejected")

	def test_stale_calculate_is_rejected_before_controller_delegation(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified", side_effect=frappe.TimestampMismatchError),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables") as calculate,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			calculate_goods_received_note(doc.name, [], "Accepted", "stale")
		calculate.assert_not_called()

	def test_direct_calculation_endpoints_reject_ineligible_special_mode(self):
		doc = self.make_document()
		doc.from_finishing = 1
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_grn_calculation_context") as context,
			self.assertRaisesRegex(frappe.ValidationError, "Calculate is not available"),
		):
			get_goods_received_note_calculation(doc.name)
		context.assert_not_called()

		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables") as calculate,
			self.assertRaisesRegex(frappe.ValidationError, "Calculate is not available"),
		):
			calculate_goods_received_note(doc.name, [], "Accepted", doc.modified)
		calculate.assert_not_called()

	def test_submitted_grn_exposes_inspection_initial_payload_and_existing_entries(self):
		doc = self.make_document(docstatus=1)
		related = {"inspection_entries": [{"name": "INS-1"}], "completion_entries": []}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value=related),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._target_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_inspection_initial_payload", return_value=[{"ref_docname": "GRNI-1"}]),
		):
			workspace = get_goods_received_note_workspace(doc.name)
		self.assertIn("create_inspection", workspace["capabilities"])
		self.assertIn("view_inspections", workspace["capabilities"])
		self.assertTrue(workspace["inspection"]["can_submit"])
		self.assertEqual(workspace["inspection"]["initial_payload"][0]["ref_docname"], "GRNI-1")

	def test_inspection_save_uses_authoritative_sources_and_submits_controller(self):
		grn = self.make_document(docstatus=1)
		inspection = frappe._dict(
			doctype="YRP Inspection Entry",
			name="INS-NEW",
			docstatus=0,
			modified="2026-10-06 11:00:00",
			items=[],
		)
		inspection.update = MagicMock(side_effect=lambda values: dict.update(inspection, values))
		inspection.set = MagicMock(side_effect=lambda key, value: dict.__setitem__(inspection, key, value))
		inspection.insert = MagicMock()
		inspection.submit = MagicMock()
		source = {
			"item_variant": "STYLE-S",
			"warehouse": "Transit - E",
			"grn_qty": 5,
			"ref_doctype": "YRP Goods Received Note Item",
			"ref_docname": "GRNI-1",
			"source_received_type": "Accepted",
			"received_type": "Accepted",
			"lot": "LOT-1",
			"splits": [{"target_received_type": "Accepted", "qty": 5, "received_date": "2026-10-06"}],
		}
		browser = dict(source, warehouse="FORGED", lot="FORGED", splits=[{"target_received_type": "Rejected", "qty": 5, "received_date": "2026-10-06"}])
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=inspection),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_inspection_initial_payload", return_value=[source]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.db.exists", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._inspection_projection", return_value={"record": {"name": inspection.name}}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			result = save_goods_received_note_inspection(
				grn.name,
				{"remarks": "Checked", "item_details": [browser]},
				submit=True,
			)
		self.assertEqual(inspection.against_id, grn.name)
		self.assertIn('"warehouse": "Transit - E"', inspection.item_details)
		self.assertNotIn("FORGED", inspection.item_details)
		inspection.insert.assert_called_once()
		inspection.submit.assert_called_once()
		self.assertEqual(result["inspection"]["record"]["name"], inspection.name)

	def test_inspection_splits_cannot_exceed_authoritative_source_quantity(self):
		source = {
			"item_variant": "STYLE-S",
			"grn_qty": 5,
			"ref_doctype": "YRP Goods Received Note Item",
			"ref_docname": "GRNI-1",
		}
		browser = {
			**source,
			"splits": [
				{"target_received_type": "Accepted", "qty": 4},
				{"target_received_type": "Rejected", "qty": 2},
			],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.db.exists", return_value=True),
			self.assertRaisesRegex(frappe.ValidationError, "exceed.*available quantity"),
		):
			_merge_inspection_sources([source], [browser])

	def test_complete_transfer_and_lifecycle_commands_use_native_controllers(self):
		grn = self.make_document(docstatus=1, is_internal_unit=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._target_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.make_grn_completion", return_value="STE-1") as complete,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			result = execute_goods_received_note_command(grn.name, "complete_transfer")
		complete.assert_called_once_with(grn.name)
		self.assertEqual(result["created"]["name"], "STE-1")

		draft = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=draft),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			execute_goods_received_note_command(draft.name, "submit")
		draft.submit.assert_called_once()

	def test_forged_or_wrong_state_command_is_rejected(self):
		grn = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaises(frappe.ValidationError),
		):
			execute_goods_received_note_command(grn.name, "delete_everything")

		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaises(frappe.ValidationError),
		):
			execute_goods_received_note_command(grn.name, "submit")

	def test_notification_commands_delegate_to_existing_supplier_services(self):
		grn = self.make_document(docstatus=1)
		prepared = {"channel": "sms", "context": {"templates": [{"name": "GRN"}]}}
		sent = {"channel": "sms", "result": {"ok": True}}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.prepare_supplier_notification", return_value=prepared) as prepare,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.send_supplier_notification", return_value=sent) as send,
		):
			self.assertEqual(
				execute_goods_received_note_command(grn.name, "prepare_sms", expected_modified=grn.modified),
				prepared,
			)
			payload = {"template_name": "Receipt", "mobile_no": "9944405056", "params": {"name": grn.name}}
			self.assertEqual(
				execute_goods_received_note_command(grn.name, "send_sms", payload, grn.modified),
				sent,
			)

		prepare.assert_called_once_with(grn, "YRP Goods Received Note", "sms")
		send.assert_called_once_with(grn, "YRP Goods Received Note", "sms", payload)

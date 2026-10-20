from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.stock.save_stock_items import group_items_for_ui

from essdee_yrp.fabric_store.documents.work_order import (
	_target_create_permission,
	execute_work_order_command,
	get_work_order_editor,
	get_work_order_workspace,
	save_work_order_document,
)


class TestFabricStoreWorkOrder(TestCase):
	def test_editor_duplicate_returns_unsaved_headers_and_requires_recalculation(self):
		source = self.make_document(docstatus=1)
		duplicate = self.make_document()
		duplicate.name = None
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=source),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.new_doc", return_value=duplicate),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=lambda rows, _doctype: [] if not rows else [{"copy": "rows"}]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={}),
		):
			editor = get_work_order_editor(source={"duplicate_from": source.name})

		self.assertEqual(editor["name"], "")
		self.assertEqual(editor["values"]["supplier"], source.supplier)
		self.assertEqual(editor["deliverable_details"], [])
		self.assertEqual(editor["receivable_details"], [])
		self.assertEqual(editor["calculated_items"], [])

	def test_adapter_uses_raw_permission_for_related_doctype_outside_workspace_registry(self):
		adapter = MagicMock()
		adapter.SUPPORTED_DOCTYPES = {"YRP Work Order"}
		adapter._permission_flags.side_effect = AssertionError("unsupported doctype adapter called")
		adapter.frappe.has_permission.return_value = False

		self.assertFalse(_target_create_permission("YRP Debit", adapter))
		adapter.frappe.has_permission.assert_called_once_with("YRP Debit", ptype="create")

	def make_document(self, *, docstatus=0, open_status="Open"):
		doc = frappe._dict(
			doctype="YRP Work Order",
			name="WO-1",
			docstatus=docstatus,
			modified="2026-10-06 10:00:00",
			status="Draft" if docstatus == 0 else "Submitted",
			open_status=open_status,
			lot="LOT-1",
			process_name="Cutting",
			item="STYLE-1",
			production_detail="IPD-1",
			supplier="SUPPLIER-1",
			includes_packing=1,
			no_receivables=1,
			delivery_location="UNIT-1",
			sd_close_reason="Sewing Shortage",
			close_other_reason="",
			close_remarks="Short receipt approved",
			planned_quantity=12,
			total_quantity=10,
			total_no_of_pieces_delivered=8,
			total_no_of_pieces_received=6,
			is_rework=0,
			deliverables=[
				frappe._dict(item_variant="RAW-S", qty=12, pending_quantity=4, row_index=0),
			],
			receivables=[
				frappe._dict(item_variant="STYLE-S", qty=10, pending_quantity=3, row_index=0),
			],
			work_order_calculated_items=[
				frappe._dict(name="CALC-1", item_variant="STYLE-S", quantity=10),
			],
		)
		doc.check_permission = MagicMock()
		doc.has_permission = MagicMock(return_value=True)
		doc.set = MagicMock(side_effect=lambda fieldname, value: setattr(doc, fieldname, value))
		doc.meta = MagicMock()
		doc.meta.fields = [
			frappe._dict(
				fieldname="lot",
				label="Lot",
				fieldtype="Link",
				options="SD YRP Lot",
				hidden=0,
				read_only=0,
				reqd=1,
			),
			frappe._dict(
				fieldname="process_name",
				label="Process",
				fieldtype="Link",
				options="YRP Process",
				hidden=0,
				read_only=0,
				reqd=1,
			),
			frappe._dict(
				fieldname="expected_delivery_date",
				label="Expected Delivery Date",
				fieldtype="Date",
				options="",
				hidden=0,
				read_only=0,
				reqd=1,
			),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		return doc

	def workspace_base(self, doc, **kwargs):
		permissions = {
			"can_read": True,
			"can_create": True,
			"can_write": doc.docstatus == 0,
			"can_submit": doc.docstatus == 0,
			"can_cancel": doc.docstatus == 1,
			"can_amend": False,
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
			"fields": [{"fieldname": "process_name", "label": "Process", "value": doc.process_name}],
			"totals": [],
			"permissions": permissions,
			"capabilities": capabilities,
			"print_formats": [],
		}

	def test_workspace_exposes_effective_fields_dimensions_selection_and_separate_pending_values(self):
		doc = self.make_document(docstatus=1)
		deliverables = [
			{"items": [{"name": "RAW", "values": {"S": {"qty": 12, "pending_quantity": 4}}}]},
		]
		receivables = [
			{"items": [{"name": "STYLE", "values": {"S": {"qty": 10, "pending_quantity": 3}}}]},
		]
		selection = {"options": [{"item": "STYLE-1", "production_detail": "IPD-1"}]}
		actions = {
			"is_open": True,
			"can_make_delivery_challan": True,
			"can_make_goods_received_note": True,
			"can_change_delivery_date": True,
			"can_calculate_pieces": True,
		}
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.get_workspace_base", side_effect=self.workspace_base),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.group_items_for_ui",
				side_effect=[deliverables, receivables],
			),
			patch("essdee_yrp.fabric_store.documents.work_order.fetch_summary_details", return_value={"item_detail": []}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[
				{"fieldname": "lot", "label": "Lot", "options": "SD YRP Lot", "mandatory": 1},
			]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value=selection),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_action_context", return_value=actions),
			patch("essdee_yrp.fabric_store.documents.work_order.get_close_permission", return_value={"approver_role": "WO Manager", "is_close_manager": True}),
			patch("essdee_yrp.fabric_store.documents.work_order._target_create_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order._related_documents", return_value=[]),
		):
			workspace = get_work_order_workspace(doc.name)

		self.assertEqual(workspace["fields"][0]["fieldname"], "process_name")
		self.assertEqual(workspace["dimensions"][0]["fieldname"], "lot")
		self.assertEqual(workspace["selection_context"], selection)
		self.assertEqual(workspace["matrices"]["deliverables"][0]["items"][0]["values"]["S"]["qty"], 12)
		self.assertEqual(
			workspace["matrices"]["deliverables"][0]["items"][0]["values"]["S"]["pending_quantity"],
			4,
		)
		self.assertEqual(workspace["calculated_items"][0]["quantity"], 10)
		self.assertIn("create_delivery_challan", workspace["capabilities"])
		self.assertIn("create_goods_received_note", workspace["capabilities"])

	def test_target_create_permission_removes_related_capabilities(self):
		doc = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.fetch_summary_details", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_action_context", return_value={
				"is_open": True,
				"can_make_delivery_challan": True,
				"can_make_goods_received_note": True,
			}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_close_permission", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order._target_create_permission", return_value=False),
			patch("essdee_yrp.fabric_store.documents.work_order._related_documents", return_value=[]),
		):
			workspace = get_work_order_workspace(doc.name)

		self.assertNotIn("create_delivery_challan", workspace["capabilities"])
		self.assertNotIn("create_goods_received_note", workspace["capabilities"])

	def test_editor_returns_calculated_rows_and_authoritative_garment_context(self):
		doc = self.make_document()
		garment_context = {"process": "Cutting", "rows": [{"source_row": "LOT-ROW-1", "qty": 12}]}
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=[[], []]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={
				"process_is_cloth_process": False,
				"options": [{"item": "STYLE-1", "production_detail": "IPD-1"}],
			}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_garment_work_order_context", return_value=garment_context),
		):
			editor = get_work_order_editor(doc.name)

		self.assertEqual(editor["calculation_contexts"]["garment"], garment_context)
		self.assertEqual(editor["calculated_items"][0]["name"], "CALC-1")
		self.assertEqual(editor["selection_context"]["options"][0]["item"], "STYLE-1")
		self.assertEqual(editor["values"]["no_receivables"], 1)

	def test_editor_returns_effective_required_and_read_only_field_metadata(self):
		doc = self.make_document()
		metadata = [
			{
				"fieldname": "wo_date",
				"label": "WO Date",
				"fieldtype": "Date",
				"reqd": True,
				"read_only": False,
				"read_only_depends_on": "eval: !doc.edit_wo_date",
			},
			{
				"fieldname": "supplier_address",
				"label": "Supplier Address",
				"fieldtype": "Link",
				"reqd": True,
				"read_only": False,
			},
		]
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=[[], []]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_garment_work_order_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_effective_fields", return_value=metadata) as effective_fields,
		):
			editor = get_work_order_editor(doc.name)

		self.assertEqual(editor["fields"], metadata)
		self.assertEqual(editor["condition_values"], {"edit_wo_date": None})
		effective_fields.assert_called_once_with(doc, tuple(editor["values"]))

	def test_editor_exposes_complete_sectioned_setup_without_hiding_source_owned_values(self):
		doc = self.make_document()
		doc.naming_series = "YRP-WO-.YYYY.-"
		doc.edit_wo_date = 1
		doc.parent_wo = "WO-PARENT-1"
		doc.supplier_type = "Same Supplier"
		doc.rework_type = "No Cost"
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=[[], []]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_garment_work_order_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_effective_fields", return_value=[]) as effective_fields,
		):
			editor = get_work_order_editor(doc.name)

		self.assertEqual(editor["values"]["naming_series"], "YRP-WO-.YYYY.-")
		self.assertEqual(editor["values"]["edit_wo_date"], 1)
		self.assertEqual(editor["values"]["planned_quantity"], 12)
		self.assertEqual(editor["values"]["is_rework"], 0)
		self.assertEqual(editor["values"]["parent_wo"], "WO-PARENT-1")
		self.assertEqual(editor["values"]["supplier_type"], "Same Supplier")
		self.assertEqual(editor["values"]["rework_type"], "No Cost")
		effective_fields.assert_called_once_with(doc, tuple(editor["values"]))

	def test_editor_exposes_only_applicable_work_order_header_dimensions(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=[[], []]),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui",
				return_value=[
					{"fieldname": "lot", "is_production_group": 1, "mandatory": 1},
					{"fieldname": "received_type", "is_production_group": 0, "mandatory": 1},
				],
			),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_garment_work_order_context", return_value={}),
		):
			editor = get_work_order_editor(doc.name)

		self.assertEqual([dimension["fieldname"] for dimension in editor["dimensions"]], ["lot"])

	def test_editor_returns_authoritative_fabric_context_unchanged(self):
		doc = self.make_document()
		fabric_context = {"is_fabric_process": True, "kind": "dyeing", "rows": [{"fabric_row": "FAB-1"}]}
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.group_items_for_ui", side_effect=[[], []]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_selection_context", return_value={
				"process_is_cloth_process": True,
				"options": [{"item": "CLOTH-1", "production_detail": "IPD-1"}],
			}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_fabric_deliverable_context", return_value=fabric_context),
		):
			editor = get_work_order_editor(doc.name)

		self.assertEqual(editor["calculation_contexts"], {"fabric": fabric_context})

	def test_save_passes_grouped_rows_through_work_order_controller(self):
		doc = MagicMock()
		doc.doctype = "YRP Work Order"
		doc.name = "WO-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 10:00:00"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		deliverables = [{"items": [{"name": "RAW", "values": {"S": {"qty": 12}}}]}]
		receivables = [{"items": [{"name": "STYLE", "values": {"S": {"qty": 10}}}]}]
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace", return_value=refreshed),
		):
			result = save_work_order_document(
				{
					"supplier": "SUPPLIER-2",
					"no_receivables": 1,
					"deliverable_details": deliverables,
					"receivable_details": receivables,
					"open_status": "Close",
				},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result, refreshed)
		doc.update.assert_called_once_with({"supplier": "SUPPLIER-2", "no_receivables": 1})
		self.assertEqual(
			doc.set.call_args_list,
			[
				call("deliverable_details", frappe.as_json(deliverables)),
				call("receivable_details", frappe.as_json(receivables)),
			],
		)
		doc.save.assert_called_once_with()

	def test_save_allows_date_control_but_rejects_source_owned_setup_values(self):
		doc = MagicMock()
		doc.doctype = "YRP Work Order"
		doc.name = "WO-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 10:00:00"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			save_work_order_document(
				{
					"naming_series": "YRP-WO-.YYYY.-",
					"edit_wo_date": 1,
					"is_rework": 1,
					"parent_wo": "FORGED-PARENT",
					"supplier_type": "Different Supplier",
					"rework_type": "Additional Cost",
					"planned_quantity": 999,
				},
				name=doc.name,
				expected_modified=doc.modified,
			)

		doc.update.assert_called_once_with(
			{"naming_series": "YRP-WO-.YYYY.-", "edit_wo_date": 1}
		)

	def test_save_serializes_empty_groups_so_controller_can_clear_rows(self):
		doc = MagicMock()
		doc.doctype = "YRP Work Order"
		doc.name = "WO-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 10:00:00"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			save_work_order_document(
				{"deliverable_details": [], "receivable_details": []},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(
			doc.set.call_args_list,
			[call("deliverable_details", "[]"), call("receivable_details", "[]")],
		)

	def test_save_includes_only_configured_dynamic_stock_dimensions(self):
		doc = MagicMock()
		doc.doctype = "YRP Work Order"
		doc.name = "WO-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 10:00:00"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		doc.meta.get_field.return_value = frappe._dict(fieldtype="Link")
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui",
				return_value=[{"fieldname": "production_batch", "is_production_group": 1}],
			),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			save_work_order_document(
				{"supplier": "SUPPLIER-2", "production_batch": "BATCH-1", "internal_mode": 1},
				name=doc.name,
				expected_modified=doc.modified,
			)

		doc.update.assert_called_once_with(
			{"supplier": "SUPPLIER-2", "production_batch": "BATCH-1"}
		)

	def test_save_dimension_collision_cannot_reopen_source_owned_fields(self):
		doc = MagicMock()
		doc.doctype = "YRP Work Order"
		doc.name = "WO-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 10:00:00"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		doc.meta.get_field.return_value = frappe._dict(fieldtype="Link")
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_stock_dimensions_for_ui",
				return_value=[{"fieldname": "is_rework", "is_production_group": 1}],
			),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			save_work_order_document(
				{"supplier": "SUPPLIER-2", "is_rework": 1},
				name=doc.name,
				expected_modified=doc.modified,
			)

		doc.update.assert_called_once_with({"supplier": "SUPPLIER-2"})

	def test_stale_calculation_is_rejected_before_domain_service_runs(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.calculate_garment_work_order") as calculate,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			execute_work_order_command(
				doc.name,
				"calculate_garment",
				{"rows": [{"source_row": "ROW-1", "qty": 4}]},
				expected_modified="2026-10-06 09:00:00",
			)

		calculate.assert_not_called()

	def test_close_with_debit_delegates_complete_payload_to_owner_services(self):
		doc = self.make_document(docstatus=1)
		refreshed = {"record": {"name": doc.name}}
		payload = {
			"with_debit": True,
			"debit_no": "D-1",
			"debit_value": 250,
			"debit_reason": "Short receipt",
			"close_reason": "Sewing Shortage",
			"close_other_reason": "",
			"close_remarks": "Verified",
		}
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.create_debit") as create_debit,
			patch("essdee_yrp.fabric_store.documents.work_order.close_work_order") as close,
			patch(
				"essdee_yrp.fabric_store.documents.work_order.get_close_permission",
				return_value={"approver_role": "WO Manager", "is_close_manager": True},
			),
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace", return_value=refreshed),
		):
			result = execute_work_order_command(
				doc.name,
				"close",
				payload,
				expected_modified=doc.modified,
			)

		self.assertEqual(result, refreshed)
		create_debit.assert_called_once_with(
			doc.name,
			debit_no="D-1",
			debit_value=250,
			reason="Short receipt",
			on_close=1,
		)
		close.assert_called_once_with(
			doc.name,
			sd_close_reason="Sewing Shortage",
			close_other_reason="",
			close_remarks="Verified",
		)

	def test_close_context_reports_debit_creation_and_approval_permissions(self):
		doc = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order.fetch_summary_details", return_value={}),
			patch("essdee_yrp.fabric_store.documents.work_order._close_recuts", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order._target_read_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order._target_create_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.work_order.get_close_permission", return_value={"approver_role": "WO Manager", "is_close_manager": True}),
			patch("essdee_yrp.fabric_store.documents.work_order.get_debits", return_value=[{"name": "DEBIT-1"}]),
			patch("essdee_yrp.fabric_store.documents.work_order._settings_role_allowed", return_value=True),
		):
			context = execute_work_order_command(
				doc.name,
				"get_close_context",
				expected_modified=doc.modified,
			)

		self.assertTrue(context["can_create_debit"])
		self.assertTrue(context["can_approve_debit"])
		self.assertEqual(context["debits"], [{"name": "DEBIT-1"}])
		self.assertEqual(
			context["reason_options"],
			[
				"NA",
				"Cutting Shortage",
				"Printing Shortage",
				"Sewing Shortage",
				"Sewing Missing",
				"Others",
			],
		)
		self.assertEqual(context["close_reason"], "Sewing Shortage")
		self.assertEqual(context["close_other_reason"], "")
		self.assertEqual(context["close_remarks"], "Short receipt approved")

	def test_create_debit_capability_uses_owner_permission_and_open_submitted_state(self):
		from essdee_yrp.fabric_store.documents.work_order import _capability_candidates

		for docstatus, open_status, allowed, expected in (
			(1, "Open", True, True),
			(1, "Open", False, False),
			(0, "Open", True, False),
			(2, "Open", True, False),
			(1, "Close", True, False),
			(1, "Close Request", True, False),
		):
			with self.subTest(docstatus=docstatus, open_status=open_status, allowed=allowed), patch(
				"essdee_yrp.fabric_store.documents.work_order.has_debit_request_permission",
				return_value=allowed,
			):
				doc = self.make_document(docstatus=docstatus, open_status=open_status)
				capabilities = _capability_candidates(doc, {}, {}, {})
				self.assertEqual(capabilities["create_debit"]["eligible"], expected)

	def test_create_debit_forwards_attachment_and_refreshes_workspace(self):
		doc = self.make_document(docstatus=1)
		refreshed = {"record": {"name": doc.name}}
		for attachment in ("/private/files/debit.pdf", ""):
			with (
				self.subTest(attachment=attachment),
				patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
				patch("essdee_yrp.fabric_store.documents.work_order.has_debit_request_permission", return_value=True),
				patch("essdee_yrp.fabric_store.documents.work_order.create_debit") as create,
				patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace", return_value=refreshed),
			):
				result = execute_work_order_command(
					doc.name,
					"create_debit",
					{"debit_no": "D-1", "debit_value": 250, "reason": "Short receipt", "debit_document": attachment},
					expected_modified=doc.modified,
				)
				self.assertEqual(result, refreshed)
				create.assert_called_once_with(
					doc.name,
					debit_no="D-1",
					debit_value=250,
					reason="Short receipt",
					debit_document=attachment or None,
					on_close=0,
				)

	def test_forged_create_debit_requires_owner_permission(self):
		doc = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.has_debit_request_permission", return_value=False),
			patch("essdee_yrp.fabric_store.documents.work_order.create_debit") as create,
			self.assertRaises(frappe.PermissionError),
		):
			execute_work_order_command(
				doc.name,
				"create_debit",
				{"debit_no": "D-1", "debit_value": 250, "reason": "Short receipt"},
				expected_modified=doc.modified,
			)

		create.assert_not_called()

	def test_forged_create_debit_rejects_non_open_work_order(self):
		doc = self.make_document(docstatus=0)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.create_debit") as create,
			self.assertRaises(frappe.ValidationError),
		):
			execute_work_order_command(
				doc.name,
				"create_debit",
				{"debit_no": "D-1", "debit_value": 250, "reason": "Short receipt"},
				expected_modified=doc.modified,
			)

		create.assert_not_called()

	def test_rework_command_delegates_selected_sources_and_supplier(self):
		doc = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.work_order.create_rework_work_order", return_value="WO-RW-1") as create,
			patch("essdee_yrp.fabric_store.documents.work_order.get_work_order_workspace", return_value={"record": {"name": "WO-RW-1"}}),
		):
			result = execute_work_order_command(
				doc.name,
				"create_rework",
				{
					"rows": [{"source_key": "GRN-ROW-1", "qty": 2}],
					"supplier_type": "Different Supplier",
					"supplier": "SUPPLIER-2",
				},
				expected_modified=doc.modified,
			)

		self.assertEqual(result["record"]["name"], "WO-RW-1")
		create.assert_called_once_with(
			doc.name,
			[{"source_key": "GRN-ROW-1", "qty": 2}],
			supplier_type="Different Supplier",
			supplier="SUPPLIER-2",
		)

	def test_approve_debit_rejects_a_debit_from_another_work_order(self):
		doc = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.work_order._get_work_order", return_value=doc),
			patch(
				"essdee_yrp.fabric_store.documents.work_order.frappe.db.get_value",
				return_value="WO-OTHER",
			),
			patch("essdee_yrp.fabric_store.documents.work_order.approve_debit") as approve,
			self.assertRaises(frappe.PermissionError),
		):
			execute_work_order_command(
				doc.name,
				"approve_debit",
				{"debit": "DEBIT-1"},
				expected_modified=doc.modified,
			)

		approve.assert_not_called()


class TestFabricStoreWorkOrderControllerSave(IntegrationTestCase):
	def test_duplicate_editor_supports_a_real_frappe_work_order_document(self):
		name = frappe.db.get_value(
			"YRP Work Order",
			{"docstatus": ["in", [0, 1, 2]], "is_rework": 0},
			"name",
			order_by="modified desc",
		)
		if not name:
			self.skipTest("No Work Order is available for duplicate regression")

		editor = get_work_order_editor(source={"duplicate_from": name})

		self.assertEqual(editor["name"], "")
		self.assertEqual(editor["deliverable_details"], [])
		self.assertEqual(editor["receivable_details"], [])
		self.assertEqual(editor["calculated_items"], [])

	def test_real_controller_accepts_grouped_json_and_can_clear_draft_rows(self):
		name = frappe.db.get_value(
			"YRP Work Order",
			{"docstatus": 0, "is_rework": 0},
			"name",
		)
		if not name:
			self.skipTest("No Draft Work Order is available for controller save regression")
		doc = frappe.get_doc("YRP Work Order", name)
		deliverables = group_items_for_ui(
			doc.get("deliverables") or [],
			"YRP Work Order Deliverables",
		)
		receivables = group_items_for_ui(
			doc.get("receivables") or [],
			"YRP Work Order Receivables",
		)
		if not deliverables or not receivables:
			self.skipTest(f"Draft Work Order {name} has no grouped rows")

		save_work_order_document(
			{
				"deliverable_details": deliverables,
				"receivable_details": receivables,
			},
			name=name,
			expected_modified=doc.modified,
		)
		refreshed = frappe.get_doc("YRP Work Order", name)
		self.assertTrue(refreshed.deliverables)
		self.assertTrue(refreshed.receivables)
		self.assertIsInstance(refreshed.deliverable_details, str)
		self.assertIsInstance(refreshed.receivable_details, str)

		save_work_order_document(
			{"deliverable_details": [], "receivable_details": []},
			name=name,
			expected_modified=refreshed.modified,
		)
		cleared = frappe.get_doc("YRP Work Order", name)
		self.assertEqual(cleared.deliverables, [])
		self.assertEqual(cleared.receivables, [])

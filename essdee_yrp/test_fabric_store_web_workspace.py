from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe

import essdee_yrp.fabric_store.web_workspace as workspace
from essdee_yrp.fabric_store.web_workspace import (
	DOCUMENT_KEYS,
	STOCK_OPERATION_DOCTYPES,
	SUPPORTED_DOCTYPES,
	_get_supported_document,
	_permission_flags,
	_require_supported_doctype,
	_require_supported_operation,
	change_document_status,
	get_capabilities,
	get_document,
	get_work_order_workspace,
)


class TestFabricStoreWebWorkspace(TestCase):
	def test_document_item_groups_use_readable_grouped_projection_for_hidden_child_table(self):
		rows = [frappe._dict(item_variant="STYLE-S", qty=2)]
		groups = [{"items": [{"name": "STYLE", "values": {"S": {"qty": 2}}}]}]
		doc = MagicMock(doctype="YRP Delivery Challan")
		doc.get.side_effect = lambda key, default=None: {
			"items": rows,
			"__onload": {"item_details": groups},
		}.get(key, default)

		with patch(
			"essdee_yrp.fabric_store.web_workspace.get_permitted_fields",
			return_value=["item_details"],
		):
			item_groups, row_count = workspace._document_item_groups(doc)

		self.assertEqual(item_groups, groups)
		self.assertEqual(row_count, 1)
		doc.run_method.assert_called_once_with("onload")

	def test_supported_documents_match_the_fabric_store_contract(self):
		self.assertEqual(
			SUPPORTED_DOCTYPES,
			{
				"YRP Work Order",
				"Purchase Order",
				"YRP Stock Entry",
				"YRP Stock Reconciliation",
				"YRP Stock Update",
				"SD YRP Lot Transfer",
				"YRP Delivery Challan",
				"YRP Goods Received Note",
			},
		)

	def test_permission_flags_use_record_permissions_and_document_state(self):
		doc = MagicMock(doctype="YRP Stock Entry", docstatus=1)

		def has_permission(doctype, ptype="read", doc=None, **kwargs):
			self.assertEqual(doctype, "YRP Stock Entry")
			if ptype == "create":
				self.assertIsNone(doc)
			else:
				self.assertIs(doc, expected_doc)
			return ptype in {"read", "create", "write", "submit", "cancel", "amend", "print"}

		expected_doc = doc
		with patch(
			"essdee_yrp.fabric_store.web_workspace.frappe.has_permission",
			side_effect=has_permission,
		) as permission:
			flags = _permission_flags("YRP Stock Entry", doc)

		self.assertEqual(
			flags,
			{
				"can_read": True,
				"can_create": True,
				"can_write": False,
				"can_submit": False,
				"can_cancel": True,
				"can_amend": False,
				"can_print": True,
			},
		)
		self.assertEqual(
			permission.call_args_list,
			[
				call("YRP Stock Entry", ptype="read", doc=doc),
				call("YRP Stock Entry", ptype="create"),
				call("YRP Stock Entry", ptype="write", doc=doc),
				call("YRP Stock Entry", ptype="submit", doc=doc),
				call("YRP Stock Entry", ptype="cancel", doc=doc),
				call("YRP Stock Entry", ptype="amend", doc=doc),
				call("YRP Stock Entry", ptype="print", doc=doc),
			],
		)

	def test_capabilities_omit_unreadable_sections_and_operations(self):
		unreadable = {"Purchase Order", "SD YRP Lot Transfer", "YRP Goods Received Note"}

		def has_permission(doctype, ptype="read", **kwargs):
			if ptype == "read":
				return doctype not in unreadable
			return True

		with patch(
			"essdee_yrp.fabric_store.web_workspace.frappe.has_permission",
			side_effect=has_permission,
		):
			payload = get_capabilities()

		self.assertIn("work_orders", payload["sections"])
		self.assertNotIn("purchase_orders", payload["sections"])
		self.assertIn("stock_transfers", payload["sections"])
		self.assertNotIn(
			"lot_transfer",
			payload["sections"]["stock_transfers"]["operations"],
		)
		self.assertFalse(payload["related_documents"]["goods_received_note"]["can_read"])

	def test_capabilities_do_not_embed_implicit_business_filters(self):
		with patch(
			"essdee_yrp.fabric_store.web_workspace.frappe.has_permission",
			return_value=True,
		):
			payload = get_capabilities()

		def assert_no_filters(value):
			if isinstance(value, dict):
				self.assertNotIn("filters", value)
				for child in value.values():
					assert_no_filters(child)
			elif isinstance(value, list):
				for child in value:
					assert_no_filters(child)

		assert_no_filters(payload)
		self.assertEqual(
			set(payload["sections"]["stock_transfers"]["operations"]),
			set(STOCK_OPERATION_DOCTYPES),
		)
		self.assertEqual(
			payload["sections"]["work_orders"]["doctype"],
			DOCUMENT_KEYS["work_orders"],
		)

	def test_unsupported_operations_and_doctypes_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_require_supported_operation("delete_everything")
		with self.assertRaises(frappe.ValidationError):
			_require_supported_doctype("User")

	def test_supported_document_uses_record_level_permission_check(self):
		doc = MagicMock(doctype="YRP Work Order", name="WO-1")
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True) as permission,
		):
			result = _get_supported_document("YRP Work Order", "WO-1")

		self.assertIs(result, doc)
		permission.assert_called_once_with("YRP Work Order", ptype="read", doc=doc, throw=True)

	@patch("essdee_yrp.fabric_store.web_workspace.group_items_for_ui")
	@patch("essdee_yrp.fabric_store.web_workspace.fetch_summary_details")
	@patch("essdee_yrp.fabric_store.web_workspace._permission_flags")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_work_order_workspace_reuses_summary_and_grouping_services(
		self,
		get_document,
		permission_flags,
		fetch_summary,
		group_items,
	):
		doc = frappe._dict(
			doctype="YRP Work Order",
			name="WO-1",
			docstatus=1,
			modified="2026-10-03 10:00:00",
			status="Partially Delivered",
			open_status="Open",
			production_detail="IPD-1",
			deliverables=[frappe._dict(item_variant="ITEM-IN")],
			receivables=[frappe._dict(item_variant="ITEM-OUT")],
		)
		doc.meta = MagicMock()
		doc.meta.get_field.return_value = None
		get_document.return_value = doc
		permission_flags.return_value = {
			"can_read": True,
			"can_create": False,
			"can_write": False,
			"can_submit": False,
			"can_cancel": False,
			"can_amend": False,
			"can_print": True,
		}
		fetch_summary.return_value = {
			"item_detail": [{"overall_planned": 10, "overall_delivered": 8, "overall_received": 6}],
			"deliverables": [{"items": [{"name": "ITEM-IN"}]}],
			"work_order_docstatus": 1,
		}
		group_items.side_effect = [
			[{"items": [{"name": "ITEM-IN"}]}],
			[{"items": [{"name": "ITEM-OUT"}]}],
		]

		with patch("essdee_yrp.fabric_store.web_workspace.frappe.get_list", return_value=[]):
			payload = get_work_order_workspace("WO-1")

		fetch_summary.assert_called_once_with("WO-1", "IPD-1")
		self.assertEqual(
			group_items.call_args_list,
			[
				call(doc.deliverables, "YRP Work Order Deliverables"),
				call(doc.receivables, "YRP Work Order Receivables"),
			],
		)
		self.assertEqual(payload["summary"], fetch_summary.return_value)
		self.assertEqual(payload["deliverables"][0]["items"][0]["name"], "ITEM-IN")
		self.assertEqual(payload["receivables"][0]["items"][0]["name"], "ITEM-OUT")

	@patch("essdee_yrp.fabric_store.web_workspace.group_items_for_ui", return_value=[])
	@patch("essdee_yrp.fabric_store.web_workspace.fetch_summary_details", return_value={})
	@patch("essdee_yrp.fabric_store.web_workspace._permission_flags")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_draft_work_order_hides_related_document_create_actions(
		self,
		get_document,
		permission_flags,
		_fetch_summary,
		_group_items,
	):
		doc = frappe._dict(
			doctype="YRP Work Order",
			name="WO-DRAFT",
			docstatus=0,
			modified="2026-10-05 10:00:00",
			status="Draft",
			open_status="Open",
			production_detail="IPD-1",
			deliverables=[],
			receivables=[],
		)
		doc.meta = MagicMock()
		doc.meta.get_field.return_value = None
		get_document.return_value = doc
		permission_flags.return_value = {
			"can_read": True,
			"can_create": True,
			"can_write": True,
			"can_submit": True,
			"can_cancel": False,
			"can_amend": False,
			"can_print": True,
		}

		with patch("essdee_yrp.fabric_store.web_workspace.frappe.get_list", return_value=[]):
			payload = get_work_order_workspace(doc.name)

		for capability in payload["related_permissions"].values():
			self.assertFalse(capability["can_create"])
			self.assertIn("submitted", capability["create_reason"].lower())

	@patch("essdee_yrp.fabric_store.web_workspace.group_items_for_ui", return_value=[])
	@patch("essdee_yrp.fabric_store.web_workspace.fetch_summary_details", return_value={})
	@patch("essdee_yrp.fabric_store.web_workspace._permission_flags")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_work_order_related_documents_use_exact_relationships_and_modified_order(
		self,
		get_document,
		permission_flags,
		_fetch_summary,
		_group_items,
	):
		doc = frappe._dict(
			doctype="YRP Work Order",
			name="WO-1",
			docstatus=1,
			modified="2026-10-03 10:00:00",
			production_detail="IPD-1",
			deliverables=[],
			receivables=[],
		)
		doc.meta = MagicMock()
		doc.meta.get_field.return_value = None
		get_document.return_value = doc
		permission_flags.return_value = {
			"can_read": True,
			"can_create": True,
			"can_write": True,
			"can_submit": True,
			"can_cancel": True,
			"can_amend": True,
			"can_print": True,
		}

		def related(doctype, **kwargs):
			if doctype == "YRP Delivery Challan":
				return [frappe._dict(name="DC-2", modified="2026-10-03 12:00:00"), frappe._dict(name="DC-1", modified="2026-10-03 11:00:00")]
			return [frappe._dict(name="GRN-1", modified="2026-10-03 13:00:00")]

		with patch("essdee_yrp.fabric_store.web_workspace.frappe.get_list", side_effect=related) as get_list:
			payload = get_work_order_workspace("WO-1")

		self.assertEqual([row["name"] for row in payload["delivery_challans"]], ["DC-2", "DC-1"])
		self.assertEqual([row["name"] for row in payload["goods_received_notes"]], ["GRN-1"])
		calls = {entry.args[0]: entry.kwargs for entry in get_list.call_args_list}
		self.assertEqual(calls["YRP Delivery Challan"]["filters"], {"work_order": "WO-1"})
		self.assertEqual(
			calls["YRP Goods Received Note"]["filters"],
			{"against": "YRP Work Order", "against_id": "WO-1"},
		)
		self.assertEqual(calls["YRP Delivery Challan"]["order_by"], "modified desc")
		self.assertNotIn("process_name", calls["YRP Delivery Challan"]["filters"])

	def _lifecycle_doc(self, docstatus):
		doc = MagicMock()
		doc.doctype = "YRP Stock Entry"
		doc.name = "STE-1"
		doc.docstatus = docstatus
		doc.modified = "2026-10-03 12:00:00"
		return doc

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "STE-1"}})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_draft_document_can_be_submitted_with_permission(self, get_supported, get_payload):
		doc = self._lifecycle_doc(0)
		get_supported.return_value = doc
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True) as permission:
			result = change_document_status(
				"YRP Stock Entry",
				"STE-1",
				"submit",
				expected_modified=doc.modified,
			)

		doc.submit.assert_called_once_with()
		permission.assert_called_once_with("YRP Stock Entry", ptype="submit", doc=doc, throw=True)
		self.assertEqual(result["record"]["name"], "STE-1")
		get_payload.assert_called_once_with("YRP Stock Entry", "STE-1")

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_submitted_document_can_be_cancelled_with_permission(self, get_supported, _get_payload):
		doc = self._lifecycle_doc(1)
		get_supported.return_value = doc
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True):
			change_document_status("YRP Stock Entry", "STE-1", "cancel")
		doc.cancel.assert_called_once_with()

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "STE-2"}})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_cancelled_document_can_be_amended_with_permission(self, get_supported, get_payload):
		doc = self._lifecycle_doc(2)
		amended = MagicMock(name="STE-2", doctype="YRP Stock Entry", docstatus=0)
		amended.name = "STE-2"
		get_supported.return_value = doc
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.copy_doc", return_value=amended),
		):
			result = change_document_status("YRP Stock Entry", "STE-1", "amend")

		self.assertEqual(amended.amended_from, "STE-1")
		self.assertEqual(amended.docstatus, 0)
		amended.insert.assert_called_once_with()
		get_payload.assert_called_once_with("YRP Stock Entry", "STE-2")
		self.assertEqual(result["record"]["name"], "STE-2")

	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_lifecycle_rejects_stale_document_before_mutation(self, get_supported):
		doc = self._lifecycle_doc(0)
		get_supported.return_value = doc
		with self.assertRaises(frappe.TimestampMismatchError):
			change_document_status(
				"YRP Stock Entry",
				"STE-1",
				"submit",
				expected_modified="2026-10-03 11:59:59",
			)
		doc.submit.assert_not_called()

	def test_document_endpoints_reject_unsupported_or_unauthorized_calls(self):
		with self.assertRaises(frappe.ValidationError):
			get_document("User", "Administrator")

		doc = self._lifecycle_doc(0)
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=doc),
			patch(
				"essdee_yrp.fabric_store.web_workspace.frappe.has_permission",
				side_effect=frappe.PermissionError,
			),
			self.assertRaises(frappe.PermissionError),
		):
			change_document_status("YRP Stock Entry", "STE-1", "submit")
			doc.submit.assert_not_called()

	@patch("essdee_yrp.fabric_store.web_workspace.get_document_print_formats", return_value=[])
	@patch("essdee_yrp.fabric_store.web_workspace._document_details", return_value=[])
	@patch("essdee_yrp.fabric_store.web_workspace._document_item_groups", return_value=([], 0))
	@patch("essdee_yrp.fabric_store.web_workspace._serialize_document")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_submitted_dc_popup_exposes_return_and_complete_transfer_actions(
		self,
		get_supported,
		serialize,
		_groups,
		_details,
		_formats,
	):
		doc = frappe._dict(
			doctype="YRP Delivery Challan",
			name="DC-1",
			docstatus=1,
			work_order="WO-1",
			item="STYLE-1",
			lot="LOT-1",
			is_internal_unit=1,
			transfer_complete=0,
		)
		get_supported.return_value = doc
		serialize.return_value = {
			"doctype": doc.doctype,
			"name": doc.name,
			"docstatus": 1,
			"permissions": {"can_read": True},
		}
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True):
			payload = get_document(doc.doctype, doc.name)

		self.assertIn("actions", payload, "Submitted DC popup has no contextual actions")
		self.assertEqual(
			payload["actions"],
			{"can_return": True, "can_complete_transfer": True},
		)
		self.assertEqual(
			payload["context"],
			{"work_order": "WO-1", "item": "STYLE-1", "lot": "LOT-1"},
		)

	def test_delivery_challan_return_endpoint_returns_new_grn_popup_payload(self):
		self.assertTrue(
			hasattr(workspace, "create_delivery_challan_return"),
			"Fabric Store has no Delivery Challan return endpoint",
		)
		dc = frappe._dict(
			doctype="YRP Delivery Challan",
			name="DC-1",
			docstatus=1,
			work_order="WO-1",
		)
		expected = {"record": {"doctype": "YRP Goods Received Note", "name": "GRN-RET-1", "docstatus": 0}}
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=dc),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.create_return_grn", return_value="GRN-RET-1") as create,
			patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value=expected),
		):
			payload = workspace.create_delivery_challan_return(
				"DC-1",
				[{"delivery_challan_item": "DCI-1", "return_quantity": 2}],
				"PURCHASE",
			)

		self.assertEqual(payload, expected)
		create.assert_called_once_with(
			"DC-1",
			[{"delivery_challan_item": "DCI-1", "return_quantity": 2}],
			"PURCHASE",
		)

	def test_complete_transfer_endpoint_returns_stock_entry_popup_payload(self):
		self.assertTrue(
			hasattr(workspace, "complete_work_order_document_transfer"),
			"Fabric Store has no Complete Transfer endpoint",
		)
		dc = frappe._dict(doctype="YRP Delivery Challan", name="DC-1", docstatus=1)
		expected = {"record": {"doctype": "YRP Stock Entry", "name": "STE-1", "docstatus": 0}}
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=dc),
			patch("essdee_yrp.fabric_store.web_workspace.make_dc_completion", return_value="STE-1") as complete,
			patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value=expected),
		):
			payload = workspace.complete_work_order_document_transfer(dc.doctype, dc.name)

		self.assertEqual(payload, expected)
		complete.assert_called_once_with("DC-1")

	@patch("essdee_yrp.fabric_store.web_workspace.get_purchase_order_defaults")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_purchase_order_workspace_opens_readable_non_yrp_orders_without_grn(self, get_supported, defaults):
		doc = frappe._dict(
			doctype="Purchase Order",
			name="PO-REGULAR",
			docstatus=1,
			modified="2026-10-03 10:00:00",
			status="To Receive",
			open_status="Open",
			is_yrp_managed=0,
			supplier="SUPPLIER-1",
			items=[frappe._dict(item_code="ITEM-1", qty=4)],
		)
		doc.meta = MagicMock()
		get_supported.return_value = doc

		with (
			patch("essdee_yrp.fabric_store.web_workspace._document_details", return_value=[]),
			patch("essdee_yrp.fabric_store.web_workspace._permission_flags", return_value={"can_read": True, "can_create": True, "can_print": True}),
			patch("essdee_yrp.fabric_store.web_workspace.group_items_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.web_workspace.get_document_print_formats", return_value=[]),
		):
			payload = workspace.get_purchase_order_workspace("PO-REGULAR")

		self.assertEqual(payload["record"]["name"], "PO-REGULAR")
		self.assertFalse(payload["grn"]["can_create"])
		self.assertIn("YRP managed", payload["grn"]["reason"])
		defaults.assert_not_called()

	@patch("essdee_yrp.fabric_store.web_workspace.get_purchase_order_defaults")
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_purchase_order_workspace_grn_eligibility_reuses_controller_defaults(self, get_supported, defaults):
		doc = frappe._dict(
			doctype="Purchase Order",
			name="PO-YRP-1",
			docstatus=1,
			modified="2026-10-03 10:00:00",
			status="To Receive",
			open_status="Open",
			is_yrp_managed=1,
			supplier="SUPPLIER-1",
			items=[frappe._dict(item_code="ITEM-S", qty=4, row_index=0)],
		)
		doc.meta = MagicMock()
		get_supported.return_value = doc
		defaults.return_value = {"items": [frappe._dict(item_variant="ITEM-S", quantity=4)]}

		def permissions(doctype, doc=None):
			return {"can_read": True, "can_create": doctype == "YRP Goods Received Note", "can_print": True}

		with (
			patch("essdee_yrp.fabric_store.web_workspace._document_details", return_value=[]),
			patch("essdee_yrp.fabric_store.web_workspace._permission_flags", side_effect=permissions),
			patch("essdee_yrp.fabric_store.web_workspace.group_items_for_ui", return_value=[{"items": [{"name": "ITEM"}]}]),
			patch("essdee_yrp.fabric_store.web_workspace.get_document_print_formats", return_value=[]),
		):
			payload = workspace.get_purchase_order_workspace("PO-YRP-1")

		defaults.assert_called_once_with("PO-YRP-1")
		self.assertTrue(payload["grn"]["can_create"])
		self.assertEqual(payload["item_row_count"], 1)
		self.assertEqual(payload["item_groups"][0]["items"][0]["name"], "ITEM")

	def test_purchase_order_editor_exposes_permission_safe_new_document_defaults(self):
		doc = frappe._dict(
			doctype="Purchase Order",
			name=None,
			docstatus=0,
			is_yrp_managed=0,
			supplier=None,
			transaction_date="2026-10-05",
			schedule_date="2026-10-12",
			set_warehouse=None,
			default_delivery_location=None,
			deliver_to_supplier=0,
			currency="INR",
			company="Essdee",
			terms_and_condition=None,
			comments=None,
			items=[],
		)
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.db.get_single_value", return_value=1),
			patch("essdee_yrp.fabric_store.web_workspace.get_stock_dimensions_for_ui", return_value=[
				{"fieldname": "lot", "label": "Lot", "options": "SD YRP Lot", "mandatory": 1},
			]),
		):
			payload = workspace.get_purchase_order_editor()

		self.assertEqual(payload["doctype"], "Purchase Order")
		self.assertEqual(payload["values"]["is_yrp_managed"], 1)
		self.assertEqual(payload["values"]["transaction_date"], "2026-10-05")
		self.assertEqual(payload["item_groups"], [])
		self.assertEqual(payload["dimensions"][0]["fieldname"], "lot")
		self.assertTrue(payload["price_validation_enabled"])
		self.assertTrue(payload["permissions"]["can_create"])
		self.assertTrue(payload["permissions"]["can_submit"])

	@patch("essdee_yrp.fabric_store.web_workspace.get_purchase_order_workspace", return_value={"record": {"name": "YRP-PO-2026-00001"}})
	@patch("essdee_yrp.fabric_store.web_workspace.ungroup_items_from_ui")
	def test_purchase_order_save_uses_grouped_items_and_allowlisted_header(self, ungroup, get_workspace):
		ungroup.return_value = [frappe._dict(item_code="ITEM-S", qty=4, row_index=0)]
		doc = MagicMock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-2026-00001"
		doc.docstatus = 0
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)

		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
		):
			payload = workspace.save_purchase_order(
				{
					"supplier": "SUPPLIER-1",
					"transaction_date": "2026-10-05",
					"schedule_date": "2026-10-12",
					"set_warehouse": "FABRIC-WH",
					"owner": "malicious@example.com",
					"item_details": [{"items": [{"name": "ITEM", "values": {"S": {"qty": 4}}}]}],
				},
				submit=True,
			)

		header = doc.update.call_args.args[0]
		self.assertEqual(header["supplier"], "SUPPLIER-1")
		self.assertEqual(header["is_yrp_managed"], 1)
		self.assertNotIn("owner", header)
		doc.set.assert_any_call("items", ungroup.return_value)
		doc.insert.assert_called_once_with()
		doc.submit.assert_called_once_with()
		get_workspace.assert_called_once_with("YRP-PO-2026-00001")
		self.assertEqual(payload["record"]["name"], "YRP-PO-2026-00001")

	@patch("essdee_yrp.fabric_store.web_workspace.validate_price_details", create=True)
	@patch("essdee_yrp.fabric_store.web_workspace.ungroup_items_from_ui")
	def test_purchase_order_submit_delegates_price_policy_to_controller(self, ungroup, validate_prices):
		ungroup.return_value = [frappe._dict(item_code="ITEM-S", qty=4, row_index=0, rate=0)]
		doc = MagicMock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-2026-00001"
		doc.docstatus = 0
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)

		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.web_workspace.get_purchase_order_workspace", return_value={"record": {"name": doc.name}}),
		):
			payload = workspace.save_purchase_order(
				{
					"supplier": "SUPPLIER-1",
					"transaction_date": "2026-10-05",
					"schedule_date": "2026-10-12",
					"set_warehouse": "FABRIC-WH",
					"item_details": [{"items": [{"name": "ITEM", "values": {"S": {"qty": 4}}}]}],
				},
				submit=True,
			)

		validate_prices.assert_not_called()
		doc.insert.assert_called_once_with()
		doc.submit.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], doc.name)

	def test_purchase_order_item_price_uses_same_authoritative_resolver_as_desk(self):
		item_detail = {"name": "ITEM", "values": {"S": {"qty": 4}}}
		expected_price = {"rates": {"S": 125}, "tax": "GST 5", "tax_rate": 5}
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.fabric_store.web_workspace.get_item_price_for_ui", return_value=expected_price) as get_price,
			patch("essdee_yrp.fabric_store.web_workspace._get_purchase_order_item_lead_time", return_value=7) as get_lead_time,
		):
			payload = workspace.get_purchase_order_item_price(item_detail, "SUPPLIER-1")

		permission.assert_any_call("Purchase Order", ptype="create", throw=True)
		get_price.assert_called_once_with(item_detail, "SUPPLIER-1")
		get_lead_time.assert_called_once_with(item_detail, "SUPPLIER-1")
		self.assertEqual(payload, {**expected_price, "lead_time_days": 7})

	def test_purchase_order_item_price_allows_missing_price_for_disabled_policy(self):
		item_detail = {"name": "ITEM", "values": {"S": {"qty": 4}}}
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.get_item_price_for_ui", return_value=None),
		):
			payload = workspace.get_purchase_order_item_price(item_detail, "SUPPLIER-1")

		self.assertEqual(payload, {})

	def test_purchase_order_item_schema_uses_write_permission_for_existing_draft(self):
		doc = frappe._dict(doctype="Purchase Order", name="PO-DRAFT-1", docstatus=0)
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=doc) as get_supported,
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data", return_value={"item": "ITEM"}) as schema,
		):
			payload = workspace.get_purchase_order_item_schema("ITEM", "PO-DRAFT-1")

		get_supported.assert_called_once_with("Purchase Order", "PO-DRAFT-1")
		permission.assert_any_call("Purchase Order", ptype="write", doc=doc, throw=True)
		schema.assert_called_once_with("ITEM")
		self.assertEqual(payload["item"], "ITEM")

	def test_purchase_order_parameter_search_uses_po_permission_for_non_system_manager(self):
		def permissions(doctype, ptype="read", **kwargs):
			if doctype == "YRP Additional Parameter Value":
				raise AssertionError("The editor must not require System Manager read access")
			return True

		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", side_effect=permissions) as permission,
			patch(
				"essdee_yrp.cutting.web_workspace._get_stock_item_schema_data",
				return_value={
					"item": "ITEM",
					"additional_parameters": [{"additional_parameter_key": "Shade Code"}],
				},
			),
			patch(
				"essdee_yrp.fabric_store.web_workspace.frappe.get_all",
				return_value=[frappe._dict(name="SHADE-01", value="SHADE-01")],
			) as get_all,
		):
			payload = workspace.search_purchase_order_additional_parameter_values(
				"ITEM",
				"Shade Code",
				"shade",
			)

		permission.assert_any_call("Purchase Order", ptype="create", throw=True)
		permission.assert_any_call("Item", ptype="read", throw=True)
		get_all.assert_called_once_with(
			"YRP Additional Parameter Value",
			filters={"key": "Shade Code", "value": ["like", "%shade%"]},
			fields=["name", "value"],
			order_by="value asc",
			limit_page_length=20,
		)
		self.assertEqual(payload, [{"name": "SHADE-01", "label": "SHADE-01"}])

	def test_purchase_order_parameter_search_rejects_keys_not_configured_for_item(self):
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.cutting.web_workspace._get_stock_item_schema_data",
				return_value={"item": "ITEM", "additional_parameters": []},
			),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.get_all") as get_all,
			self.assertRaises(frappe.ValidationError),
		):
			workspace.search_purchase_order_additional_parameter_values("ITEM", "Private Key")

		get_all.assert_not_called()

	def test_purchase_order_parameter_search_allows_legacy_key_on_authorized_draft_row(self):
		doc = frappe._dict(
			doctype="Purchase Order",
			name="PO-DRAFT-1",
			docstatus=0,
			items=[
				frappe._dict(
					item_code="ITEM-VARIANT",
					additional_parameters='[{"additional_parameter_key":"Legacy Shade","additional_parameter_value":"OLD"}]',
				)
			],
		)
		with (
			patch(
				"essdee_yrp.fabric_store.web_workspace.get_purchase_order_item_schema",
				return_value={"item": "ITEM", "additional_parameters": []},
			),
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=doc) as get_supported,
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.fabric_store.web_workspace.frappe.get_cached_value", return_value="ITEM"),
			patch(
				"essdee_yrp.fabric_store.web_workspace.frappe.get_all",
				return_value=[frappe._dict(name="NEW-SHADE", value="NEW-SHADE")],
			),
		):
			payload = workspace.search_purchase_order_additional_parameter_values(
				"ITEM",
				"Legacy Shade",
				purchase_order="PO-DRAFT-1",
			)

		get_supported.assert_called_once_with("Purchase Order", "PO-DRAFT-1")
		permission.assert_called_once_with("Purchase Order", ptype="write", doc=doc, throw=True)
		self.assertEqual(payload, [{"name": "NEW-SHADE", "label": "NEW-SHADE"}])

	@patch("essdee_yrp.fabric_store.web_workspace.get_stock_dimensions_for_ui")
	def test_context_free_stock_editors_expose_dynamic_unlocked_dimensions_and_options(self, dimensions):
		dimensions.return_value = [
			{"fieldname": "lot", "label": "Lot", "options": "SD YRP Lot", "mandatory": 1},
			{"fieldname": "received_type", "label": "Received Type", "options": "YRP Received Type", "mandatory": 1},
		]
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True):
			editors = {
				operation: workspace.get_stock_operation_editor(operation)
				for operation in STOCK_OPERATION_DOCTYPES
			}

		for operation in ("stock_entry", "stock_reconciliation", "stock_update"):
			self.assertEqual([row["fieldname"] for row in editors[operation]["dimensions"]], ["lot", "received_type"])
			self.assertEqual(editors[operation]["locked_dimensions"], [])
			self.assertEqual(editors[operation]["default_dimensions"], {})
		self.assertEqual(editors["stock_entry"]["purpose_options"], ["Material Issue", "Material Consumed", "Send to Warehouse"])
		self.assertEqual(editors["stock_update"]["update_type_options"], ["Add", "Reduce"])
		self.assertEqual(
			[row["fieldname"] for row in editors["lot_transfer"]["dimensions"]],
			["from_lot", "to_lot", "warehouse", "received_type"],
		)
		self.assertTrue(all(editors[key]["permissions"]["can_submit"] for key in editors))

	@patch("essdee_yrp.fabric_store.web_workspace._document_item_groups", return_value=([{"items": [{"name": "STYLE"}]}], 1))
	@patch("essdee_yrp.fabric_store.web_workspace._permission_flags", return_value={"can_write": True, "can_submit": True})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_existing_stock_draft_reopens_in_editor(self, get_supported, _permissions, _groups):
		draft = frappe._dict(
			doctype="YRP Stock Entry",
			name="STE-1",
			docstatus=0,
			modified="2026-10-03 11:00:00",
			purpose="Material Issue",
		)
		get_supported.return_value = draft
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.get_stock_dimensions_for_ui", return_value=[]),
		):
			payload = workspace.get_stock_operation_editor("stock_entry", name="STE-1")

		self.assertEqual(payload["name"], "STE-1")
		self.assertEqual(payload["item_groups"][0]["items"][0]["name"], "STYLE")
		self.assertTrue(payload["permissions"]["can_write"])

	@patch("essdee_yrp.fabric_store.web_workspace._document_item_groups", return_value=([{"items": [{"name": "STYLE"}]}], 1))
	@patch("essdee_yrp.fabric_store.web_workspace._permission_flags", return_value={"can_write": True, "can_submit": True})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_completion_stock_draft_keeps_its_protected_purpose(self, get_supported, _permissions, _groups):
		draft = frappe._dict(
			doctype="YRP Stock Entry",
			name="STE-COMPLETE-1",
			docstatus=0,
			modified="2026-10-06 12:00:00",
			purpose="DC Completion",
		)
		get_supported.return_value = draft
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.get_stock_dimensions_for_ui", return_value=[]),
		):
			payload = workspace.get_stock_operation_editor("stock_entry", name=draft.name)

		self.assertEqual(payload["purpose_options"][0], "DC Completion")
		self.assertTrue(payload["purpose_locked"])
		self.assertTrue(payload["protected_completion"])

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "STE-COMPLETE-1"}})
	@patch("essdee_yrp.fabric_store.web_workspace._get_supported_document")
	def test_completion_stock_draft_can_submit_but_cannot_change_purpose(self, get_supported, _get_payload):
		doc = MagicMock()
		doc.doctype = "YRP Stock Entry"
		doc.name = "STE-COMPLETE-1"
		doc.docstatus = 0
		doc.modified = "2026-10-06 12:00:00"
		doc.purpose = "DC Completion"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		get_supported.return_value = doc
		values = {
			"purpose": "DC Completion",
			"from_warehouse": "TRANSIT-WH",
			"to_warehouse": "UNIT-WH",
			"item_details": [{"items": [{"name": "STYLE", "values": {"default": {"qty": 2}}}]}],
		}
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True):
			workspace.save_stock_operation(
				"stock_entry",
				values,
				name=doc.name,
				submit=True,
				expected_modified=doc.modified,
			)

		doc.save.assert_not_called()
		doc.submit.assert_called_once_with()
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			self.assertRaises(frappe.ValidationError),
		):
			workspace.save_stock_operation(
				"stock_entry",
				{**values, "purpose": "GRN Completion"},
				name=doc.name,
				expected_modified=doc.modified,
			)

	@patch("essdee_yrp.cutting.web_workspace._get_stock_item_schema_data")
	def test_context_free_stock_item_schema_reuses_cutting_schema_contract(self, schema):
		schema.return_value = {"item": "STYLE", "primary_attribute": "Size", "primary_attribute_values": ["S", "M"]}
		with patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True):
			payload = workspace.get_stock_item_schema("stock_entry", "STYLE")
		schema.assert_called_once_with("STYLE")
		self.assertEqual(payload["primary_attribute_values"], ["S", "M"])

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "STOCK-1"}})
	@patch(
		"essdee_yrp.fabric_store.web_workspace.ungroup_items_from_ui",
		return_value=[{"item": "ITEM-001", "qty": 2}],
	)
	def test_context_free_stock_save_uses_operation_fields_and_controller_lifecycle(self, _ungroup, get_payload):
		cases = {
			"stock_entry": ({"purpose": "Send to Warehouse", "from_warehouse": "A", "to_warehouse": "B"}, {"purpose": "Send to Warehouse", "from_warehouse": "A", "to_warehouse": "B"}),
			"stock_reconciliation": ({"purpose": "Stock Reconciliation", "default_warehouse": "A", "default_supplier": "SUP-1"}, {"purpose": "Stock Reconciliation", "default_warehouse": "A", "default_supplier": "SUP-1"}),
			"stock_update": ({"update_type": "Add", "warehouse": "A", "supplier": "SUP-1"}, {"update_type": "Add", "warehouse": "A", "supplier": "SUP-1"}),
			"lot_transfer": ({}, {}),
		}
		for operation, (headers, expected_headers) in cases.items():
			with self.subTest(operation=operation):
				doc = MagicMock()
				doc.doctype = STOCK_OPERATION_DOCTYPES[operation]
				doc.name = "STOCK-1"
				doc.docstatus = 0
				doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
				row = {"name": "STYLE", "values": {"default": {"qty": 2}}}
				if operation == "lot_transfer":
					row["dimensions"] = {"from_lot": "LOT-A", "to_lot": "LOT-B", "warehouse": "A", "received_type": "PURCHASE"}
				values = {**headers, "edit_posting_date_and_time": 1, "item_details": [{"items": [row]}]}
				with (
					patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
				):
					payload = workspace.save_stock_operation(operation, values, submit=True)

				updated = doc.update.call_args.args[0]
				for fieldname, expected in expected_headers.items():
					self.assertEqual(updated[fieldname], expected)
				self.assertEqual(updated["edit_posting_date_and_time"], 1)
				self.assertTrue(doc.item_details)
				doc.insert.assert_called_once_with()
				doc.submit.assert_called_once_with()
				self.assertEqual(payload["record"]["name"], "STOCK-1")
				get_payload.assert_called_with(STOCK_OPERATION_DOCTYPES[operation], "STOCK-1")

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "SRC-1"}})
	@patch("essdee_yrp.fabric_store.web_workspace.ungroup_items_from_ui")
	def test_context_free_reconciliation_preserves_zero_variant_counts(self, ungroup, _get_payload):
		doc = frappe._dict(
			doctype="YRP Stock Reconciliation",
			name="SRC-1",
			docstatus=0,
			items=[],
		)
		doc.insert = MagicMock()
		doc.set = MagicMock(side_effect=lambda fieldname, value: doc.__setitem__(fieldname, value))
		doc.append = MagicMock(side_effect=lambda _field, row: doc["items"].append(row))
		ungroup.return_value = [{"item": "ITEM-S", "qty": 0}]
		item_details = [
			{
				"items": [
					{
						"name": "ITEM-TEMPLATE",
						"primary_attribute": "Size",
						"values": {"S": {"qty": 0}},
					}
				]
			}
		]

		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
		):
			workspace.save_stock_operation(
				"stock_reconciliation",
				{
					"purpose": "Stock Reconciliation",
					"default_warehouse": "FABRIC-WH",
					"item_details": item_details,
				},
			)

		ungroup.assert_called_once_with(
			item_details,
			"YRP Stock Reconciliation",
			keep_zero=True,
		)
		self.assertEqual(doc["items"], [{"item": "ITEM-S", "qty": 0, "warehouse": "FABRIC-WH"}])
		doc.insert.assert_called_once_with()

	@patch("essdee_yrp.fabric_store.web_workspace.get_document", return_value={"record": {"name": "LT-1"}})
	def test_lot_transfer_promotes_entry_dimensions_required_by_controller(self, _get_payload):
		doc = MagicMock(doctype="SD YRP Lot Transfer", name="LT-1", docstatus=0)
		doc.name = "LT-1"
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)
		item_details = [{
			"items": [{
				"name": "STYLE",
				"dimensions": {"from_lot": "LOT-A", "to_lot": "LOT-B", "warehouse": "FABRIC-WH", "received_type": "PURCHASE"},
				"values": {"default": {"qty": 2}},
			}],
		}]

		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc", return_value=doc),
		):
			workspace.save_stock_operation("lot_transfer", {"item_details": item_details})

		stored = frappe.parse_json(doc.item_details)
		row = stored[0]["items"][0]
		self.assertEqual(row["from_lot"], "LOT-A")
		self.assertEqual(row["to_lot"], "LOT-B")
		self.assertEqual(row["warehouse"], "FABRIC-WH")
		self.assertEqual(row["received_type"], "PURCHASE")

	def test_context_free_stock_save_rejects_unsupported_select_values(self):
		with (
			patch("essdee_yrp.fabric_store.web_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.web_workspace.frappe.new_doc") as new_doc,
			self.assertRaises(frappe.ValidationError),
		):
			workspace.save_stock_operation("stock_entry", {"purpose": "Material Receipt", "item_details": []})
		new_doc.assert_not_called()

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.fabric_store.documents.purchase_order import (
	_capability_candidates,
	_related_documents,
	execute_purchase_order_command,
	get_purchase_order_editor,
	get_purchase_order_workspace,
	save_purchase_order_document,
)


class TestFabricStorePurchaseOrder(TestCase):
	def test_editor_duplicate_returns_unsaved_copy_with_items(self):
		source = self.make_document(docstatus=1)
		duplicate = self.make_document(docstatus=0)
		duplicate.name = None
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=source),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.new_doc", return_value=duplicate),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.purchase_order.group_items_for_ui", return_value=[{"copy": "items"}]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_stock_dimensions_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.db.get_single_value", return_value=0),
		):
			editor = get_purchase_order_editor(source={"duplicate_from": source.name})

		self.assertEqual(editor["name"], "")
		self.assertEqual(editor["values"]["supplier"], source.supplier)
		self.assertEqual(editor["item_groups"], [{"copy": "items"}])
	def make_document(self, *, docstatus=1, status="To Receive", open_status="Open"):
		doc = frappe._dict(
			doctype="Purchase Order",
			name="YRP-PO-1",
			docstatus=docstatus,
			modified="2026-10-06 10:00:00",
			status=status,
			open_status=open_status,
			is_yrp_managed=1,
			supplier="SUPPLIER-1",
			total_qty=12,
			total=1200,
			total_discount=60,
			net_total=1140,
			total_tax=57,
			total_taxes_and_charges=57,
			grand_total=1197,
			items=[frappe._dict(item_code="ITEM-S", qty=12, rate=100, tax=5, row_index=0)],
			sd_lot=[frappe._dict(lot="LOT-1")],
		)
		doc.check_permission = MagicMock()
		doc.meta = MagicMock()
		doc.meta.fields = [
			frappe._dict(fieldname="supplier", label="Supplier", fieldtype="Link", options="Supplier", hidden=0, read_only=0, reqd=1),
			frappe._dict(fieldname="grand_total", label="Grand Total", fieldtype="Currency", hidden=0, read_only=1, reqd=0),
			frappe._dict(fieldname="sd_lot", label="Linked Lots", fieldtype="Table MultiSelect", hidden=0, read_only=0, reqd=0),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		return doc

	def permission_side_effect(self, doctype, ptype="read", **_kwargs):
		if doctype == "YRP Delivery Challan" and ptype == "create":
			return False
		return True

	def test_workspace_returns_effective_fields_controller_totals_and_item_matrix(self):
		doc = self.make_document()
		groups = [{"items": [{"name": "ITEM", "values": {"S": {"qty": 12, "rate": 100, "tax": 5}}}]}]
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["supplier", "grand_total"]),
			patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission", side_effect=self.permission_side_effect),
			patch("essdee_yrp.fabric_store.documents.common.get_document_print_formats", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", side_effect=self.permission_side_effect),
			patch("essdee_yrp.fabric_store.documents.purchase_order.group_items_for_ui", return_value=groups),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_purchase_order_defaults", return_value={"items": [{"quantity": 2}]}),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles", return_value=["Purchase Manager"]),
		):
			workspace = get_purchase_order_workspace(doc.name)

		self.assertEqual(workspace["fields"][0]["fieldname"], "supplier")
		self.assertEqual(workspace["matrices"], {"items": groups})
		self.assertEqual(
			{total["fieldname"]: total["value"] for total in workspace["totals"]},
			{
				"total_qty": 12,
				"total": 1200,
				"total_discount": 60,
				"net_total": 1140,
				"total_tax": 57,
				"total_taxes_and_charges": 57,
				"grand_total": 1197,
			},
		)
		self.assertIn("close", workspace["capabilities"])
		self.assertIn("create_goods_received_note", workspace["capabilities"])
		self.assertNotIn("create_delivery_challan", workspace["capabilities"])
		self.assertEqual(workspace["linked_lots"], ["LOT-1"])

	def test_web_adapter_keeps_authoritative_supplier_notification_capabilities(self):
		doc = self.make_document()
		adapter = MagicMock()
		adapter.frappe.has_permission.return_value = True
		adapter._permission_flags.return_value = {"can_create": True}
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles", return_value=[]),
			patch(
				"essdee_yrp.fabric_store.documents.purchase_order.get_supplier_notification_capabilities",
				return_value={"sms": True, "whatsapp": True},
			) as notifications,
		):
			capabilities = _capability_candidates(doc, {}, {"can_create": False}, adapter)

		notifications.assert_called_once_with(
			doc,
			"Purchase Order",
			hidden_statuses={"Closed", "Cancelled", "Partially Cancelled"},
		)
		self.assertTrue(capabilities["prepare_sms"]["eligible"])
		self.assertTrue(capabilities["prepare_whatsapp"]["eligible"])

	def test_related_documents_use_exact_purchase_order_links(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.fabric_store.documents.purchase_order.frappe.get_all",
				side_effect=[["DC-PO-1"], ["GRN-PO-1"]],
			) as get_all,
			patch(
				"essdee_yrp.fabric_store.documents.purchase_order.frappe.get_list",
				side_effect=[
					[frappe._dict(name="DC-PO-1", docstatus=1)],
					[frappe._dict(name="GRN-PO-1", docstatus=0)],
				],
			) as get_list,
		):
			related = _related_documents(doc)

		self.assertEqual(related["delivery_challans"][0]["name"], "DC-PO-1")
		self.assertEqual(related["goods_received_notes"][0]["name"], "GRN-PO-1")
		self.assertEqual(get_all.call_args_list[0].kwargs["filters"], {"purchase_order": doc.name})
		self.assertEqual(
			get_all.call_args_list[1].kwargs["filters"],
			{"against": "Purchase Order", "against_id": doc.name},
		)
		self.assertEqual(get_list.call_args_list[0].kwargs["filters"], {"name": ["in", ["DC-PO-1"]]})
		self.assertEqual(get_list.call_args_list[1].kwargs["filters"], {"name": ["in", ["GRN-PO-1"]]})

	def test_related_documents_are_not_suppressed_by_web_adapter(self):
		doc = self.make_document(status="Completed")
		adapter = MagicMock()
		adapter.frappe.has_permission.return_value = True
		with patch(
			"essdee_yrp.fabric_store.documents.purchase_order._permission_filtered_related_rows",
			side_effect=[[{"name": "DC-PO-1", "docstatus": 1}], [{"name": "GRN-PO-1", "docstatus": 1}]],
		) as related_rows:
			related = _related_documents(doc, adapter)

		self.assertEqual(related["delivery_challans"][0]["name"], "DC-PO-1")
		self.assertEqual(related["goods_received_notes"][0]["name"], "GRN-PO-1")
		self.assertEqual(
			related_rows.call_args_list[1].args,
			("YRP Goods Received Note", {"against": "Purchase Order", "against_id": doc.name}),
		)

	def test_approval_capabilities_follow_pending_state_role_and_live_request(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_workspace_base") as base,
			patch("essdee_yrp.fabric_store.documents.purchase_order.group_items_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_live_request", return_value=None),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles", return_value=["System Manager"]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", return_value=True),
		):
			base.side_effect = lambda _doc, **kwargs: {
				"record": {"doctype": "Purchase Order", "name": doc.name, "docstatus": 0, "status": "Draft", "modified": doc.modified},
				"fields": [], "totals": [],
				"permissions": {"can_read": True, "can_create": True, "can_write": True, "can_submit": True, "can_cancel": False, "can_amend": False, "can_print": False},
				"capabilities": {
					name: {key: value for key, value in spec.items() if key not in {"permission", "eligible"}}
					for name, spec in kwargs["capabilities"].items()
					if spec.get("eligible", True)
				},
				"print_formats": [],
			}
			workspace = get_purchase_order_workspace(doc.name)

		self.assertTrue(workspace["approval"]["pending_approval"])
		for capability in ["send_approval_request", "approve", "reject"]:
			self.assertIn(capability, workspace["capabilities"])

	def test_close_capability_follows_configured_manager_role(self):
		doc = self.make_document()
		for roles, eligible in ((["Stock User"], True), (["Purchase Manager"], False)):
			with (
				patch("yrp.attribute_links.get_single_value", return_value="Stock User"),
				patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles", return_value=roles),
				patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", return_value=True),
				patch(
					"essdee_yrp.fabric_store.documents.purchase_order.get_supplier_notification_capabilities",
					return_value={"sms": False, "whatsapp": False},
				),
			):
				capabilities = _capability_candidates(doc, {}, {})

			self.assertEqual(capabilities["close"]["eligible"], eligible)

	def test_live_request_and_missing_approver_role_remove_approval_actions(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_workspace_base") as base,
			patch("essdee_yrp.fabric_store.documents.purchase_order.group_items_for_ui", return_value=[]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_live_request", return_value=frappe._dict(name="REQ-1", status="Pending")),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.get_roles", return_value=["Purchase User"]),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", return_value=True),
		):
			base.side_effect = lambda _doc, **kwargs: {
				"record": {}, "fields": [], "totals": [], "permissions": {},
				"capabilities": {
					name: spec for name, spec in kwargs["capabilities"].items() if spec.get("eligible", True)
				},
				"print_formats": [],
			}
			workspace = get_purchase_order_workspace(doc.name)

		for capability in ["save", "submit", "send_approval_request", "approve", "reject"]:
			self.assertNotIn(capability, workspace["capabilities"])

	def test_pending_approval_never_exposes_plain_submit(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		capabilities = _capability_candidates(
			doc,
			{"pending_approval": True, "live_request": None},
			{"can_create": False},
		)

		self.assertFalse(capabilities["submit"]["eligible"])
		self.assertTrue(capabilities["save"]["eligible"])

	def test_forged_submit_is_rejected_before_insert(self):
		doc = MagicMock()
		doc.doctype = "Purchase Order"
		doc.name = "YRP-PO-NEW"
		doc.docstatus = 0
		doc.get.side_effect = lambda key, default=None: getattr(doc, key, default)

		def permissions(_doctype, ptype="read", **_kwargs):
			if ptype == "submit":
				raise frappe.PermissionError
			return True

		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.has_permission", side_effect=permissions),
			patch("essdee_yrp.fabric_store.documents.purchase_order.frappe.new_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			save_purchase_order_document(
				{"supplier": "SUPPLIER-1", "item_details": [{"items": [{"name": "ITEM"}]}]},
				submit=True,
			)

		doc.insert.assert_not_called()
		doc.submit.assert_not_called()

	def test_forged_approve_is_rejected_by_authoritative_approval_service(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.approve_purchase_order", side_effect=frappe.PermissionError),
			self.assertRaises(frappe.PermissionError),
		):
				execute_purchase_order_command(doc.name, "approve", expected_modified=doc.modified)

	def test_reject_requires_and_forwards_an_audit_reason(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.reject_purchase_order") as reject,
			patch(
				"essdee_yrp.fabric_store.documents.purchase_order.get_purchase_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
			self.assertRaises(frappe.ValidationError),
		):
			execute_purchase_order_command(
				doc.name,
				"reject",
				{"reason": "   "},
				expected_modified=doc.modified,
			)

		reject.assert_not_called()
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.reject_purchase_order") as reject,
			patch(
				"essdee_yrp.fabric_store.documents.purchase_order.get_purchase_order_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			execute_purchase_order_command(
				doc.name,
				"reject",
				{"reason": "Rate exceeds the approved budget"},
				expected_modified=doc.modified,
			)

		reject.assert_called_once_with(doc.name, reason="Rate exceeds the approved budget")

	def test_send_approval_request_reaches_approval_service_not_notification_dispatch(self):
		doc = self.make_document(docstatus=0, status="Pending Approval")
		refreshed = {"record": {"name": doc.name, "status": "Pending Approval"}}
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.send_purchase_order_request") as send_request,
			patch("essdee_yrp.fabric_store.documents.purchase_order.send_supplier_notification") as notify,
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_purchase_order_workspace", return_value=refreshed),
		):
			result = execute_purchase_order_command(
				doc.name,
				"send_approval_request",
				expected_modified=doc.modified,
			)

		send_request.assert_called_once_with(doc.name)
		notify.assert_not_called()
		self.assertEqual(result, refreshed)

	def test_close_reopen_and_linked_lots_delegate_to_domain_services(self):
		doc = self.make_document()
		refreshed = {"record": {"name": doc.name}}
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.close_purchase_order") as close,
			patch("essdee_yrp.fabric_store.documents.purchase_order.reopen_purchase_order") as reopen,
			patch("essdee_yrp.fabric_store.documents.purchase_order.update_po_lot_links") as update_lots,
			patch("essdee_yrp.fabric_store.documents.purchase_order.get_purchase_order_workspace", return_value=refreshed),
		):
			self.assertEqual(execute_purchase_order_command(doc.name, "close", expected_modified=doc.modified), refreshed)
			self.assertEqual(execute_purchase_order_command(doc.name, "reopen", expected_modified=doc.modified), refreshed)
			self.assertEqual(
				execute_purchase_order_command(
					doc.name,
					"update_linked_lots",
					{"add_lots": ["LOT-2"], "remove_lots": ["LOT-1"], "comment": "Change mill lot"},
					expected_modified=doc.modified,
				),
				refreshed,
			)

		close.assert_called_once_with(doc.name)
		reopen.assert_called_once_with(doc.name)
		update_lots.assert_called_once_with(
			doc.name,
			add_lots=["LOT-2"],
			remove_lots=["LOT-1"],
			comment="Change mill lot",
		)

	def test_notification_commands_delegate_to_existing_supplier_services(self):
		doc = self.make_document()
		prepared = {"channel": "sms", "context": {"templates": [{"name": "PO"}]}}
		sent = {"channel": "whatsapp", "result": {"ok": True}}
		with (
			patch("essdee_yrp.fabric_store.documents.purchase_order._get_purchase_order", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.purchase_order.prepare_supplier_notification", return_value=prepared) as prepare,
			patch("essdee_yrp.fabric_store.documents.purchase_order.send_supplier_notification", return_value=sent) as send,
		):
			self.assertEqual(
				execute_purchase_order_command(doc.name, "prepare_sms", expected_modified=doc.modified),
				prepared,
			)
			payload = {"template_name": "po_ready", "language_code": "en", "mobile_no": "9944405056"}
			self.assertEqual(
				execute_purchase_order_command(doc.name, "send_whatsapp", payload, doc.modified),
				sent,
			)

		prepare.assert_called_once_with(
			doc,
			"Purchase Order",
			"sms",
			hidden_statuses={"Closed", "Cancelled", "Partially Cancelled"},
		)
		send.assert_called_once_with(
			doc,
			"Purchase Order",
			"whatsapp",
			payload,
			hidden_statuses={"Closed", "Cancelled", "Partially Cancelled"},
		)

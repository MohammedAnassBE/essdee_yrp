from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.fabric_store.documents.common import (
	assert_expected_modified,
	filter_authorized_capabilities,
	get_allow_on_submit_fields,
	get_document_permissions,
	get_effective_fields,
	get_supplier_notification_capabilities,
	get_workspace_base,
	prepare_supplier_notification,
	send_supplier_notification,
)
from essdee_yrp.fabric_store.web_workspace import change_document_status


class TestFabricStoreDocumentContract(TestCase):
	def make_document(self, *, docstatus=0, status="", supplier="SUP-1", alternate_supplier=""):
		doc = MagicMock()
		doc.doctype = "Purchase Order"
		doc.name = "PO-1"
		doc.docstatus = docstatus
		doc.modified = "2026-10-06 10:00:00"
		values = {
			"modified": doc.modified,
			"status": status,
			"supplier": supplier,
			"alternate_supplier": alternate_supplier,
			"comments": "Handle carefully",
			"internal_state": "private",
			"grand_total": 1250,
		}
		doc.get.side_effect = lambda key, default=None: values.get(key, default)
		doc.meta.fields = [
			frappe._dict(
				fieldname="supplier",
				label="Vendor",
				fieldtype="Link",
				options="Supplier",
				reqd=1,
				read_only=0,
				allow_on_submit=1,
				hidden=0,
				depends_on="eval:doc.is_yrp_managed",
				mandatory_depends_on="",
				read_only_depends_on="",
			),
			frappe._dict(
				fieldname="comments",
				label="Instructions",
				fieldtype="Small Text",
				options="",
				reqd=0,
				read_only=1,
				allow_on_submit=1,
				hidden=0,
				depends_on="",
				mandatory_depends_on="",
				read_only_depends_on="eval:doc.docstatus == 1",
			),
			frappe._dict(
				fieldname="internal_state",
				label="Internal State",
				fieldtype="Data",
				allow_on_submit=1,
				hidden=1,
			),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		return doc

	def test_effective_fields_keep_meta_rules_and_omit_hidden_or_unreadable_fields(self):
		doc = self.make_document()
		with patch(
			"essdee_yrp.fabric_store.documents.common.get_permitted_fields",
			return_value=["supplier", "comments", "internal_state"],
		):
			fields = get_effective_fields(doc, ("supplier", "comments", "internal_state", "missing"))

		self.assertEqual(
			fields,
			[
				{
					"fieldname": "supplier",
					"label": "Vendor",
					"fieldtype": "Link",
					"options": "Supplier",
					"reqd": True,
					"allow_on_submit": True,
					"read_only": False,
					"depends_on": "eval:doc.is_yrp_managed",
					"mandatory_depends_on": "",
					"read_only_depends_on": "",
					"value": "SUP-1",
				},
				{
					"fieldname": "comments",
					"label": "Instructions",
					"fieldtype": "Small Text",
					"options": "",
					"reqd": False,
					"allow_on_submit": True,
					"read_only": True,
					"depends_on": "",
					"mandatory_depends_on": "",
					"read_only_depends_on": "eval:doc.docstatus == 1",
					"value": "Handle carefully",
				},
			],
		)

	def test_submitted_fields_enable_only_visible_writable_allow_on_submit_fields(self):
		doc = self.make_document(docstatus=1)
		with patch(
			"essdee_yrp.fabric_store.documents.common.get_permitted_fields",
			side_effect=lambda _doctype, permission_type=None: (
				["supplier", "comments", "internal_state"]
				if permission_type == "read"
				else ["supplier", "comments", "internal_state"]
			),
		):
			fields = get_effective_fields(doc, ("supplier", "comments", "internal_state"))

		self.assertFalse(fields[0]["read_only"], "writable Allow on Submit field was disabled")
		self.assertTrue(fields[1]["read_only"], "read-only field became editable after submit")
		self.assertEqual([field["fieldname"] for field in fields], ["supplier", "comments"])

	def test_allow_on_submit_tables_use_their_parent_permlevel(self):
		doc = self.make_document(docstatus=1)
		doc.meta.fields = [
			frappe._dict(
				fieldname="items",
				fieldtype="Table",
				allow_on_submit=1,
				hidden=0,
				read_only=0,
				permlevel=0,
			),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		doc.meta.get_permlevel_access.return_value = [0]

		with patch(
			"essdee_yrp.fabric_store.documents.common.get_permitted_fields",
			return_value=[],
		):
			self.assertEqual(get_allow_on_submit_fields(doc), ["items"])

	def test_document_permissions_are_constrained_by_document_state(self):
		doc = self.make_document(docstatus=1)
		allowed = {"read", "create", "write", "submit", "cancel", "amend", "print"}

		with patch(
			"essdee_yrp.fabric_store.documents.common.frappe.has_permission",
			side_effect=lambda _doctype, ptype="read", **_kwargs: ptype in allowed,
		):
			permissions = get_document_permissions(doc.doctype, doc)

		self.assertEqual(
			permissions,
			{
				"can_read": True,
				"can_create": True,
				"can_write": False,
				"can_update_after_submit": True,
				"can_submit": False,
				"can_cancel": True,
				"can_amend": False,
				"can_print": True,
			},
		)

	def test_unauthorized_and_ineligible_capabilities_are_absent(self):
		capabilities = filter_authorized_capabilities(
			{
				"submit": {"permission": "submit", "label": "Submit"},
				"print": {"permission": "print", "label": "Print"},
				"calculate": {"permission": "write", "eligible": False, "label": "Calculate"},
			},
			{"can_submit": False, "can_print": True, "can_write": True},
		)

		self.assertEqual(capabilities, {"print": {"label": "Print"}})

	def test_workspace_base_has_stable_keys_and_filters_capabilities(self):
		doc = self.make_document(docstatus=1)
		with (
			patch(
				"essdee_yrp.fabric_store.documents.common.get_permitted_fields",
				return_value=["supplier"],
			),
			patch(
				"essdee_yrp.fabric_store.documents.common.frappe.has_permission",
				side_effect=lambda _doctype, ptype="read", **_kwargs: ptype in {"read", "cancel", "print"},
			),
			patch(
				"essdee_yrp.fabric_store.documents.common.get_document_print_formats",
				return_value=[{"name": "Essdee Purchase Order"}],
			),
		):
			workspace = get_workspace_base(
				doc,
				fieldnames=("supplier",),
				totals=("grand_total",),
				capabilities={
					"cancel": {"permission": "cancel", "label": "Cancel"},
					"submit": {"permission": "submit", "label": "Submit"},
				},
			)

		self.assertEqual(
			set(workspace),
			{"record", "fields", "allow_on_submit_fields", "totals", "permissions", "capabilities", "print_formats"},
		)
		self.assertEqual(workspace["capabilities"], {"cancel": {"label": "Cancel"}})
		self.assertEqual(workspace["totals"], [{"fieldname": "grand_total", "label": "Grand Total", "value": 1250}])

	def test_stale_timestamp_is_rejected(self):
		doc = self.make_document()
		with self.assertRaises(frappe.TimestampMismatchError):
			assert_expected_modified(doc, "2026-10-06 09:59:59")

	def test_supplier_notification_capabilities_follow_status_supplier_permission_and_configuration(self):
		doc = self.make_document(docstatus=1, status="To Receive")
		supplier = MagicMock()
		supplier.get_primary_contact_details.return_value = {"mobile": "9944405056"}
		sms_settings = MagicMock(enabled=True)
		sms_settings.get_templates_for_doctype.return_value = [frappe._dict(template_name="Receipt")]
		whatsapp_template = MagicMock()
		whatsapp_template.is_applicable_for.return_value = True

		def get_doc(doctype, *_args, **_kwargs):
			return supplier if doctype == "Supplier" else whatsapp_template

		with (
			patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.frappe.get_doc", side_effect=get_doc),
			patch("essdee_yrp.fabric_store.documents.common.frappe.get_cached_doc", return_value=sms_settings),
			patch("essdee_yrp.fabric_store.documents.common.frappe.get_all", return_value=["WA-1"]),
			patch("yrp.whatsapp_notification.get_enabled_whatsapp_doctypes", return_value={"doctypes": {"Purchase Order": "supplier"}}),
		):
			available = get_supplier_notification_capabilities(
				doc,
				"Purchase Order",
				hidden_statuses={"Closed", "Cancelled", "Partially Cancelled"},
			)

		self.assertEqual(available, {"sms": True, "whatsapp": True})
		closed_doc = self.make_document(docstatus=1, status="Closed")
		with patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission") as permission:
			self.assertEqual(
				get_supplier_notification_capabilities(closed_doc, "Purchase Order", hidden_statuses={"Closed"}),
				{"sms": False, "whatsapp": False},
			)
		permission.assert_not_called()
		with patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission", return_value=False):
			self.assertEqual(
				get_supplier_notification_capabilities(doc, "Purchase Order"),
				{"sms": False, "whatsapp": False},
			)

	def test_supplier_notification_prepare_and_send_reuse_existing_services(self):
		doc = self.make_document(docstatus=1)
		doc.status = "To Receive"
		with (
			patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission", return_value=True),
			patch("yrp.notification.get_flow_sms_context", return_value={"templates": [{"name": "Receipt"}]}) as context,
			patch("yrp.notification.send_flow_sms_notification", return_value={"ok": True, "request_id": "REQ-1"}) as send,
		):
			prepared = prepare_supplier_notification(doc, "Purchase Order", "sms")
			result = send_supplier_notification(
				doc,
				"Purchase Order",
				"sms",
				{"template_name": "Receipt", "mobile_no": "9944405056", "params": {"name": doc.name}},
			)

		self.assertEqual(prepared["channel"], "sms")
		self.assertTrue(result["result"]["ok"])
		context.assert_called_once_with("Purchase Order", doc.name, "supplier")
		send.assert_called_once_with(
			"Purchase Order",
			doc.name,
			"Receipt",
			mobile_no="9944405056",
			params={"name": doc.name},
			supplier_key="supplier",
		)

	def test_whatsapp_uses_the_hub_configured_supplier_field_for_capability_prepare_and_send(self):
		doc = self.make_document(
			docstatus=1,
			status="To Receive",
			supplier="",
			alternate_supplier="SUP-ALT",
		)
		supplier = MagicMock()
		supplier.get_primary_contact_details.return_value = {"mobile": "9944405056"}
		template = MagicMock()
		template.is_applicable_for.return_value = True

		def get_doc(doctype, *_args, **_kwargs):
			return supplier if doctype == "Supplier" else template

		with (
			patch("essdee_yrp.fabric_store.documents.common.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.frappe.get_doc", side_effect=get_doc),
			patch("essdee_yrp.fabric_store.documents.common.frappe.get_all", return_value=["WA-1"]),
			patch(
				"yrp.whatsapp_notification.get_enabled_whatsapp_doctypes",
				return_value={"doctypes": {"Purchase Order": "alternate_supplier"}},
			),
			patch("yrp.whatsapp_notification.get_whatsapp_context", return_value={"templates": [{"name": "WA-1"}]}) as context,
			patch("yrp.whatsapp_notification.send_whatsapp_notification", return_value={"ok": True}) as send,
		):
			available = get_supplier_notification_capabilities(doc, "Purchase Order")
			prepared = prepare_supplier_notification(doc, "Purchase Order", "whatsapp")
			result = send_supplier_notification(
				doc,
				"Purchase Order",
				"whatsapp",
				{"template_name": "po_ready", "language_code": "en"},
			)

		self.assertTrue(available["whatsapp"])
		self.assertEqual(prepared["channel"], "whatsapp")
		self.assertTrue(result["result"]["ok"])
		context.assert_called_once_with("Purchase Order", doc.name, "alternate_supplier")
		send.assert_called_once_with(
			"Purchase Order",
			doc.name,
			"po_ready",
			"en",
			params=None,
			mobile_no=None,
			header_file=None,
			supplier_key="alternate_supplier",
		)

	def test_forged_lifecycle_command_is_rejected_before_mutation(self):
		doc = self.make_document(docstatus=0)
		doc.submit = MagicMock()
		with (
			patch("essdee_yrp.fabric_store.web_workspace._get_supported_document", return_value=doc),
			patch(
				"essdee_yrp.fabric_store.web_workspace.frappe.has_permission",
				side_effect=frappe.PermissionError,
			),
			self.assertRaises(frappe.PermissionError),
		):
			change_document_status("Purchase Order", "PO-1", "submit", doc.modified)

		doc.submit.assert_not_called()

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.sales import web_workspace


class FakeEditableProductionOrder:
	def __init__(self, *, name="PPO-0001", docstatus=0, modified="2026-10-09 11:00:00.000000", **values):
		self.doctype = "YRP Production Order"
		self.name = name
		self.docstatus = docstatus
		self.modified = modified
		self._values = {"status": "Draft", "production_order_details": [], "production_ordered_details": [], "__onload": {}, **values}
		self.checked_permissions = []
		self.saved = 0
		self.inserted = 0
		self.cancelled = 0
		self.meta = SimpleNamespace(fields=[], get_field=lambda _fieldname: None)

	def get(self, key, default=None):
		if key in {"name", "docstatus", "modified"}:
			return getattr(self, key)
		return self._values.get(key, default)

	def set(self, key, value):
		self._values[key] = value

	def check_permission(self, permission):
		self.checked_permissions.append(permission)

	def run_method(self, method):
		if method != "onload":
			raise AssertionError(f"Unexpected method {method}")

	def save(self):
		self.saved += 1
		return self

	def insert(self):
		self.inserted += 1
		return self

	def cancel(self):
		self.cancelled += 1
		self.docstatus = 2
		return self


class TestSalesProductionOrderCommands(TestCase):
	def test_editor_exposes_complete_draft_fields_and_existing_matrix(self):
		doc = FakeEditableProductionOrder(
			item="Premium Polo",
			production_detail="IPD-1",
			production_term="Default Term",
			delivery_date="2026-10-20",
			dont_deliver_after="2026-10-25",
			comments="Priority",
			skip_box_sticker_print=1,
		)
		context = {
			"items": [{"item": "Premium Polo", "entries": [{"attributes": {"Size": "M"}, "qty": 50, "ratio": 2}]}],
			"primary_attribute": "Size",
		}
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace.workflow, "get_order_editor_context", return_value=context),
		):
			payload = web_workspace.get_production_order_editor(doc.name)

		self.assertEqual(doc.checked_permissions, ["write"])
		self.assertEqual(
			[field["fieldname"] for field in payload["fields"]],
			[
				"naming_series",
				"item",
				"production_detail",
				"production_term",
				"delivery_date",
				"dont_deliver_after",
				"comments",
				"skip_box_sticker_print",
			],
		)
		self.assertEqual(payload["matrix"], context)
		self.assertEqual(payload["modified"], doc.modified)

	def test_save_draft_uses_allowlist_and_preserves_matrix_payload(self):
		doc = FakeEditableProductionOrder(item="Old Item")
		values = {
			"item": "Premium Polo",
			"production_term": "Default Term",
			"delivery_date": "2026-10-20",
			"dont_deliver_after": "2026-10-25",
			"comments": "Buyer priority",
			"status": "Closed",
			"transferred_to_ppo": "PPO-EVIL",
			"item_details": [{"item": "Premium Polo", "entries": [{"attributes": {"Size": "M"}, "qty": 50, "ratio": 2}]}],
		}
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace, "get_production_order_workspace", return_value={"record": {"name": doc.name}}),
		):
			payload = web_workspace.save_production_order(values, name=doc.name, expected_modified=doc.modified)

		self.assertEqual(doc.checked_permissions, ["write"])
		self.assertEqual(doc.saved, 1)
		self.assertEqual(doc.get("item"), "Premium Polo")
		self.assertEqual(doc.get("status"), "Draft")
		self.assertIsNone(doc.get("transferred_to_ppo"))
		self.assertEqual(frappe.parse_json(doc.get("item_details")), values["item_details"])
		self.assertEqual(payload, {"record": {"name": "PPO-0001"}})

	def test_stale_save_is_rejected_before_mutation(self):
		doc = FakeEditableProductionOrder(item="Original")
		with patch.object(frappe, "get_doc", return_value=doc):
			with self.assertRaises(frappe.TimestampMismatchError):
				web_workspace.save_production_order(
					{"item": "Changed", "item_details": [{"item": "Changed", "entries": []}]},
					name=doc.name,
					expected_modified="2026-10-09 09:00:00.000000",
				)
		self.assertEqual(doc.get("item"), "Original")
		self.assertEqual(doc.saved, 0)

	def test_save_rejects_malformed_or_empty_matrix(self):
		for matrix in (None, {}, [], "not-json"):
			with self.subTest(matrix=matrix):
				doc = FakeEditableProductionOrder()
				with patch.object(frappe, "get_doc", return_value=doc):
					with self.assertRaises(frappe.ValidationError):
						web_workspace.save_production_order({"item": "Premium Polo", "item_details": matrix}, name=doc.name)
				self.assertEqual(doc.saved, 0)

	def test_submit_option_sends_saved_draft_to_existing_approval_workflow(self):
		doc = FakeEditableProductionOrder()
		values = {"item": "Premium Polo", "item_details": [{"item": "Premium Polo", "entries": [{"qty": 10}]}]}
		calls = []
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace.workflow, "request_ppo_approval", side_effect=lambda production_order: calls.append(production_order)),
			patch.object(web_workspace, "get_production_order_workspace", return_value={"record": {"name": doc.name}}),
		):
			web_workspace.save_production_order(values, name=doc.name, submit=True)
		self.assertEqual(calls, [doc.name])
		self.assertEqual(doc.saved, 1)

	def test_workflow_command_registry_delegates_exact_payloads(self):
		cases = {
			"request_ppo_approval": ("request_ppo_approval", {}, {"production_order": "PPO-0001"}),
			"approve_ppo": ("approve_ppo", {}, {"production_order": "PPO-0001"}),
			"request_changes": ("request_ppo_changes", {"reason": "Correct dates"}, {"production_order": "PPO-0001", "reason": "Correct dates"}),
			"update_quantity_ratio": (
				"update_quantity_and_ratio",
				{"size_quantities": {"S": 10}, "size_ratios": {"S": 1}, "requested_by": "Buyer", "reason": "Revised order"},
				{"production_order": "PPO-0001", "size_quantities": {"S": 10}, "size_ratios": {"S": 1}, "requested_by": "Buyer", "reason": "Revised order"},
			),
			"approve_quantity_ratio": ("approve_quantity_and_ratio", {}, {"production_order": "PPO-0001"}),
			"update_price": ("update_price", {"item_details": [{"size": "S", "mrp": 799}]}, {"production_order": "PPO-0001", "item_details": [{"size": "S", "mrp": 799}]}),
			"change_dates": (
				"update_production_order_date",
				{"date_field": "Delivery Date", "new_date": "2026-10-22", "reason": "Buyer request"},
				{"production_order": "PPO-0001", "date_field": "Delivery Date", "new_date": "2026-10-22", "reason": "Buyer request"},
			),
			"change_status": ("change_status", {"new_status": "Not Processed", "reason": "Cancelled style"}, {"production_order": "PPO-0001", "new_status": "Not Processed", "reason": "Cancelled style"}),
			"approve_status": ("approve_status_change", {}, {"production_order": "PPO-0001"}),
			"transfer_quantity": (
				"transfer_quantity_to_ppo",
				{"target_production_order": "PPO-0002", "reason": "Alternative item"},
				{"source_production_order": "PPO-0001", "target_production_order": "PPO-0002", "reason": "Alternative item"},
			),
			"approve_transfer": ("approve_quantity_transfer", {}, {"production_order": "PPO-0001"}),
			"create_lot": ("create_lot", {"lot_name": "LOT-NEW"}, {"production_order": "PPO-0001", "lot_name": "LOT-NEW"}),
			"link_lot": ("link_lot", {"lot_name": "LOT-OLD"}, {"production_order": "PPO-0001", "lot_name": "LOT-OLD"}),
			"reopen": ("reopen_production_order", {}, {"production_order": "PPO-0001"}),
		}
		for command, (function_name, payload, expected) in cases.items():
			with self.subTest(command=command):
				doc = FakeEditableProductionOrder(docstatus=1, status="Open")
				calls = []
				with (
					patch.object(frappe, "get_doc", return_value=doc),
					patch.object(web_workspace, "_production_order_actions", return_value={command: {"allowed": True, "label": command, "reason": ""}}),
					patch.object(web_workspace.workflow, function_name, side_effect=lambda **kwargs: calls.append(kwargs)),
					patch.object(web_workspace, "get_production_order_workspace", return_value={"record": {"name": doc.name}}),
				):
					result = web_workspace.execute_production_order_command(doc.name, command, payload, expected_modified=doc.modified)
				self.assertEqual(calls, [expected])
				self.assertEqual(result, {"record": {"name": doc.name}})

	def test_cancel_lifecycle_command_uses_document_permission_and_refreshes(self):
		doc = FakeEditableProductionOrder(docstatus=1, status="Open")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace, "_production_order_actions", return_value={"cancel": {"allowed": True, "label": "Cancel", "reason": ""}}),
			patch.object(web_workspace, "get_production_order_workspace", return_value={"record": {"docstatus": 2}}),
		):
			result = web_workspace.execute_production_order_command(doc.name, "cancel", expected_modified=doc.modified)
		self.assertEqual(doc.checked_permissions, ["cancel"])
		self.assertEqual(doc.cancelled, 1)
		self.assertEqual(result["record"]["docstatus"], 2)

	def test_unknown_disallowed_and_stale_commands_never_delegate(self):
		doc = FakeEditableProductionOrder(docstatus=1, status="Open")
		with patch.object(frappe, "get_doc", return_value=doc):
			with self.assertRaises(frappe.ValidationError):
				web_workspace.execute_production_order_command(doc.name, "unknown")

		calls = []
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace, "_production_order_actions", return_value={"update_price": {"allowed": False, "label": "Update Price", "reason": "Locked"}}),
			patch.object(web_workspace.workflow, "update_price", side_effect=lambda **kwargs: calls.append(kwargs)),
		):
			with self.assertRaises(frappe.PermissionError):
				web_workspace.execute_production_order_command(doc.name, "update_price", {"item_details": []})
		self.assertEqual(calls, [])

		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace, "_production_order_actions", return_value={"update_price": {"allowed": True, "label": "Update Price", "reason": ""}}),
			patch.object(web_workspace.workflow, "update_price", side_effect=lambda **kwargs: calls.append(kwargs)),
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				web_workspace.execute_production_order_command(
					doc.name,
					"update_price",
					{"item_details": []},
					expected_modified="2026-10-09 08:00:00.000000",
				)
		self.assertEqual(calls, [])

	def test_editor_and_command_endpoints_are_authenticated(self):
		for endpoint in (
			web_workspace.get_production_order_editor,
			web_workspace.save_production_order,
			web_workspace.execute_production_order_command,
		):
			self.assertIn(endpoint, frappe.whitelisted)
			self.assertNotIn(endpoint, frappe.guest_methods)

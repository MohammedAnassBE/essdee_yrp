from unittest import TestCase
from unittest.mock import call, patch

import frappe

from essdee_yrp.fabric_store import web_workspace as workspace
from essdee_yrp.fabric_store.documents import common

PERMISSIONS = {"read": 1, "delete": 1}
ACTIVITY = {"created": {}, "modified": {}, "versions": [], "has_more": False, "next_start": 0}


class TestFormSidePayload(TestCase):
	def side_calls(self, *, readable=True):
		permission = self.enterContext(patch.object(common.frappe, "has_permission", return_value=readable))
		doc_permissions = self.enterContext(
			patch.object(common, "get_doc_permissions", return_value={"permissions": PERMISSIONS})
		)
		activity = self.enterContext(patch.object(common, "get_document_activity", return_value=ACTIVITY))
		return permission, doc_permissions, activity

	def test_saved_readable_record_carries_doc_permissions_and_first_activity_page(self):
		permission, doc_permissions, activity = self.side_calls()
		payload = common.add_form_side_payload(
			{"record": {"doctype": "YRP Delivery Challan", "name": "DC-1"}}
		)
		self.assertEqual(payload["doc_permissions"], PERMISSIONS)
		self.assertEqual(payload["activity"], ACTIVITY)
		permission.assert_called_once_with("YRP Delivery Challan", "read", "DC-1")
		doc_permissions.assert_called_once_with("YRP Delivery Challan", "DC-1")
		activity.assert_called_once_with("YRP Delivery Challan", "DC-1")

	def test_unsaved_or_unreadable_record_is_left_for_the_client_to_fetch(self):
		_permission, doc_permissions, activity = self.side_calls(readable=False)
		for record in (
			{},
			{"doctype": "YRP Work Order", "name": None},
			{"doctype": "YRP Work Order", "name": "WO-1"},
		):
			with self.subTest(record=record):
				payload = common.add_form_side_payload({"record": record})
				self.assertNotIn("doc_permissions", payload)
				self.assertNotIn("activity", payload)
		doc_permissions.assert_not_called()
		activity.assert_not_called()

	def test_a_failing_side_value_is_left_out_without_its_messages(self):
		def failing_activity(doctype, name):
			frappe.throw("Broken version data")

		self.side_calls()
		self.enterContext(patch.object(common, "get_document_activity", side_effect=failing_activity))
		self.enterContext(patch.object(frappe.local, "message_log", ["earlier message"]))
		payload = common.add_form_side_payload({"record": {"doctype": "YRP Work Order", "name": "WO-1"}})
		self.assertEqual(payload["doc_permissions"], PERMISSIONS)
		self.assertNotIn("activity", payload)
		self.assertEqual(frappe.local.message_log, ["earlier message"])

	def test_a_failing_read_check_leaves_the_whole_side_payload_to_the_client(self):
		def failing_check(doctype, ptype, name):
			frappe.throw("Permission hook failed")

		_permission, doc_permissions, activity = self.side_calls()
		self.enterContext(patch.object(common.frappe, "has_permission", side_effect=failing_check))
		self.enterContext(patch.object(frappe.local, "message_log", []))
		payload = common.add_form_side_payload({"record": {"doctype": "YRP Work Order", "name": "WO-1"}})
		self.assertEqual(payload, {"record": {"doctype": "YRP Work Order", "name": "WO-1"}})
		self.assertEqual(frappe.local.message_log, [])
		doc_permissions.assert_not_called()
		activity.assert_not_called()

	def test_a_failing_supplier_check_leaves_only_that_party_to_the_client(self):
		def permission(doctype, ptype, party):
			if party == "UNIT-B":
				frappe.throw("Permission hook failed")
			return True

		self.enterContext(patch.object(workspace.frappe.db, "exists", return_value=True))
		self.enterContext(patch.object(workspace.frappe, "has_permission", side_effect=permission))
		self.enterContext(
			patch.object(workspace, "get_location_address_status", side_effect=lambda party: {"party": party})
		)
		self.enterContext(patch.object(frappe.local, "message_log", []))
		self.assertEqual(
			workspace.get_location_address_statuses({"from_location": "UNIT-B", "supplier": "UNIT-A"}),
			{"UNIT-A": {"party": "UNIT-A"}},
		)
		self.assertEqual(frappe.local.message_log, [])

	def test_a_failing_address_status_leaves_only_that_party_to_the_client(self):
		def status(party):
			if party == "UNIT-B":
				raise frappe.ValidationError("broken address")
			return {"party": party}

		self.enterContext(patch.object(workspace.frappe.db, "exists", return_value=True))
		self.enterContext(patch.object(workspace.frappe, "has_permission", return_value=True))
		self.enterContext(patch.object(workspace, "get_location_address_status", side_effect=status))
		self.assertEqual(
			workspace.get_location_address_statuses({"from_location": "UNIT-A", "supplier": "UNIT-B"}),
			{"UNIT-A": {"party": "UNIT-A"}},
		)

	def test_location_address_status_only_for_existing_readable_locations(self):
		readable = {"UNIT-A": True, "UNIT-B": False}
		self.enterContext(
			patch.object(workspace.frappe.db, "exists", side_effect=lambda doctype, party: party != "GONE")
		)
		permission = self.enterContext(
			patch.object(
				workspace.frappe,
				"has_permission",
				side_effect=lambda doctype, ptype, party: readable.get(party, True),
			)
		)
		status = self.enterContext(
			patch.object(workspace, "get_location_address_status", side_effect=lambda party: {"party": party})
		)
		self.assertEqual(
			workspace.get_location_address_statuses({"from_location": "UNIT-A", "supplier": "UNIT-A"}),
			{"UNIT-A": {"party": "UNIT-A"}},
		)
		self.assertEqual(
			workspace.get_location_address_statuses({"from_location": "UNIT-B", "supplier": "GONE"}), {}
		)
		self.assertEqual(workspace.get_location_address_statuses({}), {})
		status.assert_called_once_with("UNIT-A")
		self.assertIn(call("Supplier", "read", "UNIT-B"), permission.call_args_list)

	def test_routed_workspaces_add_the_side_payload_for_saved_documents_only(self):
		add = self.enterContext(
			patch.object(workspace, "add_form_side_payload", side_effect=lambda payload: payload)
		)
		statuses = self.enterContext(
			patch.object(workspace, "get_location_address_statuses", return_value={"U": {}})
		)
		services = {
			"delivery_challan_service": "get_delivery_challan_workspace",
			"goods_received_note_service": "get_goods_received_note_workspace",
			"work_order_service": "get_work_order_workspace",
			"purchase_order_service": "get_purchase_order_workspace",
		}
		for service, method in services.items():
			self.enterContext(
				patch.object(
					getattr(workspace, service),
					method,
					side_effect=lambda *args, **kwargs: {"values": {"supplier": "U"}},
				)
			)
		dc = workspace.get_delivery_challan_workspace("DC-1")
		self.assertEqual(dc["location_address_status"], {"U": {}})
		statuses.assert_called_once_with({"supplier": "U"})
		workspace.get_goods_received_note_workspace("GRN-1")
		workspace.get_work_order_workspace("WO-1")
		workspace.get_purchase_order_workspace("PO-1")
		self.assertEqual(add.call_count, 4)
		add.reset_mock()
		new_dc = workspace.get_delivery_challan_workspace(None, {"work_order": "WO-1"})
		workspace.get_goods_received_note_workspace(None, {"against": "Work Order"})
		self.assertNotIn("location_address_status", new_dc)
		add.assert_not_called()

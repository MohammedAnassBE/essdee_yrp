from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.hr import web_workspace
from essdee_yrp.overrides.bill_tracking import CANCEL_PENDING_STATUS


class FakeBillTracking:
	def __init__(self, **values):
		defaults = {
			"doctype": "YRP Bill Tracking",
			"name": "E2E-AHR-BT-0001",
			"docstatus": 1,
			"form_status": "Assigned",
			"modified": "2026-10-12 10:00:00",
			"supplier": "E2E-AHR-SUPPLIER",
			"bill_no": "E2E-AHR-BILL-001",
			"invoice_value": 1200,
			"purchase_invoice": None,
			"erp_purchase_invoice": None,
			"assigned_to": "Accounts",
			"bill_tracking_history": [],
		}
		defaults.update(values)
		self.values = defaults
		self.__dict__.update(defaults)
		self.doctype = defaults["doctype"]
		self.name = defaults["name"]
		self.docstatus = defaults["docstatus"]
		self.modified = defaults["modified"]
		self.meta = SimpleNamespace(get_field=self.get_meta_field)
		self.permitted_fieldnames = {
			*defaults,
			*web_workspace.DETAIL_FIELDS,
			*web_workspace.EDITOR_FIELDS,
		}
		self.checked_permissions = []
		self.inserted = False
		self.saved = False
		self.submitted = False
		self.fieldlevel_permissions_applied = 0

	def get(self, fieldname, default=None):
		return self.values.get(fieldname, default)

	def set(self, fieldname, value):
		self.values[fieldname] = value
		setattr(self, fieldname, value)

	def check_permission(self, permission_type):
		self.checked_permissions.append(permission_type)

	def insert(self):
		self.inserted = True
		return self

	def save(self):
		self.saved = True
		return self

	def submit(self):
		self.submitted = True
		self.docstatus = 1
		self.values["docstatus"] = 1
		return self

	def apply_fieldlevel_read_permissions(self):
		self.fieldlevel_permissions_applied += 1

	def get_meta_field(self, fieldname):
		return SimpleNamespace(
			label=fieldname.replace("_", " ").title(),
			fieldtype="Data",
			options=None,
			reqd=fieldname in {"supplier", "bill_no"},
		)


def action_permissions(**overrides):
	permissions = {
		"can_write": True,
		"can_submit": True,
		"can_delete": True,
	}
	permissions.update(overrides)
	return permissions


def role_permissions(**overrides):
	permissions = {
		"can_request_cancel": True,
		"can_approve_cancel": True,
		"can_create_invoice": True,
	}
	permissions.update(overrides)
	return permissions


class TestBillTrackingActions(TestCase):
	def test_actions_hide_assign_and_create_while_cancel_pending(self):
		doc = FakeBillTracking(form_status=CANCEL_PENDING_STATUS)
		with patch.object(frappe, "has_permission", return_value=True):
			actions = web_workspace.bill_tracking_actions(
				doc, action_permissions(), role_permissions(), can_acknowledge=True
			)

		self.assertFalse(actions["assign"]["allowed"])
		self.assertFalse(actions["create_purchase_invoice"]["allowed"])

	def test_request_cancel_needs_role_and_no_invoice(self):
		doc = FakeBillTracking(form_status="Open", assigned_to=None)
		without_role = web_workspace.bill_tracking_actions(
			doc,
			action_permissions(),
			role_permissions(can_request_cancel=False),
			can_acknowledge=False,
		)
		self.assertFalse(without_role["request_cancel"]["allowed"])

		doc.values["purchase_invoice"] = "E2E-AHR-PI-0001"
		with_invoice = web_workspace.bill_tracking_actions(
			doc, action_permissions(), role_permissions(), can_acknowledge=False
		)
		self.assertFalse(with_invoice["request_cancel"]["allowed"])

		doc.values["purchase_invoice"] = None
		allowed = web_workspace.bill_tracking_actions(
			doc, action_permissions(), role_permissions(), can_acknowledge=False
		)
		self.assertTrue(allowed["request_cancel"]["allowed"])

	def test_bill_received_needs_unreceived_last_row(self):
		doc = FakeBillTracking(
			bill_tracking_history=[
				frappe._dict(action="Assign", assigned_to="Accounts", received=1),
				frappe._dict(action="Assign", assigned_to="Accounts", received=0),
			]
		)
		actions = web_workspace.bill_tracking_actions(
			doc, action_permissions(), role_permissions(), can_acknowledge=True
		)
		self.assertTrue(actions["bill_received"]["allowed"])

		doc.values["bill_tracking_history"][-1].received = 1
		actions = web_workspace.bill_tracking_actions(
			doc, action_permissions(), role_permissions(), can_acknowledge=True
		)
		self.assertFalse(actions["bill_received"]["allowed"])

	def test_create_purchase_invoice_requires_pi_create_permission(self):
		doc = FakeBillTracking(form_status="Open", assigned_to=None)
		with patch.object(frappe, "has_permission", return_value=False):
			denied = web_workspace.bill_tracking_actions(
				doc, action_permissions(), role_permissions(), can_acknowledge=False
			)
		with patch.object(frappe, "has_permission", return_value=True):
			allowed = web_workspace.bill_tracking_actions(
				doc, action_permissions(), role_permissions(), can_acknowledge=False
			)

		self.assertFalse(denied["create_purchase_invoice"]["allowed"])
		self.assertTrue(allowed["create_purchase_invoice"]["allowed"])


class TestCreateErpPurchaseInvoiceAction(TestCase):
	def get_actions(self, doc, *, can_create_erp_invoice=True, is_erp_available=True, roles=None):
		def has_permission(doctype, ptype=None, **kwargs):
			return doctype != "Purchase Invoice" or can_create_erp_invoice

		with (
			patch.object(frappe, "has_permission", side_effect=has_permission),
			patch.object(web_workspace, "is_same_site_erp_available", return_value=is_erp_available),
		):
			return web_workspace.bill_tracking_actions(
				doc, action_permissions(), roles or role_permissions(), can_acknowledge=False
			)

	def test_open_bill_offers_erp_invoice_beside_yrp_invoice(self):
		actions = self.get_actions(FakeBillTracking(form_status="Open"))
		self.assertTrue(actions["create_erp_purchase_invoice"]["allowed"])
		self.assertEqual(actions["create_erp_purchase_invoice"]["label"], "Create ERP Purchase Invoice")
		self.assertTrue(actions["create_purchase_invoice"]["allowed"])

	def test_requires_erp_purchase_invoice_create_permission(self):
		actions = self.get_actions(FakeBillTracking(), can_create_erp_invoice=False)
		self.assertFalse(actions["create_erp_purchase_invoice"]["allowed"])
		self.assertTrue(actions["create_purchase_invoice"]["allowed"])

	def test_requires_configured_invoice_role(self):
		actions = self.get_actions(FakeBillTracking(), roles=role_permissions(can_create_invoice=False))
		self.assertFalse(actions["create_erp_purchase_invoice"]["allowed"])

	def test_requires_same_site_erpnext(self):
		actions = self.get_actions(FakeBillTracking(), is_erp_available=False)
		self.assertFalse(actions["create_erp_purchase_invoice"]["allowed"])

	def test_hidden_once_either_invoice_is_linked_or_bill_is_not_open(self):
		for values in (
			{"purchase_invoice": "PI-YRP-1"},
			{"erp_purchase_invoice": "PI-ERP-1"},
			{"docstatus": 0},
			{"form_status": "Closed"},
			{"form_status": CANCEL_PENDING_STATUS},
			{"form_status": "Cancel Request Approved"},
		):
			with self.subTest(values=values):
				actions = self.get_actions(FakeBillTracking(**values))
				self.assertFalse(actions["create_erp_purchase_invoice"]["allowed"])


class TestBillTrackingWorkspace(TestCase):
	def setUp(self):
		formats = patch.object(web_workspace, "get_document_print_formats", return_value=[{"label": "Standard", "format": "Standard"}])
		self.print_formats = formats.start()
		self.addCleanup(formats.stop)

	def test_workspace_requires_read(self):
		doc = FakeBillTracking(
			bill_tracking_history=[
				frappe._dict(
					action="Assign",
					assigned_to="Accounts",
					assigned_by="Administrator",
					assigned_on="2026-10-12 10:00:00",
					received=0,
					remarks="Review",
				)
			]
		)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_roles", return_value=["System Manager"]),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(web_workspace, "get_role_permissions", return_value=role_permissions()),
			patch.object(web_workspace, "check_for_can_show_receive_btn", return_value=True),
		):
			payload = web_workspace.get_bill_tracking_workspace(doc.name)

		self.assertEqual(doc.checked_permissions, ["read"])
		self.assertEqual(payload["record"]["name"], doc.name)
		self.assertEqual(payload["print_formats"], [{"label": "Standard", "format": "Standard"}])
		self.print_formats.assert_called_once_with(doc)
		self.assertEqual(payload["history"][0]["remarks"], "Review")
		self.assertTrue(payload["can_open_desk"])
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_workspace_filters_permlevel_fields_and_masks_parent_and_history_values(self):
		history = frappe._dict(
			action="Assign",
			assigned_to="Accounts",
			assigned_by="e2e.ahr.private@example.test",
			assigned_on="2026-10-12 10:00:00",
			received=0,
			remarks="Restricted remarks",
		)
		doc = FakeBillTracking(bill_tracking_history=[history])

		def apply_field_permissions():
			doc.fieldlevel_permissions_applied += 1
			doc.set("supplier", "XXXXXXXX")
			doc.values.pop("bill_no")
			delattr(doc, "bill_no")
			doc.permitted_fieldnames.remove("bill_no")
			history.assigned_by = "XXXXXXXX"
			history.pop("remarks")

		doc.apply_fieldlevel_read_permissions = apply_field_permissions
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_roles", return_value=[]),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(web_workspace, "get_role_permissions", return_value=role_permissions()),
			patch.object(web_workspace, "check_for_can_show_receive_btn", return_value=True),
		):
			payload = web_workspace.get_bill_tracking_workspace(doc.name)

		self.assertEqual(payload["record"]["supplier"], "XXXXXXXX")
		self.assertNotIn("bill_no", payload["record"])
		self.assertEqual(payload["history"][0]["assigned_by"], "XXXXXXXX")
		self.assertNotIn("remarks", payload["history"][0])
		self.assertTrue(payload["capabilities"]["bill_received"]["allowed"])
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_workspace_applies_frappe_mask_and_permlevel_rules(self):
		bill_names = frappe.get_all(
			"YRP Bill Tracking",
			filters={"docstatus": 1, "supplier": ["!=", ""], "bill_no": ["!=", ""]},
			pluck="name",
			limit=1,
		)
		self.assertTrue(bill_names, "Expected a Bill Tracking record with supplier and bill number")
		test_token = frappe.generate_hash(length=8)
		user_email = f"e2e.ahr.hr.workspace.{test_token}@example.test"
		contact_name = f"E2E-AHR-HR-Workspace-{test_token}"
		original_user = frappe.session.user
		meta = frappe.get_meta(web_workspace.DOCTYPE)
		bill_number_field = meta.get_field("bill_no")
		supplier_field = meta.get_field("supplier")
		original_permlevel = bill_number_field.permlevel
		original_mask = supplier_field.mask
		try:
			frappe.get_doc({
				"doctype": "User",
				"email": user_email,
				"first_name": contact_name,
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": "HR User"}],
			}).insert(ignore_permissions=True)
			bill_number_field.permlevel = 1
			supplier_field.mask = 1
			frappe.set_user(user_email)

			payload = web_workspace.get_bill_tracking_workspace(bill_names[0])

			self.assertNotIn("bill_no", payload["record"])
			self.assertEqual(payload["record"]["supplier"], "XXXXXXXX")
		finally:
			frappe.set_user("Administrator")
			bill_number_field.permlevel = original_permlevel
			supplier_field.mask = original_mask
			frappe.cache.delete_value(
				f"masked_fields::{web_workspace.DOCTYPE}::::{user_email}"
			)
			if frappe.db.exists("User", user_email):
				frappe.delete_doc("User", user_email, ignore_permissions=True, force=True)
			if frappe.db.exists("Contact", contact_name):
				frappe.delete_doc("Contact", contact_name, ignore_permissions=True, force=True)
			frappe.set_user(original_user)

	def test_workspace_loads_real_closed_bill(self):
		original_user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			rows = frappe.get_all(
				"YRP Bill Tracking",
				filters={"docstatus": 1, "form_status": "Closed"},
				fields=["name", "modified"],
				limit=1,
			)
			self.assertTrue(rows, "Expected a real Closed YRP Bill Tracking record")
			payload = web_workspace.get_bill_tracking_workspace(rows[0].name)
			modified_after = frappe.db.get_value("YRP Bill Tracking", rows[0].name, "modified")

			self.assertTrue(payload["history"])
			self.assertFalse(payload["capabilities"]["assign"]["allowed"])
			self.assertEqual(modified_after, rows[0].modified)
		finally:
			frappe.set_user(original_user)


class TestBillTrackingEditor(TestCase):
	def test_editor_returns_allowlisted_values_schema_and_enabled_received_via(self):
		doc = FakeBillTracking(docstatus=0, form_status=None, assigned_to=None)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(frappe, "get_all", return_value=["HO", "Post"]) as get_all,
		):
			payload = web_workspace.get_bill_tracking_editor()

		self.assertEqual(set(payload["values"]), set(web_workspace.EDITOR_FIELDS))
		self.assertEqual(set(payload["schema"]), set(web_workspace.EDITOR_FIELDS))
		self.assertEqual(payload["received_via_options"], ["HO", "Post"])
		self.assertTrue(payload["can_create_delivery_person"])
		self.assertTrue(payload["can_submit"])
		get_all.assert_called_once_with(
			web_workspace.RECEIVED_VIA_DOCTYPE,
			filters={"disabled": 0},
			pluck="name",
			order_by="name asc",
		)
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_editor_duplicates_source_values_without_inserting(self):
		doc = FakeBillTracking(name=None, docstatus=0, form_status=None, assigned_to=None, bill_no="BILL-9")
		values = {"doctype": web_workspace.DOCTYPE, "bill_no": "BILL-9"}
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(web_workspace, "build_duplicate_values", return_value=values) as build,
			patch.object(frappe, "get_doc", return_value=doc) as get_doc,
			patch.object(frappe, "new_doc") as new_doc,
			patch.object(frappe, "get_all", return_value=[]),
		):
			payload = web_workspace.get_bill_tracking_editor(duplicate_from="BT-00001")

		build.assert_called_once_with(web_workspace.DOCTYPE, "BT-00001")
		get_doc.assert_called_once_with(values)
		new_doc.assert_not_called()
		self.assertEqual(payload["values"]["bill_no"], "BILL-9")
		self.assertIsNone(payload["modified"])

	def test_editor_filters_permlevel_field_and_masks_value(self):
		doc = FakeBillTracking(docstatus=0, form_status=None, assigned_to=None)

		def apply_field_permissions():
			doc.fieldlevel_permissions_applied += 1
			doc.set("supplier", "XXXXXXXX")
			doc.values.pop("bill_no")
			delattr(doc, "bill_no")
			doc.permitted_fieldnames.remove("bill_no")

		doc.apply_fieldlevel_read_permissions = apply_field_permissions
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_all", return_value=[]),
		):
			payload = web_workspace.get_bill_tracking_editor(doc.name)

		self.assertEqual(payload["values"]["supplier"], "XXXXXXXX")
		self.assertNotIn("bill_no", payload["values"])
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_editor_exposes_submit_permission(self):
		doc = FakeBillTracking(docstatus=0, form_status=None, assigned_to=None)

		def has_permission(doctype, ptype, **_kwargs):
			return not (doctype == web_workspace.DOCTYPE and ptype == "submit")

		with (
			patch.object(frappe, "has_permission", side_effect=has_permission),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_all", return_value=[]),
		):
			payload = web_workspace.get_bill_tracking_editor(doc.name)

		self.assertFalse(payload["can_submit"])


class TestBillTrackingSave(TestCase):
	def test_save_ignores_non_editor_fields(self):
		doc = FakeBillTracking(
			docstatus=0,
			form_status=None,
			purchase_invoice=None,
			assigned_to=None,
		)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(web_workspace, "get_bill_tracking_workspace", return_value={"saved": True}),
		):
			result = web_workspace.save_bill_tracking(
				{
					"supplier": "E2E-AHR-SUPPLIER-NEW",
					"form_status": "Closed",
					"purchase_invoice": "E2E-AHR-PI-0001",
				}
			)

		self.assertEqual(result, {"saved": True})
		self.assertEqual(doc.get("supplier"), "E2E-AHR-SUPPLIER-NEW")
		self.assertIsNone(doc.get("form_status"))
		self.assertIsNone(doc.get("purchase_invoice"))
		self.assertTrue(doc.inserted)

	def test_save_rejects_stale_modified(self):
		doc = FakeBillTracking(docstatus=0)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			web_workspace.save_bill_tracking(
				{"bill_no": "E2E-AHR-BILL-NEW"},
				name=doc.name,
				expected_modified="2026-10-12 09:00:00",
			)

		self.assertFalse(doc.saved)

	def test_save_rejects_missing_expected_modified_for_existing_bill(self):
		doc = FakeBillTracking(docstatus=0)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Reload the record before making changes",
			),
		):
			web_workspace.save_bill_tracking(
				{"bill_no": "E2E-AHR-BILL-NEW"},
				name=doc.name,
			)

		self.assertFalse(doc.saved)

	def test_save_and_submit_calls_submit(self):
		doc = FakeBillTracking(docstatus=0, form_status=None, assigned_to=None)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(web_workspace, "get_bill_tracking_workspace", return_value={"submitted": True}),
		):
			result = web_workspace.save_bill_tracking(
				{"supplier": "E2E-AHR-SUPPLIER"}, submit=True
			)

		self.assertEqual(result, {"submitted": True})
		self.assertEqual(doc.checked_permissions, ["submit"])
		self.assertTrue(doc.submitted)


class TestBillTrackingCommands(TestCase):
	def test_submit_and_delete_are_draft_only(self):
		doc = FakeBillTracking(docstatus=1, form_status="Open", assigned_to=None)
		permissions = action_permissions(can_submit=True, can_delete=True)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(web_workspace, "permission_flags", return_value=permissions),
			patch.object(web_workspace, "get_role_permissions", return_value=role_permissions()),
		):
			for command in ("submit", "delete"):
				with self.subTest(command=command), self.assertRaises(frappe.PermissionError):
					web_workspace.execute_bill_tracking_command(
						doc.name,
						command,
						expected_modified=doc.modified,
					)

		self.assertEqual(doc.checked_permissions, [])

	def test_command_rejects_missing_expected_modified(self):
		doc = FakeBillTracking(docstatus=0, form_status=None, assigned_to=None)
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Reload the record before making changes",
			),
		):
			web_workspace.execute_bill_tracking_command(doc.name, "submit")

		self.assertFalse(doc.submitted)
		self.assertEqual(doc.checked_permissions, [])

	def test_public_interfaces_are_whitelisted(self):
		for function in (
			web_workspace.get_bill_tracking_workspace,
			web_workspace.get_bill_tracking_editor,
			web_workspace.save_bill_tracking,
			web_workspace.execute_bill_tracking_command,
		):
			with self.subTest(function=function.__name__):
				self.assertIn(function, frappe.whitelisted)

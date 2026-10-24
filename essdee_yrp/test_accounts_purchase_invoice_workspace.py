from numbers import Number
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe


class FakeInvoice:
	def __init__(self, fieldtypes=None, **values):
		defaults = {
			"doctype": "YRP Purchase Invoice",
			"name": "YRP-MPI-2026-00001",
			"docstatus": 0,
			"status": "Draft",
			"modified": "2026-10-12 10:00:00",
			"supplier": "SUPPLIER-001",
			"billing_supplier": "SUPPLIER-001",
			"bill_no": "BILL-001",
			"against": "Purchase Order",
			"grand_total": 118,
			"bill_tracking": None,
			"total": 100,
			"total_tax": 18,
			"total_quantity": 10,
			"items": [],
			"essdee_items": [],
			"grn": [],
			"purchase_invoice_wo_approval_details": [],
			"pi_work_order_billed_details": [],
			"__onload": {},
		}
		defaults.update(values)
		self.values = defaults
		self.doctype = defaults["doctype"]
		self.name = defaults["name"]
		self.docstatus = defaults["docstatus"]
		self.modified = defaults["modified"]
		self.fieldtypes = fieldtypes or {}
		self.meta = SimpleNamespace(get_field=self.get_meta_field)
		self.checked_permissions = []
		self.called_methods = []
		self.fieldlevel_permissions_applied = 0

	def as_dict(self, **_kwargs):
		return dict(self.values)

	def check_permission(self, permission_type):
		self.checked_permissions.append(permission_type)

	def get(self, fieldname, default=None):
		return self.values.get(fieldname, default)

	def get_meta_field(self, fieldname):
		fieldtype = self.fieldtypes.get(
			fieldname,
			"Date" if fieldname.endswith("date") else "Data",
		)
		return SimpleNamespace(
			label=fieldname.replace("_", " ").title(),
			fieldtype=fieldtype,
			options=None,
		)

	def has_permission(self, _permission_type):
		return True

	def apply_fieldlevel_read_permissions(self):
		self.fieldlevel_permissions_applied += 1

	def run_method(self, method):
		self.called_methods.append(method)


class TestPurchaseInvoiceWorkspace(TestCase):
	def test_grns_follow_supplier_when_billing_supplier_differs_on_site(self):
		from frappe.utils import nowdate

		from essdee_yrp.accounts.purchase_invoice_editor import (
			get_purchase_invoice_editor,
			save_purchase_invoice,
		)
		from essdee_yrp.purchase_invoice import fetch_grn_details, get_eligible_grns

		original_user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			grn_name = frappe.db.get_value(
				"YRP Goods Received Note",
				{"docstatus": 1, "against": "Purchase Order", "total": [">", 0]},
				"name",
			)
			self.assertTrue(grn_name, "Expected a Purchase Order GRN with non-zero value")
			grn = frappe.copy_doc(frappe.get_doc("YRP Goods Received Note", grn_name), ignore_no_copy=False)
			grn.name = f"E2E-LOCAL-BILLING-GRN-{frappe.generate_hash(length=8)}"
			grn.docstatus = 1
			grn.purchase_invoice_name = None
			grn.set_parent_in_children()
			grn.db_insert()
			for row in grn.get_all_children():
				row.docstatus = 1
				row.db_insert()
			billing_supplier = frappe.db.get_value("Supplier", {"name": ["!=", grn.supplier], "disabled": 0})
			self.assertTrue(billing_supplier, "Expected another billing supplier")
			payload = fetch_grn_details([grn.name], "Purchase Order", supplier=grn.supplier)
			items = payload["additional_field_values"]["essdee_items"]
			self.assertGreater(sum(row["qty"] for row in items), 0)
			self.assertGreater(payload["additional_field_values"]["grand_total"], 0)
			eligible = get_eligible_grns(supplier=grn.supplier, against="Purchase Order", search_text=grn.name)
			self.assertEqual([row.name for row in eligible], [grn.name])
			workspace = save_purchase_invoice(
				values={
					"supplier": grn.supplier,
					"billing_supplier": billing_supplier,
					"against": "Purchase Order",
					"bill_no": grn.name,
					"bill_date": nowdate(),
					"posting_date": nowdate(),
				},
				grns=[grn.name],
				items=items,
			)
			name = workspace["record"]["name"]
			self.assertEqual(workspace["record"]["supplier"], grn.supplier)
			self.assertEqual([row["grn"] for row in workspace["grns"]], [grn.name])
			self.assertGreater(workspace["record"]["grand_total"], 0)
			self.assertEqual(frappe.db.get_value("YRP Purchase Invoice", name, "billing_supplier"), billing_supplier)
			editor = get_purchase_invoice_editor(name)
			self.assertEqual(editor["values"]["billing_supplier"], billing_supplier)
			eligible = get_eligible_grns(against="Purchase Order", purchase_invoice=name, search_text=grn.name)
			self.assertEqual([row.name for row in eligible], [grn.name])
			self.assertTrue(eligible[0].selected)
			fetched = fetch_grn_details([grn.name], "Purchase Order", purchase_invoice=name)
			self.assertEqual(fetched["additional_field_values"]["essdee_items"], items)
			with self.assertRaisesRegex(frappe.ValidationError, "belongs to another supplier"):
				fetch_grn_details([grn.name], "Purchase Order", supplier=billing_supplier, purchase_invoice=name)
		finally:
			frappe.db.rollback()
			frappe.set_user(original_user)

	def test_details_follow_desk_visibility_in_desk_order(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import (
			DETAIL_FIELDS,
			serialize_purchase_invoice_details,
		)

		field_flags = {
			"gstin": {"read_only": 1},
			"status": {"read_only": 1},
			"final_amount": {"fieldtype": "Currency", "read_only": 1, "allow_on_submit": 1},
			"debit_value": {"fieldtype": "Currency"},
			"due_date": {"fieldtype": "Date", "allow_on_submit": 1},
			"do_not_submit_invoice": {"fieldtype": "Check", "permlevel": 1},
			"cancel_without_cancelling_erp_inv": {"fieldtype": "Check", "permlevel": 2, "allow_on_submit": 1},
		}
		doc = FakeInvoice(gstin=None, debit_value=0, final_amount=0, remarks="Checked")
		doc.meta = SimpleNamespace(
			get_field=lambda fieldname: SimpleNamespace(
				label=fieldname.replace("_", " ").title(),
				options=None,
				**{"fieldtype": "Data", **field_flags.get(fieldname, {})},
			)
		)
		doc.has_permlevel_access_to = lambda _fieldname, field, _ptype: field.permlevel == 1

		draft = [field["fieldname"] for field in serialize_purchase_invoice_details(doc)]
		self.assertEqual(draft, [f for f in DETAIL_FIELDS if f not in {"gstin", "final_amount", "cancel_without_cancelling_erp_inv"}])
		self.assertIn("billing_supplier", draft)

		doc.docstatus = 1
		doc.values.update({"gstin": "29ABCDE1234F1Z5", "final_amount": 10, "remarks": None})
		submitted = [field["fieldname"] for field in serialize_purchase_invoice_details(doc)]
		self.assertIn("gstin", submitted)
		self.assertIn("final_amount", submitted)
		self.assertIn("due_date", submitted)
		self.assertNotIn("remarks", submitted)
		self.assertNotIn("debit_value", submitted)
		self.assertNotIn("do_not_submit_invoice", submitted)

	def test_serialize_rows_handles_frappe_dict_rows(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import _serialize_rows

		row = frappe._dict(name="E2E-AHR-DEBIT-001", debit_value=125)

		self.assertEqual(_serialize_rows([row]), [dict(row)])

	def test_close_mode_matrix(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import work_order_close_mode

		manager = {"approver_role": "WO Closer", "is_close_manager": True}
		member = {"approver_role": "WO Closer", "is_close_manager": False}
		self.assertEqual(work_order_close_mode("Open", manager), "close")
		self.assertEqual(work_order_close_mode("Open", member), "request_close")
		self.assertEqual(work_order_close_mode("Close Request", manager), "approve_close")
		self.assertEqual(work_order_close_mode("Close Request", member), "")
		self.assertEqual(work_order_close_mode("Open", {}), "")
		self.assertEqual(work_order_close_mode("Close", manager), "")

	def test_approve_only_for_unapproved_work_order_draft(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import purchase_invoice_actions

		permissions = {
			"can_write": True,
			"can_submit": True,
			"can_cancel": True,
			"can_delete": True,
			"can_amend": True,
			"can_create": True,
		}
		draft = FakeInvoice(docstatus=0, against="YRP Work Order", approved_by=None)
		self.assertTrue(
			purchase_invoice_actions(draft, permissions, {"erp_sync_enabled": False})["approve"]["allowed"]
		)

		approved = FakeInvoice(docstatus=0, against="YRP Work Order", approved_by="a@b.c")
		self.assertFalse(
			purchase_invoice_actions(approved, permissions, {"erp_sync_enabled": False})["approve"]["allowed"]
		)

		purchase = FakeInvoice(docstatus=0, against="Purchase Order")
		self.assertFalse(
			purchase_invoice_actions(purchase, permissions, {"erp_sync_enabled": False})["approve"]["allowed"]
		)

	def test_erp_actions_follow_sync_flag(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import purchase_invoice_actions

		permissions = {"can_submit": True, "can_create": True}
		submitted = FakeInvoice(docstatus=1, erp_inv_name="ACC-PINV-1", erp_inv_docstatus=0)
		off = purchase_invoice_actions(submitted, permissions, {"erp_sync_enabled": False})
		self.assertTrue(off["show_erp_bill"]["allowed"])
		self.assertFalse(off["submit_erp_bill"]["allowed"])
		self.assertTrue(
			purchase_invoice_actions(submitted, permissions, {"erp_sync_enabled": True})[
				"submit_erp_bill"
			]["allowed"]
		)

	def test_workspace_requires_read_and_shows_desk_fields(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		doc = FakeInvoice(
			against="YRP Work Order",
			posting_date="2026-10-12",
			billing_supplier="SUPPLIER-001",
			naming_series="YRP-MPI-.YYYY.-",
			gstin="29ABCDE1234F1Z5",
			remarks="Checked",
		)
		permission_values = {
			"can_read": True,
			"can_write": True,
			"can_create": True,
			"can_submit": True,
			"can_cancel": False,
			"can_delete": True,
			"can_amend": False,
			"can_print": True,
		}
		with (
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.permission_flags",
				return_value=permission_values,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.is_erp_purchase_invoice_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_document_print_formats",
				return_value=[],
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_close_permission",
				return_value={},
			),
		):
			payload = get_purchase_invoice_workspace(doc.name)

		fieldnames = [field["fieldname"] for field in payload["details"]]
		self.assertEqual(doc.checked_permissions, ["read"])
		self.assertEqual(doc.called_methods, [])
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)
		self.assertIn("against", fieldnames)
		self.assertIn("posting_date", fieldnames)
		self.assertIn("remarks", fieldnames)
		self.assertIn("billing_supplier", fieldnames)
		self.assertIn("gstin", fieldnames)
		self.assertNotIn("naming_series", fieldnames)

	def test_workspace_serializes_masked_and_field_permitted_values(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		doc = FakeInvoice(
			supplier="SUPPLIER-SECRET",
			billing_supplier="SUPPLIER-SECRET",
			remarks="Restricted remarks",
		)

		def apply_field_permissions():
			doc.fieldlevel_permissions_applied += 1
			doc.values["supplier"] = "XXXXXXXX"
			doc.values.pop("remarks")

		doc.apply_fieldlevel_read_permissions = apply_field_permissions
		base_field = doc.get_meta_field
		doc.meta = SimpleNamespace(
			get_field=lambda fieldname: SimpleNamespace(
				**vars(base_field(fieldname)), permlevel=1 if fieldname == "remarks" else 0
			)
		)
		doc.has_permlevel_access_to = lambda *_args: False
		with (
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.permission_flags",
				return_value={},
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.is_erp_purchase_invoice_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_document_print_formats",
				return_value=[],
			),
		):
			payload = get_purchase_invoice_workspace(doc.name)

		details = {field["fieldname"]: field for field in payload["details"]}
		self.assertEqual(payload["record"]["supplier"], "XXXXXXXX")
		self.assertEqual(details["billing_supplier"]["value"], "XXXXXXXX")
		self.assertNotIn("remarks", details)
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_workspace_computes_permissions_and_actions_before_masking(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		doc = FakeInvoice(
			against="YRP Work Order",
			supplier="ALLOWED-SUPPLIER",
			billing_supplier="ALLOWED-SUPPLIER",
			approved_by=None,
		)
		permission_suppliers = []

		def has_permission(_doctype, ptype, doc=None):
			if ptype != "create":
				permission_suppliers.append(doc.get("supplier"))
			return doc is None or doc.get("supplier") == "ALLOWED-SUPPLIER"

		def get_print_formats(invoice):
			self.assertEqual(invoice.get("supplier"), "ALLOWED-SUPPLIER")
			return [{"name": "Purchase Invoice"}]

		def apply_field_permissions():
			doc.fieldlevel_permissions_applied += 1
			doc.values["supplier"] = "XXXXXXXX"
			doc.values["against"] = None

		doc.apply_fieldlevel_read_permissions = apply_field_permissions
		with (
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.frappe.has_permission",
				side_effect=has_permission,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.is_erp_purchase_invoice_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_document_print_formats",
				side_effect=get_print_formats,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_close_permission",
				return_value={},
			) as get_close_permission,
		):
			payload = get_purchase_invoice_workspace(doc.name)

		self.assertEqual(permission_suppliers, ["ALLOWED-SUPPLIER"] * 7)
		self.assertTrue(all(payload["permissions"].values()))
		self.assertTrue(payload["capabilities"]["approve"]["allowed"])
		self.assertEqual(payload["print_formats"], [{"name": "Purchase Invoice"}])
		self.assertEqual(payload["record"]["supplier"], "XXXXXXXX")
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)
		get_close_permission.assert_called_once_with()

	def test_workspace_applies_frappe_mask_and_permlevel_rules(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		invoice_name = frappe.get_all(
			"YRP Purchase Invoice",
			filters={"supplier": ["!=", ""]},
			pluck="name",
			limit=1,
		)
		self.assertTrue(invoice_name, "Expected a Purchase Invoice with a supplier")
		user_email = f"e2e.ahr.workspace.{frappe.generate_hash(length=8)}@example.com"
		original_user = frappe.session.user
		meta = frappe.get_meta("YRP Purchase Invoice")
		against_field = meta.get_field("against")
		original_permlevel = against_field.permlevel
		supplier_field = meta.get_field("supplier")
		original_mask = supplier_field.mask
		try:
			user = frappe.get_doc({
				"doctype": "User",
				"email": user_email,
				"first_name": "E2E AHR Workspace",
				"enabled": 1,
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": "Accounts User"}],
			})
			user.insert(ignore_permissions=True)
			against_field.permlevel = 1
			supplier_field.mask = 1
			frappe.set_user(user_email)

			payload = get_purchase_invoice_workspace(invoice_name[0])

			fieldnames = [field["fieldname"] for field in payload["details"]]
			self.assertEqual(payload["record"]["supplier"], "XXXXXXXX")
			self.assertNotIn("against", fieldnames)
		finally:
			frappe.set_user("Administrator")
			against_field.permlevel = original_permlevel
			supplier_field.mask = original_mask
			if frappe.db.exists("User", user_email):
				frappe.delete_doc("User", user_email, ignore_permissions=True, force=True)
			for contact in frappe.get_all("Contact", filters={"email_id": user_email}, pluck="name"):
				frappe.delete_doc("Contact", contact, ignore_permissions=True, force=True)
			frappe.set_user(original_user)

	def test_workspace_does_not_invoke_base_work_order_item_fetch(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		work_order_row = frappe._dict(work_order="YRP-WO-0001")
		doc = FakeInvoice(
			against="YRP Work Order",
			pi_work_order_billed_details=[work_order_row],
		)
		with (
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.permission_flags",
				return_value={},
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.is_erp_purchase_invoice_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.get_document_print_formats",
				return_value=[],
			),
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace.build_verification_details",
				return_value=[],
			) as build_details,
			patch(
				"essdee_yrp.accounts.purchase_invoice_workspace._debit_summary",
				return_value=[],
			),
			patch(
				"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.fetch_work_order_items"
			) as base_fetch,
		):
			get_purchase_invoice_workspace(doc.name)

		build_details.assert_called_once_with([work_order_row])
		base_fetch.assert_not_called()
		self.assertEqual(doc.called_methods, [])

	def test_workspace_on_real_submitted_invoice(self):
		payload = self.get_real_workspace({"docstatus": 1, "against": "YRP Work Order"})

		self.assertEqual(
			set(payload),
			{
				"record",
				"details",
				"totals",
				"items",
				"grns",
				"verification",
				"debit_summary",
				"approvals",
				"work_orders",
				"permissions",
				"capabilities",
				"print_formats",
				"erp_sync_enabled",
			},
		)
		self.assertTrue(payload["items"])
		self.assertEqual(
			set(payload["items"][0]),
			{"group_key", "item", "lot", "qty", "uom", "source_rate", "rate", "tax", "amount", "expense_head"},
		)
		self.assertTrue(payload["grns"])
		self.assertEqual(
			set(payload["grns"][0]),
			{
				"grn",
				"posting_date",
				"against",
				"against_id",
				"supplier_document_no",
				"total_received_quantity",
				"grand_total",
			},
		)
		self.assertTrue(all(isinstance(total["value"], Number) for total in payload["totals"]))
		self.assertTrue(payload["capabilities"]["cancel"]["allowed"])

	def test_workspace_on_real_purchase_order_draft_has_no_write_side_effect(self):
		payload = self.get_real_workspace({"docstatus": 0, "against": "Purchase Order"})

		self.assertEqual(payload["record"]["docstatus"], 0)
		self.assertTrue(payload["capabilities"]["edit"]["allowed"])
		self.assertTrue(payload["capabilities"]["submit"]["allowed"])
		self.assertFalse(payload["capabilities"]["approve"]["allowed"])

	def test_workspace_on_all_real_work_order_drafts_has_no_write_side_effect(self):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		original_user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			invoices = frappe.get_all(
				"YRP Purchase Invoice",
				filters={"docstatus": 0, "against": "YRP Work Order"},
				fields=["name", "modified"],
				limit=20,
			)
			self.assertTrue(invoices, "Expected at least one draft Work Order Purchase Invoice")
			for invoice in invoices:
				with self.subTest(invoice=invoice.name):
					payload = get_purchase_invoice_workspace(invoice.name)
					modified = frappe.db.get_value("YRP Purchase Invoice", invoice.name, "modified")
					self.assertEqual(payload["record"]["name"], invoice.name)
					self.assertEqual(modified, invoice.modified)
		finally:
			frappe.db.rollback()
			frappe.set_user(original_user)

	def get_real_workspace(self, filters):
		from essdee_yrp.accounts.purchase_invoice_workspace import get_purchase_invoice_workspace

		original_user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			invoices = frappe.get_all(
				"YRP Purchase Invoice",
				filters=filters,
				fields=["name", "modified"],
				limit=1,
			)
			self.assertTrue(invoices, f"Expected a Purchase Invoice matching {filters}")
			invoice = invoices[0]
			payload = get_purchase_invoice_workspace(invoice.name)
			modified_after = frappe.db.get_value("YRP Purchase Invoice", invoice.name, "modified")
			self.assertEqual(modified_after, invoice.modified)
			return payload
		finally:
			frappe.set_user(original_user)

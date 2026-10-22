import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

MODULE = "essdee_yrp.accounts.purchase_invoice_editor"


class FakeRow:
	def __init__(self, **values):
		self.__dict__.update(values)

	def as_dict(self):
		return dict(self.__dict__)

	def get(self, fieldname, default=None):
		return getattr(self, fieldname, default)

	def set(self, fieldname, value):
		setattr(self, fieldname, value)


class FakeMeta:
	def __init__(self, fieldnames=None):
		self.fields = [self.get_field(fieldname) for fieldname in fieldnames or []]

	def get_field(self, fieldname):
		fieldtype = "Date" if fieldname.endswith("date") else "Data"
		return SimpleNamespace(
			fieldname=fieldname,
			label=fieldname.replace("_", " ").title(),
			fieldtype=fieldtype,
			options=None,
			reqd=fieldname in {"supplier", "bill_no", "bill_date"},
		)


class FakeInvoice:
	def __init__(self, **values):
		defaults = {
			"doctype": "YRP Purchase Invoice",
			"name": "YRP-MPI-2026-00001",
			"docstatus": 0,
			"modified": "2026-10-12 10:00:00",
			"status": "Draft",
			"supplier": "SUP-1",
			"against": "Purchase Order",
			"posting_date": "2026-10-12",
			"due_date": None,
			"bill_no": "BILL-1",
			"billing_supplier": "SUP-1",
			"bill_date": "2026-10-11",
			"bill_tracking": None,
			"eligibility_for_itc": "All Other ITC",
			"debit_type": None,
			"debit_no": None,
			"debit_value": None,
			"remarks": None,
			"essdee_items": [],
			"essdee_rate_table_source": "migrated_v1",
			"grn": [],
			"erp_inv_name": None,
			"erp_inv_docstatus": 0,
			"approved_by": None,
		}
		defaults.update(values)
		self.values = defaults
		self.doctype = defaults["doctype"]
		self.name = defaults["name"]
		self.docstatus = defaults["docstatus"]
		self.modified = defaults["modified"]
		self.meta = FakeMeta(defaults)
		self.checked_permissions = []
		self.set_calls = []
		self.db_set_calls = []
		self.saved = 0
		self.inserted = 0
		self.submitted = 0
		self.cancelled = 0
		self.fieldlevel_permissions_applied = 0

	def get(self, fieldname, default=None):
		if fieldname == "docstatus":
			return self.docstatus
		if fieldname == "modified":
			return self.modified
		return self.values.get(fieldname, default)

	def set(self, fieldname, value):
		self.set_calls.append((fieldname, value))
		self.values[fieldname] = value
		if fieldname == "status":
			self.values["status"] = value

	def check_permission(self, permission_type):
		self.checked_permissions.append(permission_type)

	def save(self):
		self.saved += 1
		return self

	def insert(self):
		self.inserted += 1
		return self

	def submit(self):
		self.submitted += 1
		return self

	def cancel(self):
		self.cancelled += 1
		return self

	def db_set(self, fieldname, value, **kwargs):
		self.db_set_calls.append((fieldname, value, kwargs))
		self.values[fieldname] = value

	def apply_fieldlevel_read_permissions(self):
		self.fieldlevel_permissions_applied += 1


class FakeBillTracking:
	def __init__(self, **values):
		defaults = {
			"name": "BT-00001",
			"supplier": "SUP-2",
			"bill_no": "TRACKED-1",
			"bill_date": "2026-10-10",
			"purchase_invoice": None,
			"erp_purchase_invoice": None,
		}
		defaults.update(values)
		self.values = defaults
		self.name = defaults["name"]
		self.checked_permissions = []

	def get(self, fieldname, default=None):
		return self.values.get(fieldname, default)

	def check_permission(self, permission_type):
		self.checked_permissions.append(permission_type)


def full_permissions():
	return {
		"can_read": True,
		"can_write": True,
		"can_create": True,
		"can_submit": True,
		"can_cancel": True,
		"can_delete": True,
		"can_amend": True,
		"can_print": True,
	}


class TestPurchaseInvoiceEditor(TestCase):
	def tearDown(self):
		frappe.db.rollback()

	def save_existing(self, doc, values=None, grns=None, items=None):
		from essdee_yrp.accounts.purchase_invoice_editor import save_purchase_invoice

		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}.get_purchase_invoice_workspace", return_value={"record": {"name": doc.name}}),
		):
			return save_purchase_invoice(
				values or {},
				grns or [],
				items or [],
				name=doc.name,
				expected_modified=doc.modified,
			)

	def test_save_updates_rates_in_place_for_same_group_keys(self):
		first = FakeRow(group_key="g1", item="ITEM-1", rate=10, expense_head="EXP-1")
		second = FakeRow(group_key="g2", item="ITEM-2", rate=20, expense_head="EXP-2")
		doc = FakeInvoice(essdee_items=[first, second])

		self.save_existing(
			doc,
			grns=["GRN-1", "GRN-1", "GRN-2"],
			items=json.dumps([
				{"group_key": "g1", "item": "CHANGED", "rate": 15},
				{"group_key": "g2", "rate": 25, "expense_head": "EXP-3"},
			]),
		)

		self.assertIs(doc.get("essdee_items")[0], first)
		self.assertIs(doc.get("essdee_items")[1], second)
		self.assertEqual((first.rate, second.rate), (15, 25))
		self.assertEqual(first.item, "ITEM-1")
		self.assertEqual((first.expense_head, second.expense_head), ("EXP-1", "EXP-3"))
		self.assertEqual(doc.get("essdee_rate_table_source"), "migrated_v1")
		self.assertNotIn("essdee_items", [fieldname for fieldname, _value in doc.set_calls])
		self.assertIn(("grn", [{"grn": "GRN-1"}, {"grn": "GRN-2"}]), doc.set_calls)

	def test_save_replaces_rows_after_fetch(self):
		doc = FakeInvoice(essdee_items=[FakeRow(group_key="g1", rate=10)])
		child_meta = FakeMeta(["group_key", "item", "rate", "expense_head"])
		posted = [{"group_key": "g3", "item": "ITEM-3", "rate": 30, "unknown": "ignored"}]
		with patch(f"{MODULE}.frappe.get_meta", return_value=child_meta):
			self.save_existing(doc, items=posted)

		self.assertIn(
			("essdee_items", [{"group_key": "g3", "item": "ITEM-3", "rate": 30}]),
			doc.set_calls,
		)
		self.assertEqual(doc.get("essdee_rate_table_source"), "yrp_grn_v1")

	def test_save_empty_draft_keeps_rate_source_unset(self):
		doc = FakeInvoice(essdee_items=[], essdee_rate_table_source=None)
		self.save_existing(doc, items=[])

		self.assertIsNone(doc.get("essdee_rate_table_source"))
		self.assertNotIn("essdee_items", [fieldname for fieldname, _value in doc.set_calls])

	def test_save_refetched_amendment_rebuilds_hidden_items_for_identical_keys(self):
		group_key = "E2E-AHR-GROUP-1"
		amended = frappe.new_doc("YRP Purchase Invoice")
		amended.name = "E2E-AHR-PI-AMEND-001-1"
		amended.modified = "2026-10-12 10:00:00"
		amended.amended_from = "E2E-AHR-PI-AMEND-001"
		amended.against = "Purchase Order"
		amended.supplier = "E2E-AHR-SUPPLIER-001"
		amended.essdee_rate_table_source = None
		retained_grouped_row = amended.append(
			"essdee_items",
			{
				"item": "E2E-AHR-ITEM-001",
				"qty": 2,
				"uom": "Nos",
				"source_rate": 10,
				"rate": 10,
				"group_key": group_key,
			},
		)
		amended.append(
			"items",
			{
				"item": "E2E-AHR-STALE-ITEM",
				"item_group": "E2E-AHR-GROUP",
				"qty": 2,
				"uom": "Nos",
				"source_rate": 10,
				"rate": 10,
			},
		)
		posted_row = {
			"item": "E2E-AHR-ITEM-001",
			"qty": 2,
			"uom": "Nos",
			"source_rate": 10,
			"rate": 12,
			"amount": 24,
			"group_key": group_key,
		}
		payload = {
			"items": [{**posted_row, "essdee_group_key": group_key, "essdee_rate_weight": 1}],
			"commercial_items": [posted_row],
			"allow_to_change_rate": 1,
			"total_quantity": 2,
		}

		def save_with_controller_validation(invoice):
			invoice._action = "save"
			invoice.run_before_save_methods()
			return invoice

		database_get_value = frappe.db.get_value

		def get_value(doctype, *args, **kwargs):
			if doctype == "YRP Goods Received Note":
				return 24
			return database_get_value(doctype, *args, **kwargs)

		with (
			patch.object(type(amended), "save", new=save_with_controller_validation),
			patch.object(type(amended), "_lock_selected_grns"),
			patch("essdee_yrp.overrides.purchase_invoice.build_purchase_order_invoice_payload", return_value=payload),
			patch("yrp.stock.uom.apply_item_uoms"),
			patch("essdee_yrp.overrides.purchase_invoice._validate_selected_grn"),
			patch.object(frappe.db, "get_value", side_effect=get_value),
		):
			self.save_existing(amended, grns=["E2E-AHR-GRN-001"], items=[posted_row])

		self.assertEqual(amended.essdee_rate_table_source, "yrp_grn_v1")
		self.assertIsNot(amended.essdee_items[0], retained_grouped_row)
		self.assertEqual(amended.essdee_items[0].rate, 12)
		self.assertEqual(amended.items[0].item, "E2E-AHR-ITEM-001")
		self.assertEqual(amended.items[0].rate, 12)

	def test_save_rejects_stale_modified(self):
		from essdee_yrp.accounts.purchase_invoice_editor import save_purchase_invoice

		doc = FakeInvoice(modified="2026-10-12 11:00:00")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			save_purchase_invoice({}, [], [], name=doc.name, expected_modified="2026-10-12 10:00:00")
		self.assertEqual(doc.saved, 0)
		self.assertEqual(doc.set_calls, [])

	def test_save_rejects_missing_expected_modified_for_existing_invoice(self):
		from essdee_yrp.accounts.purchase_invoice_editor import save_purchase_invoice

		doc = FakeInvoice()
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Reload the record before making changes",
			),
		):
			save_purchase_invoice({}, [], [], name=doc.name)
		self.assertEqual(doc.saved, 0)
		self.assertEqual(doc.set_calls, [])

	def test_save_keeps_stored_suppliers_when_values_are_masked(self):
		doc = FakeInvoice(supplier="SUP-1", billing_supplier="SUP-1")

		self.save_existing(
			doc,
			values={
				"supplier": "  XXXXXXX  ",
				"billing_supplier": "  *******  ",
				"bill_no": "BILL-2",
			},
		)

		self.assertEqual(doc.get("supplier"), "SUP-1")
		self.assertEqual(doc.get("billing_supplier"), "SUP-1")
		self.assertEqual(doc.get("bill_no"), "BILL-2")

	def test_resolve_grn_supplier_requires_unmasked_supplier(self):
		from essdee_yrp.purchase_invoice import _resolve_grn_supplier

		for supplier in (None, "XXXXXXXX"):
			with self.subTest(supplier=supplier), self.assertRaisesRegex(
				frappe.ValidationError,
				"Supplier is required",
			):
				_resolve_grn_supplier(supplier)

	def test_resolve_grn_supplier_uses_billing_supplier_with_fallback(self):
		from essdee_yrp.purchase_invoice import _resolve_grn_supplier

		for billing_supplier in ("SUP-2", "", None):
			for supplier in (None, "XXXXXXXX"):
				doc = FakeInvoice(supplier="SUP-1", billing_supplier=billing_supplier)
				with (
					self.subTest(billing_supplier=billing_supplier, supplier=supplier),
					patch("essdee_yrp.purchase_invoice.frappe.db.exists", return_value=True),
					patch("essdee_yrp.purchase_invoice.frappe.get_doc", return_value=doc),
				):
					self.assertEqual(
						_resolve_grn_supplier(supplier, purchase_invoice=doc.name),
						billing_supplier or "SUP-1",
					)
					self.assertEqual(_resolve_grn_supplier("SUP-3", purchase_invoice=doc.name), "SUP-3")
				self.assertEqual(doc.checked_permissions, ["write"])

	def test_eligible_grns_requires_resolvable_supplier(self):
		from essdee_yrp.purchase_invoice import get_eligible_grns

		for supplier in (None, "XXXXXXXX"):
			with (
				self.subTest(supplier=supplier),
				patch("essdee_yrp.purchase_invoice.frappe.get_list") as get_list,
				self.assertRaisesRegex(frappe.ValidationError, "Supplier is required"),
			):
				get_eligible_grns(supplier=supplier, against="YRP Work Order")
			get_list.assert_not_called()

	def test_eligible_grns_resolves_masked_supplier_from_existing_invoice(self):
		from essdee_yrp.purchase_invoice import get_eligible_grns

		doc = FakeInvoice(supplier="SUP-1", billing_supplier="SUP-2")
		with (
			patch("essdee_yrp.purchase_invoice.frappe.db.exists", return_value=True),
			patch("essdee_yrp.purchase_invoice.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.purchase_invoice._is_active_purchase_invoice", return_value=True),
			patch("essdee_yrp.purchase_invoice._active_purchase_invoice_names", return_value=set()),
			patch("essdee_yrp.purchase_invoice._active_invoice_links_for_grns", return_value={}),
			patch("essdee_yrp.purchase_invoice.frappe.get_list", return_value=[]) as get_list,
		):
			get_eligible_grns(
				supplier=None,
				against="Purchase Order",
				search_text="E2E-AHR",
				purchase_invoice=doc.name,
				limit=25,
			)

		self.assertEqual(doc.checked_permissions, ["write"])
		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			{"docstatus": 1, "supplier": "SUP-2", "against": "Purchase Order"},
		)
		self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 75)

	def test_eligible_grns_resolves_masked_supplier_from_bill_tracking(self):
		from essdee_yrp.purchase_invoice import get_eligible_grns

		bill = FakeBillTracking(supplier="SUP-2")
		with (
			patch("essdee_yrp.purchase_invoice.frappe.get_doc", return_value=bill),
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.purchase_invoice._is_active_purchase_invoice", return_value=False),
			patch("essdee_yrp.purchase_invoice._active_purchase_invoice_names", return_value=set()),
			patch("essdee_yrp.purchase_invoice._active_invoice_links_for_grns", return_value={}),
			patch("essdee_yrp.purchase_invoice.frappe.get_list", return_value=[]) as get_list,
		):
			get_eligible_grns(
				supplier="XXXXXXXX",
				against="YRP Work Order",
				bill_tracking=bill.name,
			)

		self.assertEqual(bill.checked_permissions, ["read"])
		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			{"docstatus": 1, "supplier": "SUP-2", "against": "YRP Work Order", "is_return": 0},
		)

	def test_eligible_grns_keep_only_unlinked_cancelled_or_own_draft_rows(self):
		from essdee_yrp.purchase_invoice import get_eligible_grns

		rows = [
			frappe._dict(name="GRN-FREE", purchase_invoice_name=None),
			frappe._dict(name="GRN-DIRECT-ACTIVE", purchase_invoice_name="PI-DRAFT"),
			frappe._dict(name="GRN-DIRECT-CANCELLED", purchase_invoice_name="PI-CANCELLED"),
			frappe._dict(name="GRN-CHILD-ACTIVE", purchase_invoice_name=None),
			frappe._dict(name="GRN-CHILD-CANCELLED", purchase_invoice_name=None),
			frappe._dict(name="GRN-DIRECT-OWN", purchase_invoice_name="PI-OWN"),
			frappe._dict(name="GRN-CHILD-OWN", purchase_invoice_name=None),
		]
		child_links = {
			"GRN-CHILD-ACTIVE": {"PI-SUBMITTED"},
			"GRN-CHILD-OWN": {"PI-OWN"},
		}
		with (
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.purchase_invoice._is_active_purchase_invoice", return_value=True),
			patch(
				"essdee_yrp.purchase_invoice._active_purchase_invoice_names",
				return_value={"PI-DRAFT", "PI-OWN"},
			),
			patch("essdee_yrp.purchase_invoice._active_invoice_links_for_grns", return_value=child_links),
			patch("essdee_yrp.purchase_invoice.frappe.get_list", return_value=rows) as get_list,
		):
			eligible = get_eligible_grns(
				"SUP-1",
				"YRP Work Order",
				purchase_invoice="PI-OWN",
			)

		self.assertEqual(
			[(row.name, row.selected) for row in eligible],
			[
				("GRN-FREE", False),
				("GRN-DIRECT-CANCELLED", False),
				("GRN-CHILD-CANCELLED", False),
				("GRN-DIRECT-OWN", True),
				("GRN-CHILD-OWN", True),
			],
		)
		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			{"docstatus": 1, "supplier": "SUP-1", "against": "YRP Work Order", "is_return": 0},
		)

	def test_eligible_grns_pages_past_an_ineligible_first_window(self):
		from essdee_yrp.purchase_invoice import get_eligible_grns

		first_page = [
			frappe._dict(name=f"GRN-LINKED-{index}", purchase_invoice_name=f"PI-{index}")
			for index in range(3)
		]
		last_page = [frappe._dict(name="GRN-ELIGIBLE", purchase_invoice_name=None)]

		def active_names(names):
			return {name for name in names if name}

		with (
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.purchase_invoice._is_active_purchase_invoice", return_value=False),
			patch(
				"essdee_yrp.purchase_invoice._active_purchase_invoice_names",
				side_effect=active_names,
			),
			patch("essdee_yrp.purchase_invoice._active_invoice_links_for_grns", return_value={}),
			patch(
				"essdee_yrp.purchase_invoice.frappe.get_list",
				side_effect=[first_page, last_page],
			) as get_list,
		):
			eligible = get_eligible_grns("SUP-1", "YRP Work Order", limit=1)

		self.assertEqual([row.name for row in eligible], ["GRN-ELIGIBLE"])
		self.assertEqual(
			[call.kwargs["limit_start"] for call in get_list.call_args_list],
			[0, 3],
		)
		self.assertTrue(
			all(call.kwargs["limit_page_length"] == 3 for call in get_list.call_args_list)
		)

	def test_fetch_grns_honours_changed_supplier_on_existing_invoice(self):
		from essdee_yrp.purchase_invoice import fetch_grn_details

		payload = {
			"items": [],
			"commercial_items": [],
			"pre_tax_total": 0,
			"tax_total": 0,
			"total": 0,
		}
		with (
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch(
				"essdee_yrp.purchase_invoice.build_purchase_order_invoice_payload",
				return_value=payload,
			) as build_payload,
			patch("essdee_yrp.purchase_invoice.fetch_expense_accounts", side_effect=lambda rows: rows),
		):
			fetch_grn_details(
				["E2E-AHR-GRN-002"],
				"Purchase Order",
				"SUP-2",
				purchase_invoice="E2E-AHR-PI-001",
			)

		build_payload.assert_called_once_with(
			["E2E-AHR-GRN-002"],
			supplier="SUP-2",
			purchase_invoice="E2E-AHR-PI-001",
		)

	def test_fetch_grns_resolves_masked_supplier_from_bill_tracking(self):
		from essdee_yrp.purchase_invoice import fetch_grn_details

		bill = FakeBillTracking(supplier="SUP-2")
		payload = {
			"items": [],
			"commercial_items": [],
			"pre_tax_total": 0,
			"tax_total": 0,
			"total": 0,
		}
		with (
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.get_doc", return_value=bill),
			patch(
				"essdee_yrp.purchase_invoice.build_purchase_order_invoice_payload",
				return_value=payload,
			) as build_payload,
			patch("essdee_yrp.purchase_invoice.fetch_expense_accounts", side_effect=lambda rows: rows),
		):
			fetch_grn_details(
				["E2E-AHR-GRN-002"],
				"Purchase Order",
				supplier=None,
				bill_tracking=bill.name,
			)

		self.assertEqual(bill.checked_permissions, ["read"])
		build_payload.assert_called_once_with(
			["E2E-AHR-GRN-002"],
			supplier="SUP-2",
			purchase_invoice=None,
		)

	def test_fetch_grns_requires_resolvable_supplier(self):
		from essdee_yrp.purchase_invoice import fetch_grn_details

		for against in ("Purchase Order", "YRP Work Order"):
			for supplier in (None, "XXXXXXXX"):
				with (
					self.subTest(against=against, supplier=supplier),
					patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
					patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
					self.assertRaisesRegex(frappe.ValidationError, "Supplier is required"),
				):
					fetch_grn_details(["E2E-AHR-GRN-003"], against, supplier=supplier)

	def test_work_order_fetch_rejects_grn_from_another_supplier(self):
		from essdee_yrp.purchase_invoice import fetch_grn_details

		grn = frappe._dict(
			docstatus=1,
			supplier="SUP-2",
			against="YRP Work Order",
			purchase_invoice_name=None,
		)
		with (
			patch("essdee_yrp.purchase_invoice._check_invoice_fetch_permission"),
			patch("essdee_yrp.purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
			patch("essdee_yrp.work_order_billing.frappe.has_permission"),
			self.assertRaisesRegex(frappe.ValidationError, "belongs to another supplier"),
		):
			fetch_grn_details(["GRN-OTHER"], "YRP Work Order", supplier="SUP-1")

	def test_invoice_validation_rejects_grn_from_another_supplier(self):
		from essdee_yrp.overrides.purchase_invoice import EssdeePurchaseInvoice

		doc = frappe._dict(
			name="PI-1",
			supplier="SUP-1",
			against="YRP Work Order",
			grn=[frappe._dict(idx=1, grn="GRN-OTHER")],
		)
		grn = frappe._dict(
			docstatus=1,
			supplier="SUP-2",
			against="YRP Work Order",
			purchase_invoice_name=None,
		)
		with (
			patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
			patch("essdee_yrp.work_order_billing.frappe.has_permission"),
			self.assertRaisesRegex(frappe.ValidationError, "belongs to another supplier"),
		):
			EssdeePurchaseInvoice.validate_grns(doc)

	def test_invoice_validation_uses_billing_supplier_with_fallback(self):
		from essdee_yrp.overrides.purchase_invoice import EssdeePurchaseInvoice

		for against in ("Purchase Order", "YRP Work Order"):
			for billing_supplier in ("SUP-2", "", None):
				doc = frappe._dict(
					name="PI-1",
					supplier="SUP-1",
					billing_supplier=billing_supplier,
					against=against,
					grn=[frappe._dict(idx=1, grn="GRN-1")],
				)
				grn = frappe._dict(
					docstatus=1,
					supplier=billing_supplier or "SUP-1",
					against=against,
					purchase_invoice_name=None,
				)
				with (
					self.subTest(against=against, billing_supplier=billing_supplier),
					patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
					patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
					patch("essdee_yrp.work_order_billing.frappe.has_permission"),
					patch("essdee_yrp.work_order_billing._is_active_purchase_invoice", return_value=False),
					patch("essdee_yrp.work_order_billing._active_invoice_links_for_grns", return_value={}),
				):
					EssdeePurchaseInvoice.validate_grns(doc)
					grn.supplier = "SUP-OTHER"
					with self.assertRaisesRegex(frappe.ValidationError, "belongs to another supplier"):
						EssdeePurchaseInvoice.validate_grns(doc)

	def test_fetch_validation_ignores_cancelled_direct_link_but_rejects_active_child(self):
		from essdee_yrp.work_order_billing import _validate_selected_grn

		grn = frappe._dict(
			docstatus=1,
			supplier="SUP-1",
			against="YRP Work Order",
			purchase_invoice_name="PI-CANCELLED",
		)
		with (
			patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
			patch("essdee_yrp.work_order_billing.frappe.has_permission"),
			patch("essdee_yrp.work_order_billing._is_active_purchase_invoice", return_value=False),
			patch("essdee_yrp.work_order_billing._active_invoice_links_for_grns", return_value={}),
		):
			self.assertIs(
				_validate_selected_grn("GRN-1", "SUP-1", "YRP Work Order"),
				grn,
			)

		with (
			patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
			patch("essdee_yrp.work_order_billing.frappe.has_permission"),
			patch("essdee_yrp.work_order_billing._is_active_purchase_invoice", return_value=False),
			patch(
				"essdee_yrp.work_order_billing._active_invoice_links_for_grns",
				return_value={"GRN-1": {"PI-ACTIVE"}},
			),
			self.assertRaisesRegex(frappe.ValidationError, "already linked.*PI-ACTIVE"),
		):
			_validate_selected_grn("GRN-1", "SUP-1", "YRP Work Order")

	def test_work_order_invoice_rejects_return_grn(self):
		from essdee_yrp.work_order_billing import _validate_selected_grn

		grn = frappe._dict(
			docstatus=1,
			supplier="SUP-1",
			against="YRP Work Order",
			purchase_invoice_name=None,
			is_return=1,
		)
		with (
			patch("essdee_yrp.work_order_billing.frappe.db.exists", return_value=True),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=grn),
			patch("essdee_yrp.work_order_billing.frappe.has_permission"),
			patch("essdee_yrp.work_order_billing._is_active_purchase_invoice", return_value=False),
			patch("essdee_yrp.work_order_billing._active_invoice_links_for_grns", return_value={}),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "GRN-1 is a return"):
				_validate_selected_grn("GRN-1", "SUP-1", "YRP Work Order")
			grn.against = "Purchase Order"
			self.assertIs(_validate_selected_grn("GRN-1", "SUP-1", "Purchase Order"), grn)

	def test_eligible_grn_hook_uses_mask_aware_override(self):
		method = "yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.get_eligible_grns"
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(
			overrides[method][-1],
			"essdee_yrp.purchase_invoice.get_eligible_grns",
		)

	def test_save_ignores_unknown_fields(self):
		doc = FakeInvoice(status="Draft", approved_by=None)

		self.save_existing(doc, values={"status": "Approved", "approved_by": "x"})

		self.assertEqual(doc.get("status"), "Draft")
		self.assertIsNone(doc.get("approved_by"))

	def test_save_keeps_the_erp_bill_as_draft_choice(self):
		doc = FakeInvoice(do_not_submit_invoice=0)

		self.save_existing(doc, values={"do_not_submit_invoice": 1})

		self.assertEqual(doc.get("do_not_submit_invoice"), 1)

	def test_editor_prefills_from_bill_tracking(self):
		from essdee_yrp.accounts.purchase_invoice_editor import get_purchase_invoice_editor

		bill = FakeBillTracking()
		doc = FakeInvoice(
			name=None,
			supplier=None,
			billing_supplier=None,
			bill_no=None,
			bill_date=None,
			bill_tracking=None,
		)
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=bill) as get_doc,
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
		):
			payload = get_purchase_invoice_editor(bill_tracking=bill.name)

		get_doc.assert_called_once_with("YRP Bill Tracking", bill.name, for_update=False)
		self.assertEqual(bill.checked_permissions, ["read"])
		self.assertEqual(payload["values"]["supplier"], "SUP-2")
		self.assertEqual(payload["values"]["billing_supplier"], "SUP-2")
		self.assertEqual(payload["values"]["bill_no"], "TRACKED-1")
		self.assertEqual(payload["values"]["bill_date"], "2026-10-10")
		self.assertEqual(payload["values"]["bill_tracking"], bill.name)
		self.assertEqual(payload["locked_fields"], ["supplier", "bill_no", "bill_date"])

	def test_editor_duplicates_unsaved_values_without_the_bill_tracking_link(self):
		from essdee_yrp.accounts.purchase_invoice_editor import get_purchase_invoice_editor

		doc = FakeInvoice(name=None, bill_no="BILL-9", bill_tracking="BT-00001", remarks="copied")
		values = {"doctype": "YRP Purchase Invoice", "bill_no": "BILL-9"}
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.build_duplicate_values", return_value=values) as build,
			patch(f"{MODULE}.frappe.get_doc", return_value=doc) as get_doc,
			patch(f"{MODULE}.frappe.new_doc") as new_doc,
		):
			payload = get_purchase_invoice_editor(duplicate_from="YRP-MPI-2026-00001")

		build.assert_called_once_with("YRP Purchase Invoice", "YRP-MPI-2026-00001")
		get_doc.assert_called_once_with(values)
		new_doc.assert_not_called()
		self.assertEqual(payload["values"]["bill_no"], "BILL-9")
		self.assertEqual(payload["values"]["remarks"], "copied")
		self.assertIsNone(payload["values"]["bill_tracking"])
		self.assertEqual(payload["locked_fields"], [])
		self.assertIsNone(payload["modified"])
		self.assertEqual((doc.inserted, doc.saved), (0, 0))

	def test_editor_masks_supplier_and_duplicate_billing_supplier(self):
		from essdee_yrp.accounts.purchase_invoice_editor import get_purchase_invoice_editor

		doc = FakeInvoice(supplier="SUPPLIER-SECRET", billing_supplier="SUPPLIER-SECRET")

		def apply_field_permissions():
			doc.fieldlevel_permissions_applied += 1
			doc.values["supplier"] = "XXXXXXXX"

		doc.apply_fieldlevel_read_permissions = apply_field_permissions
		with patch(f"{MODULE}.frappe.get_doc", return_value=doc):
			payload = get_purchase_invoice_editor(doc.name)

		self.assertEqual(payload["values"]["supplier"], "XXXXXXXX")
		self.assertEqual(payload["values"]["billing_supplier"], "XXXXXXXX")
		self.assertEqual(doc.fieldlevel_permissions_applied, 1)

	def test_editor_rejects_bill_tracking_with_invoice(self):
		from essdee_yrp.accounts.purchase_invoice_editor import get_purchase_invoice_editor

		bill = FakeBillTracking(purchase_invoice="YRP-MPI-2026-00009")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=bill),
			patch(f"{MODULE}.frappe.new_doc", return_value=FakeInvoice(name=None)),
			self.assertRaises(frappe.ValidationError),
		):
			get_purchase_invoice_editor(bill_tracking=bill.name)

	def test_save_new_uses_authoritative_bill_tracking_prefill(self):
		from essdee_yrp.accounts.purchase_invoice_editor import save_purchase_invoice

		bill = FakeBillTracking()
		doc = FakeInvoice(
			name="YRP-MPI-2026-NEW",
			supplier=None,
			billing_supplier=None,
			bill_no=None,
			bill_date=None,
			bill_tracking=None,
		)
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=bill) as get_doc,
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			patch(
				f"{MODULE}.get_purchase_invoice_workspace",
				return_value={"record": {"name": doc.name}},
			),
		):
			save_purchase_invoice(
				{"bill_tracking": bill.name, "supplier": "XXXXXX", "remarks": "Checked"},
				[],
				[],
			)

		get_doc.assert_called_once_with("YRP Bill Tracking", bill.name, for_update=True)
		self.assertEqual(doc.get("bill_tracking"), bill.name)
		self.assertEqual(doc.get("supplier"), bill.get("supplier"))
		self.assertEqual(doc.get("bill_no"), bill.get("bill_no"))
		self.assertEqual(doc.get("remarks"), "Checked")
		self.assertEqual(doc.inserted, 1)

	def test_save_new_checks_locked_bill_tracking_for_existing_invoice(self):
		from essdee_yrp.accounts.purchase_invoice_editor import save_purchase_invoice

		bill = FakeBillTracking(purchase_invoice="YRP-MPI-2026-00009")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=bill) as get_doc,
			patch(f"{MODULE}.frappe.new_doc") as new_doc,
			self.assertRaises(frappe.ValidationError),
		):
			save_purchase_invoice({"bill_tracking": bill.name}, [], [])

		get_doc.assert_called_once_with("YRP Bill Tracking", bill.name, for_update=True)
		new_doc.assert_not_called()

	def test_command_rejects_disallowed_action(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		for command in ("submit", "delete"):
			with self.subTest(command=command):
				doc = FakeInvoice(docstatus=1, status="Submitted")
				with (
					patch(f"{MODULE}.frappe.get_doc", return_value=doc) as get_doc,
					patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
					patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
					self.assertRaises(frappe.PermissionError),
				):
						execute_purchase_invoice_command(
							doc.name,
							command,
							expected_modified=doc.modified,
						)
				get_doc.assert_called_once_with("YRP Purchase Invoice", doc.name, for_update=True)
				self.assertEqual(doc.checked_permissions, [])

	def test_cancel_checks_timestamp_on_locked_document(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		doc = FakeInvoice(docstatus=1, status="Submitted", modified="2026-10-12 11:00:00")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc) as get_doc,
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=True),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			execute_purchase_invoice_command(
				doc.name,
				"cancel",
				{"cancel_without_cancelling_erp_inv": True},
				expected_modified="2026-10-12 10:00:00",
			)

		get_doc.assert_called_once_with("YRP Purchase Invoice", doc.name, for_update=True)
		self.assertEqual(doc.db_set_calls, [])
		self.assertEqual(doc.cancelled, 0)

	def test_delete_checks_timestamp_on_locked_document(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		doc = FakeInvoice(modified="2026-10-12 11:00:00")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc) as get_doc,
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
			patch(f"{MODULE}.frappe.delete_doc") as delete_doc,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			execute_purchase_invoice_command(
				doc.name,
				"delete",
				expected_modified="2026-10-12 10:00:00",
			)

		get_doc.assert_called_once_with("YRP Purchase Invoice", doc.name, for_update=True)
		delete_doc.assert_not_called()

	def test_command_rejects_missing_expected_modified(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		doc = FakeInvoice()
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
			patch(f"{MODULE}.frappe.delete_doc") as delete_doc,
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Reload the record before making changes",
			),
		):
			execute_purchase_invoice_command(doc.name, "delete")

		delete_doc.assert_not_called()
		self.assertEqual(doc.checked_permissions, [])

	def test_cancel_sets_skip_erp_flag_only_with_erp_invoice(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		for erp_invoice in ("ACC-PINV-1", None):
			with self.subTest(erp_invoice=erp_invoice):
				doc = FakeInvoice(docstatus=1, status="Submitted", erp_inv_name=erp_invoice)
				with (
					patch(f"{MODULE}.frappe.get_doc", return_value=doc),
					patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
					patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=True),
					patch(
						f"{MODULE}.get_purchase_invoice_workspace",
						return_value={"record": {"name": doc.name}},
					),
				):
					execute_purchase_invoice_command(
						doc.name,
						"cancel",
						{"cancel_without_cancelling_erp_inv": True},
						expected_modified=doc.modified,
					)

				self.assertEqual(doc.checked_permissions, ["cancel"])
				self.assertEqual(doc.cancelled, 1)
				if erp_invoice:
					self.assertEqual(
						doc.db_set_calls,
						[("cancel_without_cancelling_erp_inv", 1, {})],
					)
				else:
					self.assertEqual(doc.db_set_calls, [])

	def test_submit_delete_and_amend_use_matching_permissions(self):
		from essdee_yrp.accounts.purchase_invoice_editor import execute_purchase_invoice_command

		draft = FakeInvoice()
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=draft),
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
			patch(
				f"{MODULE}.get_purchase_invoice_workspace",
				return_value={"record": {"name": draft.name}},
			),
		):
			execute_purchase_invoice_command(draft.name, "submit", expected_modified=draft.modified)
		self.assertEqual(draft.checked_permissions, ["submit"])
		self.assertEqual(draft.submitted, 1)

		draft = FakeInvoice()
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=draft),
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
			patch(f"{MODULE}.frappe.delete_doc") as delete_doc,
		):
			result = execute_purchase_invoice_command(
				draft.name,
				"delete",
				expected_modified=draft.modified,
			)
		self.assertEqual(draft.checked_permissions, ["delete"])
		delete_doc.assert_called_once_with("YRP Purchase Invoice", draft.name)
		self.assertEqual(result, {"deleted": True, "record": {"name": draft.name}})

		cancelled = FakeInvoice(
			docstatus=2,
			status="Cancelled",
			essdee_rate_table_source="yrp_grn_v1",
			erp_inv_name="ACC-PINV-1",
			erp_inv_docstatus=2,
		)
		amended = FakeInvoice(
			name="YRP-MPI-2026-00002",
			essdee_rate_table_source=None,
			erp_inv_name=None,
			erp_inv_docstatus=None,
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=cancelled),
			patch(f"{MODULE}.permission_flags", return_value=full_permissions()),
			patch(f"{MODULE}.is_erp_purchase_invoice_available", return_value=False),
			patch(f"{MODULE}.frappe.copy_doc", return_value=amended) as copy_doc,
			patch(
				f"{MODULE}.get_purchase_invoice_workspace",
				return_value={"record": {"name": amended.name}},
			),
		):
			result = execute_purchase_invoice_command(
				cancelled.name,
				"amend",
				expected_modified=cancelled.modified,
			)
		self.assertEqual(cancelled.checked_permissions, ["amend"])
		self.assertEqual(amended.docstatus, 0)
		self.assertEqual(amended.get("status"), "Draft")
		self.assertEqual(amended.get("amended_from"), cancelled.name)
		self.assertIsNone(amended.get("essdee_rate_table_source"))
		self.assertIsNone(amended.get("erp_inv_name"))
		self.assertIsNone(amended.get("erp_inv_docstatus"))
		self.assertEqual(amended.inserted, 1)
		self.assertEqual(result["record"]["name"], amended.name)
		copy_doc.assert_called_once_with(cancelled, ignore_no_copy=False)

	def test_migrated_amendment_uses_desk_no_copy_fields(self):
		from essdee_yrp.accounts.purchase_invoice_editor import _amend_purchase_invoice

		cancelled = frappe.new_doc("YRP Purchase Invoice")
		cancelled.name = "E2E-AHR-PI-MIGRATED"
		cancelled.docstatus = 2
		cancelled.status = "Cancelled"
		cancelled.against = "YRP Work Order"
		cancelled.essdee_rate_table_source = "migrated_v1"
		cancelled.erp_inv_name = "ACC-PINV-E2E-AHR-001"
		cancelled.erp_inv_docstatus = 2
		validated = []

		def validate_before_insert(amended):
			amended.before_validate()
			validated.append(amended)
			return amended

		with (
			patch.object(type(cancelled), "insert", new=validate_before_insert),
			patch(
				"essdee_yrp.overrides.purchase_invoice.build_work_order_invoice_payload"
			) as build_payload,
		):
			amended = _amend_purchase_invoice(cancelled)

		self.assertEqual(validated, [amended])
		self.assertIsNone(amended.essdee_rate_table_source)
		self.assertIsNone(amended.erp_inv_name)
		self.assertIsNone(amended.erp_inv_docstatus)
		self.assertEqual(amended.amended_from, cancelled.name)
		build_payload.assert_not_called()

	def test_amend_rejects_bill_tracking_linked_to_another_invoice(self):
		from essdee_yrp.accounts.purchase_invoice_editor import _amend_purchase_invoice

		cancelled = FakeInvoice(
			docstatus=2,
			status="Cancelled",
			bill_tracking="E2E-AHR-BT-001",
			essdee_rate_table_source="yrp_grn_v1",
		)
		amended = FakeInvoice(
			name="YRP-MPI-2026-00002",
			bill_tracking=cancelled.get("bill_tracking"),
			essdee_rate_table_source=None,
		)
		bill = FakeBillTracking(
			name=cancelled.get("bill_tracking"),
			purchase_invoice="E2E-AHR-PI-OTHER",
		)
		with (
			patch(f"{MODULE}.frappe.copy_doc", return_value=amended),
			patch(f"{MODULE}.frappe.get_doc", return_value=bill) as get_doc,
			self.assertRaisesRegex(frappe.ValidationError, "already linked to an invoice"),
		):
			_amend_purchase_invoice(cancelled)

		get_doc.assert_called_once_with("YRP Bill Tracking", bill.name, for_update=True)
		self.assertEqual(bill.checked_permissions, ["read"])
		self.assertEqual(amended.inserted, 0)

	def test_editor_loads_real_draft(self):
		from essdee_yrp.accounts.purchase_invoice_editor import get_purchase_invoice_editor

		original_user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			invoices = frappe.get_all(
				"YRP Purchase Invoice",
				filters={"docstatus": 0, "against": "Purchase Order"},
				pluck="name",
				limit=1,
			)
			self.assertTrue(invoices, "Expected a draft Purchase Order invoice")
			payload = get_purchase_invoice_editor(invoices[0])
			self.assertTrue(payload["items"])
			self.assertTrue(all(row.get("group_key") for row in payload["items"]))
		finally:
			frappe.db.rollback()
			frappe.set_user(original_user)

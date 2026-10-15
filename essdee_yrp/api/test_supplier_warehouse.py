# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import subprocess
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.supplier_warehouse import get_supplier_warehouse_context


class TestSupplierWarehouseContext(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.user = frappe.session.user
		self.original_company = frappe.defaults.get_user_default("Company", self.user)
		self.addCleanup(frappe.defaults.set_user_default, "company", self.original_company, user=self.user)
		self.company = _make_company("_Test SWH Company")
		frappe.defaults.set_user_default("company", self.company, self.user)
		self.supplier = _make_supplier("_Test SWH Supplier")

	def test_defaults_follow_supplier_warehouse_convention(self):
		context = get_supplier_warehouse_context(self.supplier)

		self.assertIsNone(context["warehouse"])
		self.assertFalse(context["warehouse_exists"])
		defaults = context["defaults"]
		self.assertEqual(defaults["supplier"], self.supplier)
		self.assertEqual(defaults["warehouse_name"], self.supplier)
		self.assertEqual(defaults["company"], self.company)
		self.assertEqual(defaults["is_group"], 0)

	def test_defaults_copy_primary_address(self):
		address = _make_address(self.supplier)
		frappe.db.set_value("Supplier", self.supplier, "supplier_primary_address", address)

		defaults = get_supplier_warehouse_context(self.supplier)["defaults"]

		self.assertEqual(defaults["address_line_1"], "12 Mill Road")
		self.assertEqual(defaults["address_line_2"], "Near Bridge")
		self.assertEqual(defaults["city"], "Tiruppur")
		self.assertEqual(defaults["pin"], "641601")
		self.assertEqual(defaults["phone_no"], "0421000000")
		self.assertEqual(defaults["email_id"], "swh@example.com")

	def test_returns_existing_enabled_warehouse(self):
		warehouse = _make_warehouse(self.supplier, self.company, disabled=0)

		context = get_supplier_warehouse_context(self.supplier)

		self.assertEqual(context["warehouse"], warehouse)
		self.assertTrue(context["warehouse_exists"])

	def test_ignores_disabled_warehouse(self):
		_make_warehouse(self.supplier, self.company, disabled=1)

		context = get_supplier_warehouse_context(self.supplier)

		self.assertIsNone(context["warehouse"])
		self.assertFalse(context["warehouse_exists"])

	def test_supplier_warehouse_uses_exact_typed_name(self):
		warehouse_name = f"  _Test Supplier Warehouse {frappe.generate_hash(length=8)}  "

		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": warehouse_name,
				"supplier": self.supplier,
				"company": self.company,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(warehouse.name, warehouse_name.strip())

	def test_non_supplier_warehouse_keeps_company_suffix(self):
		warehouse_name = f"_Test Company Warehouse {frappe.generate_hash(length=8)}"

		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": warehouse_name,
				"company": self.company,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(warehouse.name, f"{warehouse_name} - _TSWH")

	def test_duplicate_supplier_warehouse_name_fails(self):
		warehouse_name = f"_Test Duplicate Warehouse {frappe.generate_hash(length=8)}"
		values = {
			"doctype": "Warehouse",
			"warehouse_name": warehouse_name,
			"supplier": self.supplier,
			"company": self.company,
		}
		frappe.get_doc(values).insert(ignore_permissions=True)

		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc(values).insert(ignore_permissions=True)

	def test_restricted_user_cannot_see_warehouse_or_address_details(self):
		address = _make_address(self.supplier)
		frappe.db.set_value("Supplier", self.supplier, "supplier_primary_address", address)
		warehouse = _make_warehouse(self.supplier, self.company, disabled=0)
		allowed_warehouse = _make_warehouse(None, self.company, disabled=0)
		user = _make_stock_user()
		add_user_permission("Warehouse", allowed_warehouse, user, ignore_permissions=True)
		allowed_address = _make_address(_make_supplier("_Test SWH Other Supplier"))
		add_user_permission(
			"Address", allowed_address, user, ignore_permissions=True, applicable_for="Address"
		)

		with self.set_user(user):
			self.assertTrue(frappe.get_doc("Supplier", self.supplier).has_permission("read"))
			self.assertFalse(frappe.get_doc("Warehouse", warehouse).has_permission("read"))
			self.assertFalse(frappe.get_doc("Address", address).has_permission("read"))
			context = get_supplier_warehouse_context(self.supplier)

		self.assertTrue(context["warehouse_exists"])
		self.assertIsNone(context["warehouse"])
		for field in ("address_line_1", "address_line_2", "city", "state", "pin", "phone_no"):
			self.assertNotIn(field, context["defaults"])
		self.assertFalse(context["defaults"]["email_id"])

	def test_empty_company_is_omitted_from_route_defaults(self):
		with patch("essdee_yrp.api.supplier_warehouse.frappe.defaults.get_user_default", return_value=None):
			defaults = get_supplier_warehouse_context(self.supplier)["defaults"]

		self.assertNotIn("company", defaults)

	def test_desk_discards_out_of_order_responses(self):
		source = Path(frappe.get_app_path("essdee_yrp", "public", "js", "supplier.js"))
		script = r"""
const fs = require("fs");
let refresh;
const pending = [];
global.__ = (value) => value;
global.frappe = {
	ui: { form: { on: (_doctype, handlers) => { refresh = handlers.refresh; } } },
	call: (_method, args) => new Promise((resolve) => pending.push({ args, resolve })),
	model: { can_create: () => true },
	set_route: () => {},
};
eval(fs.readFileSync(process.argv[1], "utf8"));

(async () => {
	const buttons = new Map();
	const frm = {
		doc: { name: "Supplier A" },
		is_new: () => false,
		add_custom_button: (label, action) => buttons.set(label, action),
		remove_custom_button: (label) => buttons.delete(label),
	};
	refresh(frm);
	frm.doc.name = "Supplier B";
	refresh(frm);
	pending[1].resolve({ message: { warehouse: "Warehouse B", warehouse_exists: true } });
	await Promise.resolve();
	pending[0].resolve({
		message: { warehouse: null, warehouse_exists: false, defaults: { supplier: "Supplier A" } },
	});
	await Promise.resolve();
	if (buttons.size !== 1 || !buttons.has("View Warehouse") || buttons.has("Create Warehouse")) {
		throw new Error(`Unexpected buttons: ${[...buttons.keys()]}`);
	}
})().catch((error) => { console.error(error); process.exit(1); });
"""
		subprocess.run(["node", "-e", script, str(source)], check=True)

	def test_desk_prompts_when_company_has_no_resolved_default(self):
		source = Path(frappe.get_app_path("essdee_yrp", "public", "js", "supplier.js"))
		script = r"""
const fs = require("fs");
let refresh;
let promptCallback;
let resolvedCompany = null;
const newDocuments = [];
global.__ = (value) => value;
global.frappe = {
	ui: { form: { on: (_doctype, handlers) => { refresh = handlers.refresh; } } },
	call: () => Promise.resolve({
		message: { warehouse: null, warehouse_exists: false, defaults: { supplier: "Supplier A" } },
	}),
	model: {
		can_create: () => true,
		with_doctype: () => Promise.resolve(),
		get_default_value: () => resolvedCompany,
	},
	meta: { get_docfield: () => ({ fieldname: "company" }) },
	prompt: (_field, callback) => { promptCallback = callback; },
	new_doc: (doctype, defaults) => newDocuments.push({ doctype, defaults }),
};
eval(fs.readFileSync(process.argv[1], "utf8"));

(async () => {
	const buttons = new Map();
	const frm = {
		doc: { name: "Supplier A" },
		is_new: () => false,
		add_custom_button: (label, action) => buttons.set(label, action),
		remove_custom_button: (label) => buttons.delete(label),
	};
	refresh(frm);
	await Promise.resolve();
	const createWarehouse = buttons.get("Create Warehouse");
	if (!createWarehouse) throw new Error("Create Warehouse was not offered");

	await createWarehouse();
	if (!promptCallback || newDocuments.length) throw new Error("Missing Company did not prompt");
	promptCallback({ company: "Selected Company" });
	if (newDocuments[0].defaults.company !== "Selected Company") {
		throw new Error("Prompted Company was not passed to the new document");
	}

	newDocuments.length = 0;
	resolvedCompany = "Remembered Company";
	await createWarehouse();
	if (newDocuments.length !== 1 || "company" in newDocuments[0].defaults) {
		throw new Error("Resolved default was overwritten instead of being preserved");
	}
})().catch((error) => { console.error(error); process.exit(1); });
"""
		subprocess.run(["node", "-e", script, str(source)], check=True)

	def test_desk_requires_warehouse_create_permission(self):
		source = Path(frappe.get_app_path("essdee_yrp", "public", "js", "supplier.js")).read_text(
			encoding="utf-8"
		)

		self.assertIn('frappe.model.can_create("Warehouse")', source)


def _make_company(name):
	if frappe.db.exists("Company", name):
		return name
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": name,
			"abbr": "_TSWH",
			"country": "India",
			"default_currency": "INR",
		}
	)
	return company.insert(ignore_permissions=True).name


def _make_supplier(name):
	return frappe.get_doc({"doctype": "Supplier", "supplier_name": name}).insert(ignore_permissions=True).name


def _make_address(supplier):
	return (
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": supplier,
				"address_type": "Billing",
				"address_line1": "12 Mill Road",
				"address_line2": "Near Bridge",
				"city": "Tiruppur",
				"state": "Tamil Nadu",
				"country": "India",
				"pincode": "641601",
				"phone": "0421000000",
				"email_id": "swh@example.com",
				"links": [{"link_doctype": "Supplier", "link_name": supplier}],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _make_warehouse(supplier, company, disabled):
	warehouse = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": f"{supplier or 'Allowed'} {frappe.generate_hash(length=8)}",
			"supplier": supplier,
			"company": company,
			"disabled": disabled,
		}
	)
	return warehouse.insert(ignore_permissions=True).name


def _make_stock_user():
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": f"supplier-warehouse-{frappe.generate_hash(length=8)}@example.com",
			"first_name": "Supplier Warehouse User",
			"send_welcome_email": 0,
			"roles": [{"role": "Stock User"}],
		}
	)
	return user.insert(ignore_permissions=True).name

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SUPPLIER = "E2E-AHR Supplier"
DEPARTMENT = "E2E-AHR Dept"
ACCOUNTS_USER = "e2e.ahr.accounts@example.test"
HR_USER = "e2e.ahr.hr@example.test"
HR_MANAGER = "e2e.ahr.hrm@example.test"
PLAIN_USER = "e2e.ahr.plain@example.test"
CANCEL_APPROVED_STATUS = "Cancel Request Approved"
BENCH_DIRECTORY = Path(__file__).resolve().parents[3]

USERS = (
	(ACCOUNTS_USER, "E2E-AHR Accounts", ("Accounts User",)),
	(HR_USER, "E2E-AHR HR", ("HR User",)),
	(HR_MANAGER, "E2E-AHR HR Manager", ("HR Manager",)),
	(PLAIN_USER, "E2E-AHR Plain", ("Desk User",)),
)

frappe = None
frappe_initialized = False


def setup(password: str | None = None) -> dict:
	"""Create the Accounts and HR browser-test principals and masters."""
	password = password or os.environ.get("E2E_PASSWORD", "")
	if not password:
		frappe.throw("A password is required for Accounts and HR browser fixtures")

	_create_supplier()
	frappe.db.commit()
	_create_department()
	frappe.db.commit()
	for email, first_name, roles in USERS:
		_create_user(email, first_name, roles, password)
	frappe.db.commit()
	_add_hr_user_to_department()
	frappe.db.commit()
	return {
		"supplier": SUPPLIER,
		"department": DEPARTMENT,
		"accounts_user": ACCOUNTS_USER,
		"hr_user": HR_USER,
		"hr_manager": HR_MANAGER,
		"plain_user": PLAIN_USER,
	}


def create_linked_draft_probe(bill_tracking: str, name: str) -> str:
	"""Create the linked draft used to verify teardown."""
	if not name.startswith("E2E-AHR-") or frappe.db.exists("YRP Purchase Invoice", name):
		frappe.throw("A new E2E-AHR- Purchase Invoice name is required")
	bill = frappe.get_doc("YRP Bill Tracking", bill_tracking)
	if bill.supplier != SUPPLIER or bill.docstatus != 1:
		frappe.throw(f"Bill Tracking {bill_tracking} is not an active fixture record")
	if bill.purchase_invoice or bill.erp_purchase_invoice:
		frappe.throw(f"Bill Tracking {bill_tracking} is already linked to an invoice")
	doc = frappe.get_doc({
		"doctype": "YRP Purchase Invoice",
		"supplier": bill.supplier,
		"billing_supplier": bill.supplier,
		"bill_no": bill.bill_no,
		"bill_date": bill.bill_date,
		"bill_tracking": bill.name,
		"against": "Purchase Order",
		"posting_date": frappe.utils.nowdate(),
	})
	doc.insert(ignore_permissions=True, set_name=name)
	frappe.db.commit()
	return doc.name


def teardown() -> None:
	"""Remove every record owned by the Accounts and HR browser fixtures."""
	_unlink_fixture_draft_purchase_invoices()
	frappe.db.commit()
	_delete_bill_trackings()
	frappe.db.commit()
	_delete_purchase_invoices()
	frappe.db.commit()
	_delete_fixture_masters()
	frappe.db.commit()


def _create_supplier() -> None:
	if frappe.db.exists("Supplier", SUPPLIER):
		supplier = frappe.get_doc("Supplier", SUPPLIER)
		supplier.disabled = 0
		supplier.save(ignore_permissions=True)
		return
	supplier_group = frappe.get_all(
		"Supplier Group", filters={"is_group": 0}, pluck="name", order_by="name asc", limit=1
	)
	if not supplier_group:
		frappe.throw("An enabled leaf Supplier Group is required for Accounts and HR browser fixtures")
	frappe.get_doc({
		"doctype": "Supplier",
		"name": SUPPLIER,
		"supplier_name": SUPPLIER,
		"supplier_group": supplier_group[0],
		"supplier_type": "Company",
		"disabled": 0,
	}).insert(ignore_permissions=True)


def _create_department() -> None:
	if frappe.db.exists("Department", DEPARTMENT):
		department = frappe.get_doc("Department", DEPARTMENT)
		department.disabled = 0
		department.save(ignore_permissions=True)
		return
	for name in frappe.get_all("Department", filters={"department_name": DEPARTMENT}, pluck="name"):
		frappe.delete_doc("Department", name, force=True, ignore_permissions=True)
	company = frappe.defaults.get_global_default("company")
	if not company:
		frappe.throw("A default Company is required for Accounts and HR browser fixtures")
	frappe.get_doc({
		"doctype": "Department",
		"name": DEPARTMENT,
		"department_name": DEPARTMENT,
		"company": company,
		"disabled": 0,
	}).insert(ignore_permissions=True, set_name=DEPARTMENT)


def _create_user(email: str, first_name: str, roles: tuple[str, ...], password: str) -> None:
	user = frappe.get_doc("User", email) if frappe.db.exists("User", email) else frappe.new_doc("User")
	user.email = email
	user.first_name = first_name
	user.enabled = 1
	user.send_welcome_email = 0
	user.user_type = "System User"
	user.new_password = password
	user.set("roles", [{"role": role} for role in roles])
	previous_in_test = frappe.in_test
	try:
		frappe.in_test = True
		if user.is_new():
			user.insert(ignore_permissions=True)
		else:
			user.save(ignore_permissions=True)
	finally:
		frappe.in_test = previous_in_test
	frappe.clear_cache(user=email)


def _add_hr_user_to_department() -> None:
	department = frappe.get_doc("Department", DEPARTMENT)
	department.set("department_users", [{"user": HR_USER}])
	department.save(ignore_permissions=True)


def _unlink_fixture_draft_purchase_invoices() -> None:
	rows = frappe.get_all(
		"YRP Purchase Invoice",
		filters={"supplier": SUPPLIER, "bill_tracking": ["is", "set"]},
		fields=["name", "docstatus", "bill_tracking"],
	)
	linked_invoices = {row.name: row for row in rows}
	linked_bills = frappe.get_all(
		"YRP Bill Tracking",
		filters={"supplier": SUPPLIER, "purchase_invoice": ["is", "set"]},
		fields=["name", "purchase_invoice"],
	)
	unexpected = [row.name for row in linked_bills if row.purchase_invoice not in linked_invoices]
	if unexpected:
		frappe.throw(f"Refusing to unlink unverified fixture Bill Tracking records: {', '.join(unexpected)}")
	for row in rows:
		_verify_fixture_invoice_link(row)
		frappe.db.set_value("YRP Purchase Invoice", row.name, "bill_tracking", None, update_modified=False)
		frappe.db.set_value("YRP Bill Tracking", row.bill_tracking, "purchase_invoice", None, update_modified=False)


def _verify_fixture_invoice_link(row) -> None:
	if row.docstatus != 0:
		frappe.throw(f"Refusing to unlink non-draft fixture Purchase Invoice {row.name}")
	bill = frappe.db.get_value(
		"YRP Bill Tracking",
		row.bill_tracking,
		["supplier", "purchase_invoice"],
		as_dict=True,
	)
	if not bill or bill.supplier != SUPPLIER or bill.purchase_invoice != row.name:
		frappe.throw(f"Refusing to unlink mismatched fixture Purchase Invoice {row.name}")


def _delete_bill_trackings() -> None:
	names = frappe.get_all(
		"YRP Bill Tracking", filters={"supplier": SUPPLIER}, pluck="name", order_by="creation desc"
	)
	original_user = frappe.session.user
	try:
		for name in names:
			_cancel_bill_tracking(name)
		for name in names:
			if frappe.db.exists("YRP Bill Tracking", name):
				frappe.delete_doc("YRP Bill Tracking", name, force=True, ignore_permissions=True)
	finally:
		frappe.set_user(original_user)


def _cancel_bill_tracking(name: str) -> None:
	docstatus = frappe.db.get_value("YRP Bill Tracking", name, "docstatus")
	if docstatus != 1:
		return
	if not frappe.db.exists("User", HR_USER):
		frappe.throw(f"Cannot cancel {name}: fixture HR user does not exist")
	frappe.db.set_value("YRP Bill Tracking", name, "form_status", CANCEL_APPROVED_STATUS)
	frappe.set_user(HR_USER)
	doc = frappe.get_doc("YRP Bill Tracking", name)
	doc.cancel_reason = "Automated Accounts and HR fixture teardown"
	doc.flags.ignore_permissions = True
	doc.cancel()


def _delete_purchase_invoices() -> None:
	rows = frappe.get_all(
		"YRP Purchase Invoice",
		filters={"supplier": SUPPLIER},
		fields=["name", "docstatus"],
		order_by="creation desc",
	)
	invalid = [row.name for row in rows if row.docstatus != 0]
	if invalid:
		frappe.throw(f"Refusing to delete non-draft fixture Purchase Invoices: {', '.join(invalid)}")
	for row in rows:
		frappe.delete_doc("YRP Purchase Invoice", row.name, force=True, ignore_permissions=True)


def _delete_fixture_masters() -> None:
	for email, _first_name, _roles in USERS:
		_delete_attachments("User", email)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		_delete_fixture_contacts(email)
	for department in frappe.get_all("Department", filters={"department_name": DEPARTMENT}, pluck="name"):
		_delete_attachments("Department", department)
		frappe.delete_doc("Department", department, force=True, ignore_permissions=True)
	_delete_attachments("Supplier", SUPPLIER)
	if frappe.db.exists("Supplier", SUPPLIER):
		frappe.delete_doc("Supplier", SUPPLIER, force=True, ignore_permissions=True)


def _delete_fixture_contacts(email: str) -> None:
	contacts = frappe.get_all("Contact", filters={"email_id": email}, pluck="name")
	for contact in contacts:
		_delete_attachments("Contact", contact)
		frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)


def _delete_attachments(doctype: str, name: str) -> None:
	files = frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name}, pluck="name"
	)
	for file_name in files:
		frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)


def _connect(site: str) -> None:
	global frappe, frappe_initialized

	sys.path.insert(0, str(BENCH_DIRECTORY / "apps" / "frappe"))
	os.chdir(BENCH_DIRECTORY / "sites")
	import frappe as frappe_module

	frappe = frappe_module
	frappe.init(site=site, sites_path=str(BENCH_DIRECTORY / "sites"))
	frappe_initialized = True
	frappe.connect()


def _arguments():
	parser = argparse.ArgumentParser()
	parser.add_argument("--site", required=True)
	parser.add_argument("function", choices=("setup", "teardown", "create_linked_draft_probe"))
	parser.add_argument("--kwargs", default="{}")
	return parser.parse_args()


def main() -> None:
	arguments = _arguments()
	kwargs = json.loads(arguments.kwargs)
	if not isinstance(kwargs, dict):
		raise ValueError("--kwargs must decode to a JSON object")
	try:
		_connect(arguments.site)
		functions = {
			"setup": setup,
			"teardown": teardown,
			"create_linked_draft_probe": create_linked_draft_probe,
		}
		result = functions[arguments.function](**kwargs)
		frappe.db.commit()
		print(json.dumps(result, default=str))
	except Exception:
		if frappe_initialized and getattr(frappe.local, "db", None):
			frappe.db.rollback()
		raise
	finally:
		if frappe_initialized:
			frappe.destroy()


if __name__ == "__main__":
	main()

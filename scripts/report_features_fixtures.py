#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

REPORT_USER_A = "e2e.report.a@example.test"
REPORT_USER_B = "e2e.report.b@example.test"
REPORT_ROLES = ("Stock User", "Purchase User", "Transaction User", "Cutting User")
BENCH_DIRECTORY = Path(__file__).resolve().parents[3]

try:
	import frappe
except ModuleNotFoundError:
	frappe = None
frappe_initialized = False


def setup(password: str | None = None, restrict_item: bool = True) -> dict:
	"""Create the two browser-test report users."""

	password = password or os.environ.get("E2E_PASSWORD", "")
	if not password:
		frappe.throw("A password is required for report feature browser fixtures")
	_validate_roles()
	allowed_item, denied_item, stock_date = _permission_items()
	_create_user(REPORT_USER_A, "E2E Report A", password)
	_create_user(REPORT_USER_B, "E2E Report B", password)
	if restrict_item:
		_create_item_permission(REPORT_USER_A, allowed_item)
	else:
		_delete_user_permissions(REPORT_USER_A)
	frappe.db.commit()
	return {
		"user_a": REPORT_USER_A,
		"user_b": REPORT_USER_B,
		"allowed_item": allowed_item,
		"denied_item": denied_item,
		"stock_date": stock_date,
		**_cutting_date_range(),
	}


def teardown() -> None:
	"""Remove report jobs, layouts, and users owned by this fixture."""

	for email in (REPORT_USER_A, REPORT_USER_B):
		_delete_owned_records(email)
		_delete_user_permissions(email)
		_delete_contacts(email)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()


def restrict_user_a() -> None:
	"""Add an Item User Permission so user A's existing report results expire."""

	allowed_item, _denied_item, _stock_date = _permission_items()
	_create_item_permission(REPORT_USER_A, allowed_item)
	frappe.db.commit()


def clear_user_a_restrictions() -> None:
	"""Remove user A's User Permissions."""

	_delete_user_permissions(REPORT_USER_A)
	frappe.clear_cache(user=REPORT_USER_A)
	frappe.db.commit()


def _validate_roles() -> None:
	missing = [role for role in REPORT_ROLES if not frappe.db.exists("Role", role)]
	if missing:
		frappe.throw(f"Missing report fixture roles: {', '.join(missing)}")


def _create_user(email: str, first_name: str, password: str) -> None:
	user = frappe.get_doc("User", email) if frappe.db.exists("User", email) else frappe.new_doc("User")
	user.email = email
	user.first_name = first_name
	user.enabled = 1
	user.send_welcome_email = 0
	user.user_type = "System User"
	user.new_password = password
	user.set("roles", [{"role": role} for role in REPORT_ROLES])
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


def _permission_items() -> tuple[str, str, str]:
	ledger_items = frappe.db.sql(
		"""select ledger.item, max(ledger.posting_date) as posting_date
		from `tabYRP Stock Ledger Entry` ledger
		inner join `tabItem` item on item.name = ledger.item
		where ledger.is_cancelled = 0
			and item.is_stock_item = 1
			and item.name not like '\\_Test%'
			and (coalesce(item.variant_of, '') != '' or coalesce(item.has_variants, 0) = 0)
		group by ledger.item
		order by posting_date desc, ledger.item
		limit 2""",
		as_dict=True,
	)
	if len(ledger_items) < 2:
		frappe.throw("Two stock Items with YRP ledger entries are required for report feature fixtures")
	return ledger_items[0].item, ledger_items[1].item, str(ledger_items[0].posting_date)


def _create_item_permission(email: str, item: str) -> None:
	_delete_user_permissions(email)
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": email,
			"allow": "Item",
			"for_value": item,
			"apply_to_all_doctypes": 1,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(user=email)


def _cutting_date_range() -> dict:
	dates = frappe.get_all(
		"SD YRP Cutting LaySheet",
		filters={"status": "Label Printed", "bundle_generated_date": ("is", "set")},
		pluck="bundle_generated_date",
		order_by="bundle_generated_date asc",
		limit_page_length=0,
	)
	to_date = dates[-1] if dates else ""
	return {
		"cutting_from_date": str(to_date - timedelta(days=11) if to_date else ""),
		"cutting_to_date": str(to_date),
	}


def _delete_user_permissions(email: str) -> None:
	for name in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
		frappe.delete_doc("User Permission", name, force=True, ignore_permissions=True)


def _delete_owned_records(email: str) -> None:
	for doctype in ("YRP Report Job", "YRP User Report Layout"):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, filters={"owner": email}, pluck="name"):
			_delete_attachments(doctype, name)
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)


def _delete_contacts(email: str) -> None:
	for name in frappe.get_all("Contact", filters={"email_id": email}, pluck="name"):
		_delete_attachments("Contact", name)
		frappe.delete_doc("Contact", name, force=True, ignore_permissions=True)


def _delete_attachments(doctype: str, name: str) -> None:
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name},
		pluck="name",
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
	parser.add_argument("function", choices=("setup", "teardown", "restrict_user_a", "clear_user_a_restrictions"))
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
			"restrict_user_a": restrict_user_a,
			"clear_user_a_restrictions": clear_user_a_restrictions,
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

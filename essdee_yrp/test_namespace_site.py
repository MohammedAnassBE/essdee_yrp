"""Combined-site integration contract for the YRP/SD YRP namespace."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase


APP_SPECS = (
	("yrp", {"YRP", "YRP Stock"}, "YRP "),
	("essdee_yrp", {"Essdee YRP"}, "SD YRP "),
)
LINK_FIELD_TYPES = {"Link", "Table", "Table MultiSelect"}
CUSTOM_MODULES = {"YRP", "YRP Stock", "Essdee YRP"}
CUSTOM_HOOK_PATH = re.compile(
	r"^(?:yrp|essdee_yrp)(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
)


def _owned_metadata(record_type: str):
	for app_name, modules, prefix in APP_SPECS:
		root = Path(frappe.get_app_path(app_name))
		for path in root.rglob("*.json"):
			try:
				data = json.loads(path.read_text())
			except (OSError, UnicodeDecodeError, json.JSONDecodeError):
				continue
			if not isinstance(data, dict):
				continue
			if data.get("doctype") != record_type or data.get("module") not in modules:
				continue
			name = data.get("name")
			if record_type == "Report":
				name = data.get("report_name") or name
			if name:
				yield app_name, prefix, name, data


class TestCombinedSiteNamespace(IntegrationTestCase):
	def test_approved_app_stack_is_installed_without_the_retired_ewaybill_app(self):
		installed = set(frappe.get_installed_apps())
		self.assertTrue(
			{"frappe", "erpnext", "yrp", "essdee_yrp", "india_compliance"}
			<= installed
		)
		self.assertNotIn("yrp_ewaybill_api", installed)

	def test_all_owned_doctypes_reports_controllers_and_tables_are_synced(self):
		counts = {"DocType": 0, "Report": 0}
		for record_type in counts:
			for _app_name, prefix, name, source in _owned_metadata(record_type):
				counts[record_type] += 1
				with self.subTest(record_type=record_type, name=name):
					self.assertTrue(name.startswith(prefix))
					self.assertTrue(frappe.db.exists(record_type, name))
					self.assertEqual(
						frappe.db.get_value(record_type, name, "module"),
						source["module"],
					)
					if record_type == "DocType":
						meta = frappe.get_meta(name, cached=False)
						self.assertEqual(meta.name, name)
						self.assertIsNotNone(get_controller(name))
						if not source.get("issingle"):
							self.assertTrue(frappe.db.table_exists(name, cached=False))
					elif source.get("ref_doctype"):
						self.assertTrue(
							frappe.db.exists("DocType", source["ref_doctype"]),
							source["ref_doctype"],
						)

		self.assertEqual(counts, {"DocType": 327, "Report": 33})

	def test_old_custom_identities_and_orphan_tables_are_absent(self):
		for record_type in ("DocType", "Report"):
			for _app_name, prefix, name, _source in _owned_metadata(record_type):
				old_name = name.removeprefix(prefix)
				with self.subTest(record_type=record_type, old_name=old_name):
					old_module = frappe.db.get_value(record_type, old_name, "module")
					self.assertNotIn(old_module, CUSTOM_MODULES)
					if record_type == "DocType" and not old_module:
						self.assertFalse(
							frappe.db.table_exists(old_name, cached=False),
							f"Orphan table remains for {old_name}",
						)

	def test_every_custom_hook_callable_resolves(self):
		paths = set()

		def collect(value):
			if isinstance(value, str):
				if CUSTOM_HOOK_PATH.fullmatch(value) and not value.endswith((".js", ".css")):
					paths.add(value)
			elif isinstance(value, dict):
				for key, child in value.items():
					collect(key)
					collect(child)
			elif isinstance(value, (list, tuple, set)):
				for child in value:
					collect(child)

		for module_name in ("yrp.hooks", "essdee_yrp.hooks"):
			module = importlib.import_module(module_name)
			for key, value in vars(module).items():
				if not key.startswith("_"):
					collect(value)

		self.assertGreaterEqual(len(paths), 100)
		for path in sorted(paths):
			with self.subTest(path=path):
				self.assertTrue(callable(frappe.get_attr(path)), path)

	def test_every_owned_link_and_child_table_target_resolves(self):
		for _app_name, _prefix, name, _source in _owned_metadata("DocType"):
			meta = frappe.get_meta(name, cached=False)
			for field in meta.fields:
				if field.fieldtype not in LINK_FIELD_TYPES or not field.options:
					continue
				with self.subTest(doctype=name, fieldname=field.fieldname):
					self.assertTrue(
						frappe.db.exists("DocType", field.options),
						f"Missing target {field.options}",
					)

	def test_erpnext_and_custom_business_doctypes_coexist(self):
		for standard_name, standard_module, custom_name, custom_module in (
			("Supplier", "Buying", "YRP Supplier", "YRP"),
			("Item", "Stock", "YRP Item", "YRP"),
			("Warehouse", "Stock", "YRP Warehouse", "YRP"),
			("Purchase Invoice", "Accounts", "YRP Purchase Invoice", "YRP"),
			("Work Order", "Manufacturing", "YRP Work Order", "YRP"),
		):
			with self.subTest(standard=standard_name, custom=custom_name):
				self.assertEqual(
					frappe.db.get_value("DocType", standard_name, "module"),
					standard_module,
				)
				self.assertEqual(
					frappe.db.get_value("DocType", custom_name, "module"),
					custom_module,
				)

		self.assertEqual(
			frappe.db.get_value("DocType", "SD YRP Lot", "module"),
			"Essdee YRP",
		)
		self.assertFalse(frappe.db.exists("DocType", "Lot"))
		self.assertTrue(frappe.db.exists("DocType", "YRP UI Layout"))
		self.assertTrue(frappe.db.exists("DocType", "YRP YRP Settings"))
		self.assertFalse(frappe.db.exists("DocType", "YRP Settings"))

	def test_real_crud_child_link_and_submit_cancel_lifecycle(self):
		suffix = frappe.generate_hash(length=10)
		department_name = f"_Test Namespace Department {suffix}"
		action_name = f"_Test Namespace Action {suffix}"
		term_name = f"_Test Namespace Term {suffix}"

		department = frappe.get_doc(
			{
				"doctype": "YRP Department",
				"department_name": department_name,
				"department_users": [{"user": "Administrator"}],
			}
		).insert()
		self.assertEqual(department.department_users[0].parenttype, "YRP Department")
		self.assertEqual(
			department.department_users[0].doctype,
			"YRP Department User",
		)

		action = frappe.get_doc(
			{
				"doctype": "SD YRP Action",
				"__newname": action_name,
				"department": department.name,
				"lead_time": 2,
			}
		).insert()
		self.assertEqual(action.department, department.name)
		action.lead_time = 5
		action.save()
		self.assertEqual(
			frappe.db.get_value("SD YRP Action", action.name, "lead_time"),
			5,
		)

		term = frappe.get_doc(
			{
				"doctype": "YRP Production Term",
				"term_name": term_name,
				"production_term_details": [{"term": "Namespace lifecycle test"}],
			}
		).insert()
		term.submit()
		self.assertEqual(term.docstatus, 1)
		self.assertEqual(term.production_term_details[0].parenttype, "YRP Production Term")
		self.assertEqual(
			term.production_term_details[0].doctype,
			"YRP Production Term Detail",
		)
		term.cancel()
		self.assertEqual(term.docstatus, 2)

		frappe.delete_doc("SD YRP Action", action.name, force=True)
		frappe.delete_doc("YRP Department", department.name, force=True)

	def test_permissions_reports_and_india_compliance_are_live(self):
		self.assertTrue(
			frappe.has_permission("YRP Department", "create", user="Administrator")
		)
		self.assertFalse(frappe.has_permission("YRP Department", "create", user="Guest"))
		self.assertFalse(
			frappe.has_permission("SD YRP Product Season", "read", user="Guest")
		)

		from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_pending_report.sd_yrp_work_order_pending_report import (
			execute as execute_sd_yrp_report,
		)
		from yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance import (
			execute as execute_yrp_report,
		)

		stock_sample = frappe.get_all(
			'YRP Stock Ledger Entry',
			filters={"docstatus": ["<", 2], "is_cancelled": 0},
			fields=["item", "warehouse", "posting_date"],
			order_by="posting_date desc",
			limit=1,
		)[0]
		# The production dataset exceeds the report's deliberate 500k-row safety
		# limit. Exercise the live report with one real migrated stock bucket rather
		# than treating an intentionally rejected unbounded query as a namespace
		# failure.
		yrp_columns, yrp_rows = execute_yrp_report(
			{
				"item": stock_sample.item,
				"warehouse": stock_sample.warehouse,
				"from_date": stock_sample.posting_date,
				"to_date": stock_sample.posting_date,
			}
		)
		self.assertTrue(yrp_columns)
		self.assertIsInstance(yrp_rows, list)
		production_order = frappe.get_all(
			'YRP Production Order', pluck="name", order_by="modified desc", limit=1
		)[0]
		sd_result = execute_sd_yrp_report({"production_order": production_order})
		self.assertTrue(sd_result[0])
		self.assertIsInstance(sd_result[1], list)

		self.assertTrue(frappe.get_meta("Delivery Note").has_field("ewaybill"))
		self.assertFalse(frappe.db.exists("DocType", "YRP E-Waybill Settings"))


if __name__ == "__main__":
	import unittest

	unittest.main()

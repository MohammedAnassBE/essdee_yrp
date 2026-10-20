from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cut_panel_store.report_workspace import get_cut_bundle_balance


MODULE = "essdee_yrp.cut_panel_store.report_workspace"


class TestCutPanelStoreReports(UnitTestCase):
	def _permissions(self, doctype, ptype="read", **_kwargs):
		return doctype == "SD YRP Cut Bundle Movement Ledger" and ptype in {"read", "report"}

	def test_cut_bundle_balance_requires_ledger_read_and_report_permissions(self):
		for denied_type in ("read", "report"):
			def permission(doctype, ptype="read", **_kwargs):
				return doctype == "SD YRP Cut Bundle Movement Ledger" and ptype != denied_type

			with (
				patch(f"{MODULE}.frappe.has_permission", side_effect=permission),
				patch(f"{MODULE}._execute_cut_bundle_balance") as execute,
				self.assertRaises(frappe.PermissionError),
			):
				get_cut_bundle_balance()
			execute.assert_not_called()

	def test_cut_bundle_balance_checks_the_report_record_permission(self):
		report = MagicMock()
		report.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=self._permissions),
			patch(f"{MODULE}.frappe.get_doc", return_value=report),
			patch(f"{MODULE}._execute_cut_bundle_balance") as execute,
			self.assertRaises(frappe.PermissionError),
		):
			get_cut_bundle_balance()
		report.check_permission.assert_called_once_with("read")
		execute.assert_not_called()

	def test_cut_bundle_balance_accepts_only_lot_and_supplier_filters(self):
		report = MagicMock()
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=self._permissions),
			patch(f"{MODULE}.frappe.get_doc", return_value=report),
			patch(f"{MODULE}._execute_cut_bundle_balance", return_value=([], [])) as execute,
		):
			get_cut_bundle_balance({"lot": "LOT-1", "supplier": "SUP-1"})

		execute.assert_called_once_with({"lot": "LOT-1", "supplier": "SUP-1"})

		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=self._permissions),
			patch(f"{MODULE}.frappe.get_doc", return_value=report),
			self.assertRaises(frappe.ValidationError),
		):
			get_cut_bundle_balance({"warehouse": "CUT-STORE"})

	def test_cut_bundle_balance_returns_stable_columns_and_positive_rows(self):
		report = MagicMock()
		columns = [
			{"fieldname": "name", "label": "Unsafe", "fieldtype": "HTML", "options": "Secret"},
			{"fieldname": "qty", "label": "Wrong", "fieldtype": "Data"},
			{"fieldname": "private_value", "label": "Private"},
		]
		rows = [
			{"name": "CBML-1", "lot": "LOT-1", "supplier": "SUP-1", "supplier_name": "Supplier One", "item": "ITEM-1", "lay_no": 2, "bundle_no": 4, "size": "M", "colour": "Navy", "shade": "A", "panel": "Front", "qty": 8, "private_value": "secret"},
			{"name": "CBML-2", "lot": "LOT-1", "qty": 0},
			{"name": "CBML-3", "lot": "LOT-1", "qty": -2},
		]
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=self._permissions),
			patch(f"{MODULE}.frappe.get_doc", return_value=report),
			patch(f"{MODULE}._execute_cut_bundle_balance", return_value=(columns, rows)),
		):
			payload = get_cut_bundle_balance()

		self.assertEqual(
			[column["fieldname"] for column in payload["columns"]],
			[
				"lot",
				"supplier",
				"supplier_name",
				"item",
				"lay_no",
				"bundle_no",
				"size",
				"colour",
				"shade",
				"panel",
				"qty",
			],
		)
		self.assertEqual(payload["columns"][0]["fieldtype"], "Link")
		self.assertEqual(payload["columns"][0]["options"], "SD YRP Lot")
		self.assertEqual(
			payload["result"],
			[
				{
					key: rows[0].get(key)
					for key in ["name", *[column["fieldname"] for column in payload["columns"]]]
				}
			],
		)
		self.assertNotIn("private_value", payload["result"][0])
		self.assertEqual(payload["summary"], {"rows": 1, "quantity": 8})

import csv
import io

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.report_export import export_report_rows, export_web_report, get_export_permission


def read_csv_response():
	content = frappe.response["filecontent"].decode("utf-8")
	return list(csv.reader(io.StringIO(content)))


class TestReportExport(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_rendered_rows_export_as_csv_with_filters(self):
		export_report_rows(
			"Size-wise", [["Lot", "Qty"], ["L-1", 4]], doctype="SD YRP Lot", file_format_type="CSV",
			include_filters=1, applied_filters={"Lot": "L-1"}, csv_quoting=0,
		)
		self.assertEqual(frappe.response["filename"], "Size-wise.csv")
		self.assertEqual(read_csv_response(), [["Lot", "L-1"], [], ["Lot", "Qty"], ["L-1", "4"]])

	def test_rendered_rows_export_as_excel(self):
		export_report_rows("Size-wise", [["Lot"], ["L-1"]], report_key="planning-size-wise-stock")
		self.assertEqual(frappe.response["filename"], "Size-wise.xlsx")
		self.assertTrue(frappe.response["filecontent"].startswith(b"PK"))

	def test_desk_report_export_keeps_only_picked_columns(self):
		columns = [{"kind": "base", "fieldname": "item", "label": "Item"}, {"kind": "base", "fieldname": "supplier_name", "label": "Vendor"}]
		export_web_report("purchase-order-itemwise", columns, filters={"open_status": "Open"}, file_format_type="CSV")
		self.assertEqual(read_csv_response()[0], ["Item", "Vendor"])

	def test_unknown_desk_column_fails_loudly(self):
		with self.assertRaises(frappe.ValidationError):
			export_web_report("purchase-order-itemwise", [{"kind": "base", "fieldname": "missing_column"}], file_format_type="CSV")

	def test_guest_cannot_export(self):
		frappe.set_user("Guest")
		self.assertFalse(get_export_permission(doctype="SD YRP Lot"))
		with self.assertRaises(frappe.PermissionError):
			export_report_rows("Lots", [["Lot"]], doctype="SD YRP Lot")

	def test_rejects_unsupported_formats_and_nested_cells(self):
		with self.assertRaises(frappe.ValidationError):
			export_report_rows("Lots", [["Lot"]], doctype="SD YRP Lot", file_format_type="PDF")
		with self.assertRaises(frappe.ValidationError):
			export_report_rows("Lots", [[{"bad": 1}]], doctype="SD YRP Lot")

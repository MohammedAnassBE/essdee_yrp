import csv
import io
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.report_export import (
	export_report_rows,
	export_web_report,
	get_export_permission,
	keep_visible_rows,
)


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

	def test_background_sized_export_reads_the_finished_report_job(self):
		columns = [{"kind": "base", "fieldname": "dc_number", "label": "DC"}]
		filters = {"from_date": "2024-01-01", "to_date": "2026-10-23"}
		finished = {
			"job": {"name": "JOB-1", "status": "Completed"},
			"columns": [{"fieldname": "dc_number", "label": "DC", "fieldtype": "Data"}],
			"result": [{"dc_number": "DC-1"}],
		}
		with (
			patch("essdee_yrp.report_export.run_query_report", side_effect=AssertionError("re-ran in request")),
			patch("essdee_yrp.report_export.run_web_report", return_value=finished) as run,
		):
			export_web_report("dc-report", columns, filters=filters, file_format_type="CSV")
			self.assertEqual(read_csv_response(), [["DC"], ["DC-1"]])
			run.return_value = {"job": {"name": "JOB-2", "status": "Queued"}, "columns": [], "result": []}
			with self.assertRaises(frappe.ValidationError):
				export_web_report("dc-report", columns, filters=filters, file_format_type="CSV")

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

	def test_visible_rows_keep_inline_filtered_rows_and_rebuild_the_total(self):
		columns = [{"fieldname": "item", "fieldtype": "Data"}, {"fieldname": "qty", "fieldtype": "Float"}]
		rows = [{"item": "A", "qty": 2}, {"item": "B", "qty": 5}, {"item": "C", "qty": 7}, ["Total", 14]]
		data = frappe._dict(columns=columns, result=list(rows), add_total_row=1)
		keep_visible_rows(data, [2, 0, 9])
		self.assertEqual(data.result[:2], [rows[2], rows[0]])
		self.assertEqual(data.result[2][0], "Total")
		self.assertEqual(data.result[2][1], 9)
		unfiltered = frappe._dict(columns=columns, result=list(rows), add_total_row=1)
		keep_visible_rows(unfiltered, None)
		self.assertEqual(unfiltered.result, rows)
		with self.assertRaises(frappe.ValidationError):
			keep_visible_rows(unfiltered, ["1"])

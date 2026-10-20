"""Regression tests for the saved purchase/bill reports and IO page projection."""

import importlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

REPORTS = Path(frappe.get_app_path("essdee_yrp", "essdee_yrp", "report"))


def purchase_report():
	name = "essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order.sd_yrp_purchase_order"
	assert importlib.util.find_spec(name) is not None, "The legacy PO projection is missing"
	return importlib.import_module(name)


class TestWorker2DeskReports(unittest.TestCase):
	def insert(self, doctype, **values):
		name = values.pop("name", None) or "W2-" + frappe.generate_hash(length=10)
		doc = frappe.get_doc(dict(doctype=doctype, name=name, **values))
		doc.db_insert()
		return doc.name

	def test_purchase_projection_restores_legacy_dates_and_fulfillment_values(self):
		project = purchase_report().legacy_rows
		rows = project(
			[
				frappe._dict(
					name="PO-1",
					docstatus=1,
					supplier="Mill",
					transaction_date="2026-09-01",
					open_status="Open",
					status="To Receive",
					yrp_fulfillment_status="Partially Received",
				),
				frappe._dict(
					name="PO-2",
					docstatus=1,
					supplier="Mill",
					transaction_date="2026-09-02",
					open_status="Close",
					status="Completed",
					yrp_fulfillment_status="Received",
				),
				frappe._dict(
					name="PO-3",
					docstatus=0,
					supplier="Mill",
					transaction_date="2026-09-03",
					open_status="Open",
					status="Pending Approval",
					yrp_fulfillment_status="Draft",
				),
			]
		)
		self.assertEqual(
			rows,
			[
				{
					"name": "PO-1",
					"docstatus": 1,
					"supplier": "Mill",
					"po_date": "2026-09-01",
					"open_status": "Open",
					"status": "Partially Delivered",
				},
				{
					"name": "PO-2",
					"docstatus": 1,
					"supplier": "Mill",
					"po_date": "2026-09-02",
					"open_status": "Closed",
					"status": "Delivered",
				},
				{
					"name": "PO-3",
					"docstatus": 0,
					"supplier": "Mill",
					"po_date": "2026-09-03",
					"open_status": "Open",
					"status": "Pending Approval",
				},
			],
		)

	def test_purchase_saved_open_filter_and_status_filter_use_fulfillment(self):
		point = "worker2_purchase"
		frappe.db.savepoint(point)
		try:
			supplier = "W2-" + frappe.generate_hash(length=10)
			for status, fulfillment, opened, docstatus in [
				("To Receive", "Ordered", "Open", 1),
				("To Receive", "Partially Received", "Open", 1),
				("Completed", "Received", "Close", 1),
				("Pending Approval", "Draft", "Open", 0),
			]:
				self.insert(
					"Purchase Order",
					supplier=supplier,
					status=status,
					yrp_fulfillment_status=fulfillment,
					open_status=opened,
					docstatus=docstatus,
					transaction_date="2026-09-01",
				)
			columns, rows = purchase_report().execute({"supplier": supplier})
			self.assertEqual(
				[c["label"] for c in columns], ["ID", "Supplier", "PO Date", "Open Status", "Status"]
			)
			self.assertEqual(
				[r["status"] for r in rows], ["Ordered", "Partially Delivered", "Pending Approval"]
			)
			self.assertEqual(
				len(purchase_report().execute({"supplier": supplier, "status": "Partially Delivered"})[1]), 1
			)
			self.assertEqual(len(purchase_report().execute({"supplier": supplier, "status": "Draft"})[1]), 0)
			self.assertEqual(
				len(purchase_report().execute({"supplier": supplier, "status": "Pending Approval"})[1]), 1
			)
			self.assertEqual(
				len(purchase_report().execute({"supplier": supplier, "po_date": "2026-09-02"})[1]), 0
			)
			self.assertEqual(len(purchase_report().execute({"supplier": supplier, "docstatus": 0})[1]), 1)
			# Resolve the dated alias through Desk's real Custom Report dispatcher.
			# Only metadata reads use staged JSON; no Report records are imported.
			from frappe.desk.query_report import get_report_doc, get_report_result

			get_doc = frappe.get_doc
			staged = {}
			for slug in ("sd_yrp_purchase_order", "sd_yrp_purchase_order___13.02.2026"):
				doc = get_doc(json.loads((REPORTS / slug / (slug + ".json")).read_text()))
				staged[doc.name] = doc

			def staged_report(*args, **kwargs):
				if len(args) == 2 and args[0] == "Report" and args[1] in staged:
					return staged[args[1]]
				return get_doc(*args, **kwargs)

			with patch.object(frappe, "get_doc", side_effect=staged_report):
				alias = get_report_doc("SD YRP PURCHASE ORDER - 13.02.2026")
				alias.disable_prepared_report_automation = 1
				alias_columns, alias_rows = get_report_result(alias, {"supplier": supplier})[:2]
			self.assertEqual(alias_columns, columns)
			self.assertEqual(alias_rows, rows)
		finally:
			frappe.db.rollback(save_point=point)

	def test_purchase_status_filter_matches_display_with_blank_fulfillment(self):
		point = "worker2_status_fallback"
		frappe.db.savepoint(point)
		try:
			supplier = "W2-" + frappe.generate_hash(length=10)
			expected = {}
			for status, fulfillment, displayed in [
				("Cancelled", "", "Cancelled"),
				("Draft", None, "Draft"),
				("Delivered", "", "Delivered"),
				("To Receive", "Received", "Delivered"),
				("Pending Approval", "Draft", "Pending Approval"),
				("Cancelled", "Ordered", "Ordered"),
			]:
				name = self.insert(
					"Purchase Order",
					supplier=supplier,
					status=status,
					yrp_fulfillment_status=fulfillment,
					open_status="Open",
					docstatus=0,
					transaction_date="2026-09-01",
				)
				expected.setdefault(displayed, []).append(name)
			for status, names in expected.items():
				with self.subTest(status=status):
					rows = purchase_report().execute({"supplier": supplier, "status": status})[1]
					self.assertEqual([row["name"] for row in rows], names)
					self.assertTrue(all(row["status"] == status for row in rows))
		finally:
			frappe.db.rollback(save_point=point)

	def test_bill_builder_counts_assigned_department_in_previous_calendar_month(self):
		from frappe.desk import reportview

		point = "worker2_bills"
		frappe.db.savepoint(point)
		try:
			department = "W2-" + frappe.generate_hash(length=10)
			first_this_month = frappe.utils.get_first_day(frappe.utils.today())
			last_month = frappe.utils.add_days(first_this_month, -1)
			for bill_date, form_status, docstatus in [
				(last_month, "Assigned", 1),
				(last_month, "Open", 0),
				(last_month, "Closed", 1),
				(last_month, "Assigned", 2),
				(first_this_month, "Assigned", 1),
			]:
				self.insert(
					"YRP Bill Tracking",
					assigned_to=department,
					department="Other",
					bill_date=bill_date,
					form_status=form_status,
					docstatus=docstatus,
				)
			settings = json.loads(
				json.loads(
					(
						REPORTS
						/ "sd_yrp_previous_month_pending_bills___departmentwise"
						/ "sd_yrp_previous_month_pending_bills___departmentwise.json"
					).read_text()
				)["json"]
			)
			args = frappe._dict(
				doctype="YRP Bill Tracking",
				fields=["assigned_to"],
				filters=[f[:4] for f in settings["filters"]] + [["assigned_to", "=", department]],
				group_by=settings["group_by"]["group_by"],
				aggregate_function="count",
				aggregate_on_doctype="YRP Bill Tracking",
				aggregate_on_field="name",
				order_by="_aggregate_column desc",
				page_length=20,
				start=0,
			)
			reportview.validate_args(args)
			self.assertEqual(
				reportview.execute(**args), [{"assigned_to": department, "_aggregate_column": 2}]
			)
		finally:
			frappe.db.rollback(save_point=point)

	def test_io_uses_plan_supplier_even_if_work_order_supplier_differs(self):
		from essdee_yrp.essdee_yrp.report.sd_yrp_io_input_pending.sd_yrp_io_input_pending import execute

		point = "worker2_io"
		frappe.db.savepoint(point)
		try:
			supplier = "W2-" + frappe.generate_hash(length=10)
			settings = frappe.get_cached_doc("SD YRP MRP Settings")
			for opened, qty in [("Open", 7), ("Close", 90)]:
				wo = self.insert("YRP Work Order", supplier="Other", docstatus=1, open_status=opened)
				plan = self.insert(
					"SD YRP Sewing Plan", supplier=supplier, work_order=wo, lot="W2-LOT", item="W2-ITEM"
				)
				for kind, quantity in [
					(settings.sewing_input_qty_type, qty),
					(settings.sewing_line_output_type, 2),
				]:
					entry = self.insert(
						"SD YRP Sewing Plan Entry Detail", sewing_plan=plan, input_type=kind, work_station=""
					)
					self.insert(
						"SD YRP Sewing Plan Detail",
						parent=entry,
						parenttype="SD YRP Sewing Plan Entry Detail",
						parentfield="items",
						quantity=quantity,
					)
			rows = execute({"supplier": supplier})[1]
			self.assertEqual(
				rows,
				[
					{
						"serial_no": 1,
						"sewing_line": "Not Specified",
						"lot": "W2-LOT",
						"item": "W2-ITEM",
						"input_qty": 7.0,
						"line_output_qty": 2.0,
						"input_pending": 5.0,
					}
				],
			)
		finally:
			frappe.db.rollback(save_point=point)

	def test_guest_cannot_read_purchase_reports(self):
		user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				purchase_report().execute({})
		finally:
			frappe.set_user(user)

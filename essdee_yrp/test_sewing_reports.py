"""Persisted report fixtures: quantities are hand checked, never browser totals."""

import frappe
from frappe.permissions import update_permission_property
from frappe.share import add_docshare
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan import sd_yrp_sewing_plan as api


class TestSewingReports(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		point = f"sewing_reports_{frappe.generate_hash(length=10)}"
		frappe.db.savepoint(point)
		self.addCleanup(frappe.db.rollback, save_point=point)
		self.addCleanup(frappe.clear_document_cache, "SD YRP MRP Settings", "SD YRP MRP Settings")
		sources = frappe.db.sql(
			"""select sp.name from `tabSD YRP Sewing Plan` sp
			join `tabSD YRP Lot` lot on lot.name = sp.lot
			join `tabYRP Item Production Detail` ipd on ipd.name = lot.production_detail
			where exists (select 1 from `tabSD YRP Sewing Plan Order Detail` d
			              where d.parent = sp.name and d.item_variant is not null)
			order by sp.name limit 1"""
		)
		self.assertTrue(sources, "Report fixtures require one installed Item/IPD variant")
		self.source = frappe.get_doc("SD YRP Sewing Plan", sources[0][0])
		self.variant = self.source.sewing_plan_order_details[0].item_variant
		self.combination = self.source.sewing_plan_order_details[0].set_combination
		self.received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
		self.assertTrue(self.received_type)
		self.reject_type = frappe.get_doc(
			{"doctype": "YRP Received Type", "name": f"Report Reject {frappe.generate_hash(length=8)}"}
		)
		# Received Type uses prompt naming; persist an isolated valid link directly.
		self.reject_type.db_insert()
		self.station = frappe.get_all("YRP Work Station", pluck="name", limit=1)[0]
		self.supplier = self._supplier()
		self.other_supplier = self._supplier()
		settings = frappe.get_single("SD YRP MRP Settings")
		settings.sewing_input_qty_type = "Input Qty"
		settings.sewing_line_output_type = "Line Output"
		settings.type_wise_diff_summary = "Checking Output"
		settings.sewing_plan_inspection_type = "AQL Output"
		settings.set(
			"sewing_plan_status_summary",
			[
				{"input_type": "Input Qty", "received_type": self.received_type},
				{"input_type": "Line Output", "received_type": self.received_type},
				{"input_type": "Checking Output", "received_type": self.received_type},
				{"input_type": "Checking Output", "received_type": self.reject_type.name},
				{"input_type": "AQL Output", "received_type": self.received_type},
			],
		)
		settings.save()
		self.plan = self._plan(self.supplier)
		self._entry(self.plan, "Input Qty", "2090-01-01", 80)
		self._entry(self.plan, "Line Output", "2090-01-03", 60)
		self._entry(self.plan, "Checking Output", "2090-01-03", 40)
		self._entry(self.plan, "Checking Output", "2090-01-03", 5, self.reject_type.name)
		self._entry(self.plan, "AQL Output", "2090-01-04", 30)

	def _supplier(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": f"Report Unit {frappe.generate_hash(length=10)}",
					"supplier_group": frappe.db.get_value("Supplier", self.source.supplier, "supplier_group"),
					"supplier_type": "Company",
				}
			)
			.insert()
			.name
		)

	def test_scr_configured_balances_received_types_and_signed_totals(self):
		# A non-default earlier-stage receipt joins the configured received-type
		# total, matching the operational SCR contract, without changing Input Qty.
		# Received-type headers follow MRP's newest-modified entry walk.
		self._entry(self.plan, "Input Qty", "2090-01-01", 2, self.reject_type.name)
		result = api.get_scr_data(self.supplier, self.plan.lot)
		expected = ["Order Qty", "Delivered Qty", "Delivered - Input", "Input Qty", "Input Qty Balance",
			"Line Output", "Line Output Balance", "Checking Output", f"Input Qty {self.reject_type.name}",
			self.reject_type.name, "Checking Output Total", "Checking Output Balance",
			"AQL Output", "AQL Output Balance"]
		self.assertEqual(result["headers"], expected)
		self.assertFalse(result.get("derived_balances_omitted", False))
		self.assertEqual(result["balance_headers"], ["Delivered - Input", "Input Qty Balance", "Line Output Balance", "Checking Output Balance", "AQL Output Balance"])
		group = next(iter(result["data"].values()))
		for header, quantity in {"Order Qty": 100, "Delivered Qty": 90, "Delivered - Input": 10,
			"Input Qty Balance": -20, "Line Output Balance": -20, self.reject_type.name: 5,
			"Checking Output Total": 47, "Checking Output Balance": -13, "AQL Output Balance": -10}.items():
			self.assertEqual(group["type_wise_total"][header], quantity, header)
			self.assertEqual(next(iter(group["values"].values()))[header], quantity, header)

	def test_scr_missing_stages_have_zero_values_and_configured_order(self):
		plan = self._plan(self.other_supplier)
		result = api.get_scr_data(self.other_supplier, plan.lot)
		group = next(iter(result["data"].values()))
		self.assertEqual(group["type_wise_total"].get("Input Qty Balance"), 0)
		self.assertEqual(group["type_wise_total"].get("Checking Output Total"), 0)
		self.assertEqual(group["type_wise_total"].get("Checking Output Balance"), 0)
		self.assertLess(result["headers"].index("Line Output"), result["headers"].index("Checking Output"))

	def test_scr_received_only_total_has_no_default_stage_balance(self):
		plan = self._plan(self.other_supplier)
		self._entry(plan, "Checking Output", "2090-01-01", 7, self.reject_type.name)
		result = api.get_scr_data(self.other_supplier, plan.lot)
		group = next(iter(result["data"].values()))
		self.assertEqual(group["type_wise_total"]["Checking Output"], 0)
		self.assertEqual(group["type_wise_total"]["Checking Output Total"], 7)
		self.assertEqual(group["type_wise_total"]["Checking Output Balance"], 0)
		self.assertEqual(group["type_wise_total"]["Delivered - Input"], 90)

	def test_scr_absent_stage_stays_zero_with_nonzero_predecessor(self):
		# Quantities from the live JB2627-020 and F0826-22/2 W PJ 1 evidence.
		for quantity in (4048, 5575, 561):
			with self.subTest(quantity=quantity):
				plan = self._plan(self.other_supplier)
				self._entry(plan, "Checking Output", "2090-01-03", quantity)
				result = api.get_scr_data(self.other_supplier, plan.lot)
				group = next(iter(result["data"].values()))
				self.assertEqual(group["type_wise_total"]["AQL Output Balance"], 0)
				self.assertEqual(group["type_wise_total"]["Checking Output Balance"], quantity)
				self.assertTrue(all(values["AQL Output Balance"] == 0 for values in group["values"].values()))

	def test_scr_observed_zero_stage_still_calculates_signed_balance(self):
		plan = self._plan(self.other_supplier)
		self._entry(plan, "Checking Output", "2090-01-03", 561)
		self._entry(plan, "AQL Output", "2090-01-04", 0)
		group = next(iter(api.get_scr_data(self.other_supplier, plan.lot)["data"].values()))
		self.assertEqual(group["type_wise_total"]["AQL Output Balance"], -561)

	def _plan(self, supplier, *, status="Open", wo_supplier=None):
		lot = frappe.get_doc(
			{
				"doctype": "SD YRP Lot",
				"lot_name": f"REPORT-{frappe.generate_hash(length=10)}",
				"item": self.source.item,
				"production_detail": frappe.db.get_value("SD YRP Lot", self.source.lot, "production_detail"),
			}
		).insert()
		# Seed the authoritative WO tables without triggering unrelated stock lifecycle.
		wo = frappe.get_doc(
			{
				"doctype": "YRP Work Order",
				"name": f"REPORT-WO-{frappe.generate_hash(length=10)}",
				"supplier": wo_supplier or supplier,
				"lot": lot.name,
				"item": self.source.item,
				"production_detail": lot.production_detail,
				"open_status": status,
				"docstatus": 1,
			}
		)
		wo.db_insert()
		frappe.get_doc(
			{
				"doctype": "YRP Work Order Calculated Item",
				"parent": wo.name,
				"parenttype": wo.doctype,
				"parentfield": "work_order_calculated_items",
				"item_variant": self.variant,
				"set_combination": self.combination,
				"quantity": 100,
				"delivered_quantity": 90,
				"received_qty": 35,
			}
		).db_insert()
		for doctype, field, pending in (
			("YRP Work Order Deliverables", "deliverables", 10),
			("YRP Work Order Receivables", "receivables", 65),
		):
			frappe.get_doc(
				{
					"doctype": doctype,
					"parent": wo.name,
					"parenttype": wo.doctype,
					"parentfield": field,
					"item_variant": self.variant,
					"set_combination": self.combination,
					"qty": 100,
					"pending_quantity": pending,
					"uom": frappe.db.get_value("Item", self.variant, "stock_uom"),
				}
			).db_insert()
		plan = frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan",
				"naming_series": self.source.naming_series,
				"supplier": supplier,
				"work_order": wo.name,
				"lot": lot.name,
				"item": self.source.item,
				"sewing_plan_order_details": [
					{
						"item_variant": self.variant,
						"set_combination": self.combination,
						"quantity": 40,
						"pre_final": 10,
						"final_inspection": 8,
						"fi_date": "2090-01-12",
					},
					{
						"item_variant": self.variant,
						"set_combination": self.combination,
						"quantity": 60,
						"pre_final": 15,
						"final_inspection": 12,
						"fi_date": "2090-01-10",
					},
				],
			}
		).insert()
		# Retain an intentionally stale association to prove both owners are checked.
		if wo_supplier:
			frappe.db.set_value(plan.doctype, plan.name, "supplier", supplier)
			plan.supplier = supplier
		return plan

	def _entry(self, plan, stage, date, quantity, received_type=None, station=None):
		return frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan Entry Detail",
				"sewing_plan": plan.name,
				"input_type": stage,
				"entry_date": date,
				"work_station": station or self.station,
				"received_type": received_type or self.received_type,
				"sewing_plan_details": [
					{"item_variant": self.variant, "set_combination": self.combination, "quantity": quantity}
				],
			}
		).insert()

	def _summary(self, *args, **kwargs):
		endpoint = getattr(api, "get_sewing_plan_dpr_summary", None)
		self.assertTrue(callable(endpoint), "DPR date-range endpoint must be exported")
		return endpoint(*args, **kwargs)

	def test_status_totals_exclude_closed_and_other_plan_suppliers(self):
		other = self._plan(self.other_supplier)
		closed = self._plan(self.supplier, status="Close")
		for plan in (other, closed):
			self._entry(plan, "Input Qty", "2090-01-01", 9000)
		result = api.get_sp_status_summary(self.supplier)
		self.assertNotIn("derived_balances_omitted", result)
		self.assertEqual(len(result["data"]), 2)
		total, row = result["data"]
		self.assertEqual(row["sewing_plan"], self.plan.name)
		for label, expected in {
			"Order Qty": 100,
			"Delivered Qty": 90,
			"GRN Qty": 35,
			"Input Qty": 80,
			"Line Output": 60,
			"Checking Output": 40,
			self.reject_type.name: 5,
			"AQL Output": 30,
			"Pre Final": 25,
			"Final Inspection": 20,
			"Line Stock": -20,
			"Stock": -15,
			"GRN Pending": 25,
		}.items():
			self.assertIn(label, result["header2"])
			self.assertEqual(row[label], expected, label)
			self.assertEqual(total[label], expected, f"total {label}")
		self.assertEqual(row["line_stock"], -20)
		self.assertEqual(row["checking_stock"], -15)
		self.assertEqual(row["grn_pending"], 25)
		self.assertEqual(total["checking_stock"], -15)

	def test_status_scopes_supplier_to_plan_and_uses_configured_column_order(self):
		stale = self._plan(self.supplier, wo_supplier=self.other_supplier)
		self._entry(stale, "Input Qty", "2090-01-01", 12)
		self._entry(stale, "Input Qty", "2090-01-02", 2, self.reject_type.name)
		result = api.get_sp_status_summary(self.supplier)
		self.assertEqual(len(result["data"]), 3)
		self.assertEqual(result["data"][0]["Input Qty"], 92)
		self.assertEqual(result["header2"], ["Order Qty", "Delivered Qty", "Input Qty", "Line Output",
			"Checking Output", self.reject_type.name, "AQL Output", "Pre Final", "Final Inspection",
			"GRN Qty", "GRN Pending", "Line Stock", "Stock"])
		self.assertEqual(result["header3"], ["Ready for Checking", "Ready for AQL",
			"Ready for Pre final", "Ready for Final Inspection"])

	def test_status_dates_readiness_and_running_days_are_explicit(self):
		result = api.get_sp_status_summary(self.supplier)
		row = result["data"][1]
		for label in ("FI Date", "Input Date", "Last Sewing Output", "Total Running Days"):
			self.assertIn(label, result["header1"])
		self.assertEqual(getdate(row["fi_date"]), getdate("2090-01-10"))
		self.assertEqual(getdate(row["input_date"]), getdate("2090-01-01"))
		self.assertEqual(getdate(row["last_output_date"]), getdate("2090-01-03"))
		self.assertEqual(row["running_days"], 2)
		for label, key, expected in (
			("Ready for Checking", "ready_for_checking", "Under Checking"),
			("Ready for AQL", "ready_for_aql", "Under AQL"),
			("Ready for Pre final", "ready_for_pre_final", "Under Pre Final"),
			("Ready for Final Inspection", "ready_for_final_inspection", "Under Final Inspection"),
		):
			self.assertIn(label, result["header3"])
			self.assertEqual(row[label], expected)
			self.assertEqual(row[key], expected)

	def test_status_missing_dates_and_readiness_stay_blank(self):
		plan = self._plan(self.other_supplier)
		frappe.db.set_value(
			"SD YRP Sewing Plan Order Detail",
			{"parent": plan.name},
			{"fi_date": None, "pre_final": 0, "final_inspection": 0},
		)
		row = api.get_sp_status_summary(self.other_supplier)["data"][1]
		for key in ("fi_date", "input_date", "last_output_date", "running_days"):
			self.assertIn(key, row)
			self.assertIsNone(row[key])
		for label, key in (
			("Ready for Checking", "ready_for_checking"),
			("Ready for AQL", "ready_for_aql"),
			("Ready for Pre final", "ready_for_pre_final"),
			("Ready for Final Inspection", "ready_for_final_inspection"),
		):
			self.assertEqual(row[label], "")
			self.assertEqual(row[key], "")

	def test_readiness_compares_default_output_while_checking_stock_includes_rejects(self):
		self._entry(self.plan, "AQL Output", "2090-01-04", 10)
		self._entry(self.plan, "Line Output", "2090-01-03", 7, self.reject_type.name)
		result = api.get_sp_status_summary(self.supplier)
		row = result["data"][1]
		self.assertEqual(row["ready_for_aql"], "Completed")
		self.assertEqual(row["Line Output"], 60)
		self.assertEqual(row[f"Line Output {self.reject_type.name}"], 7)
		self.assertNotIn(f"Line Output {self.reject_type.name}", result["header2"])
		self.assertEqual(row["line_stock"], -20)
		self.assertEqual(row["checking_stock"], -15)

	def test_grand_totals_are_the_sum_of_multiple_open_plan_rows(self):
		second = self._plan(self.supplier)
		self._entry(second, "Input Qty", "2090-01-02", 30)
		self._entry(second, "Line Output", "2090-01-03", 10)
		result = api.get_sp_status_summary(self.supplier)
		self.assertEqual(len(result["data"]), 3)
		total = result["data"][0]
		for label, expected in {
			"Order Qty": 200,
			"Delivered Qty": 180,
			"GRN Qty": 70,
			"Input Qty": 110,
			"Line Output": 70,
			"Line Stock": -40,
			"Checking Stock": -25,
			"GRN Pending": 0,
		}.items():
			self.assertEqual(total[label], expected)
			self.assertEqual(total[label], sum(row[label] for row in result["data"][1:]))

	def test_status_uses_garment_piece_projection_not_accessory_or_panel_stock(self):
		accessory = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"REPORT-ACCESSORY-{frappe.generate_hash(length=8)}",
				"item_name": "Report accessory",
				"item_group": frappe.db.get_value("Item", self.variant, "item_group"),
				"stock_uom": frappe.db.get_value("Item", self.variant, "stock_uom"),
				"gst_hsn_code": frappe.db.get_value("Item", self.variant, "gst_hsn_code"),
			}
		).insert()
		for doctype, field, variant, quantity in (
			("YRP Work Order Deliverables", "deliverables", accessory.name, 500),
			("YRP Work Order Deliverables", "deliverables", self.variant, 180),
			("YRP Work Order Receivables", "receivables", self.variant, 250),
		):
			frappe.get_doc(
				{
					"doctype": doctype,
					"parent": self.plan.work_order,
					"parenttype": "YRP Work Order",
					"parentfield": field,
					"item_variant": variant,
					"set_combination": self.combination,
					"qty": quantity,
					"pending_quantity": 0,
					"uom": accessory.stock_uom,
				}
			).db_insert()
		result = api.get_sp_status_summary(self.supplier)
		self.assertEqual(result["data"][0]["Delivered Qty"], 90)
		self.assertEqual(result["data"][0]["GRN Qty"], 35)
		self.assertEqual(result["data"][1]["grn_pending"], 25)
		self.assertEqual(len(result["data"]), 2)

	def test_status_requires_configured_semantic_stage_roles(self):
		frappe.db.set_single_value("SD YRP MRP Settings", "sewing_line_output_type", None)
		with self.assertRaises(frappe.ValidationError):
			api.get_sp_status_summary(self.supplier)

	def test_readiness_stays_blank_before_checking_and_completes_when_fully_checked(self):
		plan = self._plan(self.other_supplier)
		self._entry(plan, "Line Output", "2090-01-03", 10)
		row = api.get_sp_status_summary(self.other_supplier)["data"][1]
		self.assertEqual(row["ready_for_checking"], "")
		self._entry(plan, "Checking Output", "2090-01-03", 10)
		row = api.get_sp_status_summary(self.other_supplier)["data"][1]
		self.assertEqual(row["ready_for_checking"], "Completed")

	def test_dpr_range_rejects_reversed_dates(self):
		with self.assertRaises(frappe.ValidationError):
			self._summary(self.supplier, "2090-01-04", "2090-01-01")

	def _assert_invalid_dpr_date(self, endpoint, args, label):
		message_count = len(frappe.local.message_log)
		try:
			endpoint(*args)
		except Exception as exc:
			self.assertIsInstance(exc, frappe.ValidationError)
			self.assertIn(label, str(exc))
			self.assertNotIn("<", str(exc))
			self.assertEqual(len(frappe.local.message_log), message_count + 1)
			self.assertEqual(frappe.local.message_log[-1].title, "Invalid DPR Date")
		else:
			self.fail(f"Invalid {label} must raise business validation")

	def test_dpr_range_rejects_missing_zero_and_malformed_bounds_explicitly(self):
		for label, index in (("From Date", 1), ("To Date", 2)):
			for invalid in (None, "", " ", "0000-00-00", "not-a-date", "2090-02-30"):
				with self.subTest(bound=label, value=invalid):
					args = [self.supplier, "2090-01-01", "2090-01-04"]
					args[index] = invalid
					self._assert_invalid_dpr_date(self._summary, args, label)

	def test_daily_dpr_rejects_missing_zero_and_malformed_dates_explicitly(self):
		for invalid in (None, "", " ", "0000-00-00", "not-a-date", "2090-02-30"):
			with self.subTest(value=invalid):
				self._assert_invalid_dpr_date(
					api.get_sewing_plan_dpr_data, (self.supplier, invalid), "DPR Date"
				)

	def test_dpr_range_includes_the_upper_bound_and_excludes_the_following_day(self):
		self._entry(self.plan, "Line Output", "2090-01-05", 17)
		self._entry(self.plan, "Line Output", "2090-01-06", 19)
		result = self._summary(self.supplier, "2090-01-04", "2090-01-05")
		self.assertEqual([row["date"] for row in result["reports"]], ["2090-01-04", "2090-01-05"])
		self.assertEqual([self._dpr_total(row) for row in result["reports"]], [30, 17])

	def test_dpr_range_contains_each_applicable_date_and_filters(self):
		result = self._summary(self.supplier, "2090-01-01", "2090-01-05")
		self.assertEqual(result["pending_fi"], [])
		self.assertEqual(
			[str(row["date"]) for row in result["reports"]], ["2090-01-01", "2090-01-03", "2090-01-04"]
		)
		self.assertEqual([self._dpr_total(row) for row in result["reports"]], [80, 105, 30])
		self.assertTrue(all(row["status"] == "success" and not row["blocked"] for row in result["reports"]))
		filtered = self._summary(
			self.supplier, "2090-01-01", "2090-01-05", work_station=self.station, input_type="Line Output"
		)
		self.assertEqual(len(filtered["reports"]), 1)
		self.assertEqual(self._dpr_total(filtered["reports"][0]), 60)
		self.assertEqual(self._summary(self.supplier, "2090-02-01", "2090-02-02")["reports"], [])

	def _dpr_total(self, report):
		return sum(
			colour["total"]
			for by_lot in report["dpr_data"].values()
			for lot in by_lot.values()
			for received in lot["details"].values()
			for colours in received.values()
			for colour in colours.values()
		)

	def test_pending_fi_is_deduplicated_and_explicit_in_daily_and_range(self):
		frappe.db.set_value("SD YRP Sewing Plan Order Detail", {"parent": self.plan.name}, "fi_date", None)
		daily = api.get_sewing_plan_dpr_data(self.supplier, "2090-01-03")
		self.assertIn("status", daily)
		self.assertEqual(daily["status"], "pending_fi")
		self.assertTrue(daily["blocked"])
		self.assertTrue(daily["message"])
		self.assertEqual(daily["dpr_data"], {})
		self.assertEqual(len(daily["pending_fi"]), 1)
		result = self._summary(self.supplier, "2090-01-01", "2090-01-04")
		self.assertEqual(result["status"], "pending_fi")
		self.assertTrue(result["blocked"])
		self.assertEqual(len(result["pending_fi"]), 1)
		# MRP lists blocked dates in pending_fi and reports only dates with data.
		self.assertEqual(result["reports"], [])

	def test_dpr_never_returns_another_suppliers_rows_or_pending_fi(self):
		other = self._plan(self.other_supplier)
		frappe.db.set_value("SD YRP Sewing Plan Order Detail", {"parent": other.name}, "fi_date", None)
		self._entry(other, "Input Qty", "2090-01-01", 9000)
		stale = self._plan(self.supplier, wo_supplier=self.other_supplier)
		self._entry(stale, "Input Qty", "2090-01-01", 8000)
		for report in (
			api.get_sewing_plan_dpr_data(self.supplier, "2090-01-01"),
			*self._summary(self.supplier, "2090-01-01", "2090-01-01")["reports"],
		):
			self.assertEqual(report["pending_fi"], [])
			self.assertEqual(self._dpr_total(report), 80)
			self.assertNotIn(other.lot, str(report))
			self.assertNotIn(stale.lot, str(report))

	def test_reports_require_read_and_report_permission_even_for_shared_plans(self):
		# All normally has report access; deny that right explicitly so a later
		# Work Order/Entry permission failure cannot masquerade as this boundary.
		update_permission_property("SD YRP Sewing Plan", "All", 0, "report", 0)
		self.addCleanup(frappe.clear_cache, doctype="SD YRP Sewing Plan")
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"report-{frappe.generate_hash(length=8)}@example.com",
				"first_name": "Report Reader",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert()
		add_docshare(self.plan.doctype, self.plan.name, user=user.name, read=1)
		previous = frappe.session.user
		try:
			for current in ("Guest", user.name):
				frappe.set_user(current)
				self.assertFalse(frappe.has_permission("SD YRP Sewing Plan", "report"))
				if current == user.name:
					self.assertTrue(frappe.has_permission("SD YRP Sewing Plan", "read"))
				for endpoint, args in (
					(api.get_sp_status_summary, (self.supplier,)),
					(api.get_sewing_plan_dpr_data, (self.supplier, "2090-01-01")),
					(self._summary, (self.supplier, "2090-01-01", "2090-01-04")),
				):
					with self.subTest(user=current, endpoint=endpoint.__name__):
						with self.assertRaises(frappe.PermissionError):
							endpoint(*args)
		finally:
			frappe.set_user(previous)
			frappe.clear_cache(user=user.name)

	def test_daily_dpr_checks_permission_before_parsing_untrusted_dates(self):
		previous = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				api.get_sewing_plan_dpr_data(self.supplier, "invalid-date")
		finally:
			frappe.set_user(previous)

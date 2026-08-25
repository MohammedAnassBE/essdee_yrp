import copy
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate, nowtime

from essdee_yrp.sewing.closed_work_order import (
	_closed_work_order_receivable_rows,
	_normalize_selected_rows,
	create_closed_work_order_grn,
	get_closed_sewing_work_orders,
	get_closed_work_order_grn_details,
)
from essdee_yrp.sewing.config import get_sewing_input_configuration
from essdee_yrp.sewing.plan import (
	_order_rows,
	_should_have_sewing_plan,
	create_or_get_sewing_plan,
)
from essdee_yrp.sewing.entry import (
	cancel_sewing_plan_entry,
	get_data_entry_data,
	submit_data_entry_log,
	update_sewing_plan_data,
)
from essdee_yrp.sewing.read_models import (
	get_consumption_mapping_data,
	get_dashboard_data,
	get_fi_updates_data,
	get_item_summary_data,
	get_item_summary_options,
	get_monthly_summary_data,
	get_monthly_summary_print_data,
	get_scr_data,
	get_sewing_consumption_print_data,
	get_sewing_plan_dpr_data,
	get_sewing_plan_entries,
	get_sp_status_summary,
	get_supplier_lots,
	get_the_lot,
	save_consumption_data,
	update_fi_dates,
)


class TestSewingBusinessLogic(IntegrationTestCase):
	def test_sewing_input_configuration_matches_f15_sequence(self):
		configuration = get_sewing_input_configuration()
		self.assertEqual(
			[
				(row.input_type, row.difference_from, flt(row.allowance))
				for row in configuration
			],
			[
				("Input Qty", "Order Qty", 75),
				("Line Output", "Input Qty", 20),
				("Checking Output", "Line Output", 3),
				("AQL Output", "Checking Output", 3),
			],
		)

		payload = get_data_entry_data("S-0172", "C0826-57")
		self.assertEqual(
			payload["diff"],
			{
				"input_qty": "order_qty",
				"line_output": "input_qty",
				"checking_output": "line_output",
				"aql_output": "checking_output",
			},
		)
		self.assertEqual(
			payload["input_types"],
			["Input Qty", "Line Output", "Checking Output", "AQL Output"],
		)

	def test_server_blocks_aql_output_before_checking_output(self):
		plan_name = frappe.db.get_value("Sewing Plan", {"lot": "C0826-57"}, "name")
		plan = frappe.get_doc("Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					value["data_entry"] = 1
					selected = value
		self.assertIsNotNone(selected)

		work_station = frappe.get_all("Work Station", pluck="name", limit=1)[0]
		received_type = frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		)
		original_sql = frappe.db.sql

		def without_prior_entries(query, *args, **kwargs):
			if "from `tabSewing Plan Entry Detail` entry" in query:
				return []
			return original_sql(query, *args, **kwargs)

		with (
			patch.object(frappe.db, "sql", side_effect=without_prior_entries),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Only .* remains from .*Checking Output",
			),
		):
			submit_data_entry_log(
				{
					"plan": plan.name,
					"input_type": "AQL Output",
					"received_type": received_type,
					"work_station": work_station,
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)

	def test_server_allows_line_output_after_input_quantity(self):
		plan_name = frappe.db.get_value("Sewing Plan", {"lot": "C0826-57"}, "name")
		plan = frappe.get_doc("Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					value["data_entry"] = 1
					selected = value
		self.assertIsNotNone(selected)
		source = next(
			row
			for row in plan.sewing_plan_order_details
			if row.name == selected["order_detail"]
		)
		original_sql = frappe.db.sql

		def with_one_input_quantity(query, *args, **kwargs):
			if "from `tabSewing Plan Entry Detail` entry" in query:
				return [
					frappe._dict(
						input_type="Input Qty",
						item_variant=source.item_variant,
						set_combination=source.set_combination,
						quantity=1,
					)
				]
			return original_sql(query, *args, **kwargs)

		with patch.object(
			frappe.db, "sql", side_effect=with_one_input_quantity
		):
			entry_name = submit_data_entry_log(
				{
					"plan": plan.name,
					"input_type": "Line Output",
					"received_type": frappe.db.get_single_value(
						"YRP Stock Settings", "default_received_type"
					),
					"work_station": frappe.get_all(
						"Work Station", pluck="name", limit=1
					)[0],
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)
		self.assertEqual(
			frappe.db.get_value("Sewing Plan Entry Detail", entry_name, "input_type"),
			"Line Output",
		)
		cancel_sewing_plan_entry(entry_name)

	def test_server_applies_allowance_to_the_stage_total(self):
		plan_name = frappe.db.get_value("Sewing Plan", {"lot": "C0826-57"}, "name")
		plan = frappe.get_doc("Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					allowed_total = flt(value.get("order_qty")) * 1.75
					value["data_entry"] = (
						allowed_total - flt(value.get("input_qty")) + 1
					)
					selected = value
		self.assertIsNotNone(selected)

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"after the configured .* allowance",
		):
			submit_data_entry_log(
				{
					"plan": plan.name,
					"input_type": "Input Qty",
					"received_type": frappe.db.get_single_value(
						"YRP Stock Settings", "default_received_type"
					),
					"work_station": frappe.get_all(
						"Work Station", pluck="name", limit=1
					)[0],
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)

	def _closed_work_order(self):
		suppliers = frappe.get_all(
			"Sewing Plan",
			fields=["supplier"],
			group_by="supplier",
			limit=20,
		)
		for supplier_row in suppliers:
			if not supplier_row.supplier:
				continue
			work_orders = get_closed_sewing_work_orders(
				"Work Order",
				"",
				"name",
				0,
				100,
				{"supplier": supplier_row.supplier},
			)
			for work_order, *_display in work_orders:
				doc = frappe.get_doc("Work Order", work_order)
				if any(flt(row.pending_quantity) > 0 for row in doc.receivables):
					return doc
		self.skipTest("No migrated closed Sewing Work Order has a pending receivable")

	def _one_quantity(self, item_details):
		item_details = copy.deepcopy(item_details)
		selected = None
		for group in item_details:
			for item in group.get("items") or []:
				for value in (item.get("values") or {}).values():
					value["qty"] = 0
					if selected is None and value.get("ref_docname"):
						value["qty"] = 1
						selected = {
							"ref_docname": value["ref_docname"],
							"received_type": (item.get("dimensions") or {}).get(
								"received_type"
							),
						}
		if not selected:
			self.fail("Closed Work Order editor data has no selectable receivable")
		return item_details, selected

	def test_sewing_endpoints_are_authenticated_and_search_scoped(self):
		methods = (
			"create_sewing_plan",
			"get_closed_sewing_work_orders",
			"get_closed_work_order_grn_details",
			"create_closed_work_order_grn",
		)
		for method in methods:
			module = (
				"essdee_yrp.sewing.plan"
				if method == "create_sewing_plan"
				else "essdee_yrp.sewing.closed_work_order"
			)
			function = frappe.get_attr(f"{module}.{method}")
			self.assertIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)

		work_order = self._closed_work_order()
		matches = get_closed_sewing_work_orders(
			"Work Order", "", "name", 0, 100, {"supplier": work_order.supplier}
		)
		self.assertIn(work_order.name, {row[0] for row in matches})
		self.assertEqual(
			get_closed_sewing_work_orders(
				"Work Order", "", "name", 0, 20, {"supplier": ""}
			),
			[],
		)

	def test_selected_rows_are_rebuilt_from_locked_work_order(self):
		work_order = self._closed_work_order()
		trusted = _closed_work_order_receivable_rows(work_order)[0]
		attacker_row = {
			**trusted,
			"quantity": 1,
			"item_variant": "ATTACKER ITEM",
			"rate": 999999,
			"uom": "ATTACKER UOM",
			"lot": "ATTACKER LOT",
			"set_combination": '{"attacker": true}',
		}

		row = _normalize_selected_rows(work_order, [attacker_row])[0]

		self.assertEqual(row["item_variant"], trusted["item_variant"])
		self.assertEqual(flt(row["rate"]), flt(trusted["rate"]))
		self.assertEqual(row["uom"], trusted["uom"])
		self.assertEqual(row["lot"], work_order.lot)
		self.assertEqual(row["set_combination"], trusted["set_combination"])

	def test_closed_work_order_grn_submit_and_cancel_lifecycle(self):
		work_order = self._closed_work_order()
		details = get_closed_work_order_grn_details(
			work_order.name, work_order.supplier
		)
		item_details, selected = self._one_quantity(details["item_details"])
		pending_before = flt(
			frappe.db.get_value(
				"Work Order Receivables", selected["ref_docname"], "pending_quantity"
			)
		)

		result = create_closed_work_order_grn(
			work_order=work_order.name,
			supplier=work_order.supplier,
			values={
				"posting_date": nowdate(),
				"posting_time": nowtime(),
				"delivery_date": nowdate(),
				"supplier_document_no": "SEWING-CLOSED-WO-TEST",
				"supplier_document_date": nowdate(),
				"vehicle_no": "TEST-VEHICLE",
			},
			item_details=item_details,
		)
		grn = frappe.get_doc("Goods Received Note", result["name"])

		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(grn.from_closed_wo_sewing_details, 1)
		self.assertEqual(grn.against_id, work_order.name)
		self.assertEqual(grn.lot, work_order.lot)
		self.assertEqual(len(grn.items), 1)
		self.assertEqual(grn.items[0].ref_docname, selected["ref_docname"])
		self.assertEqual(grn.items[0].lot, work_order.lot)
		self.assertEqual(
			grn.items[0].received_type, selected["received_type"]
		)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Work Order Receivables",
					selected["ref_docname"],
					"pending_quantity",
				)
			),
			pending_before - 1,
		)
		self.assertTrue(
			frappe.db.exists(
				"Stock Ledger Entry",
				{
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
					"lot": work_order.lot,
					"received_type": selected["received_type"],
				},
			)
		)

		grn.cancel()
		self.assertEqual(grn.docstatus, 2)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Work Order Receivables",
					selected["ref_docname"],
					"pending_quantity",
				)
			),
			pending_before,
		)
		self.assertFalse(
			frappe.db.exists(
				"Stock Ledger Entry",
				{
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			)
		)

	def test_migrated_sewing_plans_match_work_order_calculated_items(self):
		plans = frappe.get_all(
			"Sewing Plan", fields=["name", "work_order"], limit=500
		)
		self.assertGreater(len(plans), 100)
		matched = 0
		mismatches = []
		for plan_row in plans:
			work_order = frappe.get_doc("Work Order", plan_row.work_order)
			plan = frappe.get_doc("Sewing Plan", plan_row.name)
			expected = self._quantity_map(_order_rows(work_order))
			actual = self._quantity_map(plan.sewing_plan_order_details)
			if expected == actual:
				matched += 1
			else:
				mismatches.append(
					{
						"plan": plan.name,
						"work_order": work_order.name,
						"expected": expected,
						"actual": actual,
					}
				)
		self.assertEqual(matched, len(plans), mismatches)

	def test_sewing_plan_creation_is_idempotent_for_migrated_work_order(self):
		plan_name = frappe.get_all("Sewing Plan", pluck="name", limit=1)[0]
		plan = frappe.get_doc("Sewing Plan", plan_name)
		work_order = frappe.get_doc("Work Order", plan.work_order)
		self.assertTrue(_should_have_sewing_plan(work_order))
		before = frappe.db.count(
			"Sewing Plan", filters={"work_order": work_order.name}
		)
		self.assertEqual(create_or_get_sewing_plan(work_order), plan.name)
		self.assertEqual(
			frappe.db.count("Sewing Plan", filters={"work_order": work_order.name}),
			before,
		)

	def test_stock_user_can_create_and_delete_server_normalized_entry(self):
		plan_name = frappe.get_all(
			"Sewing Plan",
			filters={"supplier": "S-0172"},
			pluck="name",
			limit=1,
		)[0]
		plan = frappe.get_doc("Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				if value.get("order_detail"):
					value["data_entry"] = 1
					value["item_variant"] = "ATTACKER ITEM"
					selected = value
					break
			if selected:
				break
		self.assertIsNotNone(selected)
		work_station = frappe.get_all("Work Station", pluck="name", limit=1)[0]
		received_type = frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		)

		previous_user = frappe.session.user
		try:
			frappe.set_user("emp+devika@essdee.fit")
			self.assertTrue(
				frappe.has_permission("Sewing Plan Entry Detail", "create")
			)
			entry_name = submit_data_entry_log(
				{
					"plan": plan.name,
					"input_type": "Input Qty",
					"grn_item_type": received_type,
					"work_station": work_station,
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)
			entry = frappe.get_doc("Sewing Plan Entry Detail", entry_name)
			source = frappe.get_doc(
				"Sewing Plan Order Detail", selected["order_detail"]
			)
			self.assertEqual(entry.owner, "emp+devika@essdee.fit")
			self.assertEqual(len(entry.sewing_plan_details), 1)
			self.assertEqual(
				entry.sewing_plan_details[0].item_variant, source.item_variant
			)
			cancel_sewing_plan_entry(entry.name)
			self.assertFalse(
				frappe.db.exists("Sewing Plan Entry Detail", entry.name)
			)
		finally:
			frappe.set_user(previous_user)

	def test_system_manager_keeps_standard_entry_permissions(self):
		previous_user = frappe.session.user
		try:
			frappe.set_user("ui-verify@essdee.fit")
			for permission in ("read", "write", "create", "delete", "report", "export"):
				self.assertTrue(
					frappe.has_permission("Sewing Plan Entry Detail", permission),
					f"System Manager lost {permission} after adding custom permissions",
				)
		finally:
			frappe.set_user(previous_user)

	def test_inspection_update_resolves_saved_plan_rows(self):
		plan_name = frappe.get_all(
			"Sewing Plan",
			filters={"supplier": "S-0172"},
			pluck="name",
			limit=1,
		)[0]
		plan = frappe.get_doc("Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		colour = next(iter(plan_data["colours"].values()))
		value = next(
			row for row in colour["values"].values() if row.get("order_detail")
		)
		value["pre_final"] = 1
		row_payload = {
			"colour": colour["variant_colour"],
			"part": colour["part"],
			"set_combination": colour["set_combination"],
			"qty": colour["values"],
		}

		self.assertEqual(
			update_sewing_plan_data(
				{
					"lot": plan.lot,
					"plan": plan.name,
					"inspection_type": "pre_final",
					"action": "update",
					"rows": [row_payload],
				}
			),
			"Success",
		)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Sewing Plan Order Detail", value["order_detail"], "pre_final"
				)
			),
			1,
		)
		self.assertEqual(
			update_sewing_plan_data(
				{
					"lot": plan.lot,
					"plan": plan.name,
					"inspection_type": "pre_final",
					"action": "revert",
					"rows": [row_payload],
				}
			),
			"Success",
		)

	def test_sewing_read_models_match_persisted_entry_quantities(self):
		sample = frappe.db.sql(
			"""
				select sp.supplier, sp.lot, entry.entry_date, entry.input_type
				from `tabSewing Plan Entry Detail` entry
				join `tabSewing Plan` sp on sp.name = entry.sewing_plan
				where sp.supplier is not null and sp.lot is not null
				order by entry.creation desc
				limit 1
			""",
			as_dict=True,
		)[0]
		expected = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSewing Plan Detail` detail
					join `tabSewing Plan Entry Detail` entry on entry.name = detail.parent
					join `tabSewing Plan` sp on sp.name = entry.sewing_plan
					where sp.supplier = %s
					  and entry.entry_date = %s
					  and entry.input_type = %s
				""",
				(sample.supplier, sample.entry_date, sample.input_type),
			)[0][0]
		)
		monthly = get_monthly_summary_data(
			sample.supplier,
			sample.entry_date,
			sample.entry_date,
			sample.input_type,
		)
		self.assertEqual(flt(monthly["grand_total"]["total"]), expected)

		entries = get_sewing_plan_entries(
			sample.supplier,
			input_type=sample.input_type,
			lot_name=sample.lot,
		)
		self.assertTrue(entries)
		entry_total = sum(
			flt(colour["total"])
			for entry in entries.values()
			for colour in entry["details"].values()
		)
		expected_entry_total = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSewing Plan Detail` detail
					join `tabSewing Plan Entry Detail` entry on entry.name = detail.parent
					join `tabSewing Plan` sp on sp.name = entry.sewing_plan
					where sp.supplier = %s and sp.lot = %s and entry.input_type = %s
				""",
				(sample.supplier, sample.lot, sample.input_type),
			)[0][0]
		)
		self.assertEqual(entry_total, expected_entry_total)

		dpr = get_sewing_plan_dpr_data(sample.supplier, sample.entry_date)
		if not dpr["pending_fi"]:
			dpr_total = sum(
				flt(colour["total"])
				for by_lot in dpr["dpr_data"].values()
				for lot in by_lot.values()
				for received_types in lot["details"].values()
				for colours in received_types.values()
				for colour in colours.values()
			)
			expected_dpr = flt(
				frappe.db.sql(
					"""
						select coalesce(sum(detail.quantity), 0)
						from `tabSewing Plan Detail` detail
						join `tabSewing Plan Entry Detail` entry on entry.name = detail.parent
						join `tabSewing Plan` sp on sp.name = entry.sewing_plan
						where sp.supplier = %s and entry.entry_date = %s
					""",
					(sample.supplier, sample.entry_date),
				)[0][0]
			)
			self.assertEqual(dpr_total, expected_dpr)

	def test_dashboard_and_consumption_use_supported_f16_configuration(self):
		supplier, lot = frappe.db.sql(
			"""
				select supplier, lot
				from `tabSewing Plan`
				where supplier is not null and lot is not null
				order by creation desc
				limit 1
			"""
		)[0]
		dashboard = get_dashboard_data(supplier)
		self.assertTrue(all(row["input_type"] for row in dashboard))
		self.assertTrue(all(flt(row["qty"]) >= 0 for row in dashboard))

		consumption = get_consumption_mapping_data(lot, supplier)
		self.assertEqual(
			consumption["ipd"],
			frappe.db.get_value("Lot", lot, "production_detail"),
		)
		self.assertIn("sections", consumption)
		self.assertIn("cloth_acc_data", consumption)

		scr = get_scr_data(supplier, lot)
		self.assertEqual(scr["status"], "success")
		self.assertTrue(scr["derived_balances_omitted"])
		scr_order_total = sum(
			flt(group["type_wise_total"].get("Order Qty"))
			for group in scr["data"].values()
		)
		expected_order_total = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSewing Plan Order Detail` detail
					join `tabSewing Plan` sp on sp.name = detail.parent
					where sp.supplier = %s and sp.lot = %s
				""",
				(supplier, lot),
			)[0][0]
		)
		self.assertEqual(scr_order_total, expected_order_total)

		status = get_sp_status_summary(supplier)
		self.assertTrue(status["derived_balances_omitted"])
		self.assertEqual(status["header1"], ["Item", "Lot", "Colour", "Part"])

	def test_all_sewing_view_providers_execute_against_migrated_data(self):
		supplier, lot = frappe.db.sql(
			"""
				select supplier, lot
				from `tabSewing Plan`
				where supplier is not null and lot is not null
				order by creation desc
				limit 1
			"""
		)[0]
		production_detail = frappe.db.get_value("Lot", lot, "production_detail")

		options = get_item_summary_options(supplier)
		self.assertIn(lot, options["lots"])
		self.assertIn("groups", get_item_summary_data(supplier, lots=[lot]))
		self.assertIn(
			lot,
			{
				row[0]
				for row in get_supplier_lots(
					"Lot", lot, "name", 0, 20, {"supplier": supplier}
				)
			},
		)
		self.assertIn(lot, {row["lot"] for row in get_the_lot(supplier)["lots"]})

		monthly = get_monthly_summary_print_data(supplier)
		self.assertEqual(monthly["supplier"], supplier)
		consumption = get_consumption_mapping_data(lot, supplier)
		print_data = get_sewing_consumption_print_data(production_detail, lot)
		self.assertEqual(print_data["ipd"], production_detail)
		self.assertEqual(print_data["lot"], lot)
		self.assertEqual(
			save_consumption_data(
				supplier,
				lot,
				consumption["sections"],
				consumption["cloth_acc_data"],
			)["status"],
			"success",
		)

		fi_updates = get_fi_updates_data(supplier)["data"]
		if fi_updates:
			update = dict(fi_updates[0])
			update["date"] = nowdate()
			self.assertEqual(update_fi_dates([update]), "Success")

	def _quantity_map(self, rows):
		out = {}
		for row in rows:
			value = row.get("set_combination")
			if isinstance(value, str):
				value = frappe.parse_json(value or "{}")
			key = (row.get("item_variant"), frappe.as_json(value or {}, indent=None))
			quantity = row.get("quantity") if row.get("quantity") is not None else row.get("qty")
			out[key] = flt(out.get(key)) + flt(quantity)
		return out

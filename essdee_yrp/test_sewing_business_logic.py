import copy
from unittest.mock import patch

import frappe
from frappe.share import add_docshare
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate, nowtime

from essdee_yrp.sewing.closed_work_order import (
	_closed_work_order_receivable_rows,
	_normalize_selected_rows,
	create_closed_work_order_grn,
	get_closed_sewing_work_orders,
	get_closed_work_order_grn_details,
)
from essdee_yrp.sewing.config import get_sewing_input_configuration
from essdee_yrp.sewing.entry import (
	_assert_entry_cancellable,
	cancel_sewing_plan_entry,
	get_data_entry_data,
	submit_data_entry_log,
	update_sewing_plan_data,
)
from essdee_yrp.sewing.plan import (
	_order_rows,
	_should_have_sewing_plan,
	create_or_get_sewing_plan,
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
	def _mutation_plan(self, *, supplier=None, lot=None):
		"""Create isolated ownership and quantities using valid migrated Item links."""
		savepoint = f"sewing_mutation_{frappe.generate_hash(length=10)}"
		frappe.db.savepoint(savepoint)
		self.addCleanup(frappe.db.rollback, save_point=savepoint)
		source, _payload, _plan_data = self._data_entry_plan()
		if not supplier:
			supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": f"Sewing mutation {frappe.generate_hash(length=10)}",
					"supplier_group": frappe.db.get_value("Supplier", source.supplier, "supplier_group"),
					"supplier_type": "Company",
				}
			).insert().name
		if not lot:
			lot = frappe.get_doc(
				{
					"doctype": "SD YRP Lot",
					"lot_name": f"SEWING-MUTATION-{frappe.generate_hash(length=10)}",
					"item": source.item,
					"production_detail": frappe.db.get_value("SD YRP Lot", source.lot, "production_detail"),
				}
			).insert().name
		row = source.sewing_plan_order_details[0]
		return frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan",
				"naming_series": source.naming_series,
				"supplier": supplier,
				"lot": lot,
				"item": source.item,
				"sewing_plan_order_details": [
					{"item_variant": row.item_variant, "set_combination": row.set_combination, "quantity": 10}
				],
			}
		).insert()

	def _mutation_entry(self, plan, date):
		return frappe.get_doc(
			{
				"doctype": "SD YRP Sewing Plan Entry Detail",
				"sewing_plan": plan.name,
				"input_type": "Input Qty",
				"entry_date": date,
			}
		).insert()

	def test_entry_cancellation_honours_previous_entry_days(self):
		plan = self._mutation_plan()
		other_plan = self._mutation_plan(supplier=plan.supplier)
		other_supplier_plan = self._mutation_plan()
		frappe.db.set_single_value("SD YRP MRP Settings", "previous_day_entries", 2)
		old = self._mutation_entry(plan, "2090-01-01")
		eligible = self._mutation_entry(plan, "2090-01-03")
		self._mutation_entry(other_plan, "2090-01-05")
		self._mutation_entry(other_plan, "2090-01-05")
		self._mutation_entry(other_supplier_plan, "2099-01-01")
		self.assertTrue(frappe.has_permission(old.doctype, "delete", doc=old))

		with self.assertRaises(frappe.ValidationError):
			cancel_sewing_plan_entry(old.name)
		self.assertEqual(frappe.local.message_log[-1].title, "Sewing Entry Cancellation Blocked")
		self.assertTrue(frappe.db.exists(old.doctype, old.name))
		cancel_sewing_plan_entry(eligible.name)
		self.assertFalse(frappe.db.exists(eligible.doctype, eligible.name))

	def test_entry_cancellation_rechecks_permission_and_disabled_window(self):
		plan = self._mutation_plan()
		entry = self._mutation_entry(plan, "2090-01-01")
		frappe.db.set_single_value("SD YRP MRP Settings", "previous_day_entries", 1)
		previous_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				cancel_sewing_plan_entry(entry.name)
		finally:
			frappe.set_user(previous_user)
		self.assertTrue(frappe.db.exists(entry.doctype, entry.name))
		for days in (0, -1):
			frappe.db.set_single_value("SD YRP MRP Settings", "previous_day_entries", days)
			with self.assertRaises(frappe.ValidationError):
				cancel_sewing_plan_entry(entry.name)
			self.assertTrue(frappe.db.exists(entry.doctype, entry.name))

	def test_entry_cancellation_reloads_locked_current_date(self):
		plan = self._mutation_plan()
		frappe.db.set_single_value("SD YRP MRP Settings", "previous_day_entries", 1)
		entry = self._mutation_entry(plan, "2090-01-05")
		self._mutation_entry(plan, "2090-01-05")
		stale = frappe.get_doc(entry.doctype, entry.name)
		frappe.db.set_value(entry.doctype, entry.name, "entry_date", "2090-01-01")

		with self.assertRaises(frappe.ValidationError):
			_assert_entry_cancellable(stale)
		self.assertEqual(getdate(stale.entry_date), getdate("2090-01-01"))
		with self.assertRaises(frappe.ValidationError):
			cancel_sewing_plan_entry(entry.name)
		self.assertTrue(frappe.db.exists(entry.doctype, entry.name))

		frappe.db.set_value(entry.doctype, entry.name, "entry_date", "2090-01-07")
		_assert_entry_cancellable(stale)
		self.assertEqual(getdate(stale.entry_date), getdate("2090-01-07"))
		cancel_sewing_plan_entry(entry.name)
		self.assertFalse(frappe.db.exists(entry.doctype, entry.name))

	def _consumption_writer(self, plan, *, roles=()):
		user = f"sewing-consumption-{frappe.generate_hash(length=10)}@example.com"
		user_doc = frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "Sewing Consumption Writer",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert()
		if roles:
			user_doc.add_roles(*roles)
		add_docshare(plan.doctype, plan.name, user=user, read=1, write=1)
		self.addCleanup(frappe.clear_cache, user=user)
		return user

	def test_consumption_save_rejects_denied_ipd_read(self):
		plan = self._mutation_plan()
		user = self._consumption_writer(plan)
		before = frappe.get_doc(plan.doctype, plan.name).as_dict()
		previous_user = frappe.session.user
		try:
			frappe.set_user(user)
			self.assertTrue(frappe.has_permission(plan.doctype, "write", doc=plan.name))
			self.assertTrue(frappe.has_permission("SD YRP Lot", "read", doc=plan.lot))
			self.assertFalse(frappe.has_permission("YRP Item Production Detail", "read"))
			with self.assertRaises(frappe.PermissionError):
				get_consumption_mapping_data(plan.lot, plan.supplier)
			with self.assertRaises(frappe.PermissionError):
				save_consumption_data(plan.supplier, plan.lot, [], [])
		finally:
			frappe.set_user(previous_user)
		self.assertEqual(frappe.get_doc(plan.doctype, plan.name).as_dict(), before)

	def test_consumption_save_rejects_denied_lot_read(self):
		plan = self._mutation_plan()
		other_plan = self._mutation_plan()
		user = self._consumption_writer(plan, roles=("Production Planner",))
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "SD YRP Lot",
				"for_value": other_plan.lot,
				"apply_to_all_doctypes": 0,
				"applicable_for": "SD YRP Lot",
			}
		).insert()
		before = frappe.get_doc(plan.doctype, plan.name).as_dict()
		previous_user = frappe.session.user
		try:
			frappe.set_user(user)
			self.assertTrue(frappe.has_permission(plan.doctype, "write", doc=plan.name))
			self.assertTrue(frappe.has_permission("YRP Item Production Detail", "read"))
			self.assertFalse(frappe.has_permission("SD YRP Lot", "read", doc=plan.lot))
			with self.assertRaises(frappe.PermissionError):
				get_consumption_mapping_data(plan.lot, plan.supplier)
			with self.assertRaises(frappe.PermissionError):
				save_consumption_data(plan.supplier, plan.lot, [], [])
		finally:
			frappe.set_user(previous_user)
		self.assertEqual(frappe.get_doc(plan.doctype, plan.name).as_dict(), before)

	def test_consumption_read_and_save_reject_denied_ipd_document(self):
		plan = self._mutation_plan()
		ipd = frappe.db.get_value("SD YRP Lot", plan.lot, "production_detail")
		other_ipd = frappe.get_all(
			"YRP Item Production Detail", filters={"name": ["!=", ipd]}, pluck="name", limit=1
		)[0]
		user = self._consumption_writer(plan, roles=("Production Planner",))
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "YRP Item Production Detail",
				"for_value": other_ipd,
				"apply_to_all_doctypes": 0,
				"applicable_for": "YRP Item Production Detail",
			}
		).insert()
		before = frappe.get_doc(plan.doctype, plan.name).as_dict()
		previous_user = frappe.session.user
		try:
			frappe.set_user(user)
			self.assertTrue(frappe.has_permission(plan.doctype, "write", doc=plan.name))
			self.assertTrue(frappe.has_permission("SD YRP Lot", "read", doc=plan.lot))
			self.assertTrue(frappe.has_permission("YRP Item Production Detail", "read"))
			self.assertFalse(frappe.has_permission("YRP Item Production Detail", "read", doc=ipd))
			for label, operation in (
				("read", lambda: get_consumption_mapping_data(plan.lot, plan.supplier)),
				("save", lambda: save_consumption_data(plan.supplier, plan.lot, [], [])),
			):
				with self.subTest(operation=label), self.assertRaises(frappe.PermissionError):
					operation()
		finally:
			frappe.set_user(previous_user)
		self.assertEqual(frappe.get_doc(plan.doctype, plan.name).as_dict(), before)

	def test_consumption_read_and_save_reject_unrelated_supplier(self):
		plan = self._mutation_plan()
		unrelated = self._mutation_plan()
		before = frappe.get_doc(plan.doctype, plan.name).as_dict()
		with self.assertRaises(frappe.ValidationError):
			get_consumption_mapping_data(plan.lot, unrelated.supplier)
		with self.assertRaises(frappe.ValidationError):
			save_consumption_data(unrelated.supplier, plan.lot, [], [])
		self.assertEqual(frappe.get_doc(plan.doctype, plan.name).as_dict(), before)

	def test_consumption_print_preserves_supplier(self):
		first = self._mutation_plan()
		selected = self._mutation_plan(lot=first.lot)
		ipd = frappe.db.get_value("SD YRP Lot", first.lot, "production_detail")
		self.assertTrue(frappe.db.get_value("YRP Item Production Detail", ipd, "stiching_process"))
		frappe.db.set_value(
			"YRP Item Production Detail",
			ipd,
			"cloth_accessory_json",
			frappe.as_json({"attributes": ["Accessory"], "items": [{"Accessory": "Trim", "Weight": 1}]}),
		)
		for plan, quantity in ((first, 11), (selected, 22)):
			plan.append(
				"cloth_accessory_consumption",
				{
					"index": 1,
					"attribute": "Accessory",
					"attribute_value": "Trim",
					"consumption_weight": quantity,
				},
			)
			plan.save()

		data = get_sewing_consumption_print_data(ipd, first.lot, selected.supplier)
		self.assertEqual(data["supplier"], selected.supplier)
		self.assertEqual(data["lot"], first.lot)
		self.assertEqual(data["cloth_acc_data"][0]["columns"][0]["Consumption Weight"], 22)
		data["cloth_acc_data"][0]["columns"][0]["Consumption Weight"] = 33
		save_consumption_data(selected.supplier, selected.lot, data["sections"], data["cloth_acc_data"])
		self.assertEqual(
			frappe.get_doc(first.doctype, first.name).cloth_accessory_consumption[0].consumption_weight,
			11,
		)
		updated = get_sewing_consumption_print_data(ipd, first.lot, selected.supplier)
		self.assertEqual(updated["cloth_acc_data"][0]["columns"][0]["Consumption Weight"], 33)

	def test_consumption_legacy_calls_require_unique_ownership(self):
		plan = self._mutation_plan()
		ipd = frappe.db.get_value("SD YRP Lot", plan.lot, "production_detail")
		self.assertEqual(get_consumption_mapping_data(plan.lot)["ipd"], ipd)
		self.assertEqual(get_sewing_consumption_print_data(ipd, plan.lot)["supplier"], plan.supplier)
		self.assertEqual(get_sewing_consumption_print_data(ipd, supplier=plan.supplier)["lot"], plan.lot)
		self._mutation_plan(lot=plan.lot)
		with self.assertRaises(frappe.ValidationError):
			get_consumption_mapping_data(plan.lot)
		with self.assertRaises(frappe.ValidationError):
			get_sewing_consumption_print_data(ipd, plan.lot)
		self._mutation_plan(supplier=plan.supplier)
		with self.assertRaises(frappe.ValidationError):
			get_sewing_consumption_print_data(ipd, supplier=plan.supplier)

	def test_consumption_print_rejects_mismatched_ipd_and_supplier(self):
		plan = self._mutation_plan()
		unrelated = self._mutation_plan()
		ipd = frappe.db.get_value("SD YRP Lot", plan.lot, "production_detail")
		with self.assertRaises(frappe.ValidationError):
			get_sewing_consumption_print_data(ipd, plan.lot, unrelated.supplier)
		with self.assertRaises(frappe.ValidationError):
			get_sewing_consumption_print_data("UNRELATED-IPD", plan.lot, plan.supplier)

	def test_current_state_entries_cannot_exceed_predecessor_balance(self):
		plan = self._mutation_plan()
		row = plan.sewing_plan_order_details[0]
		selected = {"order_detail": row.name, "data_entry": 10}
		payload = {
			"plan": plan.name,
			"input_type": "Input Qty",
			"received_type": frappe.db.get_single_value("YRP Stock Settings", "default_received_type"),
			"work_station": frappe.get_all("YRP Work Station", pluck="name", limit=1)[0],
			"quantities": {"colours": {"test": {"values": {"test": selected}}}},
		}
		submit_data_entry_log(payload)
		payload["input_type"] = "Line Output"
		selected["data_entry"] = 8
		first = submit_data_entry_log(copy.deepcopy(payload))
		with self.assertRaisesRegex(frappe.ValidationError, "Only .*4.* remains"):
			submit_data_entry_log(copy.deepcopy(payload))
		self.assertEqual(
			frappe.get_all(
				"SD YRP Sewing Plan Entry Detail",
				filters={"sewing_plan": plan.name, "input_type": "Line Output"},
				pluck="name",
			),
			[first],
		)
		entry = frappe.get_doc("SD YRP Sewing Plan Entry Detail", first)
		self.assertEqual(flt(entry.sewing_plan_details[0].quantity), 8)

	def _data_entry_plan(self):
		plans = frappe.get_all(
			"SD YRP Sewing Plan",
			fields=["name", "lot", "supplier"],
			filters={
				"lot": ["is", "set"],
				"supplier": ["is", "set"],
			},
			order_by="name",
			limit_page_length=0,
		)
		for candidate in plans:
			payload = get_data_entry_data(candidate.supplier, candidate.lot)
			plan_data = (payload.get("data") or {}).get(candidate.lot, {}).get(candidate.name)
			if plan_data and any(
				colour.get("values") for colour in (plan_data.get("colours") or {}).values()
			):
				return frappe.get_doc("SD YRP Sewing Plan", candidate.name), payload, plan_data
		self.skipTest("No migrated Sewing Plan has a usable data-entry matrix")

	def test_sewing_input_configuration_matches_f15_sequence(self):
		settings = frappe.get_single("SD YRP MRP Settings")
		if not settings.get("sewing_plan_input_orders"):
			self.skipTest("Sewing sequence parity requires migrated MRP Settings")
		configuration = get_sewing_input_configuration()
		self.assertEqual(
			[(row.input_type, row.difference_from, flt(row.allowance)) for row in configuration],
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
		plan, _payload, plan_data = self._data_entry_plan()
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					value["data_entry"] = 1
					selected = value
		self.assertIsNotNone(selected)

		work_station = frappe.get_all("YRP Work Station", pluck="name", limit=1)[0]
		received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
		original_sql = frappe.db.sql

		def without_prior_entries(query, *args, **kwargs):
			if "from `tabSD YRP Sewing Plan Entry Detail` entry" in query:
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
		plan, _payload, plan_data = self._data_entry_plan()
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					value["data_entry"] = 1
					selected = value
		self.assertIsNotNone(selected)
		source = next(row for row in plan.sewing_plan_order_details if row.name == selected["order_detail"])
		original_sql = frappe.db.sql

		def with_one_input_quantity(query, *args, **kwargs):
			if "from `tabSD YRP Sewing Plan Entry Detail` entry" in query:
				return [
					frappe._dict(
						input_type="Input Qty",
						item_variant=source.item_variant,
						set_combination=source.set_combination,
						quantity=1,
					)
				]
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=with_one_input_quantity):
			entry_name = submit_data_entry_log(
				{
					"plan": plan.name,
					"input_type": "Line Output",
					"received_type": frappe.db.get_single_value(
						"YRP Stock Settings", "default_received_type"
					),
					"work_station": frappe.get_all("YRP Work Station", pluck="name", limit=1)[0],
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)
		self.assertEqual(
			frappe.db.get_value("SD YRP Sewing Plan Entry Detail", entry_name, "input_type"),
			"Line Output",
		)
		cancel_sewing_plan_entry(entry_name)

	def test_server_applies_allowance_to_the_stage_total(self):
		plan, _payload, plan_data = self._data_entry_plan()
		selected = None
		for colour in plan_data["colours"].values():
			for value in colour["values"].values():
				value["data_entry"] = 0
				if selected is None:
					allowed_total = flt(value.get("order_qty")) * 1.75
					value["data_entry"] = allowed_total - flt(value.get("input_qty")) + 1
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
					"work_station": frappe.get_all("YRP Work Station", pluck="name", limit=1)[0],
					"date": nowdate(),
					"time": nowtime(),
					"quantities": plan_data,
				}
			)

	def _closed_work_order(self):
		suppliers = frappe.get_all(
			"SD YRP Sewing Plan",
			fields=["supplier"],
			group_by="supplier",
			limit=20,
		)
		for supplier_row in suppliers:
			if not supplier_row.supplier:
				continue
			work_orders = get_closed_sewing_work_orders(
				"YRP Work Order",
				"",
				"name",
				0,
				100,
				{"supplier": supplier_row.supplier},
			)
			for work_order, *_display in work_orders:
				doc = frappe.get_doc("YRP Work Order", work_order)
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
							"received_type": (item.get("dimensions") or {}).get("received_type"),
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
			"YRP Work Order", "", "name", 0, 100, {"supplier": work_order.supplier}
		)
		self.assertIn(work_order.name, {row[0] for row in matches})
		self.assertEqual(
			get_closed_sewing_work_orders("YRP Work Order", "", "name", 0, 20, {"supplier": ""}),
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
		details = get_closed_work_order_grn_details(work_order.name, work_order.supplier)
		item_details, selected = self._one_quantity(details["item_details"])
		pending_before = flt(
			frappe.db.get_value("YRP Work Order Receivables", selected["ref_docname"], "pending_quantity")
		)

		naming_series = frappe.get_meta("YRP Goods Received Note").get_field("naming_series").default
		result = create_closed_work_order_grn(
			work_order=work_order.name,
			supplier=work_order.supplier,
			values={
				"naming_series": naming_series,
				"posting_date": nowdate(),
				"posting_time": nowtime(),
				"delivery_date": nowdate(),
				"supplier_document_no": "SEWING-CLOSED-WO-TEST",
				"supplier_document_date": nowdate(),
				"vehicle_no": "TEST-VEHICLE",
			},
			item_details=item_details,
		)
		grn = frappe.get_doc("YRP Goods Received Note", result["name"])

		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(grn.naming_series, naming_series)
		self.assertEqual(grn.from_closed_wo_sewing_details, 1)
		self.assertEqual(grn.against_id, work_order.name)
		self.assertEqual(grn.lot, work_order.lot)
		self.assertEqual(len(grn.items), 1)
		self.assertEqual(grn.items[0].ref_docname, selected["ref_docname"])
		self.assertEqual(grn.items[0].lot, work_order.lot)
		self.assertEqual(grn.items[0].received_type, selected["received_type"])
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"YRP Work Order Receivables",
					selected["ref_docname"],
					"pending_quantity",
				)
			),
			pending_before - 1,
		)
		self.assertTrue(
			frappe.db.exists(
				"YRP Stock Ledger Entry",
				{
					"voucher_type": "YRP Goods Received Note",
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
					"YRP Work Order Receivables",
					selected["ref_docname"],
					"pending_quantity",
				)
			),
			pending_before,
		)
		self.assertFalse(
			frappe.db.exists(
				"YRP Stock Ledger Entry",
				{
					"voucher_type": "YRP Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			)
		)

	def test_closed_work_order_grn_rejects_unknown_naming_series(self):
		work_order = self._closed_work_order()
		details = get_closed_work_order_grn_details(work_order.name, work_order.supplier)
		item_details, _selected = self._one_quantity(details["item_details"])

		with self.assertRaises(frappe.ValidationError) as raised:
			create_closed_work_order_grn(
				work_order=work_order.name,
				supplier=work_order.supplier,
				values={
					"naming_series": "UNKNOWN-GRN-",
					"supplier_document_no": "SEWING-CLOSED-WO-TEST",
					"vehicle_no": "TEST-VEHICLE",
				},
				item_details=item_details,
			)

		self.assertIn("UNKNOWN-GRN-", str(raised.exception))

	def test_migrated_sewing_plans_match_work_order_calculated_items(self):
		plans = frappe.get_all("SD YRP Sewing Plan", fields=["name", "work_order"], limit=500)
		if not plans:
			self.skipTest("Sewing-plan parity requires migrated plans")
		self.assertGreater(len(plans), 100)
		matched = 0
		mismatches = []
		for plan_row in plans:
			work_order = frappe.get_doc("YRP Work Order", plan_row.work_order)
			plan = frappe.get_doc("SD YRP Sewing Plan", plan_row.name)
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
		plan_names = frappe.get_all("SD YRP Sewing Plan", pluck="name", limit=1)
		if not plan_names:
			self.skipTest("Sewing-plan idempotency requires a migrated plan")
		plan_name = plan_names[0]
		plan = frappe.get_doc("SD YRP Sewing Plan", plan_name)
		work_order = frappe.get_doc("YRP Work Order", plan.work_order)
		self.assertTrue(_should_have_sewing_plan(work_order))
		before = frappe.db.count("SD YRP Sewing Plan", filters={"work_order": work_order.name})
		self.assertEqual(create_or_get_sewing_plan(work_order), plan.name)
		self.assertEqual(
			frappe.db.count("SD YRP Sewing Plan", filters={"work_order": work_order.name}),
			before,
		)

	def test_stock_user_can_create_and_delete_server_normalized_entry(self):
		plan_names = frappe.get_all(
			"SD YRP Sewing Plan",
			filters={"supplier": "S-0172"},
			pluck="name",
			limit=1,
		)
		if not plan_names:
			self.skipTest("Stock-user lifecycle requires the migrated sewing fixture")
		plan_name = plan_names[0]
		plan = frappe.get_doc("SD YRP Sewing Plan", plan_name)
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
		work_station = frappe.get_all("YRP Work Station", pluck="name", limit=1)[0]
		received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")

		previous_user = frappe.session.user
		try:
			frappe.set_user("emp+devika@essdee.fit")
			self.assertTrue(frappe.has_permission("SD YRP Sewing Plan Entry Detail", "create"))
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
			entry = frappe.get_doc("SD YRP Sewing Plan Entry Detail", entry_name)
			source = frappe.get_doc("SD YRP Sewing Plan Order Detail", selected["order_detail"])
			self.assertEqual(entry.owner, "emp+devika@essdee.fit")
			self.assertEqual(len(entry.sewing_plan_details), 1)
			self.assertEqual(entry.sewing_plan_details[0].item_variant, source.item_variant)
			cancel_sewing_plan_entry(entry.name)
			self.assertFalse(frappe.db.exists("SD YRP Sewing Plan Entry Detail", entry.name))
		finally:
			frappe.set_user(previous_user)

	def test_system_manager_keeps_standard_entry_permissions(self):
		user = f"sewing-system-manager-{frappe.generate_hash(length=10)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "Sewing System Manager",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True).add_roles("System Manager")
		previous_user = frappe.session.user
		try:
			frappe.set_user(user)
			for permission in ("read", "write", "create", "delete", "report", "export"):
				self.assertTrue(
					frappe.has_permission("SD YRP Sewing Plan Entry Detail", permission),
					f"System Manager lost {permission} after adding custom permissions",
				)
		finally:
			frappe.set_user(previous_user)
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)

	def test_inspection_update_resolves_saved_plan_rows(self):
		plan_names = frappe.get_all(
			"SD YRP Sewing Plan",
			filters={"supplier": "S-0172"},
			pluck="name",
			limit=1,
		)
		if not plan_names:
			self.skipTest("Inspection update requires the migrated sewing fixture")
		plan_name = plan_names[0]
		plan = frappe.get_doc("SD YRP Sewing Plan", plan_name)
		payload = get_data_entry_data(plan.supplier, plan.lot)
		plan_data = payload["data"][plan.lot][plan.name]
		colour = next(iter(plan_data["colours"].values()))
		value = next(row for row in colour["values"].values() if row.get("order_detail"))
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
			flt(frappe.db.get_value("SD YRP Sewing Plan Order Detail", value["order_detail"], "pre_final")),
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
		samples = frappe.db.sql(
			"""
				select sp.supplier, sp.lot, entry.entry_date, entry.input_type
				from `tabSD YRP Sewing Plan Entry Detail` entry
				join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
				where sp.supplier is not null and sp.lot is not null
				order by entry.creation desc
				limit 1
			""",
			as_dict=True,
		)
		if not samples:
			self.skipTest("Sewing read-model parity requires migrated entries")
		sample = samples[0]
		expected = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSD YRP Sewing Plan Detail` detail
					join `tabSD YRP Sewing Plan Entry Detail` entry on entry.name = detail.parent
					join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
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
			flt(colour["total"]) for entry in entries.values() for colour in entry["details"].values()
		)
		expected_entry_total = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSD YRP Sewing Plan Detail` detail
					join `tabSD YRP Sewing Plan Entry Detail` entry on entry.name = detail.parent
					join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
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
						from `tabSD YRP Sewing Plan Detail` detail
						join `tabSD YRP Sewing Plan Entry Detail` entry on entry.name = detail.parent
						join `tabSD YRP Sewing Plan` sp on sp.name = entry.sewing_plan
						where sp.supplier = %s and entry.entry_date = %s
					""",
					(sample.supplier, sample.entry_date),
				)[0][0]
			)
			self.assertEqual(dpr_total, expected_dpr)

	def test_dashboard_and_consumption_use_supported_f16_configuration(self):
		rows = frappe.db.sql(
			"""
				select supplier, lot
				from `tabSD YRP Sewing Plan`
				where supplier is not null and lot is not null
				order by creation desc
				limit 1
			"""
		)
		if not rows:
			self.skipTest("Sewing dashboard parity requires migrated plans")
		supplier, lot = rows[0]
		dashboard = get_dashboard_data(supplier)
		self.assertTrue(all(row["input_type"] for row in dashboard))
		self.assertTrue(all(flt(row["qty"]) >= 0 for row in dashboard))

		consumption = get_consumption_mapping_data(lot, supplier)
		self.assertEqual(
			consumption["ipd"],
			frappe.db.get_value("SD YRP Lot", lot, "production_detail"),
		)
		self.assertIn("sections", consumption)
		self.assertIn("cloth_acc_data", consumption)

		scr = get_scr_data(supplier, lot)
		self.assertEqual(scr["status"], "success")
		self.assertTrue(scr["derived_balances_omitted"])
		scr_order_total = sum(
			flt(group["type_wise_total"].get("Order Qty")) for group in scr["data"].values()
		)
		expected_order_total = flt(
			frappe.db.sql(
				"""
					select coalesce(sum(detail.quantity), 0)
					from `tabSD YRP Sewing Plan Order Detail` detail
					join `tabSD YRP Sewing Plan` sp on sp.name = detail.parent
					where sp.supplier = %s and sp.lot = %s
				""",
				(supplier, lot),
			)[0][0]
		)
		self.assertEqual(scr_order_total, expected_order_total)

		status = get_sp_status_summary(supplier)
		self.assertTrue(status["derived_balances_omitted"])
		self.assertEqual(status["header1"], ["Item", "SD YRP Lot", "Colour", "Part"])

	def test_all_sewing_view_providers_execute_against_migrated_data(self):
		rows = frappe.db.sql(
			"""
				select supplier, lot
				from `tabSD YRP Sewing Plan`
				where supplier is not null and lot is not null
				order by creation desc
				limit 1
			"""
		)
		if not rows:
			self.skipTest("Sewing provider parity requires migrated plans")
		supplier, lot = rows[0]
		production_detail = frappe.db.get_value("SD YRP Lot", lot, "production_detail")

		options = get_item_summary_options(supplier)
		self.assertIn(lot, options["lots"])
		self.assertIn("groups", get_item_summary_data(supplier, lots=[lot]))
		self.assertIn(
			lot,
			{row[0] for row in get_supplier_lots("SD YRP Lot", lot, "name", 0, 20, {"supplier": supplier})},
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

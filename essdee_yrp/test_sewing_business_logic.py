import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import frappe
from frappe.share import add_docshare
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, cint, flt, getdate, nowdate, nowtime

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

	def test_cancellation_retries_when_supplier_scope_changes_before_lock(self):
		plan = self._mutation_plan()
		other = self._mutation_plan()
		entry = self._mutation_entry(plan, "2090-01-05")
		frappe.db.set_single_value("SD YRP MRP Settings", "previous_day_entries", 1)
		original_sql = frappe.db.sql
		moved = False

		def move_before_first_plan_lock(query, *args, **kwargs):
			nonlocal moved
			if (
				not moved
				and isinstance(query, str)
				and "from `tabSD YRP Sewing Plan`" in query
				and "for update" in query.lower()
			):
				moved = True
				frappe.db.set_value(plan.doctype, plan.name, "supplier", other.supplier)
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=move_before_first_plan_lock):
			with self.assertRaisesRegex(frappe.ValidationError, "retry"):
				cancel_sewing_plan_entry(entry.name)
		self.assertTrue(frappe.db.exists(entry.doctype, entry.name))

	def test_sewing_mutation_scope_fields_are_indexed(self):
		for doctype, field in (
			("SD YRP Sewing Plan", "supplier"),
			("SD YRP Sewing Plan Entry Detail", "sewing_plan"),
		):
			with self.subTest(doctype=doctype):
				self.assertTrue(frappe.get_meta(doctype).get_field(field).search_index)
				indexes = frappe.db.sql(f"show index from `tab{doctype}`", as_dict=True)
				self.assertTrue(any(row.Column_name == field and row.Seq_in_index == 1 for row in indexes))

	def test_submission_retries_when_supplier_scope_changes_before_plan_lock(self):
		plan = self._mutation_plan()
		other = self._mutation_plan()
		original_sql = frappe.db.sql
		moved = False

		def move_before_plan_lock(query, *args, **kwargs):
			nonlocal moved
			if not moved and "from `tabSD YRP Sewing Plan`" in str(query) and "for update" in str(query):
				moved = True
				frappe.db.set_value(plan.doctype, plan.name, "supplier", other.supplier)
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=move_before_plan_lock):
			with self.assertRaisesRegex(frappe.ValidationError, "retry"):
				submit_data_entry_log({"plan": plan.name})
		self.assertFalse(frappe.db.exists("SD YRP Sewing Plan Entry Detail", {"sewing_plan": plan.name}))

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
		original_sql = frappe.db.sql
		locks = []

		def record_locks(query, *args, **kwargs):
			if isinstance(query, str) and "for update" in query.lower():
				locks.append(query)
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=record_locks):
			submit_data_entry_log(payload)
		self.assertIn("from `tabSupplier` where name =", locks[0])
		self.assertIn("from `tabSD YRP Sewing Plan`", locks[1])
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
		# Match the web editor's F16 structural identifiers, selections and refs.
		# Stock fields are absent; only the locked server source can supply them.
		item_details = [{"items": [{"name": row["name"], "attributes": row.get("attributes"),
			"primary_attribute": row.get("primary_attribute"),
			"dimensions": {"received_type": row.get("dimensions", {}).get("received_type")},
			"values": {key: {field: cell.get(field) for field in ("qty", "ref_doctype", "ref_docname")}
				for key, cell in row.get("values", {}).items()},
		} for row in group["items"]]} for group in item_details]
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

	def test_closed_work_order_picker_excludes_foreign_open_and_draft(self):
		"""Removing any Supplier/status predicate must expose the altered fixture."""
		work_order = self._closed_work_order()
		def search(supplier):
			return {row[0] for row in get_closed_sewing_work_orders(
				"YRP Work Order", work_order.name, "name", 0, 100, {"supplier": supplier}
			)}
		self.assertIn(work_order.name, search(work_order.supplier))
		self.assertNotIn(work_order.name, search("SEWING-FOREIGN-SUPPLIER"))
		with self.assertRaises(frappe.ValidationError):
			get_closed_work_order_grn_details(work_order.name, "SEWING-FOREIGN-SUPPLIER")
		for changed in ({"open_status": "Open"}, {"docstatus": 0}):
			frappe.db.savepoint("closed_picker")
			try:
				frappe.db.set_value("YRP Work Order", work_order.name, changed)
				self.assertNotIn(work_order.name, search(work_order.supplier))
				with self.assertRaises(frappe.ValidationError):
					get_closed_work_order_grn_details(work_order.name, work_order.supplier)
			finally:
				frappe.db.rollback(save_point="closed_picker")

	def test_closed_work_order_grn_discards_browser_tampering(self):
		"""Exercise grouped unflattening and real insert/submit, not only normalization."""
		from yrp.stock.save_stock_items import group_items_for_ui
		work_order = self._closed_work_order()
		details = get_closed_work_order_grn_details(work_order.name, work_order.supplier)
		groups, selected = self._one_quantity(details["item_details"])
		trusted = next(row for row in details["items"] if row["ref_docname"] == selected["ref_docname"]
			and row.get("received_type") == selected["received_type"])
		# A valid foreign Item gets through F16 ungrouping, so this proves the
		# closed-WO service discards the resulting item identity as well as rate/UOM.
		foreign_item = next(row.item_variant for row in work_order.receivables if row.item_variant != trusted["item_variant"])
		groups = group_items_for_ui([{"item_variant": foreign_item, "quantity": 1, "uom": "ATTACKER-UOM",
			"lot": "ATTACKER-LOT", "received_type": selected["received_type"], "rate": 999999,
			"ref_doctype": "YRP Work Order Receivables", "ref_docname": selected["ref_docname"]}], "YRP Goods Received Note")
		result = create_closed_work_order_grn(work_order.name, work_order.supplier, {
			"naming_series": frappe.get_meta("YRP Goods Received Note").get_field("naming_series").default,
			"supplier_document_no": "TASK7-TAMPER", "vehicle_no": "TASK7-VEHICLE",
		}, groups)
		grn = frappe.get_doc("YRP Goods Received Note", result["name"])
		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(grn.items[0].item_variant, trusted["item_variant"])
		self.assertEqual(grn.items[0].uom, trusted["uom"])
		self.assertEqual(flt(grn.items[0].rate), flt(trusted["rate"]))
		self.assertEqual(grn.items[0].lot, work_order.lot)

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
		self.assertNotIn("derived_balances_omitted", status)
		self.assertEqual(status["header1"][:4], ["Item", "SD YRP Lot", "Colour", "Part"])
		self.assertIn("FI Date", status["header1"])
		self.assertIn("Checking Stock", status["header2"])

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


class TestSewingClosedGrnConcurrency(IntegrationTestCase):
	def test_closed_work_order_grn_rejects_concurrent_duplicate(self):
		"""Two real connections compete for one committed receivable balance."""
		from essdee_yrp.sewing import closed_work_order as service
		site, sites_path = frappe.local.site, frappe.local.sites_path
		source = TestSewingBusinessLogic()._closed_work_order()
		fixture = source.as_dict()
		name = f"SEWING-GRN-RACE-{frappe.generate_hash(length=12)}"
		series = frappe.get_meta("YRP Goods Received Note").get_field("naming_series").default
		first_locked, second_attempting = threading.Event(), threading.Event()
		progress = threading.local()
		results, balances = [], {}
		database_class, original_get = type(frappe.local.db), service._get_closed_sewing_work_order
		original_sql = database_class.sql

		def connection(operation):
			frappe.init(site, sites_path=sites_path)
			frappe.connect()
			frappe.flags.in_test = True
			frappe.set_user("Administrator")
			try:
				return operation()
			finally:
				frappe.db.rollback()
				frappe.destroy()

		def setup():
			clone = frappe.get_doc(copy.deepcopy(fixture))
			clone.name = name
			# Copy the migrated, valid source links without recalculating a new WO.
			# Only the isolated receivable quantity differs from the source.
			clone.set("receivables", [next(row for row in clone.receivables if flt(row.pending_quantity) > 0)])
			clone.receivables[0].qty = 1
			clone.receivables[0].pending_quantity = 1
			clone.db_insert()
			for row in clone.get_all_children():
				row.name = frappe.generate_hash(length=16)
				row.parent = name
				row.db_insert()
			plan = frappe.get_doc({"doctype": "SD YRP Sewing Plan", "supplier": clone.supplier,
				"work_order": name, "naming_series": "SP-2526-"}).insert()
			frappe.get_doc({"doctype": "SD YRP Sewing Plan Entry Detail", "sewing_plan": plan.name,
				"entry_date": nowdate(), "input_type": frappe.db.get_single_value("SD YRP MRP Settings", "type_wise_diff_summary"),
				"sewing_plan_details": [{"item_variant": clone.receivables[0].item_variant, "quantity": 100}]}).insert()
			frappe.db.commit()
			groups = service.get_closed_work_order_grn_details(name, clone.supplier)["item_details"]
			groups, selected = TestSewingBusinessLogic()._one_quantity(groups)
			for group in groups:
				for row in group["items"]:
					for cell in row["values"].values():
						if cell["qty"]:
							# Consume the complete allowance, including any configured excess.
							cell["qty"] = cell["max_receivable_quantity"]
			return clone.supplier, groups, selected

		def observe_sql(database, query, *args, **kwargs):
			if getattr(progress, "request", None) == "second" and isinstance(query, str) \
				and "tabYRP Work Order`" in query and "for update" in query.lower():
				second_attempting.set()
			return original_sql(database, query, *args, **kwargs)

		def observe_lock(*args, **kwargs):
			doc = original_get(*args, **kwargs)
			if kwargs.get("for_update"):
				balances[progress.request] = flt(doc.receivables[0].pending_quantity)
				if progress.request == "first":
					first_locked.set()
					self.assertTrue(second_attempting.wait(10), "Second connection never competed for the WO lock")
			return doc

		def create(label, supplier, groups):
			progress.request = label
			if label == "second":
				self.assertTrue(first_locked.wait(10))
			try:
				result = service.create_closed_work_order_grn(name, supplier, {
					"naming_series": series, "supplier_document_no": "TASK7-RACE", "vehicle_no": "TASK7-RACE",
				}, copy.deepcopy(groups))
				results.append(result["name"])
				frappe.db.commit()
				return "submitted"
			except frappe.ValidationError as reason:
				print(f"Closed GRN {label} rejection: {reason}")
				return "rejected"

		def cleanup():
			for grn_name in results:
				grn = frappe.get_doc("YRP Goods Received Note", grn_name)
				if grn.docstatus == 1:
					grn.cancel()
				frappe.delete_doc("YRP Goods Received Note", grn_name, force=True)
				frappe.db.delete("YRP Stock Ledger Entry", {"voucher_type": "YRP Goods Received Note", "voucher_no": grn_name})
			for plan_name in frappe.get_all("SD YRP Sewing Plan", filters={"work_order": name}, pluck="name"):
				for entry_name in frappe.get_all("SD YRP Sewing Plan Entry Detail", filters={"sewing_plan": plan_name}, pluck="name"):
					frappe.db.delete("SD YRP Sewing Plan Detail", {"parent": entry_name})
				frappe.db.delete("SD YRP Sewing Plan Entry Detail", {"sewing_plan": plan_name})
			frappe.db.delete("SD YRP Sewing Plan", {"work_order": name})
			clone = frappe.get_doc("YRP Work Order", name)
			for field in clone.meta.get_table_fields():
				frappe.db.delete(field.options, {"parent": name, "parenttype": "YRP Work Order"})
			frappe.db.delete("YRP Work Order", {"name": name})
			frappe.db.commit()

		with ThreadPoolExecutor(max_workers=2) as executor:
			try:
				supplier, groups, selected = executor.submit(connection, setup).result(30)
				with patch.object(database_class, "sql", new=observe_sql), \
					patch.object(service, "_get_closed_sewing_work_order", new=observe_lock):
					first = executor.submit(connection, lambda: create("first", supplier, groups))
					second = executor.submit(connection, lambda: create("second", supplier, groups))
					self.assertEqual([first.result(30), second.result(30)], ["submitted", "rejected"])
				self.assertEqual(balances["first"], 1)
				self.assertLessEqual(balances["second"], 0)
				self.assertEqual(len(results), 1)
				self.assertEqual(executor.submit(connection, lambda: frappe.db.count(
					"YRP Goods Received Note", {"against_id": name, "docstatus": 1})).result(30), 1)
				print(f"Closed GRN race: first pending={balances['first']}, second locked pending={balances['second']}; one submitted, one rejected")
			finally:
				executor.submit(connection, cleanup).result(30)


class TestSewingCancellationConcurrency(IntegrationTestCase):
	# A separate class transaction prevents prior savepoint rollbacks retaining
	# InnoDB gap locks that would block these independently committed fixtures.
	def test_concurrent_cancellations_serialize_supplier_scope(self):
		"""Two real request transactions cancel different plans and always roll back."""
		site, sites_path = frappe.local.site, frappe.local.sites_path
		previous_days = cint(frappe.db.get_single_value("SD YRP MRP Settings", "previous_day_entries"))
		self.assertGreater(previous_days, 0)
		suffix = frappe.generate_hash(length=12)
		supplier = f"Sewing concurrent {suffix}"
		plans = [f"SEWING-CONCURRENT-{suffix}-A", f"SEWING-CONCURRENT-{suffix}-B"]
		entries = [f"SEWING-CONCURRENT-{suffix}-ENTRY-A", f"SEWING-CONCURRENT-{suffix}-ENTRY-B"]
		old_entry = f"SEWING-CONCURRENT-{suffix}-OLD"
		latest_date = add_days("2090-01-01", previous_days)

		def connection(operation):
			frappe.init(site, sites_path=sites_path)
			frappe.connect()
			frappe.flags.in_test = True
			try:
				return operation()
			finally:
				frappe.db.rollback()
				frappe.destroy()

		def setup():
			group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
			frappe.get_doc(
				{"doctype": "Supplier", "supplier_name": supplier, "supplier_group": group, "supplier_type": "Company"}
			).insert(set_name=supplier)
			for name in plans:
				frappe.get_doc(
					{"doctype": "SD YRP Sewing Plan", "naming_series": "SP-2526-", "supplier": supplier}
				).insert(set_name=name)
			for name, plan in zip(entries, plans, strict=True):
				frappe.get_doc(
					{"doctype": "SD YRP Sewing Plan Entry Detail", "sewing_plan": plan, "entry_date": latest_date}
				).insert(set_name=name)
			for index in range(previous_days):
				frappe.get_doc(
					{
						"doctype": "SD YRP Sewing Plan Entry Detail",
						"sewing_plan": plans[0],
						"entry_date": add_days("2090-01-01", index),
					}
				).insert(set_name=f"SEWING-CONCURRENT-{suffix}-DATE-{index}")
			frappe.get_doc(
				{"doctype": "SD YRP Sewing Plan Entry Detail", "sewing_plan": plans[0], "entry_date": "2080-01-01"}
			).insert(set_name=old_entry)
			frappe.db.commit()

		def cleanup():
			# Exact unique fixture names; no audit rows or global naming counters are created.
			frappe.db.delete("SD YRP Sewing Plan Entry Detail", {"sewing_plan": ["in", plans]})
			frappe.db.delete("SD YRP Sewing Plan", {"name": ["in", plans]})
			frappe.db.delete("Supplier", {"name": supplier})
			frappe.db.commit()

		start = threading.Barrier(2)
		supplier_overlap = threading.Barrier(2)
		legacy_overlap = threading.Barrier(2)
		progress = threading.local()
		database_class = type(frappe.local.db)
		original_sql = database_class.sql

		def overlap_legacy_date_read(database, query, *args, **kwargs):
			# Force the former ordering defect after both requests own their target locks.
			# Every query still executes against MariaDB; no rows or safety checks are mocked.
			if isinstance(query, str) and "for update" in query.lower():
				progress.locks.append(query)
				if "from `tabSupplier` where name =" in query and not progress.supplier_attempted:
					progress.supplier_attempted = True
					supplier_overlap.wait(timeout=10)
			if (
				isinstance(query, str)
				and "select distinct entry.entry_date" in query.lower()
				and not getattr(progress, "overlapped", False)
			):
				progress.overlapped = True
				legacy_overlap.wait(timeout=10)
			return original_sql(database, query, *args, **kwargs)

		def cancel(name):
			progress.overlapped = False
			progress.locks = []
			progress.supplier_attempted = False
			start.wait(timeout=10)
			cancel_sewing_plan_entry(name)
			self.assertIn("from `tabSupplier` where name =", progress.locks[0])
			self.assertIn("from `tabSD YRP Sewing Plan`", progress.locks[1])
			self.assertIn("from `tabSD YRP Sewing Plan Entry Detail`", progress.locks[2])
			deleted = not frappe.db.exists("SD YRP Sewing Plan Entry Detail", name)
			try:
				cancel_sewing_plan_entry(old_entry)
			except frappe.ValidationError:
				blocked = bool(frappe.db.exists("SD YRP Sewing Plan Entry Detail", old_entry))
			else:
				blocked = False
			return deleted, blocked

		with ThreadPoolExecutor(max_workers=2) as executor:
			try:
				executor.submit(connection, setup).result(timeout=30)
				with patch.object(database_class, "sql", new=overlap_legacy_date_read):
					requests = [executor.submit(connection, lambda name=name: cancel(name)) for name in entries]
					outcomes = [request.result(timeout=30) for request in requests]
				self.assertEqual(outcomes, [(True, True), (True, True)])
				self.assertEqual(
					executor.submit(
						connection,
						lambda: [bool(frappe.db.exists("SD YRP Sewing Plan Entry Detail", name)) for name in entries],
					).result(timeout=30),
					[True, True],
				)
			finally:
				executor.submit(connection, cleanup).result(timeout=30)

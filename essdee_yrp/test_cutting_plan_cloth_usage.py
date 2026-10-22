from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.attribute_links import value as attribute_value

from essdee_yrp.cutting.cloth_usage import recompute_cutting_plan_cloth_usage
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as laysheet_module
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	_save_laysheet_terminal_transition,
	update_cutting_plan,
	validate_cutting_plan_cloth_balance,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import calc
from essdee_yrp.essdee_yrp.doctype.sd_yrp_recut_and_print_panel import (
	sd_yrp_recut_and_print_panel as recut_module,
)


def _laysheet(used_weight, accessory_weight=0):
	return SimpleNamespace(
		name="CLS-TEST",
		cutting_laysheet_details=[
			SimpleNamespace(colour="Red", cloth_type="Main", actual_dia="26 Dia", used_weight=used_weight)
		],
		cutting_laysheet_accessory_details=[
			SimpleNamespace(colour="Red", cloth_type="Main", actual_dia="26 Dia", weight=accessory_weight)
		],
	)


def _plan(weight, used_weight):
	row = SimpleNamespace(
		colour="Red",
		cloth_type="Main",
		dia="26 Dia",
		weight=weight,
		used_weight=used_weight,
		balance_weight=weight - used_weight,
	)
	return SimpleNamespace(cutting_plan_cloth_details=[row], save=MagicMock())


def _patch_plan(plan):
	get_doc = frappe.get_doc

	def fake_get_doc(doctype, *args, **kwargs):
		if doctype == "SD YRP Cutting Plan":
			return plan
		return get_doc(doctype, *args, **kwargs)

	return patch.object(frappe, "get_doc", side_effect=fake_get_doc)


class TestBundleGenerationClothBalance(IntegrationTestCase):
	def test_bundle_generation_does_not_persist_cloth_usage(self):
		plan = _plan(weight=250, used_weight=100)
		with _patch_plan(plan):
			validate_cutting_plan_cloth_balance(_laysheet(121, accessory_weight=4), "CP-TEST")
			validate_cutting_plan_cloth_balance(_laysheet(121, accessory_weight=4), "CP-TEST")

		row = plan.cutting_plan_cloth_details[0]
		self.assertEqual(row.used_weight, 100)
		self.assertEqual(row.balance_weight, 150)
		plan.save.assert_not_called()

	def test_bundle_generation_rejects_usage_beyond_received_weight(self):
		plan = _plan(weight=200, used_weight=100)
		with _patch_plan(plan):
			with self.assertRaises(frappe.ValidationError):
				validate_cutting_plan_cloth_balance(_laysheet(98, accessory_weight=4), "CP-TEST")
		plan.save.assert_not_called()


class TestCuttingPlanClothUsageFromLaySheets(IntegrationTestCase):
	"""Used weight is the plan's Label Printed LaySheets counted once, whatever events ran."""

	def test_repeated_label_print_counts_each_laysheet_once(self):
		cutting_plan, laysheet_name = _find_plan_with_printed_laysheets(with_laysheet=True)
		if not cutting_plan:
			self.skipTest("No V3 Cutting Plan with two Label Printed LaySheets is available")
		expected = _expected_used_weights(cutting_plan)
		frappe.db.savepoint("label_print_retry")
		try:
			update_cutting_plan(laysheet_name)
			update_cutting_plan(laysheet_name)
			after = _plan_used_weights(cutting_plan)
		finally:
			frappe.db.rollback(save_point="label_print_retry")

		_assert_usage(self, after, expected)

	def test_bundle_generation_then_print_counts_laysheet_once(self):
		laysheet_name = _find_single_pending_laysheet()
		if not laysheet_name:
			self.skipTest("No V3 Cutting Plan with one Bundles Generated LaySheet is available")
		laysheet = frappe.get_doc("SD YRP Cutting LaySheet", laysheet_name)
		frappe.db.savepoint("generate_then_print")
		try:
			recompute_cutting_plan_cloth_usage(laysheet.cutting_plan)
			validate_cutting_plan_cloth_balance(laysheet, laysheet.cutting_plan)
			update_cutting_plan(laysheet_name)
			while_printing = _plan_used_weights(laysheet.cutting_plan)
			expected_while_printing = _expected_used_weights(laysheet.cutting_plan)
			laysheet.reload()
			laysheet.status = "Label Printed"
			_save_laysheet_terminal_transition(laysheet)
			update_cutting_plan(laysheet_name)
			printed = _plan_used_weights(laysheet.cutting_plan)
			expected_printed = _expected_used_weights(laysheet.cutting_plan)
		finally:
			frappe.db.rollback(save_point="generate_then_print")

		_assert_usage(self, while_printing, expected_while_printing)
		_assert_usage(self, printed, expected_printed)

	def test_two_printed_laysheets_sum_their_used_cloth(self):
		cutting_plan, _laysheet_name = _find_plan_with_printed_laysheets(with_laysheet=True)
		if not cutting_plan:
			self.skipTest("No V3 Cutting Plan with two Label Printed LaySheets is available")
		frappe.db.savepoint("two_laysheets")
		try:
			row = _keep_two_laysheets_cutting(cutting_plan, [(121, 0), (160, 1.5)])
			recompute_cutting_plan_cloth_usage(cutting_plan)
			recompute_cutting_plan_cloth_usage(cutting_plan)
			used_weight, balance_weight = frappe.db.get_value(
				"SD YRP Cutting Plan Cloth Detail", row.name, ["used_weight", "balance_weight"]
			)
		finally:
			frappe.db.rollback(save_point="two_laysheets")

		self.assertAlmostEqual(flt(used_weight), 279.5, places=3)
		self.assertAlmostEqual(flt(balance_weight), flt(row.weight) - 279.5, places=3)


class TestClothUsageRecomputeTriggers(IntegrationTestCase):
	def _laysheet_save(self, before_status, status):
		doc = frappe.new_doc("SD YRP Cutting LaySheet")
		doc.update({"cutting_plan": "CP-TEST", "status": status})
		doc._doc_before_save = frappe._dict(status=before_status)
		with patch.object(laysheet_module, "recompute_cutting_plan_cloth_usage") as recompute:
			doc.on_update()
		return recompute

	def test_label_print_and_revert_recompute_plan_usage(self):
		self._laysheet_save("Bundles Generated", "Label Printed").assert_called_once_with("CP-TEST")
		self._laysheet_save("Label Printed", "Bundles Generated").assert_called_once_with("CP-TEST")
		self._laysheet_save("Label Printed", "Cancelled").assert_called_once_with("CP-TEST")

	def test_unprinted_laysheet_save_leaves_plan_usage(self):
		self._laysheet_save("Completed", "Bundles Generated").assert_not_called()

	def test_recut_submit_and_cancel_recompute_plan_usage(self):
		doc = frappe.new_doc("SD YRP Recut and Print Panel")
		doc.cutting_plan = "CP-TEST"
		with (
			patch.object(recut_module, "recompute_cutting_plan_cloth_usage") as recompute,
			patch.object(recut_module, "make_sl_entries"),
			patch.object(type(doc), "_get_stock_ledger_entries", return_value=[]),
			patch.object(type(doc), "_validate_cutting_plan_balance"),
		):
			doc.on_submit()
			doc.on_cancel()
		self.assertEqual(recompute.call_args_list, [call("CP-TEST"), call("CP-TEST")])


def _assert_usage(test, actual, expected):
	for key, (used_weight, balance_weight) in expected.items():
		test.assertAlmostEqual(actual[key][0], used_weight, places=3, msg=str(key))
		test.assertAlmostEqual(actual[key][1], balance_weight, places=3, msg=str(key))


def _keep_two_laysheets_cutting(cutting_plan, weights):
	"""Leave two Label Printed LaySheets, each cutting one (weight, balance) of the plan's first cloth row."""
	row = frappe.get_all(
		"SD YRP Cutting Plan Cloth Detail",
		filters={"parent": cutting_plan, "parentfield": "cutting_plan_cloth_details"},
		fields=["name", "colour", "cloth_type", "dia", "weight"],
		order_by="idx asc",
		limit=1,
	)[0]
	laysheets = frappe.get_all(
		"SD YRP Cutting LaySheet",
		filters={"cutting_plan": cutting_plan, "status": "Label Printed"},
		pluck="name",
		limit=2,
	)
	frappe.db.sql(
		"""UPDATE `tabSD YRP Cutting LaySheet` SET status = 'Cancelled'
		WHERE cutting_plan = %s AND name NOT IN %s""",
		(cutting_plan, tuple(laysheets)),
	)
	for doctype in ("SD YRP Cutting LaySheet Detail", "SD YRP Cutting LaySheet Accessory Detail"):
		frappe.db.delete(doctype, {"parent": ["in", laysheets]})
	for laysheet, (weight, balance_weight) in zip(laysheets, weights, strict=True):
		frappe.get_doc(
			{
				"doctype": "SD YRP Cutting LaySheet Detail",
				"name": frappe.generate_hash(length=12),
				"parent": laysheet,
				"parenttype": "SD YRP Cutting LaySheet",
				"parentfield": "cutting_laysheet_details",
				"colour": row.colour,
				"cloth_type": row.cloth_type,
				"dia": row.dia,
				"actual_dia": row.dia,
				"weight": weight,
				"balance_weight": balance_weight,
			}
		).db_insert()
	return row


def _find_single_pending_laysheet():
	rows = frappe.db.sql(
		"""
		SELECT laysheet.name
		FROM `tabSD YRP Cutting LaySheet` laysheet
		JOIN `tabSD YRP Cutting Plan` plan ON plan.name = laysheet.cutting_plan
		WHERE laysheet.status = 'Bundles Generated' AND plan.docstatus = 1 AND plan.version = 'V3'
			AND laysheet.is_manual_entry = 0 AND IFNULL(laysheet.cutting_bulk_lay_sheet, '') = ''
			AND (
				SELECT COUNT(*) FROM `tabSD YRP Cutting LaySheet` other
				WHERE other.cutting_plan = laysheet.cutting_plan
					AND other.status IN ('Bundles Generated', 'Approval Pending')
			) = 1
		ORDER BY laysheet.creation DESC
		LIMIT 1
		"""
	)
	return rows[0][0] if rows else None


def _plan_used_weights(cutting_plan):
	plan = frappe.get_doc("SD YRP Cutting Plan", cutting_plan)
	return {
		_key(row.colour, row.cloth_type, row.dia): (flt(row.used_weight, 3), flt(row.balance_weight, 3))
		for row in plan.cutting_plan_cloth_details
	}


class TestCalculateLaySheetsRepairsUsedWeight(IntegrationTestCase):
	def test_planner_without_laysheet_write_recomputes_double_counted_plan(self):
		cutting_plan = _find_plan_with_printed_laysheets()
		if not cutting_plan:
			self.skipTest("No V3 Cutting Plan with two Label Printed LaySheets is available")
		expected = _expected_used_weights(cutting_plan)
		frappe.db.savepoint("calc_repair")
		try:
			frappe.db.sql(
				"""UPDATE `tabSD YRP Cutting Plan Cloth Detail` SET used_weight = used_weight * 2 + 158
				WHERE parent = %s AND parentfield = 'cutting_plan_cloth_details'""",
				cutting_plan,
			)
			frappe.set_user(_planner_without_laysheet_write())
			calc(cutting_plan)
			first = _plan_used_weights(cutting_plan)
			calc(cutting_plan)
			second = _plan_used_weights(cutting_plan)
		finally:
			frappe.set_user("Administrator")
			frappe.db.rollback(save_point="calc_repair")

		_assert_usage(self, first, expected)
		_assert_usage(self, second, expected)

	def test_recompute_repairs_double_counted_plan_idempotently(self):
		cutting_plan = _find_plan_with_printed_laysheets()
		if not cutting_plan:
			self.skipTest("No V3 Cutting Plan with two Label Printed LaySheets is available")
		expected = _expected_used_weights(cutting_plan)
		frappe.db.savepoint("recompute_repair")
		try:
			frappe.db.sql(
				"""UPDATE `tabSD YRP Cutting Plan Cloth Detail` SET used_weight = used_weight * 2 + 158
				WHERE parent = %s""",
				cutting_plan,
			)
			recompute_cutting_plan_cloth_usage(cutting_plan)
			first = _plan_used_weights(cutting_plan)
			recompute_cutting_plan_cloth_usage(cutting_plan)
			second = _plan_used_weights(cutting_plan)
		finally:
			frappe.db.rollback(save_point="recompute_repair")

		_assert_usage(self, first, expected)
		_assert_usage(self, second, expected)


def _find_plan_with_printed_laysheets(with_laysheet=False):
	rows = frappe.db.sql(
		"""
		SELECT plan.name, MAX(laysheet.name)
		FROM `tabSD YRP Cutting Plan` plan
		JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.cutting_plan = plan.name
		WHERE plan.docstatus = 1 AND plan.version = 'V3' AND laysheet.status = 'Label Printed'
			AND laysheet.is_manual_entry = 0
			AND NOT EXISTS (
				SELECT 1 FROM `tabSD YRP Recut and Print Panel` recut
				WHERE recut.cutting_plan = plan.name AND recut.docstatus = 1
			)
		GROUP BY plan.name
		HAVING COUNT(*) >= 2
		ORDER BY plan.creation DESC
		LIMIT 1
		"""
	)
	if with_laysheet:
		return rows[0] if rows else (None, None)
	return rows[0][0] if rows else None


def _expected_used_weights(cutting_plan):
	weights = {
		_key(row.colour, row.cloth_type, row.dia): flt(row.weight)
		for row in frappe.get_doc("SD YRP Cutting Plan", cutting_plan).cutting_plan_cloth_details
	}
	expected = dict.fromkeys(weights, 0.0)
	details = frappe.db.sql(
		"""
		SELECT detail.colour, detail.cloth_type, detail.actual_dia, detail.weight - detail.balance_weight
		FROM `tabSD YRP Cutting LaySheet Detail` detail
		JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.name = detail.parent
		WHERE laysheet.cutting_plan = %(plan)s AND laysheet.status = 'Label Printed'
		UNION ALL
		SELECT accessory.colour, accessory.cloth_type, accessory.actual_dia, accessory.weight
		FROM `tabSD YRP Cutting LaySheet Accessory Detail` accessory
		JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.name = accessory.parent
		WHERE laysheet.cutting_plan = %(plan)s AND laysheet.status = 'Label Printed'
		""",
		{"plan": cutting_plan},
	)
	for colour, cloth_type, dia, used_weight in details:
		key = _key(colour, cloth_type, dia)
		if key in expected:
			expected[key] += flt(used_weight)
	return {key: (used, weights[key] - used) for key, used in expected.items()}


def _key(colour, cloth_type, dia):
	return (attribute_value(colour), cloth_type, attribute_value(dia))


def _planner_without_laysheet_write():
	email = "cutting.plan.calc.planner@example.test"
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Calc Planner", "send_welcome_email": 0}
		)
		user.append("roles", {"role": "Production Planner"})
		user.insert(ignore_permissions=True)
	return email

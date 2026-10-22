from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	update_cutting_plan,
	validate_cutting_plan_cloth_balance,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import calc


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


class TestCuttingPlanUsedWeightFlow(IntegrationTestCase):
	def test_generate_then_print_counts_laysheet_cloth_once(self):
		laysheet_name = _find_single_pending_laysheet()
		if not laysheet_name:
			self.skipTest("No V3 Cutting Plan with one Bundles Generated LaySheet is available")
		laysheet = frappe.get_doc("SD YRP Cutting LaySheet", laysheet_name)
		frappe.db.savepoint("cloth_usage_flow")
		try:
			calc(laysheet.cutting_plan)
			before = _plan_used_weights(laysheet.cutting_plan)
			validate_cutting_plan_cloth_balance(laysheet, laysheet.cutting_plan)
			update_cutting_plan(laysheet_name)
			after = _plan_used_weights(laysheet.cutting_plan)
		finally:
			frappe.db.rollback(save_point="cloth_usage_flow")

		for row in laysheet.cutting_laysheet_details:
			key = (row.colour, row.cloth_type, row.actual_dia)
			self.assertAlmostEqual(after[key], before[key] + flt(row.used_weight), places=3)


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
		(row.colour, row.cloth_type, row.dia): flt(row.used_weight, 3)
		for row in plan.cutting_plan_cloth_details
	}

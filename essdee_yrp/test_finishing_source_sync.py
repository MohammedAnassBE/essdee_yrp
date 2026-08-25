from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.finishing.rebuild import (
	_process_matches_configured,
	sync_finishing_plans_from_work_order,
)


class TestFinishingSourceSync(IntegrationTestCase):
	@patch("essdee_yrp.finishing.rebuild.rebuild_finishing_plan")
	@patch(
		"essdee_yrp.finishing.rebuild.get_configured_cutting_process",
		return_value="Cutting",
	)
	@patch("essdee_yrp.finishing.rebuild.frappe.get_all")
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_single_value")
	def test_submitted_stitching_update_rebuilds_every_plan_for_the_lot(
		self, get_single_value, get_all, _cutting_process, rebuild_plan
	):
		get_single_value.return_value = "Stitching"
		get_all.return_value = [
			frappe._dict(name="FP-1", production_detail="IPD-1"),
			frappe._dict(name="FP-2", production_detail="IPD-2"),
		]
		work_order = _work_order(process_name="Stitching")

		updated = sync_finishing_plans_from_work_order(work_order)

		self.assertEqual(updated, ["FP-1", "FP-2"])
		rebuild_plan.assert_has_calls([
			(("FP-1",), {"check_permission": False}),
			(("FP-2",), {"check_permission": False}),
		])

	@patch("essdee_yrp.finishing.rebuild.rebuild_finishing_plan")
	@patch(
		"essdee_yrp.finishing.rebuild.get_configured_cutting_process",
		return_value="Configured Cutting",
	)
	@patch("essdee_yrp.finishing.rebuild.frappe.get_all")
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_single_value")
	def test_cancelled_configured_cutting_work_order_rebuilds_the_plan(
		self, get_single_value, get_all, _cutting_process, rebuild_plan
	):
		get_single_value.return_value = "Stitching"
		get_all.return_value = [frappe._dict(name="FP-1", production_detail="IPD-1")]
		work_order = _work_order(
			process_name="Configured Cutting",
			docstatus=2,
		)

		self.assertEqual(sync_finishing_plans_from_work_order(work_order), ["FP-1"])
		rebuild_plan.assert_called_once_with("FP-1", check_permission=False)

	@patch("essdee_yrp.finishing.rebuild.rebuild_finishing_plan")
	@patch(
		"essdee_yrp.finishing.rebuild.get_configured_cutting_process",
		return_value="Cutting",
	)
	@patch("essdee_yrp.finishing.rebuild.frappe.get_all")
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_value", return_value=0)
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_single_value")
	def test_unrelated_process_does_not_touch_finishing_plan(
		self, get_single_value, _get_value, get_all, _cutting_process, rebuild_plan
	):
		get_single_value.return_value = "Stitching"
		get_all.return_value = [frappe._dict(name="FP-1", production_detail="IPD-1")]

		self.assertEqual(
			sync_finishing_plans_from_work_order(_work_order(process_name="Printing")),
			[],
		)
		rebuild_plan.assert_not_called()

	def test_generic_after_submit_hook_is_not_used_as_completion_signal(self):
		from essdee_yrp import hooks

		self.assertNotIn("on_update_after_submit", hooks.doc_events["Work Order"])

	@patch("essdee_yrp.finishing.rebuild.frappe.db.exists", return_value=True)
	@patch("essdee_yrp.finishing.rebuild.frappe.db.get_value", return_value=1)
	def test_process_group_matches_its_configured_child(self, _get_value, _exists):
		self.assertTrue(_process_matches_configured("Cutting Group", "Cutting"))


def _work_order(**values):
	data = {
		"name": "WO-1",
		"docstatus": 1,
		"is_rework": 0,
		"lot": "LOT-1",
		"process_name": "Stitching",
	}
	data.update(values)
	doc = frappe._dict(data)
	doc.get = lambda key, default=None: doc[key] if key in doc else default
	return doc

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.work_order import calculate_fabric_deliverables
from essdee_yrp.fabric_store.documents import work_order as workspace
from essdee_yrp.fabric_store.documents.work_order import execute_work_order_command

MESSAGE = (
	"Rework Work Orders keep the source receipt and return contract created "
	"by Rework. Calculate Fabric Deliverables is not available for rework."
)


class TestReworkCalculateGuard(TestCase):
	def setUp(self):
		self.work_order = Mock(name="ZZ TEST Rework Work Order")
		self.work_order.docstatus = 0
		self.work_order.get.side_effect = lambda field: field == "is_rework"
		self.enterContext(patch.object(frappe, "get_doc", return_value=self.work_order))
		self.enterContext(patch("essdee_yrp.api.work_order._lock_calculation_target"))
		self.enterContext(patch("essdee_yrp.api.work_order._guard_not_modified"))
		self.lot = self.enterContext(patch("essdee_yrp.api.work_order._get_lot"))
		self.enterContext(patch.object(frappe, "throw", side_effect=self.throw))

	@staticmethod
	def throw(message, exception=frappe.ValidationError):
		raise exception(message)

	def test_direct_calculate_rejects_before_rows_are_touched(self):
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			calculate_fabric_deliverables("ZZ TEST Rework", [])
		self.lot.assert_not_called()
		self.work_order.save.assert_not_called()
		self.work_order.set.assert_not_called()

	def test_workspace_command_reaches_same_rework_guard(self):
		with patch.object(workspace, "assert_expected_modified"):
			with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
				execute_work_order_command("ZZ TEST Rework", "calculate_fabric", payload={"rows": []})
		self.lot.assert_not_called()
		self.work_order.save.assert_not_called()
		self.work_order.set.assert_not_called()


class TestWorkOrderReworkCalculate(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.work_order = frappe.get_doc({
			"doctype": "YRP Work Order", "name": f"ZZ TEST Rework {frappe.generate_hash(length=6)}",
			"docstatus": 0, "is_rework": 1,
			"deliverables": [{"qty": 7, "is_calculated": 1, "source_grn": "ZZ TEST Source Receipt"}],
			"receivables": [{"qty": 5, "is_calculated": 1}],
		})
		self.work_order.db_insert()
		for row in self.work_order.get_all_children():
			row.db_insert()
		self.before = self.work_order.reload().as_json()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_direct_calculate_rejects_rework_without_changing_rows(self):
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			calculate_fabric_deliverables(self.work_order.name, [])
		self.assertEqual(self.work_order.reload().as_json(), self.before)

	def test_workspace_calculate_rejects_rework_without_changing_rows(self):
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			execute_work_order_command(
				self.work_order.name, "calculate_fabric", payload={"rows": []},
				expected_modified=self.work_order.modified,
			)
		self.assertEqual(self.work_order.reload().as_json(), self.before)

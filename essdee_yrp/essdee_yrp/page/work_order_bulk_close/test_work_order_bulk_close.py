import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close import (
	get_open_work_orders,
	get_work_order_close_details,
)


class TestWorkOrderBulkClose(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		work_orders = frappe.get_all(
			'YRP Work Order',
			filters={"docstatus": 1, "open_status": "Open"},
			fields=["name", "supplier"],
			limit=1,
		)
		if not work_orders:
			self.skipTest("Bulk-close source-record parity runs after data migration")
		self.work_order = work_orders[0]

	def test_open_work_orders_are_scoped_to_supplier(self):
		rows = get_open_work_orders(self.work_order.supplier)
		self.assertTrue(any(row.name == self.work_order.name for row in rows))
		self.assertTrue(all(row.difference == row.total_delivered - row.total_received for row in rows))

	def test_close_preview_uses_f16_summary_and_debit_shape(self):
		result = get_work_order_close_details(self.work_order.name)
		self.assertEqual(
			set(result), {"summary", "recut_details", "debits"}
		)
		self.assertEqual(
			result["summary"]["work_order_docstatus"], 1
		)
		self.assertTrue(all("name" in row for row in result["debits"]))

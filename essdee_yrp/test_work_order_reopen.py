from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.stock.utils import get_conversion_factor, get_stock_balance
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _get_warehouse_for_supplier
from yrp.yrp.doctype.yrp_purchase_invoice.test_yrp_purchase_invoice import (
	_work_order_for_invoice,
	_work_order_grn,
)
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

from essdee_yrp.work_order_close import close_work_order
from essdee_yrp.work_order_reopen import reopen_work_order


class TestWorkOrderReopen(IntegrationTestCase):
	"""Close -> Reopen round trips on throwaway Work Orders; all rolled back."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		real_get_single_value = frappe.db.get_single_value

		def get_single_value(doctype, fieldname, *args, **kwargs):
			if doctype == "YRP Settings" and fieldname == "work_order_closing_approver_role":
				return "System Manager"
			return real_get_single_value(doctype, fieldname, *args, **kwargs)

		patcher = patch.object(frappe.db, "get_single_value", side_effect=get_single_value)
		patcher.start()
		cls.addClassCleanup(patcher.stop)

	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")

	def test_only_system_manager_can_reopen(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"reopen-{frappe.generate_hash(length=8)}@example.com",
				"first_name": "Reopen Test",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			reopen_work_order("WO-DOES-NOT-EXIST")

	def test_open_work_order_cannot_be_reopened(self):
		work_order = _work_order_for_invoice(qty=1)
		with self.assertRaisesRegex(frappe.ValidationError, "Only a closed Work Order"):
			reopen_work_order(work_order.name)

	def test_close_then_reopen_restores_supplier_stock(self):
		work_order, bucket = self._closable_work_order()
		opening = self._balance(bucket)

		closed = close_work_order(work_order.name, sd_close_reason="NA")
		self.assertGreater(closed["deducted_qty"], 0)
		self.assertAlmostEqual(self._balance(bucket), opening - closed["deducted_qty"])

		result = reopen_work_order(work_order.name)

		self.assertAlmostEqual(self._balance(bucket), opening)
		self.assertAlmostEqual(result["restored_qty"], closed["deducted_qty"])
		receipt = frappe.get_doc("YRP Stock Entry", result["stock_entry"])
		self.assertEqual((receipt.purpose, receipt.docstatus), ("Material Receipt", 1))
		self.assertEqual(receipt.to_warehouse, bucket["warehouse"])
		self.assertEqual((receipt.against, receipt.against_id), ("YRP Work Order", work_order.name))
		row = receipt.items[0]
		self.assertEqual(row.item, bucket["item"])
		self.assertEqual(row.lot, bucket["dimensions"]["lot"])
		self.assertEqual(row.received_type, bucket["dimensions"]["received_type"])
		self.assertAlmostEqual(flt(row.rate), 7)

		work_order.reload()
		self.assertEqual(work_order.open_status, "Open")
		self.assertNotEqual(work_order.status, "Closed")
		self.assertFalse(work_order.closed_by)
		self.assertFalse(work_order.sd_close_reason)
		self.assertEqual(flt(work_order.deliverables[0].stock_update), 0)
		self.assertGreater(flt(work_order.total_quantity), 0)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "YRP Work Order",
					"reference_name": work_order.name,
					"content": ["like", f"%{receipt.name}%"],
				},
			)
		)

		with self.assertRaisesRegex(frappe.ValidationError, "Only a closed Work Order"):
			reopen_work_order(work_order.name)

	def test_second_close_and_reopen_reverse_only_the_new_close(self):
		work_order, bucket = self._closable_work_order()
		opening = self._balance(bucket)
		close_work_order(work_order.name, sd_close_reason="NA")
		first = reopen_work_order(work_order.name)

		closed = close_work_order(work_order.name, sd_close_reason="NA")
		self.assertAlmostEqual(closed["deducted_qty"], first["restored_qty"])
		second = reopen_work_order(work_order.name)

		self.assertAlmostEqual(second["restored_qty"], first["restored_qty"])
		self.assertAlmostEqual(self._balance(bucket), opening)

	def test_reopen_fails_loudly_when_close_ledger_is_missing(self):
		work_order, _bucket = self._closable_work_order()
		close_work_order(work_order.name, sd_close_reason="NA")
		frappe.db.set_value(
			"YRP Stock Ledger Entry",
			{"voucher_type": "YRP Work Order", "voucher_no": work_order.name},
			"is_cancelled",
			1,
		)
		with self.assertRaisesRegex(frappe.ValidationError, "close stock ledger"):
			reopen_work_order(work_order.name)
		self.assertEqual(frappe.db.get_value("YRP Work Order", work_order.name, "open_status"), "Close")

	def _closable_work_order(self):
		"""Submitted WO with 3 of 5 pieces delivered and that leftover held at the supplier."""
		work_order = _work_order_for_invoice(qty=5)
		row = work_order.deliverables[0]
		warehouse = _get_warehouse_for_supplier(work_order.supplier)
		dimensions = _stock_dimension_values(work_order, row)
		stock_uom = get_conversion_factor(row.item_variant, row.uom).get("stock_uom") or row.uom
		receipt = frappe.new_doc("YRP Stock Entry")
		receipt.update({"purpose": "Material Receipt", "to_warehouse": warehouse})
		receipt.append(
			"items", {"item": row.item_variant, "qty": 3, "uom": stock_uom, "rate": 7, **dimensions}
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()
		frappe.db.set_value("YRP Work Order Deliverables", row.name, "pending_quantity", 2)
		_work_order_grn(work_order, qty=5)
		work_order.reload()
		return work_order, {"item": row.item_variant, "warehouse": warehouse, "dimensions": dimensions}

	def _balance(self, bucket):
		return flt(get_stock_balance(bucket["item"], bucket["warehouse"], **bucket["dimensions"]))

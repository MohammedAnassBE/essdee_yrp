from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.yrp_debit import yrp_debit
from yrp.yrp.doctype.yrp_purchase_invoice.test_yrp_purchase_invoice import _work_order_for_invoice

from essdee_yrp.accounts.purchase_invoice_workspace import _debit_summary
from essdee_yrp.api.lifecycle import cancel_document


class TestDebitCancelFromWeb(FrappeTestCase):
	"""Cancelling a debit through the /web lifecycle endpoint drops it from Purchase Invoice debits."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		patcher = patch.object(yrp_debit, "_user_has_settings_role", return_value=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_cancelled_debit_leaves_purchase_invoice_debit_summary(self):
		work_order = _work_order_for_invoice(qty=1)
		debit = yrp_debit.create_debit(work_order.name, debit_no="D-CANCEL", debit_value=10, reason="Short")
		invoice = SimpleNamespace(get=lambda key, default=None: [{"work_order": work_order.name}] if key == "pi_work_order_billed_details" else default)
		self.assertEqual([row.name for row in _debit_summary(invoice)], [debit.name])
		self.assertEqual(debit.status, "Approved")

		result = cancel_document("YRP Debit", debit.name, str(frappe.db.get_value("YRP Debit", debit.name, "modified")))

		self.assertEqual((result["docstatus"], result["status"]), (2, "Cancelled"))
		self.assertEqual(frappe.db.get_value("YRP Debit", debit.name, ["docstatus", "status"]), (2, "Cancelled"))
		self.assertEqual(_debit_summary(invoice), [])

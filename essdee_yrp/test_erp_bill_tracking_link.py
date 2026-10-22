from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.yrp_bill_tracking.test_yrp_bill_tracking import _bill, _received_via
from yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn import _default_received_type

HOOK_MODULES = ("essdee.", "essdee_yrp.")


def _erp_invoice(bill):
	"""Insert a bare submitted ERPNext Purchase Invoice row created from ``bill``."""
	invoice = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"name": f"_T-ERP-PI-{frappe.generate_hash(length=8)}",
			"supplier": bill.supplier,
			"company": frappe.db.get_value("Company", {}, "name"),
			"bill_no": bill.bill_no,
			"bill_date": bill.bill_date,
			"vendor_bill_tracking": bill.name,
			"docstatus": 1,
		}
	)
	invoice.db_insert()
	return frappe.get_doc("Purchase Invoice", invoice.name)


def _run_bill_tracking_hooks(invoice, *events):
	"""Run the Essdee and Essdee YRP Purchase Invoice hooks in Frappe's app order."""
	doc_events = frappe.get_hooks("doc_events").get("Purchase Invoice", {})
	for event in events:
		for method in doc_events.get(event, []):
			if method.startswith(HOOK_MODULES):
				frappe.get_attr(method)(invoice, event)


class TestErpBillTrackingLink(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_default_received_type()
		_received_via("HO")

	def setUp(self):
		self.bill = _bill()
		self.bill.submit()
		self.invoice = _erp_invoice(self.bill)

	def test_hooks_run_after_the_legacy_essdee_callback(self):
		doc_events = frappe.get_hooks("doc_events")["Purchase Invoice"]
		on_submit = doc_events["on_submit"]
		on_cancel = doc_events["on_cancel"]
		self.assertLess(
			on_submit.index("essdee.essdee.utils.mrp.purchase_invoice.vendor_bill_on_submit"),
			on_submit.index("essdee_yrp.erp_purchase_invoice.close_bill_tracking_on_erp_submit"),
		)
		self.assertLess(
			on_cancel.index("essdee.essdee.utils.mrp.purchase_invoice.vendor_bill_on_cancel"),
			on_cancel.index("essdee_yrp.erp_purchase_invoice.reopen_bill_tracking_on_erp_cancel"),
		)

	def test_submit_links_and_closes_bill_and_cancel_reopens_it(self):
		with patch("essdee.essdee.utils.mrp.mrp_utilities.requests.post") as remote_post:
			_run_bill_tracking_hooks(self.invoice, "before_submit", "on_submit")
		remote_post.assert_not_called()

		bill = frappe.get_doc("YRP Bill Tracking", self.bill.name)
		self.assertEqual(bill.form_status, "Closed")
		self.assertEqual(bill.erp_purchase_invoice, self.invoice.name)
		self.assertEqual(bill.bill_tracking_history[-1].action, "Close")
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", self.invoice.name, "vendor_bill_tracking"),
			self.bill.name,
		)

		self.invoice.docstatus = 2
		with patch("essdee.essdee.utils.mrp.mrp_utilities.requests.post") as remote_post:
			_run_bill_tracking_hooks(self.invoice, "before_cancel", "on_cancel")
		remote_post.assert_not_called()

		bill = frappe.get_doc("YRP Bill Tracking", self.bill.name)
		self.assertEqual(bill.form_status, "Reopen")
		self.assertIsNone(bill.erp_purchase_invoice)
		self.assertEqual(bill.bill_tracking_history[-1].action, "Reopen")
		self.assertIn(self.invoice.name, bill.bill_tracking_history[-1].remarks)
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", self.invoice.name, "vendor_bill_tracking"),
			self.bill.name,
		)

	def test_submitter_needs_no_bill_tracking_write_permission(self):
		self.assertFalse(frappe.has_permission("YRP Bill Tracking", "write", user="Guest"))
		frappe.set_user("Guest")
		try:
			with patch("essdee.essdee.utils.mrp.mrp_utilities.requests.post"):
				_run_bill_tracking_hooks(self.invoice, "before_submit", "on_submit")
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("YRP Bill Tracking", self.bill.name, "form_status"), "Closed")

	def test_unknown_bill_tracking_keeps_the_legacy_callback(self):
		frappe.db.set_value("Purchase Invoice", self.invoice.name, "vendor_bill_tracking", "VBT-MISSING")
		self.invoice.reload()
		_run_bill_tracking_hooks(self.invoice, "before_submit")
		self.assertEqual(self.invoice.vendor_bill_tracking, "VBT-MISSING")

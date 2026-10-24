from unittest import TestCase

from frappe import _dict

from essdee_yrp.migration import repair_bill_tracking_links as repair


def _bill(**values):
	return _dict({"name": "VBT-1", "docstatus": 1, "form_status": "Assigned", **values})


def _yrp(name="MPI-1", docstatus=1, erp_inv_name=None):
	return _dict(name=name, docstatus=docstatus, erp_inv_name=erp_inv_name)


def _erp(name="PI-1", docstatus=1, mrp_purchase_invoice_name=None):
	return _dict(name=name, docstatus=docstatus, mrp_purchase_invoice_name=mrp_purchase_invoice_name)


class TestRepairBillTrackingSelection(TestCase):
	def test_submitted_yrp_invoice_closes_with_its_erp_invoice(self):
		plan = repair.get_repair_plan(
			_bill(), [_yrp(erp_inv_name="PI-1")], [_erp(mrp_purchase_invoice_name="MPI-1")]
		)
		self.assertEqual(plan["action"], repair.CLOSE_YRP)
		self.assertEqual((plan["purchase_invoice"], plan["erp_purchase_invoice"]), ("MPI-1", "PI-1"))

	def test_draft_yrp_invoice_only_links(self):
		plan = repair.get_repair_plan(_bill(), [_yrp(docstatus=0)], [])
		self.assertEqual(plan["action"], repair.LINK_YRP_DRAFT)
		self.assertIsNone(plan["erp_purchase_invoice"])

	def test_direct_submitted_erp_invoice_closes(self):
		plan = repair.get_repair_plan(_bill(), [], [_erp()])
		self.assertEqual(plan["action"], repair.CLOSE_ERP)
		self.assertEqual(plan["erp_purchase_invoice"], "PI-1")

	def test_skips_unsafe_cases(self):
		cases = {
			"not submitted": (_bill(docstatus=2), [_yrp()], []),
			"already Closed": (_bill(form_status="Closed"), [], [_erp()]),
			"several": (_bill(), [_yrp(), _yrp("MPI-2")], []),
			"several erp": (_bill(), [], [_erp(), _erp("PI-2")]),
			"not one pair": (_bill(), [_yrp(erp_inv_name="PI-9")], [_erp()]),
			"draft yrp with erp": (_bill(), [_yrp(docstatus=0)], [_erp()]),
			"erp missing": (_bill(), [_yrp(erp_inv_name="PI-1")], []),
			"draft erp": (_bill(), [], [_erp(docstatus=0)]),
			"foreign yrp": (_bill(), [], [_erp(mrp_purchase_invoice_name="MPI-7")]),
		}
		for label, (bill, yrp_invoices, erp_invoices) in cases.items():
			with self.subTest(label):
				plan = repair.get_repair_plan(bill, yrp_invoices, erp_invoices)
				self.assertIsNone(plan["action"])
				self.assertTrue(plan["reason"])

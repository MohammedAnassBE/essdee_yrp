import frappe
from yrp.yrp.doctype.yrp_purchase_invoice import yrp_purchase_invoice as base_purchase_invoice

DOCTYPE = "YRP Purchase Invoice"


@frappe.whitelist()
def approve_invoice(name, comments=None):
	"""Approve after confirming the caller may write this invoice."""
	frappe.get_doc(DOCTYPE, name).check_permission("write")
	return base_purchase_invoice.approve_invoice(name, comments=comments)


@frappe.whitelist()
def check_all_wo_closed(purchase_invoice):
	"""Report Work Order closure only to readers of the invoice."""
	frappe.get_doc(DOCTYPE, purchase_invoice).check_permission("read")
	return base_purchase_invoice.check_all_wo_closed(purchase_invoice)

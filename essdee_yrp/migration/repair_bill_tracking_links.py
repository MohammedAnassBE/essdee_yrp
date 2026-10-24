"""One-off repair of YRP Bill Trackings whose Purchase Invoice links were never set.

Bills invoiced before the live link/close fix still have empty ``purchase_invoice``
and ``erp_purchase_invoice``, so they stay in "Assigned to me". This replays the
live hooks for each such bill:

- submitted YRP Purchase Invoice (``bill_tracking``): ``close_vendor_bill`` (Close
  history row, Closed, ``purchase_invoice``) and ``link_erp_invoice_to_bill_tracking``.
- draft YRP Purchase Invoice: ``link_to_bill_tracking`` (``purchase_invoice`` only, stays open).
- submitted ERPNext Purchase Invoice (``vendor_bill_tracking``) with no YRP invoice:
  ``close_bill_tracking_for_erp_invoice`` (Close history row, Closed, ``erp_purchase_invoice``).

Cancelled, already Closed and ambiguous bills are reported and left alone.

Dry run (default, no writes):
	bench --site SITE execute essdee_yrp.migration.repair_bill_tracking_links.run
Apply:
	bench --site SITE execute essdee_yrp.migration.repair_bill_tracking_links.run --kwargs "{'apply': 1}"
"""

import frappe

from essdee_yrp.erp_purchase_invoice import (
	close_bill_tracking_for_erp_invoice,
	link_erp_invoice_to_bill_tracking,
)

CLOSE_YRP = "close_yrp"
LINK_YRP_DRAFT = "link_yrp_draft"
CLOSE_ERP = "close_erp"


def run(apply=0, verbose=1):
	repairs, skipped = [], []
	for bill, yrp_invoices, erp_invoices in get_candidates():
		plan = get_repair_plan(bill, yrp_invoices, erp_invoices)
		(repairs if plan["action"] else skipped).append(plan)
	errors = apply_repairs(repairs) if apply else []
	if verbose:
		print_report(repairs, skipped, errors, apply)
	return {
		"repairs": len(repairs),
		"by_action": count_by_action(repairs),
		"skipped": len(skipped),
		"errors": errors,
		"applied": bool(apply),
	}


def get_candidates():
	"""Unlinked Bill Trackings that a non-cancelled YRP or ERPNext Purchase Invoice references."""
	yrp_invoices = frappe.db.sql(
		"""
		SELECT pi.name, pi.docstatus, pi.bill_tracking, pi.erp_inv_name
		FROM `tabYRP Purchase Invoice` pi
		JOIN `tabYRP Bill Tracking` bt ON bt.name = pi.bill_tracking
		WHERE pi.docstatus < 2
		  AND IFNULL(bt.purchase_invoice, '') = '' AND IFNULL(bt.erp_purchase_invoice, '') = ''
		ORDER BY pi.name
		""",
		as_dict=True,
	)
	erp_invoices = frappe.db.sql(
		"""
		SELECT pi.name, pi.docstatus, pi.vendor_bill_tracking AS bill_tracking,
			pi.mrp_purchase_invoice_name
		FROM `tabPurchase Invoice` pi
		JOIN `tabYRP Bill Tracking` bt ON bt.name = pi.vendor_bill_tracking
		WHERE pi.docstatus < 2
		  AND IFNULL(bt.purchase_invoice, '') = '' AND IFNULL(bt.erp_purchase_invoice, '') = ''
		ORDER BY pi.name
		""",
		as_dict=True,
	)
	names = sorted({row.bill_tracking for row in yrp_invoices + erp_invoices})
	bills = {
		row.name: row
		for row in frappe.get_all(
			"YRP Bill Tracking",
			filters={"name": ["in", names]},
			fields=["name", "docstatus", "form_status", "assigned_to", "supplier", "bill_no"],
		)
	}
	for name in names:
		yield (
			bills[name],
			[row for row in yrp_invoices if row.bill_tracking == name],
			[row for row in erp_invoices if row.bill_tracking == name],
		)


def get_repair_plan(bill, yrp_invoices, erp_invoices):
	"""Pick the live hook to replay for ``bill``, or the reason it is skipped."""
	plan = {"bill": bill, "yrp": yrp_invoices, "erp": erp_invoices, "action": None, "reason": None}
	plan["reason"] = get_skip_reason(bill, yrp_invoices, erp_invoices)
	if plan["reason"]:
		return plan
	yrp = yrp_invoices[0] if yrp_invoices else None
	erp = erp_invoices[0] if erp_invoices else None
	if yrp:
		plan["action"] = CLOSE_YRP if yrp.docstatus == 1 else LINK_YRP_DRAFT
		plan["purchase_invoice"] = yrp.name
		plan["erp_purchase_invoice"] = yrp.erp_inv_name if yrp.docstatus == 1 else None
	else:
		plan["action"] = CLOSE_ERP
		plan["erp_purchase_invoice"] = erp.name
	return plan


def get_skip_reason(bill, yrp_invoices, erp_invoices):
	if bill.docstatus != 1:
		return "Bill Tracking is not submitted (cancelled or amended)"
	if bill.form_status == "Closed":
		return "Bill Tracking is already Closed; the live close refuses a second close"
	if len(yrp_invoices) > 1 or len(erp_invoices) > 1:
		return "several Purchase Invoices reference this Bill Tracking"
	yrp = yrp_invoices[0] if yrp_invoices else None
	erp = erp_invoices[0] if erp_invoices else None
	if yrp and erp:
		if yrp.docstatus != 1 or yrp.erp_inv_name != erp.name:
			return "YRP and ERP Purchase Invoices are not one generated pair"
		return None
	if yrp and yrp.erp_inv_name:
		return f"ERP Purchase Invoice {yrp.erp_inv_name} of the YRP invoice is cancelled or missing"
	if erp and erp.docstatus != 1:
		return "ERP Purchase Invoice is a draft; the live code links it only on submit"
	if erp and erp.mrp_purchase_invoice_name:
		return "ERP Purchase Invoice belongs to a YRP Purchase Invoice not linked to this bill"
	return None


def apply_repairs(repairs):
	errors = []
	for plan in repairs:
		name = plan["bill"].name
		try:
			apply_repair(plan)
			frappe.db.commit()  # nosemgrep: one Bill Tracking per transaction
		except Exception as error:
			frappe.db.rollback()
			errors.append({"bill_tracking": name, "error": repr(error)})
	return errors


def apply_repair(plan):
	name = plan["bill"].name
	links = frappe.db.get_value(
		"YRP Bill Tracking", name, ["purchase_invoice", "erp_purchase_invoice"], for_update=True
	)
	if any(links):
		frappe.throw(f"Bill Tracking {name} was linked after the dry run: {links}")
	if plan["action"] == CLOSE_YRP:
		invoice = frappe.get_doc("YRP Purchase Invoice", plan["purchase_invoice"])
		invoice.close_bill_tracking()
		link_erp_invoice_to_bill_tracking(invoice)
	elif plan["action"] == LINK_YRP_DRAFT:
		frappe.get_doc("YRP Purchase Invoice", plan["purchase_invoice"]).link_to_bill_tracking()
	elif plan["action"] == CLOSE_ERP:
		close_bill_tracking_for_erp_invoice(name, plan["erp_purchase_invoice"])


def count_by_action(repairs):
	counts = {}
	for plan in repairs:
		counts[plan["action"]] = counts.get(plan["action"], 0) + 1
	return counts


def describe(plan):
	bill = plan["bill"]
	invoices = [f"YRP {row.name} (docstatus {row.docstatus})" for row in plan["yrp"]]
	invoices += [f"ERP {row.name} (docstatus {row.docstatus})" for row in plan["erp"]]
	return (
		f"{bill.name} [{bill.form_status}, {bill.assigned_to or '-'}] {bill.supplier} {bill.bill_no}: "
		+ ", ".join(invoices)
	)


def print_report(repairs, skipped, errors, apply):
	print(f"Mode: {'APPLY' if apply else 'DRY RUN'}")
	print(f"Repairs: {len(repairs)} {count_by_action(repairs)}")
	for plan in repairs:
		print(
			f"  {plan['action']}: {describe(plan)} -> purchase_invoice={plan.get('purchase_invoice')}, "
			f"erp_purchase_invoice={plan.get('erp_purchase_invoice')}"
		)
	print(f"\nSkipped: {len(skipped)}")
	for plan in skipped:
		print(f"  {describe(plan)} -- {plan['reason']}")
	print(f"\nErrors: {len(errors)}")
	for error in errors:
		print(f"  {error['bill_tracking']}: {error['error']}")

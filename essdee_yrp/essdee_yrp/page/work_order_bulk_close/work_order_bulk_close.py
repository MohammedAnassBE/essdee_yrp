import json

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, strip_html_tags
from yrp.stock.save_stock_items import group_items_for_ui
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _get_wo_close_approver_role, _is_wo_close_manager

from essdee_yrp.api.work_order import fetch_summary_details
from essdee_yrp.work_order_close import close_work_order


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except TypeError, ValueError:
			value = [value]
	if not isinstance(value, (list, tuple, set)):
		value = [value]
	return list(dict.fromkeys(cstr(entry).strip() for entry in value if cstr(entry).strip()))


@frappe.whitelist()
def get_open_work_orders(
	supplier,
	lot=None,
	item=None,
	wo_from_date=None,
	wo_to_date=None,
):
	frappe.has_permission("YRP Work Order", "read", throw=True)
	supplier = cstr(supplier).strip()
	if not supplier:
		frappe.throw(_("Supplier is required."))
	if not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("Supplier {0} does not exist.").format(frappe.bold(supplier)))

	filters = {"supplier": supplier, "docstatus": 1, "open_status": "Open"}
	if lots := _as_list(lot):
		filters["lot"] = ["in", lots]
	if items := _as_list(item):
		filters["item"] = ["in", items]

	from_date = getdate(wo_from_date) if wo_from_date else None
	to_date = getdate(wo_to_date) if wo_to_date else None
	if from_date and to_date and from_date > to_date:
		frappe.throw(_("WO From Date cannot be after WO To Date."))
	if from_date and to_date:
		filters["wo_date"] = ["between", [from_date, to_date]]
	elif from_date:
		filters["wo_date"] = [">=", from_date]
	elif to_date:
		filters["wo_date"] = ["<=", to_date]

	rows = frappe.get_list(
		"YRP Work Order",
		filters=filters,
		fields=[
			"name",
			"wo_date",
			"item",
			"lot",
			"process_name",
			"production_detail",
			"total_no_of_pieces_delivered as total_delivered",
			"total_no_of_pieces_received as total_received",
		],
		order_by="modified desc, name desc",
		limit_page_length=0,
	)
	for row in rows:
		row.total_delivered = flt(row.total_delivered)
		row.total_received = flt(row.total_received)
		row.difference = flt(row.total_delivered - row.total_received)
	return rows


@frappe.whitelist()
def close_work_orders(
	work_orders,
	close_reason=None,
	close_other_reason=None,
	close_remarks=None,
):
	"""Close each Work Order directly, with no Close Request; needs Work Order write permission."""
	names = _as_list(work_orders)
	if not names:
		frappe.throw(_("Select at least one Work Order to close."))
	frappe.has_permission("YRP Work Order", "write", throw=True)

	previous_flags = (
		frappe.flags.get("work_order_bulk_close"),
		frappe.flags.get("suppress_work_order_close_alert"),
	)
	frappe.flags.work_order_bulk_close = frappe.flags.suppress_work_order_close_alert = True
	try:
		closed, failed = _for_each_work_order(
			names,
			"work_order_bulk_close",
			lambda name: _close_one(name, close_reason, close_other_reason, close_remarks),
		)
	finally:
		frappe.flags.work_order_bulk_close, frappe.flags.suppress_work_order_close_alert = previous_flags
	results = [{"work_order": name, "open_status": status} for name, status in closed]
	return {"results": results, "failed": failed}


def _close_one(name, close_reason, close_other_reason, close_remarks):
	doc = frappe.get_doc("YRP Work Order", name, for_update=True)
	doc.check_permission("write")
	if doc.docstatus != 1 or doc.open_status != "Open":
		frappe.throw(_("Work Order {0} is no longer open.").format(frappe.bold(name)))
	result = close_work_order(
		name,
		sd_close_reason=close_reason,
		close_other_reason=close_other_reason,
		close_remarks=close_remarks,
	)
	return result.get("status")


@frappe.whitelist()
def approve_close_requests(work_orders):
	"""Approve each selected Work Order's pending Close Request; only the closing approver role may."""
	names = _as_list(work_orders)
	if not names:
		frappe.throw(_("Select at least one Work Order to approve."))
	if not _is_wo_close_manager(throw_if_missing=True):
		frappe.throw(
			_("Only users with role {0} can approve Work Order close requests.").format(
				frappe.bold(_get_wo_close_approver_role())
			),
			frappe.PermissionError,
		)
	approved, failed = _for_each_work_order(names, "work_order_approve_close", _approve_one)
	return {"approved": [name for name, _status in approved], "failed": failed}


def _approve_one(name):
	doc = frappe.get_doc("YRP Work Order", name, for_update=True)
	doc.check_permission("write")
	if doc.docstatus != 1 or doc.open_status != "Close Request":
		frappe.throw(_("Work Order {0} does not have a pending Close Request.").format(frappe.bold(name)))
	result = close_work_order(
		name,
		sd_close_reason=doc.get("sd_close_reason"),
		close_reason=doc.get("close_reason"),
		close_other_reason=doc.get("close_other_reason"),
		close_remarks=doc.get("close_remarks"),
	)
	return result.get("status")


def _for_each_work_order(names, savepoint_prefix, action):
	"""Run `action` per Work Order in its own savepoint; a failure rolls back only that order."""
	done, failed = [], []
	for index, name in enumerate(names, start=1):
		savepoint = f"{savepoint_prefix}_{index}"
		frappe.db.savepoint(savepoint)
		try:
			done.append((name, action(name)))
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_messages()
			message = strip_html_tags(cstr(error)).strip() or _("The Work Order could not be processed.")
			failed.append({"work_order": name, "error": message})
	return done, failed


@frappe.whitelist()
def get_work_order_close_details(work_order):
	doc = frappe.get_doc("YRP Work Order", work_order)
	doc.check_permission("read")
	if doc.docstatus != 1 or doc.open_status != "Open":
		frappe.throw(_("Work Order {0} is no longer open.").format(frappe.bold(work_order)))

	summary = (
		fetch_summary_details(doc.name, doc.production_detail)
		if doc.work_order_calculated_items
		else {
			"item_detail": [],
			"deliverables": [],
			"work_order_docstatus": doc.docstatus,
		}
	)
	recut_details = []
	for recut_name in frappe.get_all(
		"SD YRP WO Recut",
		filters={"work_order": doc.name, "docstatus": ["<", 2]},
		pluck="name",
		order_by="creation asc",
	):
		recut = frappe.get_doc("SD YRP WO Recut", recut_name)
		recut_details.append(
			{
				"name": recut.name,
				"items": group_items_for_ui(
					recut.get("wo_recut_details") or [], "YRP Work Order Deliverables"
				),
			}
		)

	debits = []
	if frappe.has_permission("YRP Debit", "read"):
		debits = frappe.get_list(
			"YRP Debit",
			filters={"work_order": doc.name, "docstatus": 1},
			fields=[
				"name",
				"debit_type",
				"debit_no",
				"debit_value",
				"inspection",
				"status",
				"on_close",
			],
			order_by="creation asc",
			limit_page_length=0,
		)
	return {"summary": summary, "recut_details": recut_details, "debits": debits}

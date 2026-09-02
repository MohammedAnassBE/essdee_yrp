"""Permission-aware Time and Action tracking/report services.

The F15 implementation lived in a 3,900-line generic ``utils.py`` module and
trusted browser-provided Work Order rows.  This adapter retains its Desk
contracts while deriving every mutable target from current F16 documents.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate


def _json_value(value):
	if isinstance(value, str):
		return frappe.parse_json(value)
	return value


def _open_work_order_filters(lot=None, item=None, process_name=None):
	filters = {"docstatus": 1, "open_status": "Open"}
	if lot:
		filters["lot"] = lot
	if item:
		filters["item"] = item
	if process_name:
		filters["process_name"] = process_name
	return filters


def _permitted_work_orders(lot=None, item=None, process_name=None, fields=None):
	return frappe.get_list(
		'YRP Work Order',
		filters=_open_work_order_filters(lot, item, process_name),
		fields=fields or ["name"],
		order_by="name asc",
		limit_page_length=0,
	)


def _tracking_rows(work_order_names):
	if not work_order_names:
		return {}
	rows = frappe.get_all(
		'YRP Work Order Tracking Log',
		filters={"parent": ["in", work_order_names], "parenttype": 'YRP Work Order'},
		fields=["parent", "from_date", "to_date", "reason", "check_point", "idx"],
		order_by="parent asc, idx asc",
	)
	result = defaultdict(list)
	for row in rows:
		result[row.parent].append(row)
	return result


@frappe.whitelist()
def get_t_and_a_report_data(lot=None, item=None, process_name=None):
	"""Return the legacy tracking-grid shape, scoped by Work Order read access."""
	work_orders = _permitted_work_orders(
		lot,
		item,
		process_name,
		fields=[
			"name",
			"item",
			"lot",
			"process_name",
			"planned_quantity",
			"planned_end_date",
			"expected_delivery_date",
		],
	)
	logs = _tracking_rows([row.name for row in work_orders])
	lot_names = {row.lot for row in work_orders if row.lot}
	assigned_by_lot = {
		row.name: row.assigned_person_name
		for row in frappe.get_all(
			'SD YRP Lot',
			filters={"name": ["in", list(lot_names)]},
			fields=["name", "assigned_person_name"],
		)
	} if lot_names else {}

	grouped = {}
	has_tracking_rows = False
	for work_order in work_orders:
		key = (work_order.lot, work_order.item, work_order.process_name)
		planned_end = getdate(work_order.planned_end_date) if work_order.planned_end_date else None
		expected = (
			getdate(work_order.expected_delivery_date)
			if work_order.expected_delivery_date
			else None
		)
		delay = (planned_end - expected).days if planned_end and expected else 0
		entry = grouped.setdefault(
			key,
			{
				"item": work_order.item,
				"lot": work_order.lot,
				"process_name": work_order.process_name,
				"qty": 0,
				"reason": None,
				"planned_end_date": planned_end,
				"delay": delay,
				"assigned": assigned_by_lot.get(work_order.lot),
				"_expected_date": None,
				"_reason_date": None,
				"_checkpoint_date": None,
				"_dates": {},
			},
		)
		entry["qty"] += flt(work_order.planned_quantity)
		if planned_end and (
			not entry["planned_end_date"] or planned_end > entry["planned_end_date"]
		):
			entry["planned_end_date"] = planned_end
		entry["delay"] = max(entry["delay"], delay)

		for log in logs.get(work_order.name, []):
			if not log.from_date or not log.to_date:
				continue
			has_tracking_rows = True
			from_date = getdate(log.from_date)
			to_date = getdate(log.to_date)
			from_label = from_date.strftime("%d-%m-%Y")
			previous = entry["_dates"].get(from_label)
			if not previous or to_date > previous:
				entry["_dates"][from_label] = to_date
			if not entry["_expected_date"] or to_date > entry["_expected_date"]:
				entry["_expected_date"] = to_date
			if log.reason and (
				not entry["_reason_date"] or to_date >= entry["_reason_date"]
			):
				entry["reason"] = log.reason
				entry["_reason_date"] = to_date
			if cint(log.check_point) and (
				not entry["_checkpoint_date"] or to_date > entry["_checkpoint_date"]
			):
				entry["_checkpoint_date"] = to_date

	days = cint(
		frappe.db.get_single_value(
			'SD YRP MRP Settings', "time_and_action_tracking_order_report_days"
		)
	) or 6
	date_keys = []
	if has_tracking_rows:
		current_date = getdate(nowdate())
		start_date = add_days(current_date, -(max(days, 1) - 1))
		while start_date <= current_date:
			date_keys.append(start_date.strftime("%d-%m-%Y"))
			start_date = add_days(start_date, 1)

	rows = []
	for entry in grouped.values():
		row = {
			"item": entry["item"],
			"lot": entry["lot"],
			"process_name": entry["process_name"],
			"qty": entry["qty"],
			"reason": entry["reason"],
			"planned_end_date": (
				entry["planned_end_date"].strftime("%d-%m-%Y")
				if entry["planned_end_date"]
				else None
			),
			"delay": entry["delay"],
			"assigned": entry["assigned"],
			"check_point": (
				entry["_checkpoint_date"].strftime("%d-%m-%Y")
				if entry["_checkpoint_date"]
				else None
			),
			"expected_date": (
				entry["_expected_date"].strftime("%d-%m-%Y")
				if entry["_expected_date"]
				else None
			),
		}
		row.update(
			{key: value.strftime("%d-%m-%Y") for key, value in entry["_dates"].items()}
		)
		rows.append(row)

	return {
		"row_keys": [
			"item",
			"lot",
			"process_name",
			"qty",
			*date_keys,
			"reason",
			"delay",
			"planned_end_date",
			"assigned",
			"check_point",
		],
		"dates": date_keys,
		"datas": rows,
	}


@frappe.whitelist()
def get_work_order_details(detail):
	detail = _json_value(detail)
	if not isinstance(detail, dict):
		frappe.throw(_("Invalid tracking row."))
	return _permitted_work_orders(
		detail.get("lot"),
		detail.get("item"),
		detail.get("process_name"),
		fields=[
			"name",
			"wo_colours",
			"supplier",
			"supplier_name",
			"total_quantity",
			"total_no_of_pieces_received",
		],
	)


def _set_expected_date(work_order, expected_date, reason):
	doc = frappe.get_doc('YRP Work Order', work_order)
	doc.check_permission("write")
	if doc.docstatus != 1 or doc.open_status != "Open":
		frappe.throw(
			_("Work Order {0} must be submitted and open.").format(
				frappe.bold(doc.name)
			)
		)
	expected_date = getdate(expected_date)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Reason is required."))
	doc.append(
		"work_order_tracking_logs",
		{
			"from_date": nowdate(),
			"to_date": expected_date,
			"reason": reason,
			"user": frappe.session.user,
		},
	)
	doc.expected_delivery_date = expected_date
	doc.save()
	return doc


@frappe.whitelist()
def update_expected_date(work_order, expected_date, reason, _return=True):
	doc = _set_expected_date(work_order, expected_date, reason)
	if cint(_return):
		data = get_t_and_a_report_data(doc.lot, doc.item, doc.process_name)
		return data["datas"][0] if data["datas"] else {}
	return None


@frappe.whitelist()
def update_all_work_orders(
	lot,
	item,
	process_name,
	work_order_details=None,
	expected_date=None,
	reason=None,
):
	# Browser rows are deliberately ignored; current readable records determine
	# the set and each target still has to pass its own write permission check.
	work_orders = _permitted_work_orders(lot, item, process_name)
	if not work_orders:
		frappe.throw(_("No open Work Orders are available."))
	for row in work_orders:
		_set_expected_date(row.name, expected_date, reason)
	data = get_t_and_a_report_data(lot, item, process_name)
	return data["datas"][0] if data["datas"] else {}


def _checkpoint_date(row):
	value = row.get("expected_date") or row.get("check_point")
	if value:
		return getdate(value, parse_day_first=True)
	ignored = {
		"item",
		"lot",
		"process_name",
		"qty",
		"reason",
		"planned_end_date",
		"delay",
		"assigned",
		"min_reason_date",
		"changed",
	}
	dates = []
	for key, candidate in row.items():
		if key in ignored or not candidate:
			continue
		try:
			dates.append(getdate(candidate, parse_day_first=True))
		except (TypeError, ValueError):
			continue
	return max(dates) if dates else None


@frappe.whitelist()
def update_wo_checkpoint(datas):
	datas = _json_value(datas)
	if not isinstance(datas, list):
		frappe.throw(_("Invalid checkpoint rows."))
	for row in datas:
		if not isinstance(row, dict):
			frappe.throw(_("Invalid checkpoint row."))
		to_date = _checkpoint_date(row)
		if not to_date:
			frappe.throw(
				_("No checkpoint date is available for {0} / {1}.").format(
					frappe.bold(row.get("lot") or ""),
					frappe.bold(row.get("process_name") or ""),
				)
			)
		for work_order in _permitted_work_orders(
			row.get("lot"), row.get("item"), row.get("process_name")
		):
			doc = frappe.get_doc('YRP Work Order', work_order.name)
			doc.check_permission("write")
			matched = False
			for log in doc.work_order_tracking_logs:
				log.check_point = cint(log.to_date == to_date)
				matched = matched or bool(log.check_point)
			if not matched:
				doc.append(
					"work_order_tracking_logs",
					{
						"from_date": to_date,
						"to_date": to_date,
						"check_point": 1,
						"user": frappe.session.user,
					},
				)
			doc.save()


@frappe.whitelist()
def get_t_and_a_review_report_data(lot=None, item=None, report_date=None):
	"""Return the F15 weekly-review shape for readable, Lot-linked schedules."""
	filters = {"status": ["!=", "Completed"]}
	if lot:
		filters["lot"] = lot
	if item:
		filters["item"] = item
	if report_date:
		filters["end_date"] = ["<", getdate(report_date)]
	schedules = frappe.get_list(
		'SD YRP Time and Action',
		filters=filters,
		fields=[
			"name",
			"lot",
			"item",
			"master",
			"colour",
			"sizes",
			"qty",
			"start_date",
			"delay",
		],
		order_by="lot asc, master asc, colour asc, name asc",
		limit_page_length=0,
	)
	by_lot = defaultdict(list)
	for schedule in schedules:
		if schedule.lot:
			by_lot[schedule.lot].append(schedule)

	result = {}
	for lot_name, lot_schedules in by_lot.items():
		lot_doc = frappe.get_doc('SD YRP Lot', lot_name)
		lot_doc.check_permission("read")
		linked = {
			row.time_and_action
			for row in lot_doc.lot_time_and_action_details
			if row.time_and_action
		}
		for schedule in lot_schedules:
			if schedule.name not in linked:
				continue
			doc = frappe.get_doc('SD YRP Time and Action', schedule.name)
			master_data = result.setdefault(lot_name, {}).setdefault(
				doc.master, {"actions": [], "datas": []}
			)
			if not master_data["actions"]:
				master_data["actions"] = [row.action for row in doc.details]
			master_data["datas"].append(
				{
					"item": doc.item,
					"master": doc.master,
					"colour": doc.colour,
					"sizes": doc.sizes,
					"qty": doc.qty,
					"start_date": doc.start_date,
					"delay": doc.delay,
					"actions": [
						{
							"department": row.department,
							"date": row.date,
							"rescheduled_date": row.rescheduled_date,
							"actual_date": row.actual_date,
							"reason": row.reason,
							"performance": row.performance,
							"delay": row.date_diff,
						}
						for row in doc.details
					],
				}
			)
	return result

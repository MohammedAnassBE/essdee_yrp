"""Permission-scoped providers for the Production API Time and Action reports."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def _filters(value):
	return frappe._dict(value or {})


def _allowed_names(filters=None, active_only=False):
	query_filters = dict(filters or {})
	if active_only:
		query_filters["status"] = ["!=", "Completed"]
	return frappe.get_list(
		'SD YRP Time and Action',
		filters=query_filters,
		pluck="name",
		order_by="name asc",
		limit_page_length=0,
	)


def _names_or_empty(filters=None, active_only=False):
	return tuple(_allowed_names(filters, active_only))


def execute_cumulative_time_and_action_delay(filters=None):
	columns = [
		{"fieldtype": "Link", "fieldname": "lot", "options": 'SD YRP Lot', "label": "Lot", "width": 120},
		{"fieldtype": "Link", "fieldname": "item", "options": 'YRP Item', "label": "Item", "width": 150},
		{"fieldtype": "Int", "fieldname": "delay", "label": "Delay", "width": 80},
		{"fieldtype": "Data", "fieldname": "sizes", "label": "Sizes", "width": 130},
		{"fieldtype": "Float", "fieldname": "qty", "label": "Quantity", "width": 100},
		{"fieldtype": "Data", "fieldname": "colours", "label": "Colours", "width": 150},
		{"fieldtype": "Link", "fieldname": "action", "label": "Next Action", "options": 'SD YRP Action', "width": 120},
	]
	names = _names_or_empty(active_only=True)
	if not names:
		return columns, []
	data = frappe.db.sql(
		"""
		SELECT parent.lot, parent.item, MIN(parent.delay) AS delay,
			MAX(parent.sizes) AS sizes, SUM(parent.qty) AS qty,
			GROUP_CONCAT(DISTINCT parent.colour ORDER BY parent.colour SEPARATOR ', ') AS colours,
			GROUP_CONCAT(DISTINCT parent.action ORDER BY parent.action SEPARATOR ', ') AS action
		FROM `tabSD YRP Time and Action` parent
		JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
		WHERE parent.name IN %(names)s AND detail.index2 = 1
		GROUP BY parent.lot, parent.item
		ORDER BY delay ASC, parent.lot ASC
		""",
		{"names": names},
		as_dict=True,
	)
	return columns, data


def execute_live_time_and_action_delay(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldtype": "Link", "fieldname": "lot", "label": "Lot", "options": 'SD YRP Lot', "width": 100},
		{"fieldtype": "Link", "fieldname": "item", "label": "Item", "options": 'YRP Item', "width": 150},
	]
	if filters.show_style_summary:
		columns += [
			{"fieldtype": "Data", "fieldname": "sizes", "label": "Sizes", "width": 130},
			{"fieldtype": "Int", "fieldname": "date_diff", "label": "Date Diff", "width": 90},
		]
	else:
		columns += [
			{"fieldtype": "Link", "fieldname": "master", "label": "Master", "options": 'SD YRP Action Master', "width": 120},
			{"fieldtype": "Data", "fieldname": "colour", "label": "Colour", "width": 100},
			{"fieldtype": "Data", "fieldname": "sizes", "label": "Sizes", "width": 130},
			{"fieldtype": "Float", "fieldname": "qty", "label": "Qty", "width": 100},
			{"fieldtype": "Link", "fieldname": "action", "label": "Action", "options": 'SD YRP Action', "width": 150},
			{"fieldtype": "Link", "fieldname": "department", "label": "Department", "options": 'YRP Department', "width": 120},
			{"fieldtype": "Date", "fieldname": "date", "label": "Planned Date", "width": 120},
			{"fieldtype": "Date", "fieldname": "rescheduled_date", "label": "Rescheduled Date", "width": 120},
			{"fieldtype": "Int", "fieldname": "date_diff", "label": "Date Diff", "width": 90},
		]
	parent_filters = {"lot": filters.lot} if filters.lot else None
	names = _names_or_empty(parent_filters, active_only=True)
	if not names:
		return columns, []
	values = {"names": names, "today": getdate(nowdate())}
	if filters.show_style_summary:
		data = frappe.db.sql(
			"""
			SELECT parent.lot, parent.item, MAX(parent.sizes) AS sizes,
				MIN(DATEDIFF(detail.rescheduled_date, %(today)s)) AS date_diff
			FROM `tabSD YRP Time and Action` parent
			JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
			WHERE parent.name IN %(names)s AND detail.completed = 0
				AND detail.rescheduled_date <= %(today)s
			GROUP BY parent.lot, parent.item
			ORDER BY date_diff ASC, parent.lot ASC
			""",
			values,
			as_dict=True,
		)
	else:
		data = frappe.db.sql(
			"""
			SELECT parent.lot, parent.item, parent.master, parent.colour,
				parent.sizes, parent.qty, detail.action, detail.department,
				detail.date, detail.rescheduled_date,
				DATEDIFF(detail.rescheduled_date, %(today)s) AS date_diff
			FROM `tabSD YRP Time and Action` parent
			JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
			WHERE parent.name IN %(names)s AND detail.completed = 0
				AND detail.index2 = 1 AND detail.rescheduled_date <= %(today)s
			ORDER BY date_diff ASC, parent.lot ASC
			""",
			values,
			as_dict=True,
		)
	return columns, data


def execute_time_and_action_delay_analysis(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldtype": "Link", "fieldname": "action", "label": "Action", "options": 'SD YRP Action', "width": 150},
		{"fieldtype": "Link", "fieldname": "department", "label": "Department", "options": 'YRP Department', "width": 120},
		{"fieldtype": "Date", "fieldname": "date", "label": "Planned Date", "width": 120},
		{"fieldtype": "Date", "fieldname": "rescheduled_date", "label": "Rescheduled Date", "width": 120},
		{"fieldtype": "Date", "fieldname": "actual_date", "label": "Actual Date", "width": 120},
		{"fieldtype": "Int", "fieldname": "date_diff", "label": "Date Difference", "width": 140},
		{"fieldtype": "Int", "fieldname": "cumulative_diff", "label": "Cumulative Difference", "width": 200},
	]
	if not filters.lot or not filters.time_and_action:
		return columns, [], None, _delay_chart([])
	doc = frappe.get_doc('SD YRP Time and Action', filters.time_and_action)
	doc.check_permission("read")
	if doc.lot != filters.lot:
		frappe.throw(_("Time and Action does not belong to the selected Lot."))
	data = frappe.db.sql(
		"""
		SELECT action, department, date, rescheduled_date, actual_date,
			DATEDIFF(rescheduled_date, actual_date) AS date_diff,
			DATEDIFF(date, actual_date) AS cumulative_diff
		FROM `tabSD YRP Time and Action Detail`
		WHERE parent = %(parent)s AND completed = 1
		ORDER BY idx ASC
		""",
		{"parent": doc.name},
		as_dict=True,
	)
	return columns, data, None, _delay_chart(data)


def _delay_chart(data):
	labels = [row.action for row in data]
	date_values = [row.date_diff or 0 for row in data]
	cumulative_values = [row.cumulative_diff or 0 for row in data]
	maximum = max([0, *date_values, *cumulative_values])
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": "Date Difference", "values": date_values, "color": "#4dcd32"},
				{"name": "Cumulative Difference", "values": cumulative_values, "color": "#dd0453"},
			],
			"yRegions": [{"label": "Max", "start": 0, "end": maximum + 1, "options": {"labelPos": "right"}}],
		},
		"type": "line",
		"height": 1000,
	}


def execute_time_and_action_department_performance(filters=None):
	filters = _filters(filters)
	group_map = {
		'YRP Department': ("department", 'YRP Department'),
		'SD YRP Action': ("action", 'SD YRP Action'),
		'YRP Work Station': ("work_station", 'YRP Work Station'),
	}
	fieldname, options = group_map.get(filters.select or 'YRP Department', group_map['YRP Department'])
	columns = [
		{"fieldtype": "Link", "fieldname": fieldname, "options": options, "label": options, "width": 200},
		{"fieldtype": "Percent", "fieldname": "performance", "label": "Performance", "width": 200},
	]
	names = _names_or_empty()
	if not names:
		return columns, [], None, _performance_chart([], fieldname)
	conditions = ["parent IN %(names)s", "completed = 1", f"{fieldname} IS NOT NULL"]
	values = {"names": names}
	if filters.from_date:
		conditions.append("date >= %(from_date)s")
		values["from_date"] = getdate(filters.from_date)
	if filters.to_date:
		conditions.append("date <= %(to_date)s")
		values["to_date"] = getdate(filters.to_date)
	data = frappe.db.sql(
		f"""
		SELECT {fieldname}, AVG(performance) AS performance
		FROM `tabSD YRP Time and Action Detail`
		WHERE {' AND '.join(conditions)}
		GROUP BY {fieldname}
		ORDER BY performance DESC
		""",
		values,
		as_dict=True,
	)
	return columns, data, None, _performance_chart(data, fieldname)


def _performance_chart(data, fieldname):
	labels = [row.get(fieldname) for row in data]
	return {
		"data": {"labels": labels, "datasets": [{"name": "", "values": [row.performance for row in data]}]},
		"type": "bar",
		"height": 500,
		"colors": [["#4dcd32", "#4dcd32", "#dd0453", "#4dcd32", "#dd0453"]],
	}


def execute_time_and_action_dispatch_report(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldname": "lot", "fieldtype": "Link", "label": "Lot", "options": 'SD YRP Lot', "width": 200},
		{"fieldname": "item", "fieldtype": "Link", "label": "Item", "options": 'YRP Item', "width": 200},
		{"fieldname": "sizes", "fieldtype": "Data", "label": "Sizes", "width": 300},
		{"fieldname": "date", "fieldtype": "Date", "label": "Dispatch Date", "width": 200},
		{"fieldname": "total_order_quantity", "fieldtype": "Int", "label": "Total Quantity"},
		{"fieldname": "cumulative_delay", "fieldtype": "Int", "label": "Cumulative Delay"},
	]
	names = _names_or_empty({"lot": filters.lot} if filters.lot else None)
	if not names:
		return columns, []
	data = frappe.db.sql(
		"""
		SELECT parent.lot, parent.item, MAX(parent.sizes) AS sizes,
			MAX(detail.rescheduled_date) AS date, lot.total_order_quantity,
			MIN(parent.delay) AS cumulative_delay
		FROM `tabSD YRP Time and Action` parent
		JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
		JOIN `tabSD YRP Lot` lot ON lot.name = parent.lot
		WHERE parent.name IN %(names)s
		GROUP BY parent.lot, parent.item, lot.total_order_quantity
		ORDER BY parent.lot ASC, parent.item ASC
		""",
		{"names": names},
		as_dict=True,
	)
	return columns, data


def execute_time_and_action_pending_work(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldtype": "Link", "fieldname": "lot", "options": 'SD YRP Lot', "label": "Lot", "width": 100},
		{"fieldtype": "Link", "fieldname": "item", "options": 'YRP Item', "label": "Item", "width": 150},
		{"fieldtype": "Link", "fieldname": "master", "options": 'SD YRP Action Master', "label": "Master", "width": 120},
		{"fieldtype": "Data", "fieldname": "colour", "label": "Colour", "width": 120},
		{"fieldtype": "Data", "fieldname": "sizes", "label": "Sizes", "width": 130},
		{"fieldtype": "Float", "fieldname": "qty", "label": "Quantity", "width": 100},
		{"fieldtype": "Link", "fieldname": "action", "options": 'SD YRP Action', "label": "Action", "width": 100},
		{"fieldtype": "Link", "fieldname": "department", "options": 'YRP Department', "label": "Department", "width": 120},
		{"fieldtype": "Date", "fieldname": "date", "label": "Planned Date", "width": 120},
		{"fieldtype": "Date", "fieldname": "rescheduled_date", "label": "Rescheduled Date", "width": 120},
		{"fieldtype": "Int", "fieldname": "date_diff", "label": "Date Diff", "width": 100},
	]
	if not filters.date:
		return columns, []
	names = _names_or_empty(active_only=True)
	if not names:
		return columns, []
	conditions = [
		"parent.name IN %(names)s",
		"detail.rescheduled_date <= %(date)s",
		"detail.completed = 0",
	]
	values = {"names": names, "date": getdate(filters.date)}
	if filters.action:
		conditions.append("detail.action = %(action)s")
		values["action"] = filters.action
	if filters.work_station:
		conditions.append("detail.work_station = %(work_station)s")
		values["work_station"] = filters.work_station
	data = frappe.db.sql(
		f"""
		SELECT parent.lot, parent.item, parent.master, parent.colour,
			parent.sizes, parent.qty, detail.action, detail.department,
			detail.date, detail.rescheduled_date,
			DATEDIFF(detail.rescheduled_date, %(date)s) AS date_diff
		FROM `tabSD YRP Time and Action` parent
		JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
		WHERE {' AND '.join(conditions)}
		ORDER BY date_diff ASC, parent.lot ASC, detail.idx ASC
		""",
		values,
		as_dict=True,
	)
	return columns, data


def execute_time_and_action_report(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldtype": "Link", "fieldname": "lot", "options": 'SD YRP Lot', "label": "Lot", "width": 120},
		{"fieldtype": "Link", "fieldname": "item", "options": 'YRP Item', "label": "Item", "width": 150},
		{"fieldtype": "Link", "fieldname": "master", "options": 'SD YRP Action Master', "label": "Master", "width": 120},
		{"fieldtype": "Data", "fieldname": "colour", "label": "Colour", "width": 100},
		{"fieldtype": "Data", "fieldname": "sizes", "label": "Sizes", "width": 100},
		{"fieldtype": "Float", "fieldname": "qty", "label": "Quantity", "width": 100},
		{"fieldtype": "Date", "fieldname": "start_date", "label": "Start Date", "width": 120},
		{"fieldtype": "Link", "fieldname": "action", "options": 'SD YRP Action', "label": "Action", "width": 100},
		{"fieldtype": "Link", "fieldname": "department", "options": 'YRP Department', "label": "Department", "width": 120},
		{"fieldtype": "Int", "fieldname": "lead_time", "label": "Lead Time", "width": 100},
		{"fieldtype": "Date", "fieldname": "date", "label": "Planned date", "width": 120},
		{"fieldtype": "Date", "fieldname": "rescheduled_date", "label": "Rescheduled Date", "width": 120},
	]
	names = _names_or_empty({"lot": filters.lot} if filters.lot else None, active_only=True)
	if not names:
		return columns, []
	all_rows = frappe.db.sql(
		"""
		SELECT parent.name AS parent_name, parent.lot, parent.item, parent.master,
			parent.colour, parent.sizes, parent.qty, parent.start_date,
			detail.action, detail.department, detail.lead_time, detail.date,
			detail.rescheduled_date, detail.idx
		FROM `tabSD YRP Time and Action` parent
		JOIN `tabSD YRP Time and Action Detail` detail ON detail.parent = parent.name
		WHERE parent.name IN %(names)s AND detail.completed = 0
		ORDER BY parent.lot ASC, parent.name ASC, detail.idx ASC
		""",
		{"names": names},
		as_dict=True,
	)
	seen = set()
	data = []
	for row in all_rows:
		if row.parent_name in seen:
			continue
		seen.add(row.parent_name)
		row.pop("parent_name", None)
		row.pop("idx", None)
		data.append(row)
	return columns, data


def execute_time_and_action_summary(filters=None):
	filters = _filters(filters)
	columns = [
		{"fieldtype": "Link", "fieldname": "action", "label": "Action", "options": 'SD YRP Action', "width": 150},
		{"fieldtype": "Int", "fieldname": "no_of_completed", "label": "No of Completed", "width": 200},
	]
	if filters.lot:
		columns.append({"fieldtype": "Date", "fieldname": "actual_date", "label": "Actual Date", "width": 200})
	names = _names_or_empty({"lot": filters.lot} if filters.lot else None)
	if not names:
		return columns, [], None, _summary_chart([])
	data = frappe.db.sql(
		"""
		SELECT grouped.action, SUM(grouped.no_of_completed) AS no_of_completed,
			MAX(grouped.actual_date) AS actual_date
		FROM (
			SELECT parent.lot, detail.action, MIN(detail.completed) AS no_of_completed,
				action.default_order, MAX(detail.actual_date) AS actual_date
			FROM `tabSD YRP Time and Action Detail` detail
			JOIN `tabSD YRP Time and Action` parent ON parent.name = detail.parent
			JOIN `tabSD YRP Action` action ON action.name = detail.action
			WHERE parent.name IN %(names)s AND action.`default` = 1
			GROUP BY parent.lot, detail.action, action.default_order
		) grouped
		GROUP BY grouped.action, grouped.default_order
		ORDER BY grouped.default_order ASC
		""",
		{"names": names},
		as_dict=True,
	)
	return columns, data, None, _summary_chart(data)


def _summary_chart(data):
	return {
		"data": {
			"labels": [row.action for row in data],
			"datasets": [{"name": "Completed Actions", "values": [row.no_of_completed for row in data]}],
		},
		"type": "bar",
		"height": 500,
		"colors": [["#4dcd32", "#4dcd32", "#dd0453", "#4dcd32", "#dd0453"]],
	}

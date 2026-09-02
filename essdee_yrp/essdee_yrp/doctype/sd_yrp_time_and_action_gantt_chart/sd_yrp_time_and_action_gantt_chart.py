# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SDYRPTimeandActionGanttChart(Document):
	pass


@frappe.whitelist()
def get_chart_data(action: str, work_station: str | None = None) -> list[dict]:
	if not action or not frappe.db.exists('SD YRP Action', action):
		frappe.throw(_("Select a valid Action."))
	parents = frappe.get_list(
		'SD YRP Time and Action',
		fields=["name", "lot", "item", "colour"],
		limit=5000,
	)
	if not parents:
		return []
	parent_map = {row.name: row for row in parents}
	filters = {
		"parent": ["in", list(parent_map)],
		"parenttype": 'SD YRP Time and Action',
		"completed": 0,
		"action": action,
	}
	if work_station:
		if not frappe.db.exists('YRP Work Station', work_station):
			frappe.throw(_("Select a valid Work Station."))
		filters["work_station"] = work_station
	details = frappe.get_all(
		'SD YRP Time and Action Detail',
		filters=filters,
		fields=[
			"parent",
			"rescheduled_start_date",
			"rescheduled_date",
			"actual_start_date",
			"actual_date",
		],
		order_by="rescheduled_date asc",
		limit=5000,
	)
	items = []
	for index, row in enumerate(details):
		parent = parent_map[row.parent]
		items.append(
			{
				"id": index,
				"name": f"{parent.lot}-{parent.item}-{parent.colour}",
				"start": row.actual_start_date
				if row.actual_date
				else row.rescheduled_start_date,
				"end": row.actual_date or row.rescheduled_date,
				"progress": 100,
			}
		)
	return items


TimeandActionGanttChart = SDYRPTimeandActionGanttChart

"""Essdee Action/Time-and-Action behavior layered onto base YRP Work Station."""

import frappe
from frappe import _

from yrp.utils import update_if_string_instance


def validate_default_action_work_station(doc, method=None):
	if not doc.get("default"):
		return
	if not doc.get("action"):
		frappe.throw(_("Action is required for a default Work Station."))
	filters = {"action": doc.action, "default": 1}
	if not doc.is_new():
		filters["name"] = ["!=", doc.name]
	existing = frappe.get_all('YRP Work Station', filters=filters, pluck="name", limit=1)
	if existing:
		frappe.throw(
			_("Work Station {0} is already the default for Action {1}.").format(
				frappe.bold(existing[0]), frappe.bold(doc.action)
			)
		)


@frappe.whitelist()
def get_work_stations(items, lot: str) -> dict:
	lot_doc = frappe.get_doc('SD YRP Lot', lot)
	lot_doc.check_permission("read")
	result = {}
	for link in lot_doc.lot_time_and_action_details:
		if not link.time_and_action:
			continue
		doc = frappe.get_doc('SD YRP Time and Action', link.time_and_action)
		doc.check_permission("read")
		if doc.status == "Completed":
			continue
		result[doc.colour] = []
		for row in doc.details:
			value = row.as_dict()
			value["master"] = doc.master
			result[doc.colour].append(value)
	return result


@frappe.whitelist()
def update_t_and_a_ws(datas) -> None:
	datas = update_if_string_instance(datas)
	if not isinstance(datas, dict):
		frappe.throw(_("Invalid Work Station update."))
	seen = set()
	for rows in datas.values():
		if not rows:
			continue
		parent = rows[0].get("parent")
		if not parent or parent in seen:
			frappe.throw(_("Invalid Time and Action selection."))
		doc = frappe.get_doc('SD YRP Time and Action', parent)
		doc.check_permission("write")
		incoming = {row.get("action"): row for row in rows}
		if set(incoming) != {row.action for row in doc.details}:
			frappe.throw(_("Time and Action rows changed. Refresh and try again."))
		for row in doc.details:
			work_station = incoming[row.action].get("work_station")
			if work_station:
				station_action = frappe.db.get_value(
					'YRP Work Station', work_station, "action"
				)
				if station_action != row.action:
					frappe.throw(
						_("Work Station {0} is not configured for Action {1}.").format(
							frappe.bold(work_station), frappe.bold(row.action)
						)
					)
			row.work_station = work_station or None
		doc.save()
		seen.add(parent)

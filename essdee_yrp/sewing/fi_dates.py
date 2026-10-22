"""Final Inspection dates that the planning team sets on Sewing Plans."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import getdate
from yrp.attribute_links import value as _attribute_value

from essdee_yrp.sewing.entry import _variant_attributes
from essdee_yrp.sewing.read_models import _bucket, _json_list, _metadata, _plans


def is_production_planner(user: str | None = None) -> bool:
	roles = frappe.get_roles(user)
	planner_role = frappe.db.get_single_value("SD YRP MRP Settings", "production_planner_role")
	return "System Manager" in roles or bool(planner_role and planner_role in roles)


def require_production_planner():
	if not is_production_planner():
		frappe.throw(_("Only a Production Planner can update FI dates."), frappe.PermissionError)


@frappe.whitelist()
def get_fi_updates_data(supplier):
	"""Return one pending row per Lot, Colour and Part without an FI date."""
	plans = _plans(supplier)
	plan_map = {row.name: row for row in plans}
	lots, ipds = _metadata(plans)
	rows = (
		frappe.get_all(
			"SD YRP Sewing Plan Order Detail",
			filters={"parent": ["in", list(plan_map)], "fi_date": ["is", "not set"]},
			fields=["parent", "item_variant", "set_combination"],
			limit_page_length=0,
		)
		if plan_map
		else []
	)
	attributes = _variant_attributes({row.item_variant for row in rows})
	seen = set()
	data = []
	for row in rows:
		plan = plan_map[row.parent]
		lot = lots.get(plan.lot)
		ipd = ipds.get(lot.production_detail) if lot else None
		if not ipd:
			continue
		bucket, _size = _bucket(row, ipd, attributes)
		key = (plan.lot, bucket["key"], _attribute_value(bucket["part"]))
		if key in seen:
			continue
		seen.add(key)
		data.append(
			{
				"colour": bucket["key"],
				"part": _attribute_value(bucket["part"]),
				"sewing_plan": plan.name,
				"lot": plan.lot,
				"item": plan.item,
				"is_set_item": ipd.is_set_item,
				"set_attr": ipd.set_item_attribute,
			}
		)
	return {"data": data}


@frappe.whitelist(methods=["POST"])
def update_fi_dates(data):
	"""Set the FI date on every order row of a Lot, Colour and Part.

	Planners need not have write access on the Sewing Plan, matching production_api.
	"""
	require_production_planner()
	by_plan = defaultdict(list)
	for row in _json_list(data):
		if isinstance(row, dict) and row.get("sewing_plan"):
			by_plan[row["sewing_plan"]].append(row)
	if not by_plan:
		frappe.throw(_("Set at least one FI date to update."))
	for plan_name, updates in by_plan.items():
		update_plan_fi_dates(frappe.get_doc("SD YRP Sewing Plan", plan_name), updates)
	return _("Success")


def update_plan_fi_dates(plan, updates):
	plan.check_permission("read")
	lot = frappe.get_doc("SD YRP Lot", plan.lot)
	ipd = frappe.get_doc("YRP Item Production Detail", lot.production_detail)
	attributes = _variant_attributes({row.item_variant for row in plan.sewing_plan_order_details})
	for update in updates:
		if update.get("lot") != plan.lot:
			frappe.throw(_("Sewing Plan and Lot do not match."))
		fi_date = getdate(update["date"]) if update.get("date") else None
		for row in plan.sewing_plan_order_details:
			bucket, _size = _bucket(row, ipd, attributes)
			if bucket["key"] == _attribute_value(update.get("colour")) and _attribute_value(
				bucket["part"]
			) == _attribute_value(update.get("part")):
				row.fi_date = fi_date
	plan.save(ignore_permissions=True)

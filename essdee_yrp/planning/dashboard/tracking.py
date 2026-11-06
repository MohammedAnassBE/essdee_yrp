import frappe
from frappe import _
from frappe.utils import flt, today

from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.processes import LotProcesses
from essdee_yrp.planning.dashboard.production_orders import (
	PPO,
	get_iso_date,
	get_lots,
	get_lots_with_work_orders,
	get_ppo_details,
	get_ppo_items,
)
from essdee_yrp.planning.reports.production_quantities import authorize_filter_values


def get_tracking_options():
	"""PPO options (with item, for search by item) and Lot options (lots with a submitted Work Order)."""
	production_orders = frappe.get_list(
		PPO,
		filters={"docstatus": 1},
		fields=["name", "status", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)
	items = get_ppo_items([row["name"] for row in production_orders])
	lots = get_lots([row["name"] for row in production_orders])
	started = get_lots_with_work_orders([row["name"] for row in lots])
	return {
		"ppos": [
			{
				"name": row["name"],
				"item": items[row["name"]]["item"],
				"item_name": items[row["name"]]["item_name"],
				"status": row["status"],
				"delivery": get_iso_date(row["delivery_date"]),
			}
			for row in production_orders
		],
		"lots": [
			{"name": row["name"], "item": row["item"], "ppo": row["production_order"]}
			for row in lots
			if row["name"] in started
		],
	}


def get_scope_production_orders(ppos, lots):
	"""Selected PPOs, or the PPOs of the selected lots when no PPO is selected."""
	if ppos:
		names = ppos
	else:
		names = frappe.get_list(
			"SD YRP Lot",
			filters={"name": ["in", lots]},
			pluck="production_order",
			limit_page_length=0,
		)
	return frappe.get_list(
		PPO,
		filters={"name": ["in", list({name for name in names if name})], "docstatus": 1},
		fields=["name", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)


def get_tracking_data(ppos=None, lots=None):
	"""Lots of the selected PPOs or Lots with status, quantities and processes; one of the two is required."""
	ppos = authorize_filter_values(PPO, ppos)
	lots = authorize_filter_values("SD YRP Lot", lots)
	if not ppos and not lots:
		frappe.throw(_("Select a PPO or Lot to begin."))
	production_orders = get_scope_production_orders(ppos, lots)
	ppo_lots = get_lots([row["name"] for row in production_orders])
	started = get_lots_with_work_orders([row["name"] for row in ppo_lots])
	metrics = LotMetrics([row for row in ppo_lots if row["name"] in started])
	summaries = {name: metrics.get_summary(name) for name in metrics.names}
	details = get_ppo_details(production_orders, ppo_lots)
	for name, info in details.items():
		info["lots"] = [
			get_ppo_lot(row, row["name"] in started) for row in ppo_lots if row["production_order"] == name
		]
		info["work_order_lots"] = [
			get_work_order_lot(row, summaries[row["name"]])
			for row in ppo_lots
			if row["production_order"] == name and row["name"] in started
		]
	scope = [row for row in ppo_lots if row["name"] in started and (not lots or row["name"] in lots)]
	processes = LotProcesses(metrics)
	return {
		"as_of": today(),
		"ppos": details,
		"lots": [get_lot_row(row, details, summaries[row["name"]], processes) for row in scope],
	}


def get_ppo_lot(row, has_work_order):
	return {
		"lot": row["name"],
		"item": row["item"],
		"planned": flt(row["total_order_quantity"]),
		"has_work_order": has_work_order,
	}


def get_work_order_lot(row, summary):
	return {
		"lot": row["name"],
		"status": summary["status"],
		"qty": flt(row["total_order_quantity"]),
		"cut_pcs": summary["cut"],
		"dispatch": summary["dispatch"],
	}


def get_lot_row(row, details, summary, processes):
	return {
		"lot": row["name"],
		"ppo": row["production_order"],
		"item": row["item"],
		"delivery": details[row["production_order"]]["delivery"],
		"qty": flt(row["total_order_quantity"]),
		"status": summary["status"],
		"planned": summary["planned"],
		"cut": summary["order_cut"],
		"cut_pcs": summary["cut"],
		"total": summary["total"],
		"dispatch": summary["dispatch"],
		"balance": summary["balance"],
		"processes": processes.get_processes(row["name"]),
	}

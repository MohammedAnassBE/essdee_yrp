import frappe
from frappe.utils import flt, today

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics, get_sewing_processes
from essdee_yrp.planning.dashboard.production_orders import (
	PPO,
	get_lots,
	get_lots_with_work_orders,
	get_ppo_details,
)

ZERO_FIGURES = ("planned", "cut", "stitch", "packed", "total", "dispatch", "balance")


def get_dashboard_data():
	"""Every submitted Open PPO and its lots with status and quantities, for the factory-wide Dashboard."""
	production_orders = frappe.get_list(
		PPO,
		filters={"docstatus": 1, "status": "Open"},
		fields=["name", "delivery_date"],
		order_by="name asc",
		limit_page_length=0,
	)
	lots = get_lots([row["name"] for row in production_orders])
	ppos = get_ppo_details(production_orders, lots)
	started = get_lots_with_work_orders([row["name"] for row in lots])
	sewing = get_sewing_processes()
	metrics = LotMetrics([row for row in lots if row["name"] in started], sewing)
	return {
		"as_of": today(),
		"sewing_processes": sewing,
		"ppos": ppos,
		"lots": [
			get_lot_row(lot, ppos[lot["production_order"]], metrics, lot["name"] in started) for lot in lots
		],
	}


def get_lot_row(lot, ppo, metrics, has_work_order):
	row = {
		"lot": lot["name"],
		"ppo": lot["production_order"],
		"item": lot["item"],
		"delivery": ppo["delivery"],
		"qty": flt(lot["total_order_quantity"]),
		"has_work_order": has_work_order,
	}
	if not has_work_order:
		return {**row, "status": ladder.NO_WORK_ORDER, **dict.fromkeys(ZERO_FIGURES, 0.0)}
	summary = metrics.get_summary(lot["name"])
	return {**row, **{key: summary[key] for key in ("status", *ZERO_FIGURES)}}

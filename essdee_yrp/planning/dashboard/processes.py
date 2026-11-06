from collections import defaultdict
from functools import cached_property

import frappe
from frappe.utils import cint, flt

from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.dashboard.production_orders import get_iso_date


def get_grouped(query, names):
	"""{key: row tuple without the key} from a grouped query over `names`."""
	if not names:
		return {}
	return {row[0]: row[1:] for row in frappe.db.sql(query, {"names": tuple(names)})}


class LotProcesses:
	"""Process rows (by Work Order process name, in first-DC order) for lots already in `metrics`."""

	def __init__(self, metrics):
		self.metrics = metrics

	@cached_property
	def order_names(self):
		return [order["name"] for order in self.metrics.orders if not cint(order["is_rework"])]

	@cached_property
	def first_dc(self):
		return get_grouped(
			"""select work_order, min(posting_date) from `tabYRP Delivery Challan`
			where docstatus=1 and work_order in %(names)s group by work_order""",
			self.order_names,
		)

	@cached_property
	def last_grn(self):
		return get_grouped(
			"""select against_id, max(posting_date) from `tabYRP Goods Received Note`
			where against='YRP Work Order' and docstatus=1 and is_return=0 and against_id in %(names)s
			group by against_id""",
			self.order_names,
		)

	@cached_property
	def deliverables(self):
		"""{work order: (planned, moved)} of Deliverables (cloth Kg)."""
		return get_grouped(
			"""select parent, sum(ifnull(qty, 0)), sum(ifnull(qty, 0) - ifnull(pending_quantity, 0))
			from `tabYRP Work Order Deliverables` where parent in %(names)s group by parent""",
			self.order_names,
		)

	@cached_property
	def receivables(self):
		"""{work order: (planned, moved)} of Receivables (cloth Kg)."""
		return get_grouped(
			"""select parent, sum(ifnull(qty, 0)), sum(ifnull(qty, 0) - ifnull(pending_quantity, 0))
			from `tabYRP Work Order Receivables` where parent in %(names)s group by parent""",
			self.order_names,
		)

	@cached_property
	def packed(self):
		"""{work order: packed pieces} from its non-return GRNs; version 2 GRNs already hold pieces."""
		packing = [order for order in self.metrics.orders if cint(order["includes_packing"])]
		names = [order["name"] for order in packing]
		rows = (
			frappe.db.sql(
				"""select g.against_id, g.packing_calculation_version, sum(gi.quantity)
			from `tabYRP Goods Received Note` g join `tabYRP Goods Received Note Item` gi on gi.parent=g.name
			where g.against='YRP Work Order' and g.docstatus=1 and g.is_return=0 and g.against_id in %(names)s
			group by g.against_id, g.packing_calculation_version""",
				{"names": tuple(names)},
			)
			if names
			else []
		)
		lot_of = {order["name"]: order["lot"] for order in packing}
		result = defaultdict(float)
		for work_order, version, quantity in rows:
			combo = 1 if cint(version) >= 2 else self.get_packing_combo(lot_of[work_order])
			result[work_order] += flt(quantity) * flt(combo)
		return result

	@cached_property
	def ipd_packing_combos(self):
		ipds = {row.get("production_detail") for row in self.metrics.lots.values()} - {None, ""}
		if not ipds:
			return {}
		return dict(
			frappe.get_all(
				"YRP Item Production Detail",
				filters={"name": ["in", list(ipds)]},
				fields=["name", "packing_combo"],
				as_list=True,
				limit_page_length=0,
			)
		)

	def get_packing_combo(self, lot):
		row = self.metrics.lots[lot]
		return row.get("packing_combo") or self.ipd_packing_combos.get(row.get("production_detail"))

	def get_work_order_row(self, order, kind):
		totals = self.metrics.item_totals.get(order["name"], {})
		planned, delivered, received = (totals.get(key, 0.0) for key in ("planned", "delivered", "received"))
		if kind == "cloth":
			planned, received = (flt(value) for value in self.receivables.get(order["name"], (0, 0)))
		if kind in ("cloth", "cutting"):
			delivered = flt(self.deliverables.get(order["name"], (0, 0))[1])
		if kind == "packing" and cint(order["includes_packing"]):
			received = self.packed.get(order["name"], 0.0)
		first_dc, last_grn = (
			self.first_dc.get(order["name"], (None,))[0],
			self.last_grn.get(order["name"], (None,))[0],
		)
		return {
			"name": order["name"],
			"supplier": order["supplier"],
			"supplier_name": (order.get("supplier_name") or order["supplier"] or "").strip(),
			"status": order["status"],
			"first_dc": get_iso_date(first_dc),
			"last_grn": get_iso_date(last_grn),
			"planned": planned,
			"delivered": delivered,
			"received": received,
		}

	def get_process_row(self, lot, process, orders):
		kind = ladder.get_process_kind(process, orders, self.metrics.lots[lot]["item"])
		work_orders = [self.get_work_order_row(order, kind) for order in orders]
		first_dcs = [row["first_dc"] for row in work_orders if row["first_dc"]]
		last_grns = [row["last_grn"] for row in work_orders if row["last_grn"]]
		is_packing = kind == "packing"
		return {
			"name": process,
			"kind": kind,
			"first_dc": min(first_dcs) if first_dcs else None,
			"last_grn": max(last_grns) if last_grns else None,
			**{key: sum(row[key] for row in work_orders) for key in ("planned", "delivered", "received")},
			"dispatch": self.metrics.dispatch.get(lot, 0.0) if is_packing else 0.0,
			"status": rules.step_status(orders),
			"reason": ladder.get_status_reason(orders),
			"finishing_plans": self.metrics.get_finishing_plans(lot) if is_packing else [],
			"work_orders": work_orders,
		}

	def get_processes(self, lot):
		groups = defaultdict(list)
		for order in self.metrics.get_production_orders(lot):
			groups[order["process_name"]].append(order)
		return ladder.sort_by_first_dc(
			[self.get_process_row(lot, process, orders) for process, orders in groups.items()]
		)

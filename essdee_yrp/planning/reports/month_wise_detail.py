from collections import defaultdict

import frappe

from essdee_yrp.planning.reports import production_quantities as quantities

METRICS = ("cut_qty", "sewing_sent", "finishing_inward", "dispatch")


def can_view() -> bool:
	return quantities.can_read("YRP Work Order", "SD YRP Lot", "YRP Stock Entry", "SD YRP Finishing Plan")


def require_access() -> None:
	quantities.require_report_access(can_view())


def aggregate(events):
	groups = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(METRICS, 0)))
	for event in events:
		month = str(event["date"])[:7]
		for metric in METRICS:
			groups[event["item"]][month][metric] += event.get(metric) or 0
	result = []
	for item, months in sorted(groups.items()):
		for month, values in sorted(months.items()):
			result.append({"item": item, "month": month, **values})
		result.append({"item": item, "month": "Total", "is_total_row": True, **{metric: sum(values[metric] for values in months.values()) for metric in METRICS}})
	return result


def dispatch_events(lots, start, end):
	plans = frappe.get_list("SD YRP Finishing Plan", filters={"lot": ["in", list(lots)]}, fields=["name", "lot"], limit_page_length=0) if lots else []
	plan_lots = {row["name"]: row["lot"] for row in plans}
	dispatches = frappe.get_list("SD YRP Finishing Plan Dispatch", filters=[["SD YRP Finishing Plan Dispatch Item", "against_id", "in", list(plan_lots)]], pluck="name", limit_page_length=0) if plan_lots and quantities.can_read("SD YRP Finishing Plan Dispatch") else []
	conditions = {"docstatus": 1, "against": ["in", ["SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch"]], "against_id": ["in", list(plan_lots) + dispatches]}
	if start:
		conditions["posting_date"] = ["between", [start, end]]
	entries = frappe.get_list("YRP Stock Entry", filters=conditions, fields=["name", "posting_date", "against", "against_id"], limit_page_length=0) if plan_lots else []
	entry_map = {row["name"]: row for row in entries}
	details = quantities.child_rows("YRP Stock Entry Detail", entry_map, ["item", "qty", "conversion_factor", "lot"], "YRP Stock Entry")
	variants = {row["name"]: row.get("variant_of") or row["name"] for row in frappe.get_all("Item", filters={"name": ["in", list({row["item"] for row in details})]}, fields=["name", "variant_of"], limit_page_length=0)} if details else {}
	events = []
	for row in details:
		entry = entry_map[row["parent"]]
		lot = row.get("lot") or (plan_lots.get(entry["against_id"]) if entry["against"] == "SD YRP Finishing Plan" else None)
		if lot in lots and variants.get(row["item"]) == lots[lot]["item"]:
			events.append({"item": variants[row["item"]], "date": entry["posting_date"], "dispatch": (row.get("qty") or 0) * (row.get("conversion_factor") or 0)})
	return events


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	lots = quantities.authorize_filter_values("SD YRP Lot", filters.get("lot"))
	items = quantities.authorize_filter_values("Item", filters.get("item"))
	if not lots and not items:
		frappe.throw("Select at least one Lot or Item.")
	start, end = quantities.validate_dates(filters)
	conditions = {}
	if lots:
		conditions["name"] = ["in", lots]
	if items:
		conditions["item"] = ["in", items]
	lot_rows = frappe.get_list("SD YRP Lot", filters=conditions, fields=["name", "item"], limit_page_length=0)
	lot_map = {row["name"]: row for row in lot_rows}
	settings = frappe.get_single("SD YRP IPD Settings")
	process_details = frappe.get_all("YRP Process Details", fields=["parent", "process_name"], limit_page_length=0)
	cutting = quantities.expand_processes(settings.default_cutting_process, process_details)
	sewing = quantities.expand_processes(settings.default_stitching_process, process_details)
	orders = quantities.work_orders({"lot": ["in", list(lot_map)], "process_name": ["in", sorted(set(cutting + sewing))]}, include_rework=True) if lot_map else []
	order_map = {row["name"]: row for row in orders}
	tracks = quantities.child_rows("YRP Work Order Track Piece", order_map, ["date", "delivered_quantity", "received_qty"], "YRP Work Order")
	events = []
	for row in tracks:
		date = str(row["date"])
		if start and not str(start) <= date <= str(end):
			continue
		order = order_map[row["parent"]]
		events.append({"item": lot_map[order["lot"]]["item"], "date": date, "cut_qty": row.get("received_qty") if order["process_name"] in cutting else 0, "sewing_sent": row.get("delivered_quantity") if order["process_name"] in sewing else 0, "finishing_inward": row.get("received_qty") if order["process_name"] in sewing else 0})
	events.extend(dispatch_events(lot_map, start, end))
	columns = [quantities.column("month", "Month")] + [quantities.column(field, label, "Float") for field, label in zip(METRICS, ("Cut Qty", "Sewing Sent", "Finishing Inward", "Dispatch"), strict=True)]
	return {"columns": columns, "result": aggregate(events), "summary": {"items": len({event["item"] for event in events})}}


def dependency_doctypes(filters=None) -> list[str]:
	return [*quantities.dependency_doctypes(filters), "YRP Work Order Track Piece", "SD YRP IPD Settings", "SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch", "SD YRP Finishing Plan Dispatch Item", "YRP Stock Entry", "YRP Stock Entry Detail"]

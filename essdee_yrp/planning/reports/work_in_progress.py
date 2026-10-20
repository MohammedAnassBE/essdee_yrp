from collections import defaultdict

import frappe

from essdee_yrp.planning.reports import production_quantities as quantities
from essdee_yrp.planning.reports import size_wise_stock

METRICS = (
	("order_qty", "Order Qty"), ("cut_qty", "Cut Qty"), ("order_to_cut_diff", "Order-to-Cut Diff"),
	("sewing_sent", "Sewing Sent"), ("sewing_received", "Sewing Received"), ("cut_to_sew_diff", "Cut-to-Sew Diff"),
	("ready_for_packing", "Ready for Packing"), ("finishing_inward", "Finishing Inward"), ("in_sew", "In Sew"),
	("dispatch", "Dispatch"), ("in_packing", "In Packing"), ("transferred", "Transferred"), ("cut_to_dispatch_diff", "Cut-to-Dispatch Diff"),
)
DATES = (("last_cut_date", "Last Cut Date"), ("sew_sent_date", "Sew Sent Date"), ("finishing_inward_date", "Finishing Inward Date"))


def can_view() -> bool:
	return size_wise_stock.can_view() and quantities.can_read("SD YRP GRN Rework Item", "YRP Goods Received Note")


def require_access() -> None:
	quantities.require_report_access(can_view())


def receipt_context(context):
	orders = {row["name"]: row for row in context["orders"]}
	lot_details = {lot["name"]: context["details"][lot["production_detail"]] for lot in context["lots"]}
	receipts = frappe.get_list("YRP Goods Received Note", filters={"docstatus": 1, "against": "YRP Work Order", "against_id": ["in", list(orders)], "is_return": 0}, fields=["name", "against_id"], limit_page_length=0) if orders else []
	receipts = {row["name"]: row for row in receipts}
	accepted_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	accepted = defaultdict(float)
	packing = defaultdict(lambda: {"quantity": 0, "stock_qty": 0})
	for row in quantities.child_rows("YRP Goods Received Note Item", receipts, ["quantity", "stock_qty", "received_type"], "YRP Goods Received Note"):
		order = orders[receipts[row["parent"]]["against_id"]]
		detail = lot_details[order["lot"]]
		if order["process_name"] in context["expanded"].get(detail.get("stiching_process"), []) and row.get("received_type") == accepted_type:
			accepted[order["lot"]] += row.get("quantity") or 0
		if order.get("includes_packing"):
			for field in ("quantity", "stock_qty"):
				packing[order["lot"]][field] += row.get(field) or 0
	reworks = frappe.get_list("SD YRP GRN Rework Item", filters={"lot": ["in", [lot["name"] for lot in context["lots"]]]}, fields=["name", "lot"], limit_page_length=0) if context["lots"] else []
	reworks = {row["name"]: row["lot"] for row in reworks}
	reworked = defaultdict(float)
	for row in quantities.child_rows("SD YRP GRN Rework Item Detail", reworks, ["reworked"], "SD YRP GRN Rework Item"):
		reworked[reworks[row["parent"]]] += row.get("reworked") or 0
	return {"packing": packing, "reworked": reworked, "accepted": accepted}


def aggregate(context, finishing, receipts, processes):
	stock = size_wise_stock.aggregate(context, finishing, processes)
	orders = {row["name"]: row for row in context["orders"]}
	stages = {(row["parent"], row["process_name"]): row for row in context["stages"]}
	rows = []
	for lot in context["lots"]:
		detail = context["details"][lot["production_detail"]]
		values = {key: sum(amounts.values()) for key, amounts in stock[lot["name"]].items()}
		values.update(item=lot["item"], lot=lot["name"])
		values["sewing_received"] = values.get("finishing_inward", 0)
		values["cut_qty"] = 0
		lot_orders = [order for order in orders.values() if order["lot"] == lot["name"]]
		cutting = context["expanded"].get(detail.get("cutting_process"), [])
		sewing = context["expanded"].get(detail.get("stiching_process"), [])
		for row in context["items"]:
			order = orders[row["parent"]]
			if order["lot"] != lot["name"]:
				continue
			if order["process_name"] in cutting:
				values["cut_qty"] += row.get("received_qty") or 0
		plans = [plan for plan in finishing["plans"].values() if plan["lot"] == lot["name"]]
		if plans:
			plan_names = {plan["name"] for plan in plans}
			values["finishing_inward"] = sum(row.get("dc_qty") or 0 for row in finishing["inwards"] if row["parent"] in plan_names)
		elif lot["name"] in receipts["packing"]:
			packing = receipts["packing"][lot["name"]]
			values["dispatch"] = packing["quantity"] * (detail.get("packing_combo") or 1) * finishing["parts"][detail["name"]]
			values["finishing_inward"] = packing["stock_qty"]
		values["ready_for_packing"] = max(0, receipts["accepted"].get(lot["name"], 0) + receipts["reworked"].get(lot["name"], 0) - values.get("dispatch", 0))
		values["order_to_cut_diff"] = values["cut_qty"] - values.get("order_qty", 0)
		values["cut_to_sew_diff"] = values.get("sewing_sent", 0) - values["cut_qty"]
		values["in_sew"] = values["sewing_received"] - values.get("sewing_sent", 0)
		values["in_packing"] = values.get("dispatch", 0) - values.get("finishing_inward", 0)
		values["cut_to_dispatch_diff"] = values.get("dispatch", 0) + values.get("transferred", 0) - values["cut_qty"]
		for field, date_field, allowed, reducer in (("last_cut_date", "last_grn_date", cutting, max), ("sew_sent_date", "first_dc_date", sewing, min), ("finishing_inward_date", "last_grn_date", sewing, max)):
			dates = [str(order[date_field]) for order in lot_orders if order["process_name"] in allowed and order.get(date_field)]
			values[field] = reducer(dates) if dates else None
		previous = {"cut": ("cut_qty", "Cut"), "piece": ("finishing_inward", "Finishing Inward")}
		values["process_links"] = {}
		for index, process in enumerate(processes):
			stage = stages.get((detail["name"], process), {})
			comparison = quantities.process_comparison(stage, detail)
			baseline, _label = previous[comparison]
			received = f"process_{index}_received"
			values[f"process_{index}_against_{comparison}"] = values.get(received, 0) - values.get(baseline, 0)
			previous[comparison] = (received, process)
			for suffix in ("sent", "received", "diff", "against_cut", "against_piece"):
				values["process_links"][f"process_{index}_{suffix}"] = process
		for key, allowed in (("cut_qty", cutting), ("sewing_sent", sewing), ("sewing_received", sewing), ("in_sew", sewing)):
			matching = sorted({order["process_name"] for order in lot_orders if order["process_name"] in allowed})
			if len(matching) == 1:
				values["process_links"][key] = matching[0]
		rows.append(values)
	columns = [quantities.column("item", "Style"), quantities.column("lot", "Lot")]
	columns += [quantities.column(field, label, "Float") for field, label in METRICS]
	columns += [quantities.column(field, label, "Date") for field, label in DATES]
	for index, process in enumerate(processes):
		columns += [quantities.column(f"process_{index}_{suffix}", process + " " + suffix.title(), "Float") for suffix in ("sent", "received", "diff")]
		for comparison in ("cut", "piece"):
			if any(f"process_{index}_against_{comparison}" in row for row in rows):
				columns.append(quantities.column(f"process_{index}_against_{comparison}", process + " against " + comparison, "Float"))
	numeric = [column["fieldname"] for column in columns if column["fieldtype"] == "Float"]
	totals = {field: sum(row.get(field, 0) for row in rows) for field in numeric}
	summary = {"Lots": len(rows), **{label: totals.get(field, 0) for field, label in METRICS}}
	if rows:
		rows.append({"item": "Total", "is_total_row": True, **totals})
	return {"columns": columns, "result": rows, "summary": summary, "report_summary": [{"label": label, "value": value, "datatype": "Float"} for label, value in summary.items()]}


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	processes = quantities.authorize_filter_values("YRP Process", filters.get("process_list"))
	if progress:
		progress(0, 4)
	lots = quantities.production_lots(filters, creation_end_midnight=True)
	context = quantities.production_context(lots, processes)
	if progress:
		progress(1, 4)
	finishing = quantities.finishing_context(lots, context["details"])
	context["attributes"].update(quantities.variant_attributes({row["item_variant"] for row in [*finishing["dispatches"], *finishing["inwards"]]}))
	if progress:
		progress(2, 4)
	receipts = receipt_context(context)
	if progress:
		progress(3, 4)
	result = aggregate(context, finishing, receipts, processes)
	if progress:
		progress(4, 4)
	return result


def dependency_doctypes(filters=None) -> list[str]:
	return [*size_wise_stock.dependency_doctypes(filters), "SD YRP GRN Rework Item", "SD YRP GRN Rework Item Detail", "YRP Goods Received Note", "YRP Goods Received Note Item", "YRP Stock Settings"]

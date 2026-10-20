from collections import defaultdict

import frappe
from frappe.utils import date_diff, nowdate

from essdee_yrp.planning.reports import production_quantities as quantities


def can_view() -> bool:
	return quantities.can_read("YRP Work Order", "SD YRP Lot")


def require_access() -> None:
	quantities.require_report_access(can_view())


@frappe.whitelist()
def get_defaults():
	require_access()
	return {"process": frappe.db.get_single_value("SD YRP MRP Settings", "finishing_inward_process") or ""}


def submitted_delivery_challans(lots, processes):
	# Legacy annotation dates include DCs for rework orders too, while the
	# quantity query deliberately excludes those orders.
	if not lots or not processes:
		return []
	orders = frappe.get_list("YRP Work Order", filters={"lot": ["in", [row["name"] for row in lots]], "process_name": ["in", processes]}, fields=["name", "supplier", "is_internal_unit"], limit_page_length=0)
	orders = {row["name"]: row for row in orders}
	if not orders:
		return []
	dcs = frappe.get_list("YRP Delivery Challan", filters={"docstatus": 1, "work_order": ["in", list(orders)], "lot": ["in", [row["name"] for row in lots]]}, fields=["work_order", "lot", "posting_date"], limit_page_length=0)
	return [{**dc, "supplier_bucket": orders[dc["work_order"]]["supplier"] if orders[dc["work_order"]].get("is_internal_unit") else "Others"} for dc in dcs]


def aggregate(lots, orders, items, cutting_processes, selected_processes, supplier_labels=None, delivery_challans=()):
	orders = {row["name"]: row for row in orders}
	groups = {lot["name"]: {"item": lot["item"], "lot": lot["name"], "cutting_qty": 0, "cutting_completion": None, "received": 0, "pending": defaultdict(float), "has_cutting": False} for lot in lots}
	internal = set()
	for order in orders.values():
		if order["process_name"] in cutting_processes.get(order["lot"], []):
			group = groups[order["lot"]]
			group["has_cutting"] = True
			if order.get("last_grn_date"):
				group["cutting_completion"] = max(group["cutting_completion"] or "", str(order["last_grn_date"]))
	for item in items:
		order = orders[item["parent"]]
		group = groups[order["lot"]]
		if order["process_name"] in cutting_processes.get(order["lot"], []):
			group["cutting_qty"] += item.get("received_qty") or 0
		if order["process_name"] in selected_processes:
			supplier = order["supplier"] if order.get("is_internal_unit") else "Others"
			if order.get("is_internal_unit"):
				internal.add(supplier)
			group["pending"][supplier] += (item.get("delivered_quantity") or 0) - (item.get("received_qty") or 0)
			group["received"] += item.get("received_qty") or 0
	labels = supplier_labels if supplier_labels is not None else {row["supplier"]: row.get("supplier_name") or row["supplier"] for row in orders.values()}
	last_dc_dates = defaultdict(dict)
	for dc in delivery_challans:
		order = orders.get(dc["work_order"])
		if not dc.get("posting_date"):
			continue
		if "supplier_bucket" not in dc and (not order or order["process_name"] not in selected_processes):
			continue
		supplier = dc["supplier_bucket"] if "supplier_bucket" in dc else (order["supplier"] if order.get("is_internal_unit") else "Others")
		supplier = labels.get(supplier, supplier)
		lot = dc["lot"]
		last_dc_dates[lot][supplier] = max(last_dc_dates[lot].get(supplier, ""), str(dc["posting_date"]))
	suppliers = sorted(internal)
	rows = []
	for group in groups.values():
		if not group["has_cutting"]:
			continue
		dates = {labels.get(supplier, supplier): last_dc_dates[group["lot"]].get(labels.get(supplier, supplier)) for supplier in group["pending"]}
		ages = {supplier: max(date_diff(nowdate(), date), 0) if date else None for supplier, date in dates.items()}
		rows.append({"supplier_last_dc_dates": dates, "supplier_pending_days": ages, "number": len(rows) + 1, **{key: group[key] for key in ("item", "lot", "cutting_qty", "cutting_completion", "received")}, **{f"supplier_{index}": group["pending"].get(supplier, 0) for index, supplier in enumerate(suppliers)}, "others": group["pending"].get("Others", 0)})
	fields = ["cutting_qty", "received", "others"] + [f"supplier_{index}" for index in range(len(suppliers))]
	total = {field: sum(row[field] for row in rows) for field in fields}
	pending = sum(total[field] for field in fields if field not in ("cutting_qty", "received"))
	summary = {"Total Lots": len(rows), "Cutting Received": total["cutting_qty"], "Received": total["received"], "Overall Pending": total["cutting_qty"] - total["received"], "Not Delivered": total["cutting_qty"] - total["received"] - pending}
	if rows:
		rows.append({"item": "Total", "is_total_row": True, **total})
	columns = [quantities.column("number", "#", "Int"), quantities.column("item", "Item"), quantities.column("lot", "Lot", "Link", options="SD YRP Lot"), quantities.column("cutting_qty", "Cutting Qty", "Float"), quantities.column("cutting_completion", "Cutting Completion", "Date")]
	columns += [quantities.column(f"supplier_{index}", labels.get(supplier, supplier), "Float") for index, supplier in enumerate(suppliers)]
	columns += [quantities.column("others", "Others", "Float"), quantities.column("received", "Total Received Qty", "Float")]
	return {"columns": columns, "result": rows, "summary": summary, "report_summary": [{"label": label, "value": value, "datatype": "Float"} for label, value in summary.items()]}


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	lots = quantities.authorize_filter_values("SD YRP Lot", filters.get("lot"))
	items = quantities.authorize_filter_values("Item", filters.get("item"))
	status = filters.get("lot_status", "Open")
	if status not in ("Open", "Closed"):
		frappe.throw("Lot Status must be Open or Closed.")
	conditions = {"status": status}
	if lots:
		conditions["name"] = ["in", lots]
	if filters.get("category"):
		quantities.authorize_filter_values("SD YRP Product Category", [filters["category"]])
		category_items = frappe.get_list("Item", filters={"product_category": filters["category"]}, pluck="name", limit_page_length=0)
		items = [item for item in items if item in category_items] if items else category_items
		conditions["item"] = ["in", items]
	elif items:
		conditions["item"] = ["in", items]
	lot_rows = frappe.get_list("SD YRP Lot", filters=conditions, fields=["name", "item", "production_detail"], limit_page_length=0)
	detail_names = list({row["production_detail"] for row in lot_rows if row.get("production_detail")})
	details = frappe.get_all("YRP Item Production Detail", filters={"name": ["in", detail_names]}, fields=["name", "cutting_process"], limit_page_length=0) if detail_names else []
	details = {row["name"]: row.get("cutting_process") for row in details}
	process = filters.get("process") or get_defaults()["process"]
	if process:
		quantities.authorize_filter_values("YRP Process", [process])
	process_details = frappe.get_all("YRP Process Details", fields=["parent", "process_name"], limit_page_length=0)
	cutting = {row["name"]: quantities.expand_processes(details.get(row["production_detail"]), process_details) for row in lot_rows}
	selected = quantities.expand_processes(process, process_details)
	orders = quantities.work_orders({"lot": ["in", [row["name"] for row in lot_rows]]}) if lot_rows else []
	date_processes = list({process, *[row["parent"] for row in process_details if row["process_name"] == process or row["parent"] == process]}) if process else []
	dcs = submitted_delivery_challans(lot_rows, date_processes)
	return aggregate(lot_rows, orders, quantities.calculated_items(orders), cutting, selected, quantities.supplier_names(orders + [{"supplier": dc["supplier_bucket"]} for dc in dcs if dc["supplier_bucket"] != "Others"]), dcs)


def dependency_doctypes(filters=None) -> list[str]:
	return [*quantities.dependency_doctypes(filters), "SD YRP Product Category", "SD YRP MRP Settings", "Supplier", "YRP Delivery Challan"]

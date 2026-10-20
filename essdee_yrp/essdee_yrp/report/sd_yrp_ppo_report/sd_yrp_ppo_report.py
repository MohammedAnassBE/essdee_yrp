from frappe import _
from frappe.utils import cint

from essdee_yrp.sales import ppo_report


def execute(filters=None):
	filters = filters or {}
	report = ppo_report.get_ppo_report(filters)
	rows = [
		{**order, **{f"size_{index}": value for index, value in enumerate(order["qty_by_position"])}}
		for order in report["orders"]
	]
	if cint(filters.get("summarized")):
		rows = dispatch_rows(report, rows)
	summary = [
		{"label": _(label), "value": report["summary"][key], "datatype": "Float" if key == "total_quantity" else "Int"}
		for key, label in (("total_orders", "Total Orders"), ("total_quantity", "Total Quantity"), ("size_groups", "Size Groups"))
	]
	return get_columns(report, filters), rows, None, None, summary


def dispatch_rows(report, orders):
	summaries = ppo_report.get_ppo_dispatch_summary_bulk([order["name"] for order in orders]) if orders else {}
	rows = []
	for order in orders:
		rows.append({**order, "row_type": _("Order")})
		dispatches = summaries.get(order["name"], {}).get("rows", [])
		for dispatch in dispatches:
			rows.append({
				"name": order["name"], "item": order["item"], "group_label": order["group_label"],
				"row_type": _("Dispatch"), "dispatch_date": dispatch["date"], "lot": dispatch["lot"],
				**{f"size_{index}": dispatch["sizes"].get(order["group_sizes"][index], 0) if index < len(order["group_sizes"]) else 0 for index in range(report["max_columns"])},
				"total": dispatch["total"],
			})
		if dispatches:
			rows.append({
				"name": order["name"], "item": order["item"], "row_type": _("Dispatched Total"),
				**{f"size_{index}": sum(dispatch["sizes"].get(order["group_sizes"][index], 0) for dispatch in dispatches) if index < len(order["group_sizes"]) else 0 for index in range(report["max_columns"])},
				"total": sum(dispatch["total"] for dispatch in dispatches),
			})
	return rows


def get_columns(report, filters):
	columns = [
		column("name", "PPO", "Link", options="YRP Production Order"),
		column("item", "Item", "Link", options="Item"),
	]
	for field, label, fieldtype in (("fabric", "Fabric", "Data"), ("dia", "Dia", "Data"), ("gsm", "GSM", "Float")):
		if cint(filters.get(f"show_{field}")):
			columns.append(column(field, label, fieldtype))
	columns += [
		column("posting_date", "Posting Date", "Date"),
		column("delivery_date", "Delivery Date", "Date"),
		column("dont_deliver_after", "Don't Deliver After", "Date"),
		column("lead_time", "Lead Time", "Int"),
		column("status", "Status"),
		column("group_label", "Size Group"),
	]
	if cint(filters.get("summarized")):
		columns += [column("row_type", "Type"), column("dispatch_date", "Dispatch Date", "Date"), column("lot", "Lot", "Link", options="SD YRP Lot")]
	for index in range(report["max_columns"]):
		labels = [f"{group['label']}: {group['sizes'][index]}" for group in report["size_groups"] if index < len(group["sizes"])]
		columns.append(column(f"size_{index}", " / ".join(labels), "Float"))
	return columns + [column("total", "Total", "Float"), column("transfer_summary", "Quantity Transfer"), column("comments", "Comments")]


def column(fieldname, label, fieldtype="Data", **options):
	return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": 160, **options}

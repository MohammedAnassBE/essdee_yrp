from collections import defaultdict

import frappe
from frappe.utils import date_diff

from essdee_yrp.planning.reports import production_quantities as quantities


def can_view() -> bool:
	return quantities.can_read("YRP Work Order", "SD YRP Lot")


def require_access() -> None:
	quantities.require_report_access(can_view())


def inspection_status(orders):
	if not quantities.can_read("SD YRP Essdee Quality Inspection") or not orders:
		return {}
	inspections = frappe.get_list("SD YRP Essdee Quality Inspection", filters={"docstatus": 1, "against": "YRP Work Order", "against_id": ["in", [row["name"] for row in orders]]}, fields=["name", "against_id", "posting_date", "result"], order_by="posting_date desc, modified desc, name desc", limit_page_length=0)
	parents = [row["name"] for row in inspections]
	colours = quantities.child_rows("SD YRP Essdee Quality Inspection Colour", parents, ["colour", "selected"], "SD YRP Essdee Quality Inspection")
	sizes = quantities.child_rows("SD YRP Essdee Quality Inspection Size", parents, ["size", "selected"], "SD YRP Essdee Quality Inspection")
	result = {}
	for rank, inspection in enumerate(inspections):
		for colour in (row["colour"] for row in colours if row["parent"] == inspection["name"] and row["selected"]):
			for size in (row["size"] for row in sizes if row["parent"] == inspection["name"] and row["selected"]):
				result.setdefault((inspection["against_id"], colour, size), {"tone": (inspection.get("result") or "").lower(), "rank": rank})
	return result


def aggregate(items, attributes, detail, sizes, orders, statuses=None, supplier_labels=None):
	orders = {row["name"]: row for row in orders}
	groups = {}
	for item in items:
		order = orders[item["parent"]]
		colour, part, size = quantities.matrix_identity(item, attributes, detail)
		key = (colour, part, order["supplier"])
		group = groups.setdefault(key, {"delivered": defaultdict(float), "received": defaultdict(float), "orders": {}, "tones": {}})
		group["delivered"][size] += item.get("delivered_quantity") or 0
		group["received"][size] += item.get("received_qty") or 0
		group["orders"][order["name"]] = order
		status = (statuses or {}).get((order["name"], colour, size))
		if status and (size not in group["tones"] or status["rank"] < group["tones"][size]["rank"]):
			group["tones"][size] = status
	result = []
	footers = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	for number, ((colour, part, supplier), group) in enumerate(sorted(groups.items()), 1):
		dates = {}
		for field, reducer in (("first_dc_date", min), ("last_dc_date", max), ("first_grn_date", min), ("last_grn_date", max)):
			values = [str(order[field]) for order in group["orders"].values() if order.get(field)]
			dates[field] = reducer(values) if values else None
		for row_type in ("Delivered", "Received", "Difference"):
			values = group[row_type.lower()] if row_type != "Difference" else {size: group["received"][size] - group["delivered"][size] for size in sizes}
			row = quantities.numeric_row({"number": number, "colour": colour, "part": part, "supplier": (supplier_labels or {}).get(supplier) or supplier, "type": row_type}, values, sizes)
			for size, amount in values.items():
				footers[part][row_type][size] += amount
			prefix = {"Delivered": "dc", "Received": "grn"}.get(row_type)
			row.update(first_date=dates[f"first_{prefix}_date"] if prefix else None, last_date=dates[f"last_{prefix}_date"] if prefix else None, diff=date_diff(dates["last_grn_date"], dates["last_dc_date"]) if dates["last_grn_date"] and dates["last_dc_date"] else None)
			row["tones"] = {f"size_{index}": group["tones"].get(size, {}).get("tone", "") for index, size in enumerate(sizes)} if row_type == "Received" else {}
			result.append(row)
	for part, types in sorted(footers.items()):
		for row_type in ("Delivered", "Received", "Difference"):
			result.append(quantities.numeric_row({"colour": "Total", "part": part, "type": row_type, "is_total_row": True}, types[row_type], sizes))
	return result


def run(filters, progress=None) -> dict:
	require_access()
	lot, detail, sizes, orders, items, attributes = quantities.quantity_context(filters or {})
	rows = aggregate(items, attributes, detail, sizes, orders, inspection_status(orders), quantities.supplier_names(orders))
	columns = [*quantities.matrix_columns(sizes, detail.is_set_item, supplier=True), quantities.column("first_date", "First Date", "Date"), quantities.column("last_date", "Last Date", "Date"), quantities.column("diff", "Diff", "Int")]
	return {"columns": columns, "result": rows, "summary": {"item": lot.item}, "message": lot.item}


def dependency_doctypes(filters=None) -> list[str]:
	return [*quantities.dependency_doctypes(filters), "Supplier", "SD YRP Essdee Quality Inspection", "SD YRP Essdee Quality Inspection Colour", "SD YRP Essdee Quality Inspection Size"]

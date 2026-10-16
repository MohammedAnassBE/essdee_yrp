from collections import defaultdict

import frappe

from essdee_yrp.planning.reports import production_quantities as quantities


def can_view() -> bool:
	return quantities.can_read("YRP Work Order", "SD YRP Lot")


def require_access() -> None:
	quantities.require_report_access(can_view())


def aggregate(items, attributes, detail, sizes):
	groups = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	for item in items:
		colour, part, size = quantities.matrix_identity(item, attributes, detail)
		for received_type, amount in frappe.parse_json(item.get("received_type_json") or "{}").items():
			groups[(colour, part)][received_type][size] += amount or 0
	result = []
	footers = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	for number, ((colour, part), types) in enumerate(sorted(groups.items()), 1):
		total = defaultdict(float)
		for received_type, values in sorted(types.items()):
			result.append(quantities.numeric_row({"number": number, "colour": colour, "part": part, "type": received_type}, values, sizes))
			for size, amount in values.items():
				total[size] += amount
				footers[part][received_type][size] += amount
		result.append(quantities.numeric_row({"colour": colour, "part": part, "type": "Total", "is_total_row": True}, total, sizes))
	for part, types in sorted(footers.items()):
		total = defaultdict(float)
		for received_type, values in sorted(types.items()):
			result.append(quantities.numeric_row({"colour": "Total", "part": part, "type": received_type, "is_total_row": True}, values, sizes))
			for size, amount in values.items():
				total[size] += amount
		result.append(quantities.numeric_row({"colour": "Total", "part": part, "type": "Total", "is_total_row": True}, total, sizes))
	return result


def run(filters, progress=None) -> dict:
	require_access()
	lot, detail, sizes, _orders, items, attributes = quantities.quantity_context(filters or {})
	rows = aggregate(items, attributes, detail, sizes)
	return {"columns": quantities.matrix_columns(sizes, detail.is_set_item), "result": rows, "summary": {"item": lot.item}, "message": lot.item}


def dependency_doctypes(filters=None) -> list[str]:
	return quantities.dependency_doctypes(filters)

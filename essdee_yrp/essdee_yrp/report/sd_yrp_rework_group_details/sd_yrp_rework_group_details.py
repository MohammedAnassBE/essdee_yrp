import frappe

from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("rework_groups")
	filters = frappe._dict(filters or {})
	result = web_reports.get_rework_groups(
		**{key: filters.get(key) for key in ("lot", "item", "colour", "show_reworked")}
	)
	groups = list((result.get("groups") or {}).values())
	sizes = desk.ordered_sizes(groups, "sizes")
	columns = [*desk.lot_columns(), desk.column("colour", "Colour")]
	if any(group.get("is_set_item") for group in groups):
		columns.append(desk.column("part", "Part"))
	columns += [
		desk.column("grn_number", "GRN Number", "Link", "YRP Goods Received Note"),
		desk.column("received_type", "Received Type"),
		*desk.size_columns(sizes),
		desk.column("total", "Total", "Float"),
	]
	data = [
		{
			**row,
			"item": group.get("item"),
			"lot": group.get("lot"),
			**desk.size_values(sizes, row.get("received") or {}),
			"total": sum((row.get("received") or {}).get(size, 0) for size in group.get("sizes", [])),
		}
		for group in groups
		for row in group.get("rows", [])
	]
	return columns, data

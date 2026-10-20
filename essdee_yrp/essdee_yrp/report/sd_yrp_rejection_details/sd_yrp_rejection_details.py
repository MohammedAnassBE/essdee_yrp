import frappe

from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("rejection_details")
	filters = frappe._dict(filters or {})
	desk.date_range(filters, "start_date", "end_date")
	result = web_reports.get_rejection_details(
		**{key: filters.get(key) for key in ("start_date", "end_date", "lot", "item", "colour")}
	)
	types = result.get("types") or []
	columns = [
		desk.column("series", "Series No", "Link", "SD YRP GRN Rework Item"),
		desk.column("date", "Date", "Date"),
		desk.column("grn_number", "GRN Number", "Link", "YRP Goods Received Note"),
		*desk.lot_columns(),
		desk.column("colour", "Colour"),
		*[desk.column(f"type_{index}", label, "Float") for index, label in enumerate(types)],
		desk.column("total", "Total", "Float"),
		desk.column("rejection_group", "Rejection Group"),
		desk.column("size_value", "Size"),
		desk.column("rejected_qty", "Rejected Qty", "Float"),
	]
	data = []
	for series, detail in (result.get("report_detail") or {}).items():
		data.append(
			{
				**detail,
				"series": series,
				"colour": web_reports.first_colour(detail.get("rejection_detail")),
				**{
					f"type_{index}": (detail.get("types") or {}).get(label, 0)
					for index, label in enumerate(types)
				},
			}
		)
		for key, group in (detail.get("rejection_detail") or {}).items():
			for item in group.get("items") or []:
				data.append(
					{
						**{field: detail.get(field) for field in ("date", "grn_number", "lot", "item")},
						"series": series,
						"colour": web_reports.first_colour({key: group}),
						"rejection_group": key,
						"size_value": item.get(detail.get("size")),
						"rejected_qty": item.get("rejected_qty", 0),
					}
				)
	return columns, data

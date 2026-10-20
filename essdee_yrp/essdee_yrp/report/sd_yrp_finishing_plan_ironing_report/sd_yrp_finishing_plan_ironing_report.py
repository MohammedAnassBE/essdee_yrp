from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("ironing_dpr")
	reports = web_reports.get_ironing_dpr(**desk.dpr_filters(filters)) or []
	sizes = desk.ordered_sizes(reports, "primary_attributes")
	columns = [desk.column("date", "Date", "Date"), *desk.lot_columns(), desk.column("s_no", "No", "Int")]
	if any(
		"part" == str(attr).lower() and any(row.get("part") for row in report.get("rows", []))
		for report in reports
		for attr in report.get("attributes", [])
	):
		columns.append(desk.column("part", "Part"))
	columns += [
		desk.column("colour", "Colour"),
		*desk.size_columns(sizes),
		desk.column("total_qty", "Total Qty", "Float"),
	]
	data = [
		{
			**row,
			"date": report.get("date"),
			"lot": report.get("lot"),
			"item": report.get("item"),
			**desk.size_values(sizes, row),
		}
		for report in reports
		for row in report.get("rows", [])
	]
	return columns, data

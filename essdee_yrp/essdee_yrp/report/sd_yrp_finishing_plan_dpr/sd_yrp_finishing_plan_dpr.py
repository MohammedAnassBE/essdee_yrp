from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("packing_dpr")
	result = web_reports.get_packing_dpr(**desk.dpr_filters(filters))
	rows = result.get("data") or []
	sizes = desk.ordered_sizes(rows, "sizes")
	columns = [
		desk.column("date", "Date", "Date"),
		*desk.lot_columns(),
		*desk.size_columns(sizes),
		desk.column("total_pieces", "Total Pieces", "Float"),
		desk.column("pieces_per_box", "Pcs/Box"),
		desk.column("total_boxes", "Total Boxes", "Float"),
	]
	return columns, [{**row, **desk.size_values(sizes, row.get("size_qty") or {})} for row in rows]

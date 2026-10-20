import frappe
from frappe.utils import flt

from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("dispatch_report")
	filters = frappe._dict(filters or {})
	desk.date_range(filters)
	result = web_reports.get_dispatch_report(
		**{key: filters.get(key) for key in ("from_date", "to_date", "lots", "items")}
	)
	lots = result.get("data") or []
	sizes = desk.ordered_sizes(lots, "sizes")
	columns = [
		*desk.lot_columns(),
		desk.column("type", "Type"),
		*desk.size_columns(sizes),
		desk.column("total_boxes", "Total Boxes", "Float"),
		desk.column("pieces_per_box", "Pcs/Box"),
		desk.column("total_pieces", "Total Pieces", "Float"),
	]
	data = []
	for lot in lots:
		for label, prefix in (("Packed", "packed"), ("Dispatched", "dispatched"), ("Diff", None)):
			if prefix:
				quantities = lot.get(f"{prefix}_qty") or {}
			else:
				quantities = {
					size: flt((lot.get("packed_qty") or {}).get(size))
					- flt((lot.get("dispatched_qty") or {}).get(size))
					for size in sizes
				}
			row = {**lot, "type": label, **desk.size_values(sizes, quantities)}
			for field in ("total_boxes", "total_pieces"):
				row[field] = (
					lot.get(f"{prefix}_{field}", 0)
					if prefix
					else flt(lot.get(f"packed_{field}")) - flt(lot.get(f"dispatched_{field}"))
				)
			data.append(row)
	return columns, data

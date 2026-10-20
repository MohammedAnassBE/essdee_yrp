import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.finishing import desk_reports as desk
from essdee_yrp.finishing import web_reports


def execute(filters=None):
	desk.check_access("rework_completion")
	filters = frappe._dict(filters or {})
	if not filters.lot or not filters.process:
		frappe.throw(_("Select a Lot and a Process."))
	result = web_reports.get_rework_completion(filters.lot, filters.process)
	sizes = result.get("primary_values") or []
	columns = [desk.column("colour", "Colour")]
	if result.get("is_set_item"):
		columns.append(desk.column("part", result.get("set_attr") or "Part"))
	columns += [
		desk.column("type", "Types"),
		*desk.size_columns(sizes),
		desk.column("total", "Total", "Float"),
	]
	data = []
	grand_total = 0
	for colour, detail in (result.get("data") or {}).items():
		for label in result.get("types") or []:
			values = {size: (detail.get("values", {}).get(size) or {}).get(label, 0) for size in sizes}
			data.append(
				{
					"colour": colour,
					"part": detail.get("part"),
					"type": label,
					**desk.size_values(sizes, values),
					"total": (detail.get("type_wise_total") or {}).get(label, 0),
				}
			)
		total = (detail.get("colour_total") or {}).get("total", 0)
		data.append(
			{
				"colour": colour,
				"part": detail.get("part"),
				"type": _("Total"),
				**desk.size_values(sizes, detail.get("size_wise_total") or {}),
				"total": total,
			}
		)
		grand_total += flt(total)
	summary = [{"label": _("Reworked Pieces"), "value": grand_total, "datatype": "Float", "indicator": "Green"}]
	return columns, data, None, None, summary

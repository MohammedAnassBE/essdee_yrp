from collections import defaultdict

import frappe
from frappe import _

from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.merch.lot_process_data import LotFlowData
from essdee_yrp.merch.lot_process_flow import cutting_cloth, item_identity
from essdee_yrp.planning.dashboard.lot_metrics import LotMetrics
from essdee_yrp.planning.dashboard.processes import LotProcesses
from essdee_yrp.planning.dashboard.production_orders import LOT_FIELDS


def get_process_row(lot, process):
	rows = frappe.get_list("SD YRP Lot", filters={"name": lot}, fields=LOT_FIELDS, limit_page_length=1)
	if not rows:
		frappe.throw(_("You do not have access to Lot {0}.").format(lot), frappe.PermissionError)
	row = next(
		(
			row
			for row in LotProcesses(LotMetrics(rows, sewing_processes=[])).get_processes(lot)
			if row["name"] == process
		),
		None,
	)
	if not row:
		frappe.throw(
			_("Process {0} has no submitted Work Order in Lot {1}.").format(process, lot),
			frappe.DoesNotExistError,
		)
	return row


def get_process_detail(lot, process):
	"""Size and colour detail of one process of a lot for the Size-wise and Colour-wise popups."""
	row = get_process_row(lot, process)
	data = LotFlowData(lot)
	names = {order["name"] for order in row["work_orders"]}
	is_cloth = row["kind"] == "cloth"
	items = [item for item in data.calculated_items if item["parent"] in names]
	return {
		"lot": lot,
		"item": data.doc.item,
		"process": process,
		"kind": row["kind"],
		"status": row["status"],
		"sizes": data.sizes,
		"grid": rules.size_grid(items, item_identity(data, items)) if data.ipd and not is_cloth else [],
		"packing": get_packing(data, names) if row["kind"] == "packing" and data.ipd else None,
		"cloth": cutting_cloth(data, names) if row["kind"] == "cutting" else [],
		"fabrics": get_fabrics(data, names) if is_cloth else [],
		"work_orders": row["work_orders"],
	}


def get_packing(data, names):
	packing = data.packing(names)
	return {key: packing[key] for key in ("planned", "delivered", "received", "dispatch", "finishing_plans")}


def get_fabrics(data, names):
	"""Colour · dia Kg per fabric made by these cloth Work Orders, with the input they were made from."""
	deliverables = [row for name in sorted(names) for row in data.moves["deliverables"][name]]
	receivables = [row for name in sorted(names) for row in data.moves["receivables"][name]]
	variants = {row["item_variant"] for row in [*deliverables, *receivables]}
	parents = (
		dict(
			frappe.get_all(
				"Item",
				filters={"name": ["in", list(variants)]},
				fields=["name", "variant_of"],
				as_list=True,
				limit_page_length=0,
			)
		)
		if variants
		else {}
	)
	attributes = data.attributes(variants)
	colour, dia = data.cloth_attributes()
	by_fabric = defaultdict(list)
	for row in receivables:
		by_fabric[parents.get(row["item_variant"]) or row["item_variant"]].append(row)
	source = deliverables[-1] if deliverables else None
	source_name = (
		" · ".join(
			filter(
				None,
				[
					parents.get(source["item_variant"]) or source["item_variant"],
					attributes.get(source["item_variant"], {}).get(colour),
				],
			)
		)
		if source
		else ""
	)
	delivered = sum(rules.moved(row) for row in deliverables)
	return [
		{
			"fabric": fabric,
			"input": source_name,
			"delivered": delivered,
			"rows": [
				{key: line[key] for key in ("colour", "dia", "planned", "received")}
				for line in rules.cloth_rows([], rows, attributes, colour, dia)["rows"]
			],
		}
		for fabric, rows in by_fabric.items()
	]

from collections import defaultdict

from frappe.utils import cint, flt

ORDER_STATUS = {
	"Draft": "idle",
	"Submitted": "idle",
	"Partially Delivered": "partial",
	"Fully Delivered": "partial",
	"Partially Received": "partial",
	"Fully Received": "done",
	"Partially Billed": "done",
	"Fully Billed": "done",
	"Close Request": "done",
	"Closed": "done",
}


def order_status(order):
	"""Step tone of one Work Order; None when cancelled."""
	if cint(order.get("docstatus")) == 2 or order.get("status") == "Cancelled":
		return None
	if cint(order.get("docstatus")) == 0:
		return "idle"
	return ORDER_STATUS.get(order.get("status"), "idle")


def combine_status(statuses):
	statuses = [status for status in statuses if status]
	if not statuses or all(status == "idle" for status in statuses):
		return "idle"
	return "done" if all(status == "done" for status in statuses) else "partial"


def step_status(orders):
	return combine_status(order_status(order) for order in orders)


def item_steps(ipd, ipd_processes):
	"""IPD item steps: Cutting, cut-stage processes, Stitching, piece-stage processes, Packing."""
	cut = [
		row["process_name"] for row in ipd_processes if row.get("in_stage") == ipd.get("stiching_in_stage")
	]
	piece = [
		row["process_name"] for row in ipd_processes if row.get("in_stage") != ipd.get("stiching_in_stage")
	]
	ordered = [
		(ipd.get("cutting_process"), "Cutting"),
		*((process, "Cut stage") for process in cut),
		(ipd.get("stiching_process"), "Stitching"),
		*((process, "Piece stage") for process in piece),
		(ipd.get("packing_process"), "Packing"),
	]
	steps, seen = [], set()
	for process, stage in ordered:
		if process and process not in seen:
			seen.add(process)
			steps.append({"process": process, "stage": stage})
	return steps


def item_node(process, stage, orders, covers=(), also_covered_by=()):
	return {
		"key": process,
		"process": process,
		"stage": stage,
		"covers": list(covers),
		"also_covered_by": list(also_covered_by),
		"orders": orders,
	}


def build_item_nodes(steps, orders, groups):
	"""One node per IPD step; a group Work Order becomes one node at its last covered step."""
	by_process = defaultdict(list)
	for order in orders:
		by_process[order["process_name"]].append(order)
	names = [step["process"] for step in steps]
	slots, covered, extras = defaultdict(list), defaultdict(list), []
	for process, own in by_process.items():
		if process in names:
			continue
		members = [member for member in groups.get(process, []) if member in names]
		if not members:
			extras.append(item_node(process, "Other process", own))
			continue
		slots[max(names.index(member) for member in members)].append(
			item_node(process, "Group process", own, groups[process])
		)
		for member in members:
			covered[member].append(process)
	nodes = []
	for index, step in enumerate(steps):
		own = by_process.get(step["process"], [])
		if own or step["process"] not in covered:
			nodes.append(
				item_node(
					step["process"],
					step["stage"],
					own,
					also_covered_by=covered[step["process"]] if own else (),
				)
			)
		nodes.extend(sorted(slots[index], key=lambda node: str(node["orders"][0].get("creation"))))
	at = len(nodes) - 1 if nodes and nodes[-1]["stage"] == "Packing" else len(nodes)
	return nodes[:at] + extras + nodes[at:]


def size_grid(items, identity):
	"""Planned / delivered / received per colour × part × size, summed over every Work Order."""
	groups = {}
	for item in items:
		colour, part, size = identity(item)
		group = groups.setdefault(
			(colour, part),
			{
				"colour": colour,
				"part": part,
				"planned": defaultdict(float),
				"delivered": defaultdict(float),
				"received": defaultdict(float),
			},
		)
		group["planned"][size] += flt(item.get("quantity"))
		group["delivered"][size] += flt(item.get("delivered_quantity"))
		group["received"][size] += flt(item.get("received_qty"))
	return [
		{**group, **{key: dict(group[key]) for key in ("planned", "delivered", "received")}}
		for _key, group in sorted(groups.items())
	]


def packing_pieces(grn_items, size_of, packing_combo):
	"""Packed pieces per size; GRNs from packing calculation version 2 already hold pieces."""
	result = defaultdict(float)
	for row in grn_items:
		multiplier = 1 if cint(row.get("packing_calculation_version")) >= 2 else flt(packing_combo)
		result[size_of(row["item_variant"])] += flt(row.get("quantity")) * multiplier
	return dict(result)


def dispatch_pieces(rows, size_of, multipliers):
	result = defaultdict(float)
	for row in rows:
		result[size_of(row["item_variant"])] += flt(row.get("dispatched")) * flt(
			multipliers.get(row["parent"])
		)
	return dict(result)


def moved(row):
	return flt(row.get("qty")) - flt(row.get("pending_quantity"))


def cloth_rows(deliverables, receivables, attributes, colour_attribute, dia_attribute):
	"""Colour × dia planned / delivered / received; deliverables without a dia (yarn) stay a separate table."""

	def key(row):
		return (
			attributes.get(row["item_variant"], {}).get(colour_attribute, ""),
			attributes.get(row["item_variant"], {}).get(dia_attribute, ""),
		)

	merge = bool(deliverables) and all(key(row)[1] for row in deliverables)
	rows = {}
	for row in receivables:
		entry = rows.setdefault(
			key(row),
			{
				"colour": key(row)[0],
				"dia": key(row)[1],
				"planned": 0,
				"delivered": 0 if merge else None,
				"received": 0,
			},
		)
		entry["planned"] += flt(row.get("qty"))
		entry["received"] += moved(row)
	if merge:
		for row in deliverables:
			rows.setdefault(
				key(row),
				{"colour": key(row)[0], "dia": key(row)[1], "planned": 0, "delivered": 0, "received": 0},
			)["delivered"] += moved(row)
	separate = (
		[]
		if merge
		else [
			{
				"item_variant": row["item_variant"],
				"colour": key(row)[0],
				"planned": flt(row.get("qty")),
				"delivered": moved(row),
				"uom": row.get("uom"),
			}
			for row in deliverables
		]
	)
	return {"rows": [rows[name] for name in sorted(rows)], "deliverables": separate}

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.merch.lot_process_data import (
	LotFlowData,
	movement_dates,
	movement_documents,
	require_work_order,
)
from essdee_yrp.planning.reports import production_quantities as quantities

PACKING_LABELS = ("Pieces sent on DCs", "Packed pieces on GRNs", "Dispatched pieces")


@frappe.whitelist()
def get_process_flow(lot: str) -> dict:
	"""Cloth lanes and item steps of a Lot, without size detail."""
	data = LotFlowData(lot)
	return {
		"lot": data.doc.name,
		"item": data.doc.item,
		"order_quantity": flt(data.doc.total_order_quantity),
		"lot_date": str(getdate(data.doc.creation)),
		"cloth": cloth_lanes(data),
		"items": [item_node(node, data) for node in data.item_nodes],
	}


@frappe.whitelist()
def get_step_detail(lot: str, key: str) -> dict:
	"""Size-wise grid, Work Order breakdown and documents of one item step."""
	data = LotFlowData(lot)
	node = next((row for row in data.item_nodes if row["key"] == key), None)
	if not node:
		frappe.throw(_("Process {0} is not part of Lot {1}.").format(key, lot), frappe.DoesNotExistError)
	payload = item_node(node, data)
	names = {order["name"] for order in node["orders"] if order["name"] in data.submitted}
	items = [row for row in data.calculated_items if row["parent"] in names]
	identity = item_identity(data, [*items, *data.order_rows])
	packing = packing_detail(data, names) if payload["kind"] == "packing" else None
	work_orders = [order_breakdown(row, items, identity) for row in payload["work_orders"]]
	for row in work_orders:
		if packing and row["includes_packing"] and row["name"] in names:
			row["received"] = sum(packing["received"].values())
	return {
		"node": payload,
		"sizes": data.sizes,
		"grid": [] if packing else rules.size_grid(items or data.order_rows, identity),
		"packing": packing,
		"cloth": cutting_cloth(data, names) if payload["kind"] == "cutting" else [],
		"work_orders": work_orders,
		"documents": supplier_documents(*data.documents, {order["name"] for order in node["orders"]}),
	}


@frappe.whitelist()
def get_work_order_detail(work_order: str) -> dict:
	"""One Work Order: item size grid or cloth colour × dia table, plus its documents."""
	order = require_work_order(work_order)
	data = LotFlowData(order["lot"])
	dcs, grns = movement_documents([order["name"]])
	row = serialize_order(order, data, movement_dates(dcs, grns))
	result = {
		"work_order": row,
		"lot": data.doc.name,
		"sizes": data.sizes,
		"documents": supplier_documents(dcs, grns, {order["name"]}),
	}
	if order["item"] != data.doc.item:
		return {**result, "kind": "cloth", "cloth": cloth_detail(order["name"], data)}
	items = quantities.child_rows(
		"YRP Work Order Calculated Item",
		[order["name"]] if cint(order["docstatus"]) == 1 else [],
		["item_variant", "set_combination", "quantity", "delivered_quantity", "received_qty"],
		"YRP Work Order",
	)
	is_cutting = data.ipd and order["process_name"] == data.ipd.cutting_process
	return {
		**result,
		"kind": "item",
		"grid": rules.size_grid(items, item_identity(data, items)),
		"cloth": cutting_cloth(data, {order["name"]}) if is_cutting else [],
	}


def item_identity(data, rows):
	attributes = data.attributes(row["item_variant"] for row in rows)
	return lambda item: quantities.matrix_identity(item, attributes, data.ipd)


def serialize_order(order, data, dates):
	first_dc, last_grn = dates.get(order["name"], (None, None))
	return {
		**{
			field: order.get(field)
			for field in ("name", "status", "docstatus", "supplier", "process_name", "item", "wo_date")
		},
		"supplier_name": order.get("supplier_name") or order.get("supplier"),
		"includes_packing": cint(order.get("includes_packing")),
		"tone": rules.order_status(order),
		"first_dc": first_dc,
		"last_grn": last_grn,
		"target": order_target(order, data),
	}


def order_target(order, data):
	if plan := data.plans["cutting"].get(order["name"]):
		return {"doctype": "SD YRP Cutting Plan", "name": plan, "label": "Cutting Plan"}
	plan = next(
		(row["name"] for row in data.plans["finishing"] if row.get("work_order") == order["name"]), None
	)
	if cint(order.get("includes_packing")) and plan:
		return {"doctype": "SD YRP Finishing Plan", "name": plan, "label": "Finishing Plan"}
	return {"doctype": "YRP Work Order", "name": order["name"], "label": "Work Order"}


def node_kind(node, ipd):
	if node["process"] == ipd.cutting_process:
		return "cutting"
	if node["process"] == ipd.packing_process or any(
		cint(order.get("includes_packing")) for order in node["orders"]
	):
		return "packing"
	return "inhouse"


def item_node(node, data):
	kind = node_kind(node, data.ipd)
	names = {order["name"] for order in node["orders"] if order["name"] in data.submitted}
	return {
		**{key: node[key] for key in ("key", "process", "stage", "covers", "also_covered_by")},
		"kind": kind,
		"status": rules.step_status(node["orders"]),
		"meters": packing_meters(data, names) if kind == "packing" else piece_meters(data, names, kind),
		"work_orders": [serialize_order(order, data, data.dates) for order in node["orders"]],
	}


def meter(kind, value, total, uom, label):
	return {"kind": kind, "value": flt(value, 3), "total": flt(total, 3), "uom": uom, "label": label}


def piece_meters(data, names, kind):
	items = [row for row in data.calculated_items if row["parent"] in names]
	planned = (
		sum(flt(row["quantity"]) for row in items)
		if names
		else sum(row["quantity"] for row in data.order_rows)
	)
	received = meter(
		"Received",
		sum(flt(row["received_qty"]) for row in items),
		planned,
		"Pcs",
		"Cut pieces" if kind == "cutting" else "Received on GRNs",
	)
	if kind != "cutting":
		return [
			meter(
				"Delivered",
				sum(flt(row["delivered_quantity"]) for row in items),
				planned,
				"Pcs",
				"Sent on DCs",
			),
			received,
		]
	cloth = [row for name in names for row in data.moves["deliverables"][name]]
	delivered = meter(
		"Delivered",
		sum(rules.moved(row) for row in cloth),
		sum(flt(row["qty"]) for row in cloth),
		cloth[0]["uom"] if cloth else "Kg",
		"Cloth",
	)
	return [delivered, received]


def packing_meters(data, names):
	packing = data.packing(names)
	total = flt(data.doc.total_order_quantity) or sum(packing["planned"].values())
	return [
		meter(kind, sum(packing[key].values()), total, "Pcs", label)
		for kind, key, label in zip(
			("Delivered", "Received", "Dispatch"),
			("delivered", "received", "dispatch"),
			PACKING_LABELS,
			strict=True,
		)
	]


def packing_detail(data, names):
	return {
		**data.packing(names),
		"dispatches": data.dispatches(),
		"pieces_per_box": cint(data.doc.packing_combo or data.ipd.packing_combo),
	}


def cutting_cloth(data, names):
	rows = [row for name in sorted(names) for row in data.moves["deliverables"][name]]
	variants = {row["item_variant"] for row in rows}
	parents = (
		dict(
			frappe.get_all(
				"Item", filters={"name": ["in", list(variants)]}, fields=["name", "variant_of"], as_list=True
			)
		)
		if variants
		else {}
	)
	attributes = data.attributes(variants)
	colour, _dia = data.cloth_attributes()

	def label(values):
		return " · ".join(sorted(values.values(), key=lambda value: value != values.get(colour)))

	return [
		{
			"work_order": row["parent"],
			"item": parents.get(row["item_variant"]) or row["item_variant"],
			"attributes": label(attributes.get(row["item_variant"], {})),
			"planned": flt(row["qty"]),
			"delivered": rules.moved(row),
			"uom": row["uom"],
		}
		for row in rows
	]


def order_breakdown(row, items, identity):
	own = [item for item in items if item["parent"] == row["name"]]
	grid = rules.size_grid(own, identity)

	def total(key):
		return sum(flt(item[key]) for item in own)

	return {
		**row,
		"colours": sorted({group["colour"] for group in grid if group["colour"]}),
		"planned": total("quantity"),
		"delivered": total("delivered_quantity"),
		"received": total("received_qty"),
	}


def supplier_documents(dcs, grns, names):
	groups = {}

	def group(row):
		return groups.setdefault(
			row.get("supplier") or "",
			{
				"supplier": row.get("supplier"),
				"supplier_name": row.get("supplier_name") or row.get("supplier"),
				"dcs": [],
				"grns": [],
			},
		)

	for row in dcs:
		if row["work_order"] in names:
			group(row)["dcs"].append(
				{
					"name": row["name"],
					"date": row["posting_date"],
					"qty": flt(row["total_delivered_qty"]),
					"work_order": row["work_order"],
				}
			)
	for row in grns:
		if row["against_id"] in names:
			group(row)["grns"].append(
				{
					"name": row["name"],
					"date": row["posting_date"],
					"qty": flt(row["total_received_quantity"]),
					"is_return": cint(row["is_return"]),
					"work_order": row["against_id"],
				}
			)
	return list(groups.values())


def cloth_lanes(data):
	fabrics = [row for row in data.doc.get("lot_fabric_details") or [] if row.cloth_item]
	processes = quantities.child_rows(
		"SD YRP IPD Fabric Process",
		{row.production_detail for row in fabrics if row.production_detail},
		["sequence", "fabric_process"],
		"YRP Item Production Detail",
	)
	lanes = []
	for fabric in fabrics:
		chain = [
			row["fabric_process"]
			for row in sorted(processes, key=lambda row: cint(row["sequence"]))
			if row["parent"] == fabric.production_detail
		]
		orders = [order for order in data.orders if order["item"] == fabric.cloth_item]
		chain += [
			name for name in dict.fromkeys(order["process_name"] for order in orders) if name not in chain
		]
		steps = [
			cloth_step(process, [order for order in orders if order["process_name"] == process], data)
			for process in chain
		]
		lanes.append(
			{
				"cloth_item": fabric.cloth_item,
				"fabric_ipd": fabric.production_detail,
				"status": rules.combine_status(step["status"] for step in steps),
				"steps": steps,
			}
		)
	return lanes


def cloth_step(process, orders, data):
	names = [order["name"] for order in orders if order["name"] in data.submitted]

	def moved(key):
		return sum(rules.moved(row) for name in names for row in data.moves[key][name])

	return {
		"process": process,
		"status": rules.step_status(orders),
		"delivered": moved("deliverables"),
		"received": moved("receivables"),
		"work_orders": [serialize_order(order, data, data.dates) for order in orders],
	}


def cloth_detail(name, data):
	moves = {
		key: quantities.child_rows(
			doctype, [name], ["item_variant", "qty", "pending_quantity", "uom"], "YRP Work Order"
		)
		for key, doctype in (
			("deliverables", "YRP Work Order Deliverables"),
			("receivables", "YRP Work Order Receivables"),
		)
	}
	attributes = data.attributes(row["item_variant"] for rows in moves.values() for row in rows)
	return rules.cloth_rows(moves["deliverables"], moves["receivables"], attributes, *data.cloth_attributes())

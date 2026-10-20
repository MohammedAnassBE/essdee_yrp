from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate

CUT = (("order_qty", "Order Qty"), ("cut_qty", "Cut Qty"), ("order_to_cut_diff", "Order to Cut Diff"))
SEWING = (
	("sewing_sent", "Sewing Sent"), ("sewing_received", "Sewing Received"),
	("cut_to_sew_diff", "Cut to Sew Diff"), ("ready_for_packing", "Ready for Packing"),
	("finishing_inward", "Finishing Inward"), ("in_sew", "In Sew"),
)
FINISHING = (
	("dispatch", "Dispatch"), ("in_packing", "In Packing"), ("transferred", "Transferred"),
	("cut_to_dispatch_diff", "Cut to Dispatch Diff"),
)
DATES = (
	("last_cut_date", "Last Cut Date"), ("sew_sent_date", "Sewing Sent Date"),
	("finishing_inward_date", "Finishing Inward Date"),
)
SUMMARY = (
	("order_to_cut_diff", "Order to Cut"), ("cut_to_sew_diff", "Cut to Sew"),
	("in_sew", "In Sew"), ("ready_for_packing", "Ready for Packing"),
	("in_packing", "In Packing"), ("cut_to_dispatch_diff", "Cut to Dispatch"),
)


def can_view_work_in_progress():
	return all(frappe.has_permission(doctype, ptype="read", doc=None) for doctype in ("SD YRP Lot", "YRP Work Order"))


def require_work_in_progress_access():
	if not can_view_work_in_progress():
		frappe.throw("You do not have access to Work In Progress.", frappe.PermissionError)


def filter_names(value, *, processes=False):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if value is None:
		return []
	if not isinstance(value, list):
		frappe.throw("Report filter values must be a list of names.")
	if processes:
		value = [row.get("process_name") if isinstance(row, dict) else row for row in value]
	if any(not isinstance(name, str) or not name.strip() for name in value):
		frappe.throw("Report filter values must be a list of names.")
	return list(dict.fromkeys(name.strip() for name in value))


def authorize_names(doctype, names):
	if names:
		readable = frappe.get_list(doctype, filters={"name": ["in", names]}, pluck="name", limit_page_length=0)
		if set(names) - set(readable):
			existing = frappe.db.get_all(doctype, filters={"name": ["in", names]}, pluck="name")
			unknown = [name for name in names if name not in existing]
			if unknown:
				label = doctype.removeprefix("SD YRP ").removeprefix("YRP ")
				frappe.throw(f"Unknown {label}: {', '.join(unknown)}", frappe.ValidationError)
			frappe.throw("You do not have access to one or more report filter values.", frappe.PermissionError)
	return names


def validate_filters(filters):
	filters = dict(filters or {})
	for key in ("lot", "item", "process_list"):
		filters[key] = filter_names(filters.get(key), processes=key == "process_list")
	if not any(filters.get(key) for key in ("category", "product_season", "lot", "item")):
		frappe.throw("Set at least one filter other than Lot Status.")
	filters.setdefault("lot_status", "Open")
	if filters["lot_status"] not in ("Open", "Closed"):
		frappe.throw("Lot Status must be Open or Closed.")
	validate_dates(filters)
	return filters


def validate_dates(filters):
	start, end = filters.get("from_date"), filters.get("to_date")
	if bool(start) != bool(end):
		frappe.throw("To Date is required" if start else "From Date is required")
	if start and getdate(start) > getdate(end):
		frappe.throw("Lot To Date must be on or after Lot From Date.")


def resolve_lots(filters):
	conditions = [["status", "=", filters["lot_status"]], ["production_detail", "is", "set"]]
	for key, doctype, field in (("lot", "SD YRP Lot", "name"), ("item", "Item", "item")):
		if names := authorize_names(doctype, filters[key]):
			conditions.append([field, "in", names])
	for key, doctype in (("category", "SD YRP Product Category"), ("product_season", "SD YRP Product Season")):
		if filters.get(key):
			authorize_names(doctype, [filters[key]])
	if filters.get("category"):
		items = frappe.get_list("Item", filters={"product_category": filters["category"]}, pluck="name", limit_page_length=0)
		conditions.append(["item", "in", items])
	if filters.get("product_season"):
		conditions.append(["season", "=", filters["product_season"]])
	if filters.get("from_date"):
		conditions.extend([["creation", ">=", str(getdate(filters["from_date"]))],
			["creation", "<=", str(getdate(filters["to_date"]))]])
	return frappe.get_list("SD YRP Lot", filters=conditions,
		fields=["name", "item", "production_order", "production_detail"], order_by="name", limit_page_length=0)


def source_rows(query, parameters):
	return frappe.db.sql(query, parameters, as_dict=True)


def load_sources(lots):
	parameters = {"lots": tuple(lot["name"] for lot in lots),
		"details": tuple({lot["production_detail"] for lot in lots})}
	require_work_order_access(parameters)
	return {
		"details": load_details(parameters),
		"orders": load_orders(parameters),
		"receipts": load_receipts(parameters),
		"stages": source_rows("""SELECT parent, process_name, in_stage FROM `tabYRP IPD Process`
			WHERE parent IN %(details)s ORDER BY idx""", parameters),
		"expansions": source_rows("SELECT parent, process_name FROM `tabYRP Process Details`", parameters),
		"quantities": source_rows("""SELECT parent, COALESCE(SUM(quantity), 0) AS quantity
			FROM `tabSD YRP Lot Order Detail` WHERE parent IN %(lots)s GROUP BY parent""", parameters),
		"reworks": source_rows("""SELECT r.lot, COALESCE(SUM(d.reworked), 0) AS quantity
			FROM `tabSD YRP GRN Rework Item` r JOIN `tabSD YRP GRN Rework Item Detail` d ON d.parent = r.name
			WHERE r.lot IN %(lots)s GROUP BY r.lot""", parameters),
		"plans": load_plans(parameters),
	}


def require_work_order_access(parameters):
	readable = frappe.get_list("YRP Work Order",
		filters={"lot": ["in", parameters["lots"]], "docstatus": 1},
		fields=[{"COUNT": "*", "as": "count"}], order_by=None, limit_page_length=0)
	total = source_rows("""SELECT COUNT(*) AS count FROM `tabYRP Work Order`
		WHERE lot IN %(lots)s AND docstatus = 1""", parameters)
	if readable[0]["count"] < total[0]["count"]:
		frappe.throw(_("You cannot read all Work Orders of the selected Lots."), frappe.PermissionError)


def load_details(parameters):
	return source_rows("""SELECT p.name, p.cutting_process, p.stiching_process, p.stiching_in_stage,
		p.packing_combo, p.is_set_item,
		CASE WHEN p.is_set_item = 1 AND a.mapping IS NOT NULL AND a.mapping != ''
		THEN (SELECT COUNT(*) FROM `tabYRP Item Item Attribute Mapping Value` v WHERE v.parent = a.mapping)
		ELSE 1 END AS part_qty
		FROM `tabYRP Item Production Detail` p LEFT JOIN `tabYRP IPD Item Attribute` a
		ON a.parent = p.name AND a.attribute = p.set_item_attribute
		WHERE p.name IN %(details)s""", parameters)


def load_orders(parameters):
	return source_rows("""SELECT w.name, w.lot, w.process_name, w.includes_packing, w.is_rework,
		w.first_dc_date, w.last_grn_date, COALESCE(SUM(c.delivered_quantity), 0) AS sent,
		COALESCE(SUM(c.received_qty), 0) AS received FROM `tabYRP Work Order` w
		LEFT JOIN `tabYRP Work Order Calculated Item` c ON c.parent = w.name
		WHERE w.lot IN %(lots)s AND w.docstatus = 1
		GROUP BY w.name, w.lot, w.process_name, w.includes_packing, w.is_rework,
		w.first_dc_date, w.last_grn_date""", parameters)


def load_receipts(parameters):
	parameters = {**parameters, "accepted": frappe.db.get_single_value("YRP Stock Settings", "default_received_type")}
	return source_rows("""SELECT g.against_id,
		COALESCE(MAX(g.packing_calculation_version), 0) AS version,
		COALESCE(SUM(CASE WHEN i.received_type = %(accepted)s THEN i.quantity ELSE 0 END), 0) AS accepted,
		COALESCE(SUM(CASE WHEN COALESCE(g.packing_calculation_version, 0) >= 2 THEN i.quantity ELSE 0 END), 0) AS dynamic_pieces,
		COALESCE(SUM(CASE WHEN COALESCE(g.packing_calculation_version, 0) < 2 THEN i.quantity ELSE 0 END), 0) AS legacy_boxes,
		COALESCE(SUM(i.stock_qty), 0) AS stock_qty
		FROM `tabYRP Goods Received Note` g LEFT JOIN `tabYRP Goods Received Note Item` i ON i.parent = g.name
		JOIN `tabYRP Work Order` w ON w.name = g.against_id
		WHERE w.lot IN %(lots)s AND g.against = 'YRP Work Order' AND g.docstatus = 1 AND g.is_return = 0
		GROUP BY g.against_id""", parameters)


def load_plans(parameters):
	plans = source_rows("""SELECT name, lot, work_order, pieces_per_box FROM `tabSD YRP Finishing Plan`
		WHERE lot IN %(lots)s ORDER BY name""", parameters)
	if not plans:
		return []
	parameters = {"plans": tuple(plan["name"] for plan in plans)}
	details = source_rows("""SELECT parent, COALESCE(SUM(dc_qty), 0) AS inward,
		COALESCE(SUM(transferred_qty), 0) AS transferred FROM `tabSD YRP Finishing Plan Detail`
		WHERE parent IN %(plans)s GROUP BY parent""", parameters)
	dispatches = source_rows("""SELECT parent, COALESCE(SUM(dispatched), 0) AS dispatched
		FROM `tabSD YRP Finishing Plan GRN Detail` WHERE parent IN %(plans)s GROUP BY parent""", parameters)
	details = {row["parent"]: row for row in details}
	dispatches = {row["parent"]: row for row in dispatches}
	return [{**plan, **details.get(plan["name"], {}), **dispatches.get(plan["name"], {})} for plan in plans]


def grouped(rows, key):
	result = defaultdict(list)
	for row in rows:
		result[row[key]].append(row)
	return result


def lot_context(sources):
	return {
		"details": {row["name"]: row for row in sources["details"]},
		"orders": grouped(sources["orders"], "lot"), "plans": grouped(sources["plans"], "lot"),
		"receipts": {row["against_id"]: row for row in sources["receipts"]},
		"stages": {(row["parent"], row["process_name"]): row["in_stage"] for row in sources["stages"]},
		"quantities": {row["parent"]: row["quantity"] for row in sources["quantities"]},
		"reworks": {row["lot"]: row["quantity"] for row in sources["reworks"]},
		"expanded": grouped(sources["expansions"], "process_name"),
	}


def process_orders(orders, process, context):
	names = {process, *(row["parent"] for row in context["expanded"].get(process, []))}
	return [order for order in orders if not order["is_rework"] and order["process_name"] in names]


def date_value(orders, field, reducer):
	values = [str(order[field]) for order in orders if order.get(field)]
	return reducer(values) if values else None


def sewing_values(row, sewing, detail, context):
	row["sewing_sent"] = sum(flt(order["sent"]) for order in sewing)
	for order in sewing:
		received = flt(order["received"])
		if order["includes_packing"]:
			version = context["receipts"].get(order["name"], {}).get("version", 0)
			received *= detail["part_qty"] * (1 if version >= 2 else (detail["packing_combo"] or 1))
		row["sewing_received"] += received
	row["finishing_inward"] = row["sewing_received"]
	row["ready_for_packing"] = context["reworks"].get(row["lot"], 0) + sum(
		flt(context["receipts"].get(order["name"], {}).get("accepted")) for order in sewing)
	row["sew_sent_date"] = date_value(sewing, "first_dc_date", min)
	row["finishing_inward_date"] = date_value(sewing, "last_grn_date", max)


def finishing_values(row, orders, detail, context):
	plans = context["plans"].get(row["lot"], [])
	for plan in plans:
		version = context["receipts"].get(plan["work_order"], {}).get("version", 0)
		dispatch = flt(plan.get("dispatched")) * detail["part_qty"]
		dispatch *= 1 if version >= 1 else flt(plan["pieces_per_box"])
		row["dispatch"] += dispatch
		row["transferred"] += flt(plan.get("transferred"))
		row["ready_for_packing"] = max(0, row["ready_for_packing"] - dispatch)
	if plans:
		row["finishing_inward"] = sum(flt(plan.get("inward")) for plan in plans)
	else:
		packing_values(row, orders, detail, context)
	row["cut_to_sew_diff"] = row["sewing_sent"] - row["cut_qty"]
	row["in_sew"] = row["sewing_received"] - row["sewing_sent"]
	row["in_packing"] = row["dispatch"] - row["finishing_inward"]
	row["cut_to_dispatch_diff"] = row["dispatch"] + row["transferred"] - row["cut_qty"]


def packing_values(row, orders, detail, context):
	packing = [order for order in orders if order["includes_packing"]]
	if not packing:
		return
	row["finishing_inward"] = 0
	for order in packing:
		receipt = context["receipts"].get(order["name"], {})
		row["dispatch"] += (flt(receipt.get("dynamic_pieces"))
			+ flt(receipt.get("legacy_boxes")) * (detail["packing_combo"] or 1)) * detail["part_qty"]
		row["finishing_inward"] += flt(receipt.get("stock_qty"))


def process_values(row, orders, context, processes):
	previous = {"cut": ("Cut", row["cut_qty"]), "piece": ("Sew", row["finishing_inward"])}
	for index, process in enumerate(processes):
		group = row["process_stages"].get(process)
		if not group:
			continue
		prefix = f"{group}_{index}"
		matching = process_orders(orders, process, context)
		sent = sum(flt(order["sent"]) for order in matching)
		received = sum(flt(order["received"]) for order in matching)
		row.update({f"{prefix}_sent": sent, f"{prefix}_received": received, f"{prefix}_diff": received - sent})
		if matching:
			label, baseline = previous[group]
			row[chain_key(prefix, label)] = received - baseline
			row["process_chains"][prefix] = label
			previous[group] = (process, received)


def chain_key(prefix, previous):
	return f"{prefix}_to_{frappe.scrub(previous)}_diff"


def process_stages(detail, context, processes):
	return {process: "cut" if stage == detail["stiching_in_stage"] else "piece"
		for process in processes if (stage := context["stages"].get((detail["name"], process)))}


def build_row(lot, context, processes):
	row = {key: 0 for key, label in (*CUT, *SEWING, *FINISHING)}
	row.update({key: None for key, label in DATES})
	row.update(style=lot["item"], production_order=lot.get("production_order") or "", lot=lot["name"],
		process_chains={}, process_stages={}, not_in_ipd=[])
	detail = context["details"][lot["production_detail"]]
	orders = context["orders"].get(lot["name"], [])
	row["order_qty"] = context["quantities"].get(lot["name"], 0)
	row["cut_qty"] = sum(flt(order["received"]) for order in process_orders(orders, detail["cutting_process"], context))
	row["order_to_cut_diff"] = row["cut_qty"] - row["order_qty"]
	row["last_cut_date"] = date_value([order for order in orders
		if order["process_name"] == detail["cutting_process"]], "last_grn_date", max)
	sewing = process_orders(orders, detail["stiching_process"], context)
	if sewing:
		row["process_stages"] = process_stages(detail, context, processes)
		row["not_in_ipd"] = [process for process in processes if process not in row["process_stages"]]
		sewing_values(row, sewing, detail, context)
		finishing_values(row, orders, detail, context)
		process_values(row, orders, context, processes)
	return row


def column(key, label, group, fieldtype="Float", **options):
	return {"fieldname": key, "label": label, "group": group, "fieldtype": fieldtype, "width": 150,
		"is_difference": key.endswith("diff") or key in ("in_sew", "in_packing"), **options}


def process_columns(rows, processes, stage):
	"""Use selected process order within each stage; the reference uses first-seen lot order."""
	columns = []
	for index, process in enumerate(processes):
		stages = {row["process_stages"][process] for row in rows if process in row["process_stages"]}
		if stage not in stages:
			continue
		group = f"{process} ({stage} stage)" if len(stages) > 1 else process
		prefix = f"{stage}_{index}"
		options = {"process": process, "stage": stage}
		columns.extend(column(f"{prefix}_{suffix}", f"{process} {suffix.title()}", group, **options)
			for suffix in ("sent", "received", "diff"))
		previous = dict.fromkeys(row["process_chains"][prefix] for row in rows if prefix in row["process_chains"])
		columns.extend(column(chain_key(prefix, label), f"{process} to {label} Diff", group, **options)
			for label in previous)
	return columns


def dynamic_summary(columns, totals):
	"""Disambiguate repeated summary labels with their stage, as for process headers."""
	differences = [col for col in columns if col.get("process") and col["is_difference"]
		and not col["label"].endswith((" to Cut Diff", " to Sew Diff"))]
	labels = [col["label"] for col in differences]
	return {f"{col['label']} ({col['stage']} stage)" if labels.count(col["label"]) > 1 else col["label"]:
		totals[col["fieldname"]] for col in differences}


def build_result(rows, processes):
	columns = [column("style", "Style", "", "Data"), column("production_order", "Production Order", "", "Data"),
		column("lot", "Lot No", "", "Data")]
	columns += [column(key, label, "Cut") for key, label in CUT]
	columns += process_columns(rows, processes, "cut")
	columns += [column(key, label, "Sewing") for key, label in SEWING]
	columns += process_columns(rows, processes, "piece")
	columns += [column(key, label, "Finishing") for key, label in FINISHING]
	columns += [column(key, label, "Dates", "Date") for key, label in DATES]
	totals = {col["fieldname"]: sum(flt(row.get(col["fieldname"])) for row in rows)
		for col in columns if col["fieldtype"] == "Float"}
	summary = {"Lots": len(rows), **{label: totals[key] for key, label in SUMMARY}}
	summary.update(dynamic_summary(columns, totals))
	return {"columns": columns, "result": [*rows, {"style": "Total", "is_total_row": True, **totals}] if rows else [],
		"totals": totals, "summary": summary,
		"not_in_ipd_processes": [process for process in processes
			if not any(process in row["process_stages"] for row in rows)],
		"report_summary": [{"label": label, "value": value, "datatype": "Float"} for label, value in summary.items()]}


def run_work_in_progress(filters, progress=None):
	"""Read lot movements in batches, preserving the live Merch formulas."""
	require_work_in_progress_access()
	filters = validate_filters(filters)
	authorize_names("YRP Process", filters["process_list"])
	lots = resolve_lots(filters)
	if not lots:
		return build_result([], filters["process_list"])
	if progress:
		progress(0, 2)
	context = lot_context(load_sources(lots))
	if progress:
		progress(1, 2)
	result = build_result([build_row(lot, context, filters["process_list"]) for lot in lots], filters["process_list"])
	if progress:
		progress(2, 2)
	return result


def work_in_progress_dependency_doctypes(filters=None):
	return ["SD YRP Lot", "SD YRP Lot Order Detail", "Item", "SD YRP Product Category", "SD YRP Product Season",
		"YRP Item Production Detail", "YRP IPD Process", "YRP Process", "YRP Process Details", "YRP Work Order",
		"YRP Work Order Calculated Item", "YRP Goods Received Note", "YRP Goods Received Note Item",
		"SD YRP GRN Rework Item", "SD YRP GRN Rework Item Detail", "SD YRP Finishing Plan",
		"SD YRP Finishing Plan Detail", "SD YRP Finishing Plan GRN Detail", "YRP Stock Settings",
		"YRP IPD Item Attribute", "YRP Item Item Attribute Mapping", "YRP Item Item Attribute Mapping Value",
		"YRP Production Order"]

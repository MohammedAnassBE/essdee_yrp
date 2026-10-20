from collections import defaultdict

import frappe

from essdee_yrp.planning.reports import production_quantities as quantities


def can_view() -> bool:
	return quantities.can_read("SD YRP Lot", "YRP Work Order", "YRP Item Production Detail")


def require_access() -> None:
	quantities.require_report_access(can_view())


def colour_identity(row, context, detail):
	colour, part, size = quantities.matrix_identity(row, context["attributes"], detail)
	if part:
		major = frappe.parse_json(row.get("set_combination") or "{}").get("major_colour", "")
		variant_colour = context["attributes"].get(row["item_variant"], {}).get(detail.get("packing_attribute"), colour)
		colour = f"{variant_colour}({major})"
	return f"{colour} @{part}" if part else colour, size


def aggregate(context, processes, sizes, supplier_labels=None):
	lot = context["lots"][0]
	detail = context["details"][lot["production_detail"]]
	orders = {row["name"]: row for row in context["orders"]}
	order_rank = {name: index for index, name in enumerate(orders)}
	items = sorted(context["items"], key=lambda row: (order_rank[row["parent"]], row.get("idx", 0)))
	groups = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	suppliers = defaultdict(lambda: defaultdict(dict))
	for row in sorted(context["order_rows"], key=lambda row: row.get("idx", 0)):
		colour, size = colour_identity(row, context, detail)
		groups[colour]["Order Qty"][size] += row.get("quantity") or 0
		groups[colour]["Cut Qty"][size] += row.get("cut_qty") or 0
	process_rows = [("Cut Qty", detail.get("cutting_process")), ("Sewing", detail.get("stiching_process")), *[(f"selected_{index}", process) for index, process in enumerate(processes)]]
	for row in items:
		order = orders[row["parent"]]
		colour, size = colour_identity(row, context, detail)
		for label, process in process_rows:
			if order["process_name"] not in context["expanded"].get(process, []):
				continue
			supplier = (supplier_labels or {}).get(order.get("supplier")) or order.get("supplier_name") or order.get("supplier")
			if supplier:
				suppliers[colour][label].setdefault(supplier, None)
			if label == "Cut Qty":
				continue
			groups[colour][label + " Sent"][size] += row.get("delivered_quantity") or 0
			groups[colour][label + " Received"][size] += row.get("received_qty") or 0
			if label == "Sewing":
				groups[colour]["Cut to Sew Diff"][size] += (row.get("delivered_quantity") or 0) - groups[colour]["Cut Qty"].get(size, 0)
	stages = {row["process_name"]: row for row in context["stages"]}
	# Legacy resets its last-process map for each work order. Each selected
	# process compares only its applicable colours/parts against Cut or Sew.
	comparisons = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	for process in processes:
		if process not in stages:
			continue
		comparison = quantities.process_comparison(stages[process], detail)
		baseline = "Cut Qty" if comparison == "cut" else "Sewing Received"
		received_so_far = defaultdict(lambda: defaultdict(float))
		for row in items:
			if orders[row["parent"]]["process_name"] not in context["expanded"].get(process, []):
				continue
			colour, size = colour_identity(row, context, detail)
			received_so_far[colour][size] += row.get("received_qty") or 0
			comparisons[colour][process][size] += received_so_far[colour][size] - groups[colour][baseline].get(size, 0)
	result = []
	for number, (colour, values) in enumerate(groups.items(), 1):
		def difference(label, left, right):
			values[label] = {size: values[left].get(size, 0) - values[right].get(size, 0) for size in sizes}

		difference("Order to Cut Diff", "Cut Qty", "Order Qty")
		difference("In Sew", "Sewing Received", "Sewing Sent")
		labels = [("Order Qty", ""), ("Cut Qty", "Cut Qty"), ("Order to Cut Diff", "")]
		selected = {"cut": [], "piece": []}
		for index, process in enumerate(processes):
			if process not in stages:
				continue
			comparison = quantities.process_comparison(stages[process], detail)
			sent, received, diff = (process + suffix for suffix in (" Sent", " Received", " Diff"))
			values[sent] = values[f"selected_{index} Sent"]
			values[received] = values[f"selected_{index} Received"]
			difference(diff, received, sent)
			selected[comparison].extend([(sent, f"selected_{index}"), (received, ""), (diff, "")])
			if process in comparisons[colour]:
				against = process + " to " + ("Cut" if comparison == "cut" else "Sew") + " Diff"
				values[against] = comparisons[colour][process]
				selected[comparison].append((against, ""))
		values["Finishing Inward"] = values["Sewing Received"]
		labels += selected["cut"] + [("Sewing Sent", "Sewing"), ("Cut to Sew Diff", ""), ("Finishing Inward", ""), ("In Sew", "")] + selected["piece"]
		for label, supplier_key in labels:
			result.append(quantities.numeric_row({"number": number, "colour": colour, "supplier": ",".join(suppliers[colour][supplier_key]), "process": label}, values[label], sizes))
	return result


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	if not filters.get("lot"):
		frappe.throw("Lot is required.")
	quantities.authorize_filter_values("SD YRP Lot", [filters["lot"]])
	processes = quantities.authorize_filter_values("YRP Process", filters.get("process_list"))
	lots = frappe.get_list("SD YRP Lot", filters={"name": filters["lot"]}, fields=["name", "item", "production_detail"], limit_page_length=0)
	if not lots or not lots[0].get("production_detail"):
		frappe.throw("The Lot must have a production detail.")
	context = quantities.production_context(lots, processes)
	sizes = list(dict.fromkeys(colour_identity(row, context, context["details"][lots[0]["production_detail"]])[1] for row in sorted(context["order_rows"], key=lambda row: row.get("idx", 0))))
	columns = [quantities.column("number", "S.No", "Int"), quantities.column("colour", "Colour"), quantities.column("supplier", "Supplier"), quantities.column("process", "Process")]
	columns += [quantities.column(f"size_{index}", str(size), "Float") for index, size in enumerate(sizes)] + [quantities.column("total", "Total", "Float")]
	return {"columns": columns, "result": aggregate(context, processes, sizes, quantities.supplier_names(context["orders"])), "summary": {"item": lots[0]["item"]}}


def dependency_doctypes(filters=None) -> list[str]:
	return [*quantities.dependency_doctypes(filters), "SD YRP Lot Order Detail", "YRP IPD Process", "Supplier"]

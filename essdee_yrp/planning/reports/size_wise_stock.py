from collections import defaultdict

from essdee_yrp.planning.reports import production_quantities as quantities

METRICS = (
	("order_qty", "Order Qty"), ("cut_qty", "Cut Qty"), ("order_to_cut_diff", "Order-to-Cut Diff"),
	("sewing_sent", "Sewing Sent"), ("cut_to_sew_diff", "Cut-to-Sew Diff"), ("finishing_inward", "Finishing Inward"),
	("in_sew", "In Sew"), ("dispatch", "Dispatch"), ("in_packing", "In Packing"), ("transferred", "Transferred"),
	("cut_to_dispatch_diff", "Cut-to-Dispatch Diff"), ("work_in_progress", "Work In Progress"),
)


def can_view() -> bool:
	return quantities.can_read("SD YRP Lot", "YRP Work Order", "YRP Item Production Detail", "SD YRP Finishing Plan")


def require_access() -> None:
	quantities.require_report_access(can_view())


def aggregate(context, finishing, processes):
	lots = {row["name"]: row for row in context["lots"]}
	orders = {row["name"]: row for row in context["orders"]}
	values = {name: defaultdict(lambda: defaultdict(float)) for name in lots}
	def size_for(row, lot):
		detail = context["details"][lots[lot]["production_detail"]]
		return context["attributes"].get(row["item_variant"], {}).get(detail["primary_item_attribute"], "")

	for row in context["order_rows"]:
		for metric, field in (("order_qty", "quantity"), ("cut_qty", "cut_qty")):
			values[row["parent"]][metric][size_for(row, row["parent"])] += row.get(field) or 0
	for row in context["items"]:
		order = orders[row["parent"]]
		lot = order["lot"]
		size = size_for(row, lot)
		detail = context["details"][lots[lot]["production_detail"]]
		if order["process_name"] in context["expanded"].get(detail.get("stiching_process"), []):
			values[lot]["sewing_sent"][size] += row.get("delivered_quantity") or 0
			values[lot]["finishing_inward"][size] += row.get("received_qty") or 0
		for index, process in enumerate(processes):
			if order["process_name"] in context["expanded"][process]:
				values[lot][f"process_{index}_sent"][size] += row.get("delivered_quantity") or 0
				values[lot][f"process_{index}_received"][size] += row.get("received_qty") or 0
	for row in finishing["dispatches"]:
		plan = finishing["plans"][row["parent"]]
		lot = plan["lot"]
		values[lot]["dispatch"][size_for(row, lot)] += (row.get("dispatched") or 0) * (plan.get("pieces_per_box") or 0) * finishing["parts"][lots[lot]["production_detail"]]
	for row in finishing["inwards"]:
		lot = finishing["plans"][row["parent"]]["lot"]
		values[lot]["transferred"][size_for(row, lot)] += row.get("transferred_qty") or 0
	stages = {(row["parent"], row["process_name"]): row for row in context["stages"]}
	for lot, metrics in values.items():
		sizes = set(size for amounts in metrics.values() for size in amounts)
		detail = context["details"][lots[lot]["production_detail"]]
		for size in sizes:
			metrics["order_to_cut_diff"][size] = metrics["cut_qty"][size] - metrics["order_qty"][size]
			metrics["cut_to_sew_diff"][size] = metrics["sewing_sent"][size] - metrics["cut_qty"][size]
			metrics["in_sew"][size] = metrics["finishing_inward"][size] - metrics["sewing_sent"][size]
			metrics["in_packing"][size] = metrics["dispatch"][size] - metrics["finishing_inward"][size]
			metrics["cut_to_dispatch_diff"][size] = metrics["dispatch"][size] + metrics["transferred"][size] - metrics["cut_qty"][size]
			metrics["work_in_progress"][size] = (metrics["cut_qty"][size] or metrics["order_qty"][size]) - metrics["dispatch"][size] - metrics["transferred"][size]
		previous = {"cut": "cut_qty", "piece": "finishing_inward"}
		for index, process in enumerate(processes):
			stage = stages.get((detail["name"], process), {})
			comparison = quantities.process_comparison(stage, detail)
			baseline = previous[comparison]
			for size in sizes:
				metrics[f"process_{index}_diff"][size] = metrics[f"process_{index}_received"][size] - metrics[f"process_{index}_sent"][size]
				metrics[f"process_{index}_against_{comparison}"][size] = metrics[f"process_{index}_received"][size] - metrics[baseline][size]
			previous[comparison] = f"process_{index}_received"
	return values


def matrices(context, values, processes, size_orders):
	labels = [*METRICS, *[(f"process_{index}_{suffix}", process + " " + suffix.title()) for index, process in enumerate(processes) for suffix in ("sent", "received", "diff")]]
	labels += [(f"process_{index}_against_{comparison}", process + " against " + comparison) for index, process in enumerate(processes) for comparison in ("cut", "piece") if any(f"process_{index}_against_{comparison}" in metrics for metrics in values.values())]
	styles = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
	style_sizes = defaultdict(list)
	result = []
	for lot in context["lots"]:
		metrics = values[lot["name"]]
		sizes = list(dict.fromkeys([*size_orders.get(lot["production_detail"], []), *[size for amounts in metrics.values() for size in amounts]]))
		style_sizes[lot["item"]] = list(dict.fromkeys([*style_sizes[lot["item"]], *sizes]))
		for metric, label in labels:
			result.append({"matrix": "Lot", "lot": lot["name"], "item": lot["item"], "type": label, "matrix_sizes": sizes, "quantities": dict(metrics[metric])})
			for size, amount in metrics[metric].items():
				styles[lot["item"]][metric][size] += amount
	for style, metrics in styles.items():
		for metric, label in labels:
			result.append({"matrix": "Style", "item": style, "type": label, "matrix_sizes": style_sizes[style], "quantities": dict(metrics[metric])})
	all_sizes = list(dict.fromkeys(size for sizes in style_sizes.values() for size in sizes))
	return [quantities.numeric_row({key: value for key, value in row.items() if key != "quantities"}, row["quantities"], all_sizes) for row in result], all_sizes


def run(filters, progress=None) -> dict:
	require_access()
	filters = filters or {}
	processes = quantities.authorize_filter_values("YRP Process", filters.get("process_list"))
	context = quantities.production_context(quantities.production_lots(filters, "product_category"), processes)
	finishing = quantities.finishing_context(context["lots"], context["details"])
	context["attributes"].update(quantities.variant_attributes({row["item_variant"] for row in [*finishing["dispatches"], *finishing["inwards"]]}))
	values = aggregate(context, finishing, processes)
	rows, sizes = matrices(context, values, processes, quantities.production_size_orders(context["details"]))
	columns = [quantities.column(field, label) for field, label in (("matrix", "Matrix"), ("item", "Style"), ("lot", "Lot"), ("type", "Type"))]
	columns += [quantities.column(f"size_{index}", str(size), "Float") for index, size in enumerate(sizes)] + [quantities.column("total", "Total", "Float")]
	return {"columns": columns, "result": rows, "summary": {"lots": len(context["lots"])}}


def dependency_doctypes(filters=None) -> list[str]:
	return [*quantities.dependency_doctypes(filters), "YRP IPD Process", "SD YRP Lot Order Detail", "SD YRP Product Category", "SD YRP Finishing Plan", "SD YRP Finishing Plan Detail", "SD YRP Finishing Plan GRN Detail"]

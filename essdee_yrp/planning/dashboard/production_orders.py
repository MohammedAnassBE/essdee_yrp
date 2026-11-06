from collections import defaultdict

import frappe
from frappe.utils import flt

from essdee_yrp.planning.dashboard import ladder
from essdee_yrp.planning.reports.production_quantities import child_rows

PPO = "YRP Production Order"
LOT_FIELDS = [
	"name",
	"item",
	"production_order",
	"packing_combo",
	"total_order_quantity",
	"production_detail",
]


def get_iso_date(value):
	return str(value) if value else None


def get_lots(production_orders):
	"""SD YRP Lot rows of these PPOs, readable by the user."""
	if not production_orders:
		return []
	return frappe.get_list(
		"SD YRP Lot",
		filters={"production_order": ["in", list(production_orders)]},
		fields=LOT_FIELDS,
		order_by="production_order asc, name asc",
		limit_page_length=0,
	)


def get_lots_with_work_orders(lot_names):
	if not lot_names:
		return set()
	return set(
		frappe.get_list(
			"YRP Work Order",
			filters={"lot": ["in", list(lot_names)], "docstatus": 1},
			pluck="lot",
			distinct=True,
			limit_page_length=0,
		)
	)


def get_item_names(items):
	if not items:
		return {}
	return dict(
		frappe.get_all(
			"Item",
			filters={"name": ["in", list(items)]},
			fields=["name", "item_name"],
			as_list=True,
			limit_page_length=0,
		)
	)


def get_ppo_items(production_orders):
	"""{PPO: {boxes, item, item_name}} from YRP Production Order Detail; item codes are sorted."""
	boxes, items = defaultdict(float), defaultdict(set)
	for row in child_rows("YRP Production Order Detail", production_orders, ["item", "quantity"], PPO):
		boxes[row["parent"]] += flt(row["quantity"])
		items[row["parent"]].add(row["item"])
	names = get_item_names({item for values in items.values() for item in values})
	result = {}
	for name in production_orders:
		codes = sorted(items[name])
		result[name] = {
			"boxes": flt(boxes[name], 3),
			"item": ", ".join(codes),
			"item_name": ", ".join(names.get(code) or code for code in codes),
		}
	return result


def get_ppo_details(production_orders, lots):
	"""{PPO: {delivery, item, item_name, boxes, pieces_per_box, pieces}}; `production_orders` are PPO rows."""
	items = get_ppo_items([row["name"] for row in production_orders])
	combos = defaultdict(list)
	for lot in lots:
		combos[lot["production_order"]].append(lot.get("packing_combo"))
	result = {}
	for row in production_orders:
		pieces = ladder.get_ppo_pieces(items[row["name"]]["boxes"], combos[row["name"]])
		distinct = {flt(combo) for combo in combos[row["name"]] if flt(combo)}
		result[row["name"]] = {
			"delivery": get_iso_date(row.get("delivery_date")),
			**items[row["name"]],
			"pieces_per_box": distinct.pop() if pieces is not None else None,
			"pieces": flt(pieces, 3) if pieces is not None else None,
		}
	return result

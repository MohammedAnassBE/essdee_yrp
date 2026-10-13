from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.attribute_links import value as attribute_value

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lotwise_item_profit.sd_yrp_lotwise_item_profit import (
	get_lot_qty,
)

LOT_QTY_FIELDS = {
	"Planned Qty": "qty",
	"Cutting Qty": "cut_qty",
	"Final Qty": "final_qty",
	"Audited Final": "final_qty",
}
BASED_ON_FIELDS = {
	"Total Qty": "total_qty",
	"Total Value": "total_selling_value",
	"Production Cost": "production_cost",
}
PERCENT_BASED_ON = {"Total Value", "Production Cost"}
TEMPLATE_TABLES = {
	"trade_discounts_template": ("trade_discounts", "Discounts"),
	"other_costs_template": ("other_costs", "Other"),
}
BREAKUP_TABLES = ("cmt", "packing_materials", "trims")


def calculate_all(doc) -> None:
	"""Recompute every derived Lotwise Item Profit value."""
	calculate_qty_rate_chart(doc)
	calculate_cloth_value(doc)
	calculate_production_cost(doc)
	calculate_additional_costs(doc)
	calculate_totals(doc)


def divide(numerator: float, denominator: float) -> float:
	return flt(numerator) / flt(denominator) if flt(denominator) else 0


def calculate_qty_rate_chart(doc) -> None:
	total_qty = total_value = total_weight = 0
	for row in doc.qty_rate_chart:
		row.net_rate = flt(row.rate) * cint(row.qty)
		total_qty += cint(row.qty)
		total_value += row.net_rate
		total_weight += cint(row.qty) * flt(row.weight)
	doc.total_qty, doc.total_selling_value, doc.total_weight = total_qty, total_value, total_weight


def calculate_cloth_value(doc) -> None:
	total = 0
	for row in doc.cloth_value:
		base = flt(row.rate) + flt(row.knitting_cost) + flt(row.dyeing_cost) + flt(row.compacting_cost)
		row.total_cost = base + base * flt(row.wastage_allowance) / 100
		row.net_rate = row.total_cost * flt(row.qty)
		total += row.net_rate
	doc.total_cloth_value = total
	doc.cloth_value_per_piece = divide(total, doc.total_qty)


def calculate_production_cost(doc) -> None:
	doc.total_cmt = sum(flt(row.cost) for row in doc.cmt)
	doc.packing_materials_total = sum(flt(row.cost) for row in doc.packing_materials)
	doc.trims_total = sum(flt(row.cost) for row in doc.trims)
	doc.production_cost_per_piece = doc.total_cmt + doc.packing_materials_total + doc.trims_total
	doc.production_cost = flt(doc.total_cloth_value) + doc.production_cost_per_piece * cint(doc.total_qty)


def additional_cost_total(doc, row) -> float:
	if row.based_on not in BASED_ON_FIELDS:
		return 0
	base = flt(doc.get(BASED_ON_FIELDS[row.based_on]))
	if row.based_on in PERCENT_BASED_ON:
		return flt(row.rate) / 100 * base
	return flt(row.rate) * base


def calculate_additional_costs(doc) -> None:
	for row in [*doc.trade_discounts, *doc.other_costs]:
		row.total = additional_cost_total(doc, row)
	doc.total_trade_discount = sum(flt(row.total) for row in doc.trade_discounts)
	doc.total_other_cost = sum(flt(row.total) for row in doc.other_costs)


def calculate_totals(doc) -> None:
	selling = flt(doc.total_selling_value)
	discount = flt(doc.total_trade_discount)
	doc.gst_value = flt(doc.gst) / 100 * (selling - discount)
	doc.cost_price = flt(doc.production_cost) + discount + flt(doc.total_other_cost) + doc.gst_value
	doc.avg_cost_per_piece = divide(doc.cost_price, doc.total_qty)
	doc.avg_rate_per_piece = divide(selling, doc.total_qty)
	doc.profit = selling - doc.cost_price
	doc.profit_percent = divide(doc.profit, doc.cost_price) * 100
	doc.profit_percent_markdown = divide(doc.profit, selling) * 100


def size_rows(sizes: list[str], prices: list) -> list[dict]:
	return [
		{
			"size": size,
			"qty": 0,
			"rate": flt(prices[index]) if len(prices) == len(sizes) else 0,
		}
		for index, size in enumerate(sizes)
	]


def load_product_sizes(doc) -> None:
	"""Replace the size chart with the Product's sizes."""
	if not doc.product:
		frappe.throw(_("Select a Product first."))
	product = frappe.get_doc("SD YRP Product", doc.product)
	product.check_permission("read")
	sizes = frappe.get_all(
		"SD YRP FG Item Size",
		filters={"parent": doc.product, "parenttype": "SD YRP Product"},
		pluck="attribute_value",
		order_by="idx asc",
	)
	doc.set("qty_rate_chart", size_rows([attribute_value(size) for size in sizes], []))
	doc.item = None
	calculate_all(doc)


def load_item_sizes(doc) -> None:
	"""Replace the size chart with the FG Item Master sizes and prices."""
	if not doc.item:
		frappe.throw(_("Select an Item first."))
	item = frappe.get_doc("SD YRP FG Item Master", doc.item)
	item.check_permission("read")
	sizes = [size.strip() for size in (item.available_sizes or "").split(",") if size.strip()]
	prices = [price.strip() for price in (item.prices or "").split(",")] if item.prices else []
	doc.set("qty_rate_chart", size_rows(sizes, prices))
	doc.product = None
	calculate_all(doc)


def add_rate(doc) -> None:
	extra = flt(doc.additional_rate)
	for row in doc.qty_rate_chart:
		row.rate = flt(row.rate) + extra
	doc.additional_rate = 0
	calculate_all(doc)


def unique(values) -> list:
	return list(dict.fromkeys(value for value in values if value))


def build_piece_cloth_weight(doc) -> None:
	sizes = unique(attribute_value(row.size) for row in doc.qty_rate_chart)
	groups = unique(row.yarn for row in doc.cloth_value)
	if not sizes or not groups:
		return
	doc.set(
		"piece_cloth_weight",
		[{"size": size, "cloth_group": group, "weight": 0} for group in groups for size in sizes],
	)


def size_qty(doc, size) -> int:
	key = attribute_value(size)
	return next(
		(cint(row.qty) for row in doc.qty_rate_chart if attribute_value(row.size) == key),
		0,
	)


def calculate_cloth_qty(doc) -> None:
	weights = {}
	for row in doc.piece_cloth_weight:
		weights[row.cloth_group] = weights.get(row.cloth_group, 0) + flt(row.weight) / 1000 * size_qty(
			doc, row.size
		)
	for row in doc.cloth_value:
		if row.yarn in weights:
			row.qty = weights[row.yarn]
	calculate_all(doc)


def validate_template_types(doc) -> None:
	for template_field, template_config in TEMPLATE_TABLES.items():
		name = doc.get(template_field)
		if not name:
			continue
		expected_type = template_config[1]
		template_type = frappe.db.get_value(
			"SD YRP Lotwise Item Profit Additional Cost Template", name, "type"
		)
		if template_type != expected_type:
			frappe.throw(_("Template {0} is not a {1} template.").format(frappe.bold(name), expected_type))


def apply_additional_cost_template(doc, template_field: str) -> None:
	if template_field not in TEMPLATE_TABLES:
		frappe.throw(_("Unsupported template field {0}.").format(template_field))
	table = TEMPLATE_TABLES[template_field][0]
	name = doc.get(template_field)
	if not name:
		frappe.throw(_("Select a template first."))
	template = frappe.get_doc("SD YRP Lotwise Item Profit Additional Cost Template", name)
	template.check_permission("read")
	validate_template_types(doc)
	doc.set(
		table,
		[
			{"costing_name": row.costing_name, "based_on": row.based_on, "rate": row.rate}
			for row in template.value
		],
	)
	calculate_all(doc)


def apply_production_cost_template(doc) -> None:
	if not doc.production_cost_template:
		frappe.throw(_("Select a production cost template first."))
	template = frappe.get_doc("SD YRP Lotwise Item Profit Breakup Template", doc.production_cost_template)
	template.check_permission("read")
	for table in BREAKUP_TABLES:
		doc.set(
			table,
			[{"costing_name": row.costing_name, "cost": row.cost} for row in template.get(table)],
		)
	calculate_all(doc)


def fetch_lot_qty(doc) -> None:
	if not doc.lot:
		frappe.throw(_("Please set Lot"))
	if not doc.lot_costing_type:
		frappe.throw(_("Please set Lot Costing Type"))
	if doc.lot_costing_type == "Costing":
		frappe.throw(_("Lot quantities are not used when Lot Costing Type is Costing."))
	quantity_field = LOT_QTY_FIELDS.get(doc.lot_costing_type)
	if not quantity_field:
		frappe.throw(_("Select a valid Lot Costing Type."))
	quantities = get_lot_qty(doc.lot, quantity_field)
	for row in doc.qty_rate_chart:
		quantity = quantities.get(attribute_value(row.size))
		if quantity:
			row.qty = cint(quantity)
	calculate_all(doc)


def group_cloth_weights(doc) -> dict:
	"""Group size rows by group index with per-cloth quantity and weight."""
	groups = {}
	for row in doc.qty_rate_chart:
		group = groups.setdefault(cint(row.group_index), {"rows": [], "cloth": {}})
		group["rows"].append(row)
		for weight in doc.piece_cloth_weight:
			if attribute_value(weight.size) != attribute_value(row.size):
				continue
			totals = group["cloth"].setdefault(weight.cloth_group, [0, 0.0])
			totals[0] += cint(row.qty)
			totals[1] += flt(weight.weight) / 1000 * cint(row.qty)
	return groups


def rate_adjustments(doc, percent: float) -> tuple[float, float, float]:
	"""Return per-piece extras, markup percent, and markdown percent."""
	extra_per_piece, markup, markdown = 0.0, 0.0, flt(percent) + flt(doc.gst)
	for row in [*doc.trade_discounts, *doc.other_costs]:
		if row.based_on == "Total Qty":
			extra_per_piece += flt(row.rate)
		elif row.based_on == "Total Value":
			markdown += flt(row.rate)
		elif row.based_on == "Production Cost":
			markup += flt(row.rate)
	return extra_per_piece, markup, markdown


def calculate_backwards_rate(doc, percent: float) -> None:
	"""Set each group's rate so the requested markdown percent is achieved."""
	calculate_all(doc)
	extra_per_piece, markup, markdown = rate_adjustments(doc, percent)
	if markdown >= 100:
		frappe.throw(_("Total markdown must be below 100%."))
	cloth_rates = {row.yarn: flt(row.total_cost) for row in doc.cloth_value}
	base_cost = flt(doc.total_cmt) + flt(doc.packing_materials_total) + flt(doc.trims_total) + extra_per_piece
	for group in group_cloth_weights(doc).values():
		cloth = sum(
			divide(weight, quantity) * cloth_rates[name]
			for name, (quantity, weight) in group["cloth"].items()
			if name in cloth_rates
		)
		rate = (cloth + base_cost) * (1 + markup / 100) / (1 - markdown / 100)
		for row in group["rows"]:
			row.rate = rate
	calculate_all(doc)

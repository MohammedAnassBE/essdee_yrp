"""Essdee garment-specific Work Order process-cost allocation."""

import json
from collections import defaultdict

import frappe
from frappe.utils import flt
from yrp.yrp.doctype.work_order.work_order import (
	WorkOrder,
	get_process_cost_rate,
	get_variant_attributes,
	set_receivable_process_cost,
)


class EssdeeWorkOrder(WorkOrder):
	"""Split garment rates by panel type before falling back to base YRP."""

	def apply_receivable_process_costs(self, process_cost):
		if apply_garment_panel_process_costs(self, process_cost):
			return
		super().apply_receivable_process_costs(process_cost)


def apply_garment_panel_process_costs(work_order, process_cost):
	"""Allocate a finished-garment rate equally across its panel types.

	A panel type receives one equal share of the garment process rate.  The
	stored receivable rate is per physical stock unit, so a panel needed twice
	per garment receives half the per-unit rate of a panel needed once.
	"""
	attribute = process_cost.get("attribute") if process_cost.get("depends_on_attribute") else None
	calculated_items = work_order.get("work_order_calculated_items") or []
	receivables = work_order.get("receivables") or []
	if not attribute or not calculated_items or not receivables or not work_order.get("production_detail"):
		return False

	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	panel_attribute = ipd.get("stiching_attribute")
	if not panel_attribute or attribute == panel_attribute:
		return False

	attribute_cache = {}

	def attributes(item_variant):
		if item_variant not in attribute_cache:
			attribute_cache[item_variant] = get_variant_attributes(item_variant)
		return attribute_cache[item_variant]

	demand_data = []
	attribute_quantities = defaultdict(float)
	for demand in calculated_items:
		demand_attributes = attributes(demand.item_variant)
		attribute_value = demand_attributes.get(attribute)
		if not attribute_value:
			return False
		data = {
			"row": demand,
			"attributes": demand_attributes,
			"attribute_value": attribute_value,
			"combination": _combination_key(demand.get("set_combination")),
			"receivables": [],
		}
		demand_data.append(data)
		attribute_quantities[attribute_value] += flt(demand.quantity)

	for receivable in receivables:
		receivable_attributes = attributes(receivable.item_variant)
		if not receivable_attributes.get(panel_attribute):
			return False
		matches = [
			demand
			for demand in demand_data
			if _matches_garment_demand(
				demand,
				receivable,
				receivable_attributes,
				ipd,
			)
		]
		if len(matches) != 1:
			return False
		matches[0]["receivables"].append((receivable, receivable_attributes[panel_attribute]))

	if any(not demand["receivables"] for demand in demand_data):
		return False

	for demand in demand_data:
		calculated_qty = flt(demand["row"].quantity)
		if calculated_qty <= 0:
			return False
		finished_item_rate = get_process_cost_rate(
			demand["row"].item_variant,
			attribute_quantities[demand["attribute_value"]],
			process_cost,
		)
		panel_groups = defaultdict(list)
		for receivable, panel in demand["receivables"]:
			panel_groups[panel].append(receivable)
		if not panel_groups:
			return False

		panel_type_value = flt(finished_item_rate) * calculated_qty / len(panel_groups)
		for panel_rows in panel_groups.values():
			panel_quantity = sum(flt(row.qty) for row in panel_rows)
			if panel_quantity <= 0:
				return False
			unit_rate = panel_type_value / panel_quantity
			for row in panel_rows:
				set_receivable_process_cost(row, process_cost.name, unit_rate)

	return True


def _matches_garment_demand(demand, receivable, receivable_attributes, ipd):
	if demand["combination"] != _combination_key(receivable.get("set_combination")):
		return False

	demand_attributes = demand["attributes"]
	excluded = {ipd.get("dependent_attribute"), ipd.get("packing_attribute")}
	for attribute, value in demand_attributes.items():
		if attribute in excluded:
			continue
		if receivable_attributes.get(attribute) != value:
			return False

	# The major garment colour normally lives in set_combination.  Older or
	# generic rows can have an empty combination, so use the actual packing
	# attribute as the unambiguous fallback in that case.
	if demand["combination"] == "{}":
		packing_attribute = ipd.get("packing_attribute")
		if packing_attribute and receivable_attributes.get(packing_attribute) != demand_attributes.get(
			packing_attribute
		):
			return False
	return True


def _combination_key(value):
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except TypeError, ValueError:
			return value
	value = value or {}
	return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

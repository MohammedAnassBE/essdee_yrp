# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe.utils import flt
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as attribute_value
from yrp.attribute_read_context import attribute_read_scope
from yrp.utils import get_variant_attr_details

from essdee_yrp.finishing.old_lot_history import active_old_lot_transfer_rows
from essdee_yrp.finishing.packing import PACKING_GRN_FILTERS, get_finishing_packing_summary


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "item",
			"fieldtype": "Link",
			"label": "Style",
			"options": "Item",
		},
		{
			"fieldname": "description",
			"fieldtype": "Data",
			"label": "Description",
		},
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"label": "Lot",
			"options": "SD YRP Lot",
		},
		{"fieldname": "pieces_per_box", "fieldtype": "Data", "label": "Pieces Per Box"},
		{
			"fieldname": "cut_qty",
			"fieldtype": "Int",
			"label": "Cut Qty",
		},
		{
			"fieldname": "sewing_received",
			"fieldtype": "Int",
			"label": "Sewing Received",
		},
		{
			"fieldname": "sewing_diff",
			"fieldtype": "Int",
			"label": "Sewing Difference",
		},
		{
			"fieldname": "old_lot",
			"fieldtype": "Int",
			"label": "Old Lot",
		},
		{
			"fieldname": "ironing_excess",
			"fieldtype": "Int",
			"label": "Ironing Excess",
		},
		{
			"fieldname": "finishing_inward",
			"fieldtype": "Int",
			"label": "Finishing Inward",
		},
		{
			"fieldname": "cut_to_finishing_diff",
			"fieldtype": "Int",
			"label": "Cut to Finishing Inward Difference",
		},
		{
			"fieldname": "dispatch_box_qty",
			"fieldtype": "Int",
			"label": "Dispatch ",
			"options": "",
		},
		{
			"fieldname": "dispatch_piece_qty",
			"fieldtype": "Int",
			"label": "Dispatch Piece Qty",
		},
		{"fieldname": "transferred", "fieldtype": "Int", "label": "Transferred Qty"},
		{
			"fieldname": "transferred_as_loose_piece",
			"fieldtype": "Int",
			"label": "Transferred as Loose Piece",
		},
		{
			"fieldname": "unaccountable",
			"fieldtype": "Int",
			"label": "Unaccountable",
		},
		{
			"fieldname": "unaccountable_percentage",
			"fieldtype": "Percent",
			"label": "Unaccountable Percentage",
		},
		{
			"fieldname": "loose_piece",
			"fieldtype": "Int",
			"label": "Loose Piece",
		},
		{
			"fieldname": "rejection",
			"fieldtype": "Int",
			"label": "Rejection",
		},
		{
			"fieldname": "rework",
			"fieldtype": "Int",
			"label": "Rework",
		},
		{
			"fieldname": "cut_to_dispatch_diff",
			"fieldtype": "Int",
			"label": "Cut to Dispatch Difference",
			"options": "",
		},
		{
			"fieldname": "cut_to_dispatch_diff_percent",
			"fieldtype": "Percent",
			"label": "Cut to Dispatch Difference Percentage",
		},
		{
			"fieldname": "finishing_inward_to_dispatch_diff",
			"fieldtype": "Int",
			"label": "Finishing Inward to Dispatch Difference",
		},
		{
			"fieldname": "finishing_inward_to_dispatch_diff_percent",
			"fieldtype": "Percent",
			"label": "Finishing Inward to Dispatch Difference Percentage",
		},
	]


def _report_plans(names):
	plans = {}
	fields = ("finishing_old_lot_given_items", "finishing_plan_details", "finishing_plan_reworked_details", "finishing_plan_grn_details")
	meta = frappe.get_meta("SD YRP Finishing Plan")
	for offset in range(0, len(names), 500):
		chunk = names[offset:offset + 500]
		for row in frappe.get_all("SD YRP Finishing Plan", filters={"name": ["in", chunk]}, fields=["*"], limit_page_length=0):
			plans[row.name] = row
		tied = set()
		for field in fields:
			parents = [name for name in chunk if name in plans and (field == "finishing_old_lot_given_items" or plans[name].is_set_item)]
			for name in parents:
				plans[name][field] = []
			if not parents:
				continue
			seen = set()
			for row in frappe.get_all(
				meta.get_field(field).options,
				filters={"parent": ["in", parents], "parenttype": "SD YRP Finishing Plan", "parentfield": field},
				fields=["*"], order_by="idx asc", limit_page_length=0,
			):
				key = (row.parent, row.idx)
				if key in seen:
					tied.add(row.parent)
				seen.add(key)
				plans[row.parent][field].append(row)
		# A tied idx has no defined secondary order; retain the original per-plan read.
		for name in tied:
			plans[name] = frappe.get_lazy_doc("SD YRP Finishing Plan", name)
	return plans


PLAN_SUMS = {
	"detail": (
		"SD YRP Finishing Plan Detail",
		"""SUM(cutting_qty) AS cut_qty, SUM(delivered_quantity) AS sewing_received,
		sum(dc_qty) as dc_qty, SUM(lot_transferred) as old_lot, SUM(ironing_excess) as ironing_excess,
		SUM(return_qty) + SUM(pack_return_qty) AS loose_piece,
		SUM(transferred_qty) as transferred""",
		("cut_qty", "sewing_received", "dc_qty", "old_lot", "ironing_excess", "loose_piece", "transferred"),
	),
	"dispatch": (
		"SD YRP Finishing Plan GRN Detail",
		"sum(dispatched) as dispatched_box",
		("dispatched_box",),
	),
	"rework": (
		"SD YRP Finishing Plan Reworked Detail",
		"""SUM(quantity) as rework_quantity, SUM(reworked_quantity) as reworked,
		SUM(rejected_qty) as rejected""",
		("rework_quantity", "reworked", "rejected"),
	),
}


def collation_key(value):
	"""Python twin of utf8mb4_unicode_ci equality for printable ASCII; None when unprovable."""
	if isinstance(value, str) and value.isascii() and value.isprintable():
		return value.lower().rstrip(" ")
	return None


def get_variant_attribute_rows(variants):
	"""Raw (attribute, value) rows behind get_variant_attr_details; variants it cannot prove identical are left out."""
	keys = {collation_key(variant) for variant in variants} - {None}
	ordered_keys = sorted(keys)
	rows_by_key = {}
	for offset in range(0, len(ordered_keys), 500):
		for row in frappe.db.sql(
			"SELECT parent, attribute, attribute_value FROM `tabItem Variant Attribute` WHERE parent IN %(parents)s",
			{"parents": tuple(ordered_keys[offset:offset + 500])},
			as_dict=True,
		):
			key = collation_key(row.parent)
			if key not in keys:
				return {}
			rows_by_key.setdefault(key, []).append(row)
	variant_rows = {}
	for variant in variants:
		key = collation_key(variant)
		rows = rows_by_key.get(key, [])
		# The per-variant query has no ORDER BY, so a repeated attribute keeps the scalar read.
		if key is not None and len({row.attribute for row in rows}) == len(rows):
			variant_rows[variant] = [(row.attribute, row.attribute_value) for row in rows]
	return variant_rows


def get_packing_grn_names(plans):
	"""get_finishing_packing_summary GRN lists for many plans; plans it cannot prove identical are left out."""
	plan_keys = {plan.name: (collation_key(plan.work_order), collation_key(plan.lot)) for plan in plans if plan.work_order}
	plan_keys = {name: key for name, key in plan_keys.items() if None not in key}
	work_orders = sorted({key[0] for key in plan_keys.values()})
	rows_by_key = {}
	for offset in range(0, len(work_orders), 500):
		for row in frappe.get_all(
			"YRP Goods Received Note",
			filters={**PACKING_GRN_FILTERS, "against_id": ["in", work_orders[offset:offset + 500]]},
			fields=["name", "against_id", "lot", "modified"],
		):
			key = (collation_key(row.against_id), collation_key(row.lot))
			if key[0] is None or (key[1] is None and row.lot is not None):
				return {}
			rows_by_key.setdefault(key, []).append(row)
	names = {plan.name: [] for plan in plans if not plan.work_order}
	for name, key in plan_keys.items():
		rows = rows_by_key.get(key, [])
		# Rows tied on the default `modified desc` order have no defined order: keep the per-plan read.
		if len({row.modified for row in rows}) == len(rows):
			names[name] = [row.name for row in rows]
	return names


class PlanSums:
	"""PLAN_SUMS per plan in one GROUP BY query per 500 plans, shaped like the per-plan query."""

	def __init__(self, kind, names):
		self.table, self.select, self.columns = PLAN_SUMS[kind]
		self.rows, self.has_foreign_parent = {}, False
		for offset in range(0, len(names), 500):
			chunk = set(names[offset:offset + 500])
			for row in frappe.db.sql(
				f"SELECT parent AS plan_name, {self.select} FROM `tab{self.table}` WHERE parent IN %(names)s GROUP BY parent",
				{"names": tuple(chunk)},
				as_dict=True,
			):
				name = row.pop("plan_name")
				self.has_foreign_parent |= name not in chunk
				self.rows[name] = row

	def get(self, name):
		if name in self.rows:
			return self.rows[name]
		if self.has_foreign_parent:
			# A group keyed by another spelling of a plan name: keep the per-plan read.
			return frappe.db.sql(
				f"SELECT {self.select} FROM `tab{self.table}` WHERE parent = %(name)s", {"name": name}, as_dict=True
			)[0]
		return frappe._dict.fromkeys(self.columns)


def get_data(filters):
	with attribute_read_scope():
		return _read_get_data(filters)


def _read_get_data(filters):
	data = []
	fil = {}
	if filters.get("lot"):
		fil["lot"] = filters.get("lot")
	if filters.get("item"):
		fil["item"] = filters.get("item")
	if filters.get("season"):
		lot_list = attribute_db.get_all("SD YRP Lot", filters={"season": filters.get("season")}, pluck="name")
		fil["lot"] = ["in", lot_list]
	if filters.get("product_category"):
		item_list = frappe.get_all(
			"Item",
			filters={"product_category": filters.get("product_category")},
			pluck="name",
		)
		if filters.get("item"):
			# Item + Product Category both chosen: keep the chosen item only if it
			# belongs to the selected category, otherwise nothing matches.
			if filters.get("item") not in item_list:
				return data
		else:
			# Product Category alone: restrict to every item in that category.
			if not item_list:
				return data
			fil["item"] = ["in", item_list]

	fp_list = frappe.get_all("SD YRP Finishing Plan", filters=fil, pluck="name")
	plans = _report_plans(fp_list)
	set_plans = [plan for plan in plans.values() if plan.is_set_item]
	variant_rows = get_variant_attribute_rows({
		row.item_variant
		for plan in set_plans
		for field in ("finishing_plan_details", "finishing_old_lot_given_items", "finishing_plan_reworked_details")
		for row in plan.get(field) or []
	})

	resolved = {}

	def variant_attrs(variant):
		if variant not in variant_rows:
			return get_variant_attr_details(variant)
		# Resolved on first use, like the scalar read, so unused rows (cancelled transfers) never raise.
		if variant not in resolved:
			resolved[variant] = {attribute: attribute_value(raw) for attribute, raw in variant_rows[variant]}
		return resolved[variant]

	single_plans = [name for name in fp_list if name in plans and not plans[name].is_set_item]
	sums = {kind: PlanSums(kind, single_plans) for kind in PLAN_SUMS}
	packing_grn_names = get_packing_grn_names(list(plans.values()))
	for fp_name in fp_list:
		fp_doc = plans.get(fp_name) or frappe.get_lazy_doc("SD YRP Finishing Plan", fp_name)
		packing_summary = get_finishing_packing_summary(fp_doc, packing_grn_names.get(fp_name))
		report_pieces_per_box = fp_doc.pieces_per_box
		if packing_summary.dynamic_ratio_packing:
			batch_combos = {flt(batch.get("pieces_per_box")) for batch in packing_summary.packing_batches}
			report_pieces_per_box = batch_combos.pop() if len(batch_combos) == 1 else "Mixed"
		d = {
			"item": fp_doc.item,
			"lot": fp_doc.lot,
			"pieces_per_box": report_pieces_per_box,
		}
		if fp_doc.is_set_item:
			set_dict = {}
			set_attr = frappe.get_value(
				"YRP Item Production Detail", fp_doc.production_detail, "set_item_attribute"
			)
			for row in fp_doc.finishing_plan_details:
				attrs = variant_attrs(row.item_variant)
				set_attr_value = attrs[set_attr]
				set_dict.setdefault(
					set_attr_value,
					{
						"item": fp_doc.item,
						"lot": fp_doc.lot,
						"pieces_per_box": report_pieces_per_box,
						"description": set_attr_value,
						"cut_qty": 0,
						"sewing_received": 0,
						"sewing_diff": 0,
						"old_lot": 0,
						"ironing_excess": 0,
						"finishing_inward": 0,
						"loose_piece": 0,
						"cut_to_finishing_diff": 0,
						"dispatch_box_qty": 0,
						"dispatch_piece_qty": 0,
						"cut_to_dispatch_diff": 0,
						"finishing_inward_to_dispatch_diff": 0,
						"rejection": 0,
						"rework": 0,
						"unaccountable": 0,
						"cut_to_dispatch_diff_percent": 0,
						"transferred": 0,
						"transferred_as_loose_piece": 0,
					},
				)
				set_dict[set_attr_value]["cut_qty"] += row.cutting_qty
				set_dict[set_attr_value]["sewing_received"] += row.delivered_quantity
				set_dict[set_attr_value]["old_lot"] += row.lot_transferred
				set_dict[set_attr_value]["ironing_excess"] += row.ironing_excess
				set_dict[set_attr_value]["loose_piece"] += row.return_qty + row.pack_return_qty
				set_dict[set_attr_value]["finishing_inward"] += row.dc_qty
				set_dict[set_attr_value]["transferred"] += row.transferred_qty

			for row in active_old_lot_transfer_rows(fp_doc.get("finishing_old_lot_given_items")):
				attrs = variant_attrs(row.item_variant)
				set_attr_value = attrs[set_attr]
				if set_attr_value not in set_dict:
					continue
				quantity = flt(row.loose_piece_given) + flt(row.loose_piece_set_given)
				set_dict[set_attr_value]["loose_piece"] -= quantity
				set_dict[set_attr_value]["transferred_as_loose_piece"] += quantity

			for row in fp_doc.finishing_plan_reworked_details:
				attrs = variant_attrs(row.item_variant)
				set_attr_value = attrs[set_attr]
				set_dict[set_attr_value]["rejection"] += row.rejected_qty
				set_dict[set_attr_value]["rework"] += row.quantity - (
					row.reworked_quantity + row.rejected_qty
				)

			if packing_summary.dynamic_ratio_packing:
				for set_key in set_dict:
					set_dict[set_key]["dispatch_box_qty"] = flt(packing_summary.total_dispatched_boxes)
					set_dict[set_key]["dispatch_piece_qty"] = flt(packing_summary.total_dispatched)
			else:
				for row in fp_doc.finishing_plan_grn_details:
					for set_key in set_dict:
						set_dict[set_key]["dispatch_box_qty"] += row.dispatched
						set_dict[set_key]["dispatch_piece_qty"] += row.dispatched * fp_doc.pieces_per_box

			for set_key in set_dict:
				set_dict[set_key]["sewing_diff"] = (
					set_dict[set_key]["sewing_received"] - set_dict[set_key]["cut_qty"]
				)
				set_dict[set_key]["cut_to_finishing_diff"] = (
					set_dict[set_key]["finishing_inward"] - set_dict[set_key]["cut_qty"]
				)
				set_dict[set_key]["cut_to_dispatch_diff"] = (
					set_dict[set_key]["dispatch_piece_qty"]
					+ set_dict[set_key]["transferred"]
					+ set_dict[set_key]["transferred_as_loose_piece"]
					- set_dict[set_key]["cut_qty"]
				)
				set_dict[set_key]["finishing_inward_to_dispatch_diff"] = (
					set_dict[set_key]["dispatch_piece_qty"] - set_dict[set_key]["finishing_inward"]
				)
				sum1 = (
					set_dict[set_key]["dispatch_piece_qty"]
					+ set_dict[set_key]["rejection"]
					+ set_dict[set_key]["loose_piece"]
					+ set_dict[set_key]["rework"]
					+ set_dict[set_key]["transferred"]
					+ set_dict[set_key]["transferred_as_loose_piece"]
				)
				sum2 = (
					set_dict[set_key]["sewing_received"]
					+ set_dict[set_key]["old_lot"]
					+ set_dict[set_key]["ironing_excess"]
				)
				set_dict[set_key]["unaccountable"] = sum1 - sum2
				val1 = (
					set_dict[set_key]["cut_qty"]
					+ set_dict[set_key]["old_lot"]
					+ set_dict[set_key]["ironing_excess"]
				)
				if set_dict[set_key]["unaccountable"] != 0:
					x = set_dict[set_key]["unaccountable"]
					if x < 0:
						x = x * -1
					set_dict[set_key]["unaccountable_percentage"] = round(x / val1, 2) * 100
				else:
					set_dict[set_key]["unaccountable_percentage"] = 100

				sum1 = (
					set_dict[set_key]["cut_qty"]
					+ set_dict[set_key]["old_lot"]
					+ set_dict[set_key]["ironing_excess"]
					- set_dict[set_key]["transferred"]
					- set_dict[set_key]["transferred_as_loose_piece"]
				)
				if sum1 != 0:
					set_dict[set_key]["cut_to_dispatch_diff_percent"] = 100 - (
						round(set_dict[set_key]["dispatch_piece_qty"] / sum1, 2) * 100
					)
				else:
					set_dict[set_key]["cut_to_dispatch_diff_percent"] = 100
				sum1 = (
					set_dict[set_key]["sewing_received"]
					+ set_dict[set_key]["old_lot"]
					+ set_dict[set_key]["ironing_excess"]
				)
				if set_dict[set_key]["finishing_inward"] != 0:
					set_dict[set_key]["finishing_inward_to_dispatch_diff_percent"] = 100 - (
						round(
							set_dict[set_key]["dispatch_piece_qty"] / set_dict[set_key]["finishing_inward"], 2
						)
						* 100
					)
				else:
					set_dict[set_key]["finishing_inward_to_dispatch_diff_percent"] = 100

			for set_key in set_dict:
				data.append(set_dict[set_key])

		else:
			fp_detail = sums["detail"].get(fp_name)
			d["cut_qty"] = fp_detail["cut_qty"]
			d["sewing_received"] = fp_detail["sewing_received"]
			d["sewing_diff"] = fp_detail["sewing_received"] - fp_detail["cut_qty"]
			d["old_lot"] = fp_detail["old_lot"]
			d["ironing_excess"] = fp_detail["ironing_excess"]
			d["finishing_inward"] = fp_detail["dc_qty"]
			d["transferred_as_loose_piece"] = sum(
				flt(row.loose_piece_given) + flt(row.loose_piece_set_given)
				for row in active_old_lot_transfer_rows(fp_doc.get("finishing_old_lot_given_items"))
			)
			d["loose_piece"] = fp_detail["loose_piece"] - d["transferred_as_loose_piece"]
			d["cut_to_finishing_diff"] = fp_detail["dc_qty"] - fp_detail["cut_qty"]
			d["transferred"] = fp_detail["transferred"]
			if packing_summary.dynamic_ratio_packing:
				d["dispatch_box_qty"] = flt(packing_summary.total_dispatched_boxes)
				d["dispatch_piece_qty"] = flt(packing_summary.total_dispatched)
			else:
				dispatch_detail = sums["dispatch"].get(fp_name)
				d["dispatch_box_qty"] = flt(dispatch_detail["dispatched_box"])
				d["dispatch_piece_qty"] = d["dispatch_box_qty"] * flt(fp_doc.pieces_per_box)
			d["cut_to_dispatch_diff"] = (
				d["dispatch_piece_qty"]
				+ fp_detail["transferred"]
				+ d["transferred_as_loose_piece"]
				- fp_detail["cut_qty"]
			)
			d["finishing_inward_to_dispatch_diff"] = d["dispatch_piece_qty"] - fp_detail["dc_qty"]
			rework_detail = sums["rework"].get(fp_name)
			d["rejection"] = rework_detail.get("rejected") or 0
			d["rework"] = (
				(rework_detail.get("rework_quantity") or 0)
				- (rework_detail.get("reworked") or 0)
				- (rework_detail.get("rejected") or 0)
			)
			sum1 = (
				d["dispatch_piece_qty"]
				+ d["rejection"]
				+ d["loose_piece"]
				+ d["rework"]
				+ d["transferred"]
				+ d["transferred_as_loose_piece"]
			)
			sum2 = d["sewing_received"] + d["old_lot"] + d["ironing_excess"]
			d["unaccountable"] = sum1 - sum2
			val1 = d["cut_qty"] + d["old_lot"] + d["ironing_excess"]
			if d["unaccountable"] != 0:
				x = d["unaccountable"]
				if x < 0:
					x = x * -1
				d["unaccountable_percentage"] = round(x / val1, 2) * 100
			else:
				d["unaccountable_percentage"] = 100
			sum1 = (
				d["cut_qty"]
				+ d["old_lot"]
				+ d["ironing_excess"]
				- d["transferred"]
				- d["transferred_as_loose_piece"]
			)
			if sum1 != 0:
				d["cut_to_dispatch_diff_percent"] = 100 - (round(d["dispatch_piece_qty"] / sum1, 2) * 100)
			else:
				d["cut_to_dispatch_diff_percent"] = 100

			sum1 = d["sewing_received"] + d["old_lot"] + d["ironing_excess"]
			if sum1 != 0:
				d["finishing_inward_to_dispatch_diff_percent"] = 100 - (
					round(d["dispatch_piece_qty"] / sum1, 2) * 100
				)
			else:
				d["finishing_inward_to_dispatch_diff_percent"] = 100

			data.append(d)
	return data

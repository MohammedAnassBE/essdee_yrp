import json
import math
from itertools import groupby
from copy import deepcopy

# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt
import frappe
from yrp.attribute_read_context import attribute_read_scope
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, now_datetime
from six import string_types
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_values import get_mapping_document
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_holiday_list.yrp_holiday_list import get_next_date
from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details, get_or_create_variant, get_parent_item
from yrp.yrp.doctype.yrp_item_dependent_attribute_mapping.yrp_item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	calculate_bom_for_variant_demands,
)
from yrp.yrp.doctype.yrp_purchase_order.yrp_purchase_order import get_item_group_index

from essdee_yrp.cloth_program_access import has_cloth_program_role
from essdee_yrp.fabric_program import (
	fetch_fabric_program_details,
	rebuild_plans_after_save,
	refresh_server_owned_tables,
	save_fabric_program_details,
	save_fabric_requirement_details,
	validate_unique_fabric_cloths,
)
from essdee_yrp.garment_bom import calculate_essdee_accessory_bom


def get_panel_colour_combination(ipd_doc):
	indexes = {}
	comb_details = {}
	for row in ipd_doc.stiching_item_combination_details:
		if indexes.get(row.index):
			major_colour = indexes[row.index]
			comb_details[major_colour][_attribute_value(row.set_item_attribute_value)] = _attribute_value(
				row.attribute_value
			)
		else:
			indexes[row.index] = _attribute_value(row.major_attribute_value)
			comb_details[_attribute_value(row.major_attribute_value)] = {}
			comb_details[_attribute_value(row.major_attribute_value)][
				_attribute_value(row.set_item_attribute_value)
			] = _attribute_value(row.attribute_value)

	return comb_details


class SDYRPLot(Document):
	def before_submit(self):
		if len(self.bom_summary) == 0:
			frappe.throw("BOM is not calculated")

	def before_validate(self):
		refresh_server_owned_tables(self)
		preserve_lot_fabric_conversions(self)
		validate_unique_fabric_cloths(self)
		if self.get("fabric_program_details"):
			save_fabric_program_details(self)
		save_fabric_requirement_details(self)

		if self.get("item_details"):
			items = save_item_details(self.item_details)
			self.set("items", items)

		if self.get("order_item_details") and self.production_detail:
			order_items = save_order_item_details(
				self.production_detail, self.lot_order_details, self.order_item_details
			)
			self.set("lot_order_details", order_items)
			if self.production_order and order_items and len(self.items) > 0:
				self.derive_items_from_order_details()

		if self.is_new():
			self.lot_hash_value = make_autoname(key="hash")
			if len(self.items) > 0 and not self.flags.get("items_derived"):
				self.calculate_order()
		else:
			doc = frappe.get_doc("SD YRP Lot", self.name)
			if len(doc.items) == 0 and len(self.items) > 0 and not self.flags.get("items_derived"):
				self.calculate_order()

			qty = 0
			for item in self.items:
				qty = qty + item.qty
			self.total_quantity = qty
			# if self.get("cad_details"):
			# 	cad_data = update_if_string_instance(self.cad_details)
			# 	if cad_data.get(self.item):
			# 		for colour in cad_data[self.item]:
			# 			for cat in cad_data[self.item][colour]['categories']:
			# 				weight = round(cad_data[self.item][colour]['categories'][cat]["actual_weight"], 3)
			# 				cad_data[self.item][colour]['categories'][cat]["actual_weight"] = weight
			# 				weight = round(cad_data[self.item][colour]['categories'][cat]["reqd_weight"], 3)
			# 				cad_data[self.item][colour]['categories'][cat]["reqd_weight"] = weight
			# 		self.cad_detail_data = frappe.json.dumps(cad_data)

		total_qty = 0
		for item in self.lot_order_details:
			total_qty += vars(item)["quantity"]
		self.total_order_quantity = total_qty

	def before_save(self):
		if not self.is_new():
			prev_ppo = frappe.get_value("SD YRP Lot", self.name, "production_order")
			cur_ppo = self.production_order
			if not prev_ppo and not cur_ppo:
				pass
			elif not prev_ppo and cur_ppo:
				add_ppo_lot_qty(self.production_order, self.name, self.items)
			elif prev_ppo and not cur_ppo:
				delete_ppo_lot_qty(prev_ppo, self.name)
			elif prev_ppo and cur_ppo:
				if prev_ppo == cur_ppo:
					delete_ppo_lot_qty(prev_ppo, self.name)
					add_ppo_lot_qty(self.production_order, self.name, self.items)
				else:
					delete_ppo_lot_qty(prev_ppo, self.name)
					add_ppo_lot_qty(self.production_order, self.name, self.items)

	def after_insert(self):
		if len(self.items) > 0 and self.production_order:
			add_ppo_lot_qty(self.production_order, self.name, self.items)

	def calculate_order(self):
		previous_data = {}
		for item in self.lot_order_details:
			set_combination = update_if_string_instance(item.set_combination)
			if set_combination not in [None, ""]:
				set_combination = set_combination.copy()
				set_combination.update({"variant": item.item_variant})
				set_combination = frozenset(set_combination)

				previous_data[set_combination] = {
					"cut_qty": item.cut_qty,
					"stich_qty": item.stich_qty,
					"pack_qty": item.pack_qty,
				}
		items, qty = calculate_order_details(
			self.get("items"), self.production_detail, self.packing_uom, self.uom
		)
		x = []
		if len(items) == 0:
			for item in self.items:
				x.append({"item_variant": item.item_variant, "quantity": item.qty})
				qty += item.qty
			self.set("lot_order_details", x)
			self.set("total_order_quantity", qty)
		else:
			for item in items:
				key = update_if_string_instance(item["set_combination"])
				if key not in [None, ""]:
					key = key.copy()
					key.update({"variant": item["item_variant"]})
					key = frozenset(key)
					if previous_data.get(key):
						item.update(
							{
								"cut_qty": previous_data[key]["cut_qty"],
								"stich_qty": previous_data[key]["stich_qty"],
								"pack_qty": previous_data[key]["pack_qty"],
							}
						)
			self.set("lot_order_details", items)
			self.set("total_order_quantity", qty)

	def derive_items_from_order_details(self):
		"""Derive the box table from the operator-entered piece table.

		The Lot's ``items`` rows identify the valid packed variants; their quantities
		are server-owned once a Production Order is linked.  Only the major set part
		contributes to the packed-box count because the companion parts are generated
		from the same finished-garment pieces.
		"""
		ipd = frappe.get_cached_doc("YRP Item Production Detail", self.production_detail)
		pieces_per_box = flt(ipd.packing_combo)
		if pieces_per_box <= 0:
			frappe.throw(f"Packing Combo is not set in Item Production Detail {self.production_detail}")

		pieces_by_size = {}
		for row in self.lot_order_details:
			attributes = get_variant_attr_details(row.item_variant)
			if ipd.is_set_item and attributes.get(ipd.set_item_attribute) != _attribute_value(
				ipd.major_attribute_value
			):
				continue
			size = attributes.get(ipd.primary_item_attribute)
			pieces_by_size[size] = flt(pieces_by_size.get(size)) + flt(row.quantity)

		for row in self.items:
			attributes = get_variant_attr_details(row.item_variant)
			size = attributes.get(ipd.primary_item_attribute)
			row.qty = math.ceil(flt(pieces_by_size.pop(size, 0)) / pieces_per_box)

		unmapped = [size for size, pieces in pieces_by_size.items() if flt(pieces) > 0]
		if unmapped:
			frappe.throw(
				"Order details have quantity for size {0}, but there is no box row for that size".format(
					", ".join(str(size) for size in unmapped)
				)
			)
		self.flags.items_derived = True

	def on_update(self):
		rebuild_plans_after_save(self)

	def on_trash(self):
		"""Drop this Lot's lotwise rows from every Production Order before Frappe's link check."""
		frappe.db.delete("YRP Production Ordered Detail", {"lot": self.name})
		frappe.db.delete(
			"YRP Production Ordered Detail",
			{"reference_doctype": "SD YRP Lot", "reference_name": self.name},
		)

	def onload(self):
		self.set_onload("can_manage_cloth_program", has_cloth_program_role())
		if self.get("lot_fabric_details"):
			self.set_onload("fabric_program_details", fetch_fabric_program_details(self))
		if self.production_detail:
			item_details = fetch_item_details(self.get("items"), self.production_detail)
			self.set_onload("item_details", item_details)
			if len(self.lot_order_details) > 0:
				items = fetch_order_item_details(self.get("lot_order_details"), self.production_detail)
				x = json.dumps(items[0])
				# onload runs during a GET. Keep the compatibility field on the
				# in-memory document without taking an unnecessary row lock or
				# issuing a write that the GET transaction will roll back.
				self.set("lot_order_details_json", x)
				self.set_onload("order_item_details", items)

		if self.get("lot_time_and_action_details"):
			self.set_onload(
				"action_details",
				get_time_and_action_process(self.lot_time_and_action_details),
			)

		# if self.cad_detail_data:
		# 	data = update_if_string_instance(self.cad_detail_data)
		# 	self.set_onload("cad_item_details", data)


def delete_ppo_lot_qty(ppo, lot):
	"""Delete the Lot's rows, including migrated rows that only carry the direct `lot` link."""
	frappe.db.sql(
		"""
			DELETE FROM `tabYRP Production Ordered Detail`
			WHERE parent = %(ppo)s
			AND ((reference_doctype = 'SD YRP Lot' AND reference_name = %(lot)s) OR lot = %(lot)s)
		""",
		{"ppo": ppo, "lot": lot},
	)


def add_ppo_lot_qty(ppo, lot, items):
	for item in items:
		doc = frappe.new_doc("YRP Production Ordered Detail")
		doc.parent = ppo
		doc.item_variant = item.item_variant
		doc.quantity = item.qty
		doc.reference_doctype = "SD YRP Lot"
		doc.reference_name = lot
		doc.lot = lot
		doc.parenttype = "YRP Production Order"
		doc.parentfield = "production_ordered_details"
		doc.save(ignore_permissions=True)


def get_time_and_action_process(action_details):
	"""Return the next incomplete Time and Action step for every Lot colour."""
	items = []
	for item in action_details:
		pending = frappe.get_all(
			"SD YRP Time and Action Detail",
			filters={
				"parent": item.time_and_action,
				"completed": 0,
			},
			fields=["*"],
			order_by="idx asc",
			limit=1,
		)
		if pending:
			row = pending[0]
			row["colour"] = _attribute_value(item.colour)
			row["master"] = item.master
			row["process"] = True
			items.append(row)
		else:
			items.append(
				{
					"colour": _attribute_value(item.colour),
					"master": item.master,
					"action": "Completed",
					"department": None,
					"date": None,
					"rescheduled_date": None,
					"process": False,
				}
			)
	return items


def calculate_order_details(items, production_detail, packing_uom, final_uom):
	item_detail = frappe.get_cached_doc("YRP Item Production Detail", production_detail)
	final_list = []
	doc = frappe.get_cached_doc("Item", item_detail.item)
	dept_attr = None
	pack_stage = None
	if item_detail.dependent_attribute:
		pack_stage = _attribute_value(item_detail.pack_in_stage)
		dept_attr = item_detail.dependent_attribute
	uom_factor = get_uom_conversion_factor(doc.uoms, final_uom, packing_uom)
	final_qty = 0
	if item_detail.is_set_item:
		attrs = {}
		parts = []
		comb_dict = {}
		for attr in item_detail.set_item_combination_details:
			comb_dict.setdefault(_attribute_value(attr.major_attribute_value), {})
			comb_dict[_attribute_value(attr.major_attribute_value)].setdefault(
				_attribute_value(attr.set_item_attribute_value), _attribute_value(attr.attribute_value)
			)
			if _attribute_value(attr.set_item_attribute_value) not in parts:
				parts.append(_attribute_value(attr.set_item_attribute_value))
	x = 0
	if item_detail.is_set_item:
		major_part = _attribute_value(item_detail.major_attribute_value)
		for attr in item_detail.packing_attribute_details:
			for part in parts:
				colour = comb_dict[_attribute_value(attr.attribute_value)][part]
				item_list = []
				for item in items:
					variant = frappe.get_cached_doc("Item", item.item_variant)
					qty = item.qty * uom_factor
					if item_detail.auto_calculate:
						qty = qty / item_detail.packing_attribute_no
					else:
						qty = qty / item_detail.packing_combo
					attrs = {}
					for attribute in variant.attributes:
						attribute = attribute.as_dict()
						if attribute.attribute == dept_attr:
							attrs[attribute.attribute] = pack_stage
						else:
							attrs[attribute.attribute] = _attribute_value(attribute["attribute_value"])
					attrs[item_detail.packing_attribute] = colour
					attrs[item_detail.set_item_attribute] = part
					new_variant = get_or_create_variant(
						(variant.variant_of or variant.name),
						attrs,
						dependent_attr=item_detail.dependent_attribute_mapping,
					)
					temp_qty = (
						math.ceil(qty) if item_detail.auto_calculate else math.ceil(qty * attr.quantity)
					)
					if _attribute_value(item_detail.major_attribute_value) == part:
						final_qty += temp_qty
					d = {
						"item_variant": new_variant,
						"quantity": temp_qty,
						"row_index": x,
						"table_index": 0,
						"set_combination": {},
					}
					if part == major_part:
						d["set_combination"]["major_part"] = part
						d["set_combination"]["major_colour"] = colour
					else:
						d["set_combination"]["major_part"] = major_part
						d["set_combination"]["major_colour"] = comb_dict[
							_attribute_value(attr.attribute_value)
						][major_part]
					item_list.append(d)
				x = x + 1
				final_list = final_list + item_list
	else:
		for attr in item_detail.packing_attribute_details:
			item_list = []
			for item in items:
				variant = frappe.get_cached_doc("Item", item.item_variant)
				qty = item.qty * uom_factor
				if item_detail.auto_calculate:
					qty = qty / item_detail.packing_attribute_no
				else:
					qty = qty / item_detail.packing_combo
				attrs = {}
				for attribute in variant.attributes:
					attribute = attribute.as_dict()
					if attribute.attribute == dept_attr:
						attrs[attribute.attribute] = pack_stage
					else:
						attrs[attribute.attribute] = _attribute_value(attribute["attribute_value"])
				attrs[item_detail.packing_attribute] = _attribute_value(attr.attribute_value)
				new_variant = get_or_create_variant(
					(variant.variant_of or variant.name),
					attrs,
					dependent_attr=item_detail.dependent_attribute_mapping,
				)
				temp_qty = math.ceil(qty) if item_detail.auto_calculate else math.ceil(qty * attr.quantity)
				final_qty += temp_qty
				item_list.append(
					{
						"item_variant": new_variant,
						"quantity": temp_qty,
						"row_index": x,
						"table_index": 0,
						"set_combination": {"major_colour": _attribute_value(attr.attribute_value)},
					}
				)
			x = x + 1
			final_list = final_list + item_list

	return final_list, final_qty


def save_order_item_details(name, lot_order_details, item_details):
	item_details = update_if_string_instance(item_details)
	# pack_attr, set_attr, is_set = frappe.get_value("YRP Item Production Detail",name, ['packing_attribute', 'set_item_attribute', 'is_set_item'])
	qty_dict = {}
	for item in lot_order_details:
		set_comb = update_if_string_instance(item.set_combination)
		key = (item.item_variant, tuple(sorted(set_comb.items())))
		qty_dict[key] = {
			"cut_qty": item.cut_qty,
			"pack_qty": item.pack_qty,
			"stich_qty": item.stich_qty,
		}

	items = []
	row_index = 0
	table_index = -1
	for group in item_details:
		table_index += 1
		for item in group["items"]:
			item_name = item["name"]
			item_attributes = item["attributes"]
			for attr, values in item["values"].items():
				item1 = {}
				quantity = values.get("qty")
				if not quantity:
					quantity = 0
				item_attributes[item.get("primary_attribute")] = attr
				variant = get_or_create_variant(item_name, item_attributes)
				item1["item_variant"] = variant
				item1["quantity"] = quantity
				item1["row_index"] = row_index
				item1["table_index"] = 0
				set_comb = update_if_string_instance(item["item_keys"])
				key = (variant, tuple(sorted(set_comb.items())))
				item1["cut_qty"] = qty_dict[key]["cut_qty"]
				item1["pack_qty"] = qty_dict[key]["pack_qty"]
				item1["stich_qty"] = qty_dict[key]["stich_qty"]
				item1["set_combination"] = item["item_keys"]
				items.append(item1)
			row_index += 1
	return items


def save_item_details(item_details):
	item_details = update_if_string_instance(item_details)
	if len(item_details) == 0:
		return []
	item = item_details[0]
	items = []
	for id1, row in enumerate(item["items"]):
		if row["primary_attribute"]:
			attributes = row["attributes"]
			attributes[item["dependent_attribute"]] = item["final_state"]
			for id2, val in enumerate(row["values"].keys()):
				attributes[row["primary_attribute"]] = val
				item1 = {}
				variant_name = get_or_create_variant(item["item"], attributes)
				item1["item_variant"] = variant_name
				item1["qty"] = row["values"][val]["qty"]
				item1["ratio"] = row["values"][val]["ratio"]
				item1["mrp"] = row["values"][val]["mrp"]
				item1["table_index"] = id1
				item1["row_index"] = id2
				items.append(item1)
		else:
			item1 = {}
			attributes = row["attributes"]
			variant_name = item["item"]
			variant_name = get_or_create_variant(item["item"], attributes)
			item1["item_variant"] = variant_name
			item1["qty"] = row["values"]["qty"]
			item1["ratio"] = row["values"]["ratio"]
			item1["mrp"] = row["values"]["mrp"]
			item1["table_index"] = id1
			items.append(item1)
	return items


def fetch_item_details(items, production_detail):
	items = [item.as_dict() for item in items]
	if len(items) == 0:
		return
	dependent_attr_map_value = frappe.get_value(
		"YRP Item Production Detail", production_detail, "dependent_attribute_mapping"
	)
	grp_variant = get_parent_item(items[0]["item_variant"])
	variant_attr_details = get_attribute_details(grp_variant, dependent_attr_mapping=dependent_attr_map_value)
	primary_attr = variant_attr_details["primary_attribute"]
	uom = get_isfinal_uom(production_detail)["uom"]
	doc = frappe.get_cached_doc("Item", grp_variant)
	item_structure = get_item_details(
		grp_variant,
		attr_details=variant_attr_details,
		uom=uom,
		production_detail=production_detail,
		dependent_attr_mapping=dependent_attr_map_value,
	)

	for _key, variants in groupby(items, lambda i: i["table_index"]):
		variants = list(variants)
		item1 = {}
		values = {}
		for variant in variants:
			current_variant = frappe.get_cached_doc("Item", variant["item_variant"])
			item_attribute_details = get_item_attribute_details(current_variant, variant_attr_details)
			if doc.dependent_attribute and doc.dependent_attribute in item_attribute_details:
				del item_attribute_details[doc.dependent_attribute]
			if doc.primary_attribute:
				for attr in current_variant.attributes:
					if attr.attribute == primary_attr:
						values[_attribute_value(attr.attribute_value)] = {
							"qty": variant["qty"],
							"ratio": variant["ratio"],
							"mrp": variant["mrp"],
						}
						break
			else:
				values["qty"] = variant["qty"]
				values["ratio"] = variant["ratio"]
				values["mrp"] = variant["mrp"]
		attrs = {}
		for item in item_structure["attributes"]:
			if item in item_attribute_details:
				attrs[item] = item_attribute_details[item]

		item1["primary_attribute"] = primary_attr or None
		item1["attributes"] = attrs
		item1["values"] = values
		item_structure["items"].append(item1)
	return item_structure


@frappe.whitelist()
def fetch_order_item_details(items, production_detail, process=None, includes_packing: bool = False):
	ipd_doc = frappe.get_doc("YRP Item Production Detail", production_detail)
	items = update_if_string_instance(items)

	field = "quantity"
	if process:
		prs_doc = frappe.get_cached_doc("YRP Process", process)
		if prs_doc.is_group:
			for prs in prs_doc.process_details:
				process = prs.process_name
				break

		field = (
			"quantity"
			if process == ipd_doc.cutting_process
			else "cut_qty"
			if process == ipd_doc.stiching_process
			else "stich_qty"
			if process == ipd_doc.packing_process
			else None
		)
		if includes_packing:
			field = "cut_qty"
		if not field:
			stage = None
			for prs in ipd_doc.ipd_processes:
				if prs.process_name == process:
					stage = prs.stage
					break
			if stage:
				field = (
					"cut_qty"
					if stage == _attribute_value(ipd_doc.stiching_in_stage)
					else "stich_qty"
					if stage == _attribute_value(ipd_doc.pack_in_stage)
					else "pack_qty"
				)

		if not field:
			frappe.msgprint(f"Please Mention Process {process} in IPD")
			return
	return build_order_item_details(items, ipd_doc, field)


def build_order_item_details(items, ipd_doc, field="quantity"):
	"""Group order rows into the CutPlanItems matrix using `field` as the quantity."""
	return build_order_item_stages(items, ipd_doc, (field,))[field]


def build_order_item_stages(items, ipd_doc, fields):
	"""Share the matrix structure while keeping each stage's quantities separate."""
	from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

	items = [item.as_dict() for item in items]
	item_details = []
	items = sorted(items, key=lambda i: i["row_index"])
	primary_values = get_ipd_primary_values(ipd_doc.name)
	for _key, variants in groupby(items, lambda i: i["row_index"]):
		variants = list(variants)
		current_variant = frappe.get_cached_doc("Item", variants[0]["item_variant"])
		current_item_attribute_details = get_attribute_details(
			current_variant.variant_of or current_variant.name
		)
		item = {
			"name": (current_variant.variant_of or current_variant.name),
			"attributes": get_item_attribute_details(current_variant, current_item_attribute_details),
			"item_keys": {},
			"is_set_item": ipd_doc.is_set_item,
			"set_attr": ipd_doc.set_item_attribute,
			"pack_attr": ipd_doc.packing_attribute,
			"major_attr_value": _attribute_value(ipd_doc.major_attribute_value),
			"primary_attribute": current_item_attribute_details["primary_attribute"],
			"dependent_attribute": current_item_attribute_details["dependent_attribute"],
			"dependent_attribute_details": current_item_attribute_details["dependent_attribute_details"],
			"values": {},
		}
		current_item_attribute_details["primary_attribute_values"] = primary_values
		if item["primary_attribute"]:
			for attr in current_item_attribute_details["primary_attribute_values"]:
				item["values"][attr] = {"qty": dict.fromkeys(fields, 0)}
			for variant in variants:
				set_combination = update_if_string_instance(variant.set_combination)
				if set_combination:
					if set_combination.get("major_part"):
						item["item_keys"]["major_part"] = set_combination.get("major_part")

					if set_combination.get("major_colour"):
						item["item_keys"]["major_colour"] = set_combination.get("major_colour")

				current_variant = frappe.get_cached_doc("Item", variant["item_variant"])
				for attr in current_variant.attributes:
					if attr.attribute == item.get("primary_attribute"):
						item["values"][_attribute_value(attr.attribute_value)] = {
							"qty": {field: getattr(variant, field, 0) for field in fields},
						}
						break
		else:
			item["values"]["default"] = {
				"qty": {field: getattr(variants[0], field, 0) for field in fields},
			}

		index = get_item_group_index(item_details, current_item_attribute_details)
		if index == -1:
			item_details.append(
				{
					"attributes": current_item_attribute_details["attributes"],
					"primary_attribute": current_item_attribute_details["primary_attribute"],
					"primary_attribute_values": current_item_attribute_details["primary_attribute_values"],
					"dependent_attribute": current_item_attribute_details["dependent_attribute"],
					"dependent_attribute_details": current_item_attribute_details[
						"dependent_attribute_details"
					],
					"additional_parameters": current_item_attribute_details["additional_parameters"],
					"stiching_attribute": ipd_doc.stiching_attribute,
					"items": [item],
				}
			)
		else:
			item_details[index]["items"].append(item)
	stages = {}
	for field in fields:
		stage = deepcopy(item_details)
		for item in stage:
			size_wise_total = {}
			total_sum = 0
			for row in item["items"]:
				sum = 0
				for val in row["values"]:
					row["values"][val]["qty"] = row["values"][val]["qty"][field]
					size_wise_total.setdefault(val, 0)
					size_wise_total[val] += row["values"][val]["qty"]
					sum += row["values"][val]["qty"]
				row["total_qty"] = sum
				total_sum += sum
			item["size_wise_total"] = size_wise_total
			item["total_sum"] = total_sum

		stages[field] = stage
	return stages

def get_quantity(attr, packing_attribute_details):
	for item in packing_attribute_details:
		if _attribute_value(item.attribute_value) == attr:
			return item.quantity


def get_item_attribute_details(variant, item_attributes):
	attribute_details = {}
	for attr in variant.attributes:
		if attr.attribute in item_attributes["attributes"]:
			attribute_details[attr.attribute] = _attribute_value(attr.attribute_value)
	return attribute_details


def variant_attribute_details(variant):
	attribute_details = {}
	for attr in variant.attributes:
		attribute_details[attr.attribute] = _attribute_value(attr.attribute_value)
	return attribute_details


@frappe.whitelist()
def get_item_details(
	item_name,
	attr_details=None,
	uom=None,
	production_detail=None,
	dependent_state=None,
	dependent_attr_mapping=None,
	ppo=None,
):
	from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

	if not attr_details:
		item = get_attribute_details(item_name, dependent_attr_mapping=dependent_attr_mapping)
	else:
		item = attr_details
	pack_out_stage = attribute_db.get_value("YRP Item Production Detail", production_detail, "pack_out_stage")
	if uom:
		item["default_uom"] = uom
	final_state = None
	final_state_attr = None
	item["items"] = []
	if item["dependent_attribute"]:
		attribute = dependent_state if dependent_state else pack_out_stage
		for attr in item["dependent_attribute_details"]["attr_list"]:
			if attr == attribute:
				final_state = attribute
				final_state_attr = item["dependent_attribute_details"]["attr_list"][attr]["attributes"]
				break
		if not final_state:
			frappe.msgprint("There is no final state for this item")
			return []
		item["final_state"] = final_state
		if item["primary_attribute"] in final_state_attr:
			final_state_attr.remove(item["primary_attribute"])
		item["final_state_attr"] = final_state_attr

	elif not item["dependent_attribute"] and not item["primary_attribute"]:
		doc = frappe.get_cached_doc("Item", item["item"])
		final_state_attr = []
		x = [attr.attribute for attr in doc.attributes]
		final_state_attr = final_state_attr + x
		item["final_state_attr"] = final_state_attr

	if production_detail:
		pack_attr_value = frappe.get_value(
			"YRP Item Production Detail", production_detail, "packing_attribute"
		)
		item["packing_attr"] = pack_attr_value
		item["primary_attribute_values"] = get_ipd_primary_values(production_detail)
		if ppo:
			primary = frappe.get_value(
				"YRP Item Production Detail", production_detail, "primary_item_attribute"
			)
			ppo_doc = frappe.get_doc("YRP Production Order", ppo)
			d = {
				"primary_attribute": primary,
				"attributes": {},
				"values": {},
			}
			values = {}
			for row in ppo_doc.production_order_details:
				attrs = get_variant_attr_details(row.item_variant)
				values.setdefault(attrs[primary], {"qty": row.quantity, "ratio": row.ratio, "mrp": row.mrp})
			for row in ppo_doc.production_ordered_details:
				attrs = get_variant_attr_details(row.item_variant)
				values[attrs[primary]]["qty"] -= row.quantity
			for value in values.values():
				# Lots may exceed the PPO; never suggest a negative remaining quantity.
				value["qty"] = max(flt(value["qty"]), 0)
			d["values"] = values
			item["items"].append(d)

	return item


@frappe.whitelist()
def get_isfinal_uom(item_production_detail, get_pack_stage=None):
	uom = None
	doc = frappe.get_doc("YRP Item Production Detail", item_production_detail)
	if doc.dependent_attribute_mapping:
		attribute_details = get_dependent_attribute_details(doc.dependent_attribute_mapping)
		for attr in attribute_details["attr_list"]:
			if attr == _attribute_value(doc.pack_out_stage):
				uom = attribute_details["attr_list"][attr]["uom"]
				break
	else:
		item = doc.item
		item_doc = frappe.get_cached_doc("Item", item)
		uom = item_doc.stock_uom

	if get_pack_stage:
		pack_in_stage = _attribute_value(doc.pack_in_stage)
		pack_out_stage = _attribute_value(doc.pack_out_stage)
		if doc.dependent_attribute_mapping:
			attribute_details = get_dependent_attribute_details(doc.dependent_attribute_mapping)
			return {
				"uom": uom,
				"pack_in_stage": pack_in_stage,
				"pack_out_stage": pack_out_stage,
				"packing_uom": attribute_details["attr_list"][pack_in_stage]["uom"] or uom,
				"dependent_attr_mapping": doc.dependent_attribute_mapping,
				"tech_pack_version": doc.tech_pack_version,
				"pattern_version": doc.pattern_version,
				"packing_combo": doc.packing_combo,
			}
	return {
		"uom": uom,
	}


def get_uom_conversion_factor(uoms, from_uom, to_uom):
	if not to_uom:
		to_uom = from_uom
	to_uom_factor = None
	from_uom_factor = None
	for item in uoms:
		if item.uom == from_uom:
			from_uom_factor = item.conversion_factor
		if item.uom == to_uom:
			to_uom_factor = item.conversion_factor
	return from_uom_factor / to_uom_factor


@frappe.whitelist()
def get_dict_object(data):
	if isinstance(data, string_types):
		data = json.loads(data)
	return data


@frappe.whitelist()
def combine_child_tables(table1, table2):
	table = table1 + table2
	tab_list = []
	for row in table:
		tab_list.append(row.as_dict())
	return tab_list


@frappe.whitelist()
def get_attributes(data):
	grp_variant_doc = frappe.get_cached_doc("Item", data[0].item_variant)
	grp_item = get_parent_item(grp_variant_doc.name)
	dept_attr = frappe.get_value("Item", grp_item, "dependent_attribute")
	attribute_list = []
	for attrs in grp_variant_doc.attributes:
		if attrs.attribute != dept_attr:
			attribute_list.append(attrs.attribute)
	attribute_list = [*attribute_list, "Ratio", "MRP"]

	attr_list = []
	for item in data:
		item = item.as_dict()
		doc = frappe.get_cached_doc("Item", item["item_variant"])
		temp_attr = {}
		for attr in doc.attributes:
			if attr.attribute != dept_attr:
				temp_attr[attr.attribute] = _attribute_value(attr.attribute_value)
		temp_attr["Ratio"] = item["ratio"]
		temp_attr["MRP"] = item["mrp"]
		attr_list.append(temp_attr)
	return attribute_list, attr_list


@frappe.whitelist()
def get_packing_attributes(ipd):
	ipd_doc = frappe.get_doc("YRP Item Production Detail", ipd)
	major_colours = []
	sizes = ""
	ratios = []
	combo = None
	colour_dict_list = []
	if ipd_doc.auto_calculate:
		combo = ipd_doc.packing_attribute_no

	for item in ipd_doc.packing_attribute_details:
		major_colours.append(_attribute_value(item.attribute_value))
		colour_dict_list.append(
			{
				"colour": _attribute_value(item.attribute_value),
				"major_colour": _attribute_value(item.attribute_value),
			}
		)
		if not combo:
			ratios.append(ipd_doc.packing_combo / item.quantity)
	if ipd_doc.is_set_item:
		set_mapping = None
		for item in ipd_doc.item_attributes:
			if item.attribute == ipd_doc.set_item_attribute:
				set_mapping = item.mapping
				break
		set_map_doc = get_mapping_document(set_mapping)
		colour_combo_dict_list = []
		ratio_combo = []
		index = -1
		for colour in major_colours:
			index = index + 1
			for part in set_map_doc.values:
				colour_combo_dict_list.append(
					{
						"colour": str(colour) + "-" + str(_attribute_value(part.attribute_value)),
						"major_colour": colour,
					}
				)
				if not combo:
					ratio_combo.append(ratios[index])
		colour_dict_list = colour_combo_dict_list
		ratios = ratio_combo

	mapping = None
	for item in ipd_doc.item_attributes:
		if item.attribute == ipd_doc.primary_item_attribute:
			mapping = item.mapping
			break

	map_doc = get_mapping_document(mapping)
	for item in map_doc.values:
		sizes += _attribute_value(item.attribute_value) + ","

	return {
		"colour_combo": colour_dict_list,
		"sizes": sizes,
		"ratios": ratios,
		"combo": combo,
		"major_colours": major_colours,
	}


@frappe.whitelist()
def update_order_details(doc_name):
	doc = frappe.get_doc("SD YRP Lot", doc_name)
	doc.check_permission("write")
	if doc.get("lot_time_and_action_details"):
		frappe.throw("Order Items cannot be recalculated after Time and Action is created.")
	doc.calculate_order()
	doc.save()


@frappe.whitelist()
def get_mapping_details(ipd):
	ipd_doc = frappe.get_cached_doc("YRP Item Production Detail", ipd)
	bom_attribute_list = []
	for bom in ipd_doc.item_bom:
		if bom.attribute_mapping is not None:
			doc = frappe.get_cached_doc("YRP Item BOM Attribute Mapping", bom.attribute_mapping)
			bom_attribute_list.append(
				{
					"bom_item": bom.item,
					"bom_attr_mapping_link": bom.attribute_mapping,
					"bom_attr_mapping_based_on": bom.based_on_attribute_mapping,
					"bom_attr_mapping_list": doc.values,
					"doctype": "YRP Item BOM Attribute Mapping",
					"qty": bom.qty_of_bom_item,
				}
			)

	map_dict = {}
	for mapping in bom_attribute_list:
		bom_qty = mapping.get("qty")
		bom_item = mapping.get("bom_item")
		mapping = mapping.get("bom_attr_mapping_list")
		data = []
		for d in mapping:
			x = d.index
			if len(data) <= d.index:
				while x >= 0:
					x = x - 1
					data.append({"item": [], "bom": [], "quantity": 0})
			if d.type == "item":
				data[d.index]["item"].append(_attribute_value(d.attribute_value))
			elif d.type == "bom":
				data[d.index]["bom"].append(_attribute_value(d.attribute_value))
			qty = d.quantity
			if d.quantity == 0:
				qty = bom_qty
			data[d.index]["quantity"] = qty

		i = 0
		while i < len(data):
			if data[i] is None:
				data.splice(i, 1)
			else:
				i = i + 1
		items = "\n"
		for d in data:
			if d.get("item"):
				item_str = ", ".join(d["item"])
				bom_str = ", ".join(d["bom"])
				items += f"{item_str} -> {bom_str} / {d['quantity']}<br>"
		if bom_item not in map_dict:
			map_dict[bom_item] = items
		else:
			map_dict[bom_item] += items
	return map_dict


@frappe.whitelist()
def get_ipd_print_accessory_combination(ipd):
	ipd_doc = frappe.get_cached_doc("YRP Item Production Detail", ipd)
	stiching_accessory_json = update_if_string_instance(ipd_doc.stiching_accessory_json)
	items = {}
	if ipd_doc.is_set_item:
		for row in stiching_accessory_json["items"]:
			items.setdefault(row[ipd_doc.set_item_attribute], {})
			colour_key = row["major_colour"]
			if row.get("major_attr_value"):
				colour_key += "(" + row["major_attr_value"] + ")"

			items[row[ipd_doc.set_item_attribute]].setdefault(colour_key, {})
			items[row[ipd_doc.set_item_attribute]][colour_key].setdefault(row["accessory"], {})
			items[row[ipd_doc.set_item_attribute]][colour_key][row["accessory"]] = {
				"colour": row["accessory_colour"],
				"cloth_type": row["cloth_type"],
			}
	else:
		for row in stiching_accessory_json["items"]:
			items.setdefault(row["major_colour"], {})
			items[row["major_colour"]].setdefault(row["accessory"], {})
			items[row["major_colour"]][row["accessory"]] = {
				"colour": row["accessory_colour"],
				"cloth_type": row["cloth_type"],
			}
	return items


def get_ironing_mistake_pf_items(lot):
	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	items = fetch_order_item_details(lot_doc.lot_order_details, lot_doc.production_detail)
	return items


@frappe.whitelist()
def get_ocr_details(lot):
	with attribute_read_scope():
		return _read_get_ocr_details(lot)


def _read_get_ocr_details(lot):
	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("read")
	lot_dict = {}
	wo_list = frappe.get_all(
		"YRP Work Order",
		filters={
			"lot": lot,
			"docstatus": 1,
		},
		pluck="name",
		order_by="creation",
	)

	ipd, _item = frappe.get_value("SD YRP Lot", lot, ["production_detail", "item"])
	lot_dict["sizes"] = []
	lot_dict["processes"] = {}
	lot_dict["dispatch_detail"] = {}
	lot_dict["total_dispatch"] = 0
	lot_dict["finishing_plan_list"] = []
	if not ipd:
		return lot_dict
	_sewing, primary, pcs_per_box = frappe.get_value(
		"YRP Item Production Detail", ipd, ["stiching_process", "primary_item_attribute", "packing_combo"]
	)
	includes_packing_process = None
	work_orders = {}
	restricted = False
	for wo in wo_list:
		wo_doc = frappe.get_lazy_doc("YRP Work Order", wo)
		work_orders[wo] = wo_doc
		if wo_doc.includes_packing:
			includes_packing_process = wo_doc.process_name
		if not _ocr_can_read(wo_doc):
			restricted = True
			continue
		cutting_plans = frappe.get_all(
			"SD YRP Cutting Plan",
			filters={"work_order": wo},
			pluck="name",
		)
		cutting_plans = [
			name for name in cutting_plans
			if frappe.session.user == "Administrator" or _ocr_can_read(frappe.get_doc("SD YRP Cutting Plan", name))
		]
		lot_dict["processes"].setdefault(
			wo_doc.process_name,
			{
				"wo_list": [],
				"cp_list": [],
				"data": {},
				"total_sent": 0,
				"total_received": 0,
			},
		)
		lot_dict["processes"][wo_doc.process_name]["cp_list"].extend(cutting_plans)
		lot_dict["processes"][wo_doc.process_name]["wo_list"].append(wo)
		for row in wo_doc.work_order_calculated_items:
			attr_details = get_variant_attr_details(row.item_variant)
			size = attr_details[primary]
			if size not in lot_dict["sizes"]:
				lot_dict["sizes"].append(size)
			lot_dict["processes"][wo_doc.process_name]["data"].setdefault(
				size,
				{
					"sent": 0,
					"received": 0,
				},
			)
			lot_dict["processes"][wo_doc.process_name]["data"][size]["sent"] += row.delivered_quantity
			lot_dict["processes"][wo_doc.process_name]["total_sent"] += row.delivered_quantity
			if not wo_doc.includes_packing:
				lot_dict["processes"][wo_doc.process_name]["data"][size]["received"] += row.received_qty
				lot_dict["processes"][wo_doc.process_name]["total_received"] += row.received_qty

	grn_list = []
	if includes_packing_process:
		grn_filters = {
			"against": "YRP Work Order",
			"docstatus": 1,
			"process_name": includes_packing_process,
			"lot": lot,
		}
		# The yrp/essdee GRN may not carry production_api's includes_packing / is_return
		# columns — only add those filters when the field actually exists.
		_grn_meta = frappe.get_meta("YRP Goods Received Note")
		if _grn_meta.has_field("includes_packing"):
			grn_filters["includes_packing"] = 1
		if _grn_meta.has_field("is_return"):
			grn_filters["is_return"] = 0
		grn_list = frappe.get_all("YRP Goods Received Note", filters=grn_filters, pluck="name")

	grn_item_dict = {}
	for grn in grn_list:
		grn_doc = frappe.get_lazy_doc("YRP Goods Received Note", grn)
		if frappe.session.user != "Administrator":
			source = grn_doc.against_id
			if not source:
				restricted = True
				continue
			if source not in work_orders:
				try:
					work_orders[source] = frappe.get_lazy_doc("YRP Work Order", source)
				except frappe.DoesNotExistError:
					work_orders[source] = None
			if not work_orders[source] or not _ocr_can_read(work_orders[source]):
				restricted = True
				continue
		dynamic_packing = cint(grn_doc.get("packing_calculation_version")) >= 2
		for row in grn_doc.items:
			grn_item_dict.setdefault(row.item_variant, 0)
			grn_item_dict[row.item_variant] += (
				flt(row.quantity) if dynamic_packing else flt(row.quantity) * flt(pcs_per_box)
			)

	for variant in grn_item_dict:
		if restricted and includes_packing_process not in lot_dict["processes"]:
			continue
		attr_details = get_variant_attr_details(variant)
		size = attr_details[primary]
		if restricted and size not in lot_dict["processes"].get(includes_packing_process, {}).get("data", {}):
			continue
		lot_dict["processes"][includes_packing_process]["total_received"] += grn_item_dict[variant]
		lot_dict["processes"][includes_packing_process]["data"][size]["received"] += grn_item_dict[
			variant
		]

	finishing_plan_list = frappe.get_all(
		"SD YRP Finishing Plan",
		filters={"lot": lot},
		pluck="name",
	)
	for finishing_plan in finishing_plan_list:
		finishing_doc = frappe.get_lazy_doc("SD YRP Finishing Plan", finishing_plan)
		if not _ocr_can_read(finishing_doc):
			continue
		lot_dict["finishing_plan_list"].append(finishing_plan)
		batch_tracked_packing = bool(
			finishing_doc.work_order
			and frappe.db.exists(
				"YRP Goods Received Note",
				{
					"against": "YRP Work Order",
					"against_id": finishing_doc.work_order,
					"docstatus": 1,
					"is_return": 0,
					"packing_calculation_version": [">=", 1],
				},
			)
		)
		dispatch_multiplier = 1 if batch_tracked_packing else flt(finishing_doc.pieces_per_box)
		for row in finishing_doc.finishing_plan_grn_details:
			attr_details = get_variant_attr_details(row.item_variant)
			size = attr_details[primary]
			if size not in lot_dict["sizes"]:
				lot_dict["sizes"].append(size)
			dispatched = flt(row.dispatched) * dispatch_multiplier
			lot_dict["dispatch_detail"].setdefault(size, 0)
			lot_dict["dispatch_detail"][size] += dispatched
			lot_dict["total_dispatch"] += dispatched

	return lot_dict


def _ocr_can_read(doc):
	return frappe.session.user == "Administrator" or frappe.has_permission(doc.doctype, "read", doc=doc)


# @frappe.whitelist()
# def get_cad_detail(ipd, lot):
# 	ipd_doc = frappe.get_doc("YRP Item Production Detail", ipd)
# 	lot_doc = frappe.get_doc("SD YRP Lot", lot)
# 	colour_qty = {}
# 	for row in lot_doc.lot_order_details:
# 		attr_details = get_variant_attr_details(row.item_variant)
# 		c = attr_details[ipd_doc.packing_attribute]
# 		colour_qty.setdefault(c, 0)
# 		colour_qty[c] += row.quantity

# 	d = {}
# 	d[ipd_doc.item] = {}
# 	categories = []
# 	category_panel = {}
# 	for panel in ipd_doc.stiching_item_details:
# 		if panel.category not in categories:
# 			categories.append(panel.category)
# 		category_panel.setdefault(panel.category, [])
# 		category_panel[panel.category].append(panel.stiching_attribute_value)

# 	panel_colour_comb = get_panel_colour_combination(ipd_doc)
# 	for colour in ipd_doc.packing_attribute_details:
# 		d[ipd_doc.item][colour.attribute_value] = {
# 			"qty": colour_qty[colour.attribute_value],
# 			"categories": {},
# 		}
# 		for cat in categories:
# 			panel = category_panel[cat][0]
# 			panel_colour = panel_colour_comb[colour.attribute_value][panel]
# 			d[ipd_doc.item][colour.attribute_value]["categories"][cat] = {
# 				"colour": panel_colour,
# 				"reqd_weight": 0,
# 				"actual_weight": 0,
# 				"reqd_gsm": 0,
# 				"actual_gsm": 0,
# 				"reqd_total": 0,
# 				"actual_reqd": 0,
# 				"category_panels": category_panel[cat],
# 			}
# 	return d


def get_consumption_sheet_data(ipd, lot):
	doc = frappe.get_doc("SD YRP Lot", lot)
	cad_data = update_if_string_instance(doc.cad_detail_data)
	item = doc.item
	ipd_doc = frappe.get_doc("YRP Item Production Detail", ipd)
	x = 0
	total_gsm = 0
	for row in ipd_doc.cloth_detail:
		x += 1
		total_gsm += row.required_gsm

	cut_attrs = []
	for row in ipd_doc.cutting_attributes:
		cut_attrs.append(row.attribute)

	pack_attr = ipd_doc.packing_attribute
	stich_attr = ipd_doc.stiching_attribute
	primary_attr = ipd_doc.primary_item_attribute
	## find every panel weight
	cut_json = update_if_string_instance(ipd_doc.cutting_items_json)
	panel_weight = {}
	length = len(ipd_doc.stiching_item_details)
	panel_colour_comb = get_panel_colour_combination(ipd_doc)
	direct_panel_weight = {}
	colour_panel_weight = {}

	if stich_attr in cut_attrs and len(cut_attrs) == 1:
		for row in cut_json["items"]:
			direct_panel_weight[row[stich_attr]] = row["Weight"]

	elif pack_attr in cut_attrs and len(cut_attrs) == 1:
		for row1 in cut_json["items"]:
			panel_weight.setdefault(row1[pack_attr], {})
			weight = row1["Weight"] / length
			for row2 in ipd_doc.stiching_item_details:
				panel_weight[row1[pack_attr]][_attribute_value(row2.stiching_attribute_value)] = weight

	elif primary_attr in cut_attrs and len(cut_attrs) == 1:
		count = 0
		tot_weight = 0
		for row in cut_json["items"]:
			tot_weight += row["Weight"]
			count += 1
		avg_weight = tot_weight / count
		weight = avg_weight / length
		for row in ipd_doc.stiching_item_details:
			direct_panel_weight[_attribute_value(row.stiching_attribute_value)] = weight

	elif stich_attr in cut_attrs and primary_attr in cut_attrs and len(cut_attrs) == 2:
		panel_sum = {}
		for row in cut_json["items"]:
			panel_sum.setdefault(
				row[stich_attr],
				{
					"count": 0,
					"tot_weight": 0,
					"avg_weight": 0,
				},
			)
			panel_sum[row[stich_attr]]["count"] += 1
			panel_sum[row[stich_attr]]["tot_weight"] += row["Weight"]

		for panel in panel_sum:
			panel_sum[panel]["avg_weight"] = panel_sum[panel]["tot_weight"] / panel_sum[panel]["count"]

		for row in ipd_doc.stiching_item_details:
			direct_panel_weight[_attribute_value(row.stiching_attribute_value)] = panel_sum[
				_attribute_value(row.stiching_attribute_value)
			]["avg_weight"]

	elif stich_attr in cut_attrs and pack_attr in cut_attrs and len(cut_attrs) == 2:
		panel_sum = {}
		for row in cut_json["items"]:
			colour_panel_weight.setdefault(row[stich_attr], {})
			colour_panel_weight[row[stich_attr]][row[pack_attr]] = row["Weight"]

	elif pack_attr in cut_attrs and primary_attr in cut_attrs and len(cut_attrs) == 2:
		colour_sum = {}
		for row in cut_json["items"]:
			colour_sum.setdefault(
				row[pack_attr],
				{
					"count": 0,
					"tot_weight": 0,
					"avg_weight": 0,
				},
			)
			colour_sum[row[pack_attr]]["count"] += 1
			colour_sum[row[pack_attr]]["tot_weight"] += row["Weight"]

		for colour in colour_sum:
			colour_sum[colour]["avg_weight"] = colour_sum[colour]["tot_weight"] / colour_sum[colour]["count"]

		for row1 in ipd_doc.packing_attribute_details:
			panel_weight.setdefault(_attribute_value(row1.attribute_value), {})
			weight = colour_sum[_attribute_value(row1.attribute_value)]["avg_weight"] / length
			for row2 in ipd_doc.stiching_item_details:
				panel_weight[row1[pack_attr]][_attribute_value(row2.stiching_attribute_value)] = weight

	elif (
		pack_attr in cut_attrs
		and primary_attr in cut_attrs
		and stich_attr in cut_attrs
		and len(cut_attrs) == 3
	):
		panel_sum = {}
		for row in cut_json["items"]:
			panel_sum.setdefault(row[stich_attr], {})
			panel_sum[row[stich_attr]].setdefault(
				row[pack_attr], {"tot_weight": 0, "count": 0, "avg_weight": 0}
			)
			panel_sum[row[stich_attr]][row[pack_attr]]["tot_weight"] += row["Weight"]
			panel_sum[row[stich_attr]][row[pack_attr]]["count"] += 1

		for panel in panel_sum:
			for colour in panel_sum[panel]:
				panel_sum[panel][colour]["avg_weight"] = (
					panel_sum[panel][colour]["tot_weight"] / panel_sum[panel][colour]["count"]
				)

		for panel in panel_sum:
			for colour in panel_sum[panel]:
				colour_panel_weight.setdefault(panel, {})
				colour_panel_weight[panel][colour] = panel_sum[panel][colour]["avg_weight"]

	colour_comb = {}

	for colour in panel_colour_comb:
		colour_comb.setdefault(colour, {})
		for panel in panel_colour_comb[colour]:
			colour_comb[colour][panel] = {
				"colour": panel_colour_comb[colour][panel],
				"weight": 0,
			}
	if panel_weight:
		for mj_colour in panel_weight:
			for panel in panel_weight[mj_colour]:
				colour_comb[mj_colour][panel]["weight"] = panel_weight[mj_colour][panel]
	elif direct_panel_weight:
		for colour in colour_comb:
			for panel in colour_comb[colour]:
				colour_comb[colour][panel]["weight"] = direct_panel_weight[panel]
	else:
		for colour in colour_comb:
			for panel in colour_comb[colour]:
				colour_comb[colour][panel]["weight"] = colour_panel_weight[panel][
					_attribute_value(colour_comb[colour][panel]["colour"])
				]

	for colour in cad_data[item]:
		for cat in cad_data[item][colour]["categories"]:
			cad_data[item][colour]["categories"][cat]["reqd_gsm"] = 0
			weight = 0
			for panel in cad_data[item][colour]["categories"][cat]["category_panels"]:
				weight += colour_comb[colour][panel]["weight"]
			cad_data[item][colour]["categories"][cat]["reqd_weight"] = weight
			cad_data[item][colour]["categories"][cat]["total_reqd"] = weight * cad_data[item][colour]["qty"]


@frappe.whitelist()
def check_enabled_po():
	return frappe.db.get_single_value("SD YRP MRP Settings", "enable_production_order")


def _get_lot_variant_demands(lot_doc):
	return [
		{
			"item_variant": row.item_variant,
			"qty": flt(row.quantity),
		}
		for row in lot_doc.get("lot_order_details") or []
		if row.item_variant and flt(row.quantity) > 0
	]


def _build_lot_bom_rows(calculation):
	"""Convert the generic YRP engine response into Essdee's Lot BOM rows."""
	aggregated = {}
	for section in ("major_deliverables", "accessories"):
		for row in calculation.get(section) or []:
			required_qty = flt(row.get("required_qty"))
			if required_qty <= 0:
				continue

			item_variant = row.get("item_variant")
			process_name = row.get("process_name")
			uom = row.get("uom")
			if not item_variant:
				frappe.throw(f"Calculated {section} row is missing Item Variant.")
			if not process_name:
				frappe.throw(
					f"Please mention Process for BOM item {item_variant} in the Item Production Detail."
				)
			if not uom:
				frappe.throw(f"Calculated BOM item {item_variant} is missing UOM.")

			key = (item_variant, process_name, uom)
			aggregated.setdefault(
				key,
				{
					"item_name": item_variant,
					"process_name": process_name,
					"uom": uom,
					"required_qty": 0.0,
				},
			)
			aggregated[key]["required_qty"] += required_qty

	return list(aggregated.values())


def _build_bom_summary_json(lot_doc, rows):
	"""Keep the legacy print payload in sync with the matrix-backed rows.

	The generic calculator returns final quantities rather than the old entered
	product/BOM ratio. Derive an equivalent per-unit ratio from the Lot demand so
	existing Lot BOM and consumption print formats remain useful.
	"""
	total_quantity = flt(lot_doc.total_order_quantity)
	product_uom = lot_doc.uom or ""
	summary = {}
	for row in rows:
		key = row["item_name"]
		if key in summary:
			key = f"{key} · {row['process_name']}"
		if key in summary:
			key = f"{key} · {row['uom']}"
		ratio = row["required_qty"] / total_quantity if total_quantity else 0
		summary[key] = [
			row["process_name"],
			1,
			product_uom,
			ratio,
			row["uom"],
			row["required_qty"],
		]
	return summary


@frappe.whitelist()
def calculate_bom(lot_name):
	"""Calculate and persist a Lot BOM through YRP's common IPD matrix engine."""
	lot_doc = frappe.get_doc("SD YRP Lot", lot_name)
	lot_doc.check_permission("write")
	if lot_doc.docstatus != 0:
		frappe.throw("BOM can only be recalculated while the Lot is in Draft.")
	if not lot_doc.production_detail:
		frappe.throw("Please mention Item Production Detail before calculating BOM.")

	variant_demands = _get_lot_variant_demands(lot_doc)
	if not variant_demands:
		frappe.throw("Please calculate Lot Order Details with a Qty greater than zero first.")

	# The base calculator owns generic matrix inputs. Essdee's legacy garment
	# packing stages alter accessory ratios, so replace only that section with
	# the company-specific adapter before persisting the Lot result. Resolve the
	# Essdee rows first so an incomplete migrated mapping fails before the base
	# engine can attempt to resolve an unintended Item Variant.
	essdee_accessories = calculate_essdee_accessory_bom(
		lot_doc.production_detail,
		variant_demands,
		lot_doc,
	)
	calculation = calculate_bom_for_variant_demands(
		lot_doc.production_detail,
		variant_demands,
	)
	calculation["accessories"] = essdee_accessories
	bom_rows = _build_lot_bom_rows(calculation)
	if not bom_rows:
		frappe.throw("The IPD Process Matrix and Item BOM did not produce any BOM rows.")

	lot_doc.set("bom_summary", bom_rows)
	lot_doc.set("bom_summary_json", _build_bom_summary_json(lot_doc, bom_rows))
	lot_doc.last_calculated_time = now_datetime()
	lot_doc.save()

	return {
		"bom_summary": bom_rows,
		"last_calculated_time": lot_doc.last_calculated_time,
	}


Lot = SDYRPLot


def preserve_lot_fabric_conversions(lot_doc):
	"""Prevent stale Desk saves from deleting GRN-owned conversion rows."""
	if lot_doc.is_new() or not lot_doc.meta.get_field("lot_fabric_conversions"):
		return
	rows = frappe.db.sql(
		"""
		SELECT *
		FROM `tabSD YRP Lot Fabric Conversion`
		WHERE parent = %(parent)s
			AND parenttype = 'SD YRP Lot'
			AND parentfield = 'lot_fabric_conversions'
		ORDER BY idx, creation, name
		FOR UPDATE
		""",
		{"parent": lot_doc.name},
		as_dict=True,
	)
	lot_doc.set("lot_fabric_conversions", [])
	for values in rows:
		row = lot_doc.append("lot_fabric_conversions", {})
		row.update(values)

import json
from itertools import groupby, zip_longest

import frappe
from frappe.utils import cint

from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item_dependent_attribute_mapping.item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)


def onload(doc, method=None):
	load_attribute_list(doc)
	load_bom_attribute_list(doc)
	load_dependent_attribute(doc)

	set_items = fetch_combination_items(doc.get("set_item_combination_details") or [])
	if len(set_items["values"]) > 0:
		doc.set_onload("set_item_detail", set_items)

	stich_items = fetch_combination_items(doc.get("stiching_item_combination_details") or [])
	if len(stich_items["values"]) > 0:
		doc.set_onload("stiching_item_detail", stich_items)


def load_attribute_list(doc):
	attribute_list = []
	for attribute in doc.get("item_attributes") or []:
		if not attribute.attribute:
			continue
		attribute_doc = frappe.get_cached_doc("Item Attribute", attribute.attribute)
		if attribute_doc.numeric_values:
			continue

		values = []
		if attribute.mapping:
			mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", attribute.mapping)
			values = mapping_doc.values

		attribute_list.append(
			{
				"name": attribute.name,
				"attr_name": attribute.attribute,
				"attr_values_link": attribute.mapping,
				"attr_values": values,
				"doctype": "Item Item Attribute Mapping",
			}
		)
	doc.set_onload("attr_list", attribute_list)


def load_bom_attribute_list(doc):
	bom_attribute_list = []
	for bom in doc.get("item_bom") or []:
		if not bom.attribute_mapping:
			continue
		mapping_doc = frappe.get_cached_doc("Item BOM Attribute Mapping", bom.attribute_mapping)
		bom_attribute_list.append(
			{
				"bom_item": bom.item,
				"bom_attr_mapping_link": bom.attribute_mapping,
				"bom_attr_mapping_based_on": bom.based_on_attribute_mapping,
				"bom_attr_mapping_list": mapping_doc.values,
				"doctype": "Item BOM Attribute Mapping",
			}
		)
	doc.set_onload("bom_attr_list", bom_attribute_list)


def load_dependent_attribute(doc):
	dependent_attribute = {}
	if doc.dependent_attribute and doc.dependent_attribute_mapping:
		dependent_attribute = get_dependent_attribute_details(doc.dependent_attribute_mapping)
	doc.set_onload("dependent_attribute", dependent_attribute)


@frappe.whitelist()
def get_complete_item_details(item_name):
	item = frappe.get_doc("Item", item_name).as_dict()

	from frappe.model import default_fields

	for attribute in item.get("attributes") or []:
		for fieldname in default_fields:
			attribute.pop(fieldname, None)
	return item


@frappe.whitelist()
def get_approval_roles():
	if frappe.db.exists("DocType", "MRP Settings"):
		settings = frappe.get_single("MRP Settings")
		return [
			role
			for role in [
				getattr(settings, "senior_merch_role", None),
				getattr(settings, "merchandising_manager_role", None),
			]
			if role
		]
	return ["System Manager"]


@frappe.whitelist()
def approve_ipd(doc_name, approval_type="Approved"):
	if approval_type not in ("Cutting Approved", "Approved"):
		frappe.throw("Invalid approval type")

	allowed_roles = get_approval_roles()
	if not any(role in frappe.get_roles() for role in allowed_roles):
		frappe.throw("You do not have permission to approve Item Production Detail")

	doc = frappe.get_doc("Item Production Detail", doc_name)
	doc.approval_status = approval_type
	doc.approved_by = frappe.session.user
	doc.save(ignore_permissions=True)
	return {"status": "success"}


@frappe.whitelist()
def revert_ipd_approval(doc_name):
	if "System Manager" not in frappe.get_roles():
		frappe.throw("Only System Manager can revert approval")

	doc = frappe.get_doc("Item Production Detail", doc_name)
	doc.approval_status = "Not Approved"
	doc.approved_by = None
	doc.save(ignore_permissions=True)
	return {"status": "success"}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_attribute_detail_values(doctype, txt, searchfield, start, page_len, filters):
	mapping = (filters or {}).get("mapping")
	if not mapping:
		return []

	rows = frappe.get_all(
		"Item Item Attribute Mapping Value",
		filters={"parent": mapping},
		fields=["attribute_value"],
		order_by="idx asc",
	)
	txt = (txt or "").lower()
	return [[row.attribute_value] for row in rows if row.attribute_value.lower().startswith(txt)]


@frappe.whitelist()
def get_ipd_item_group():
	if not frappe.db.exists("DocType", "IPD Settings"):
		return []
	item_group = frappe.db.get_single_value("IPD Settings", "item_group")
	if not item_group:
		return []
	if isinstance(item_group, list):
		return item_group
	return [item_group]


@frappe.whitelist()
def get_attribute_values(item_production_detail, attributes=None):
	ipd_doc = frappe.get_doc("Item Production Detail", item_production_detail)
	attribute_values = {}

	attributes = update_if_string_instance(attributes)
	if not attributes:
		attributes = [attr.attribute for attr in ipd_doc.get("item_attributes") or []]

	for attribute in ipd_doc.get("item_attributes") or []:
		if attribute.attribute not in attributes or not attribute.mapping:
			continue

		if attribute.attribute == ipd_doc.packing_attribute:
			values = []
			for row in ipd_doc.get("stiching_item_combination_details") or []:
				if row.major_attribute_value not in values:
					values.append(row.major_attribute_value)
			attribute_values[attribute.attribute] = values
		elif attribute.attribute == ipd_doc.stiching_attribute:
			attribute_values[attribute.attribute] = [
				row.stiching_attribute_value for row in ipd_doc.get("stiching_item_details") or []
			]
		else:
			mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", attribute.mapping)
			attribute_values[attribute.attribute] = [
				row.attribute_value for row in mapping_doc.get("values") or []
			]
	return attribute_values


@frappe.whitelist()
def fetch_combination_items(combination_items):
	combination_items = [
		item.as_dict() if hasattr(item, "as_dict") else item for item in (combination_items or [])
	]
	combination_result = {"attributes": [], "values": []}
	for _key, items in groupby(combination_items, lambda row: row["index"]):
		items = list(items)
		item_list = {
			"major_attribute": items[0]["major_attribute_value"],
			"val": {},
		}
		for item in items:
			if item["set_item_attribute_value"] not in combination_result["attributes"]:
				combination_result["attributes"].append(item["set_item_attribute_value"])
			item_list["val"][item["set_item_attribute_value"]] = item["attribute_value"]
		combination_result["values"].append(item_list)
	return combination_result


@frappe.whitelist()
def get_new_combination(
	attribute_mapping_value,
	packing_attribute_details,
	major_attribute_value,
	is_same_packing_attribute=False,
	doc_name=None,
):
	packing_attribute_details = update_if_string_instance(packing_attribute_details) or []
	mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", attribute_mapping_value)
	attributes = [row.attribute_value for row in mapping_doc.get("values") or []]

	stiching_item_details = {}
	set_item_details = {}
	is_default_list = []
	ipd_doc = None
	if doc_name:
		ipd_doc = frappe.get_doc("Item Production Detail", doc_name)
		if ipd_doc.is_set_item:
			for row in ipd_doc.get("stiching_item_details") or []:
				stiching_item_details[row.stiching_attribute_value] = row.set_item_attribute_value
				if row.is_default:
					is_default_list.append(row.stiching_attribute_value)

			for row in ipd_doc.get("set_item_combination_details") or []:
				set_item_details.setdefault(row.major_attribute_value, {})
				set_item_details[row.major_attribute_value][row.set_item_attribute_value] = (
					row.attribute_value
				)

	item_detail = []
	for row in packing_attribute_details:
		item_list = {"major_attribute": row.get("attribute_value"), "val": {}}
		for attribute in attributes:
			if attribute == major_attribute_value:
				item_list["val"][attribute] = row.get("attribute_value")
			elif cint(is_same_packing_attribute):
				if doc_name and ipd_doc and ipd_doc.is_set_item:
					part = stiching_item_details.get(attribute)
					item_list["val"][attribute] = set_item_details.get(row.get("attribute_value"), {}).get(part)
				else:
					item_list["val"][attribute] = row.get("attribute_value")
			elif doc_name and ipd_doc and ipd_doc.is_set_item and attribute in is_default_list:
				part = stiching_item_details.get(attribute)
				item_list["val"][attribute] = set_item_details.get(row.get("attribute_value"), {}).get(part)
			else:
				item_list["val"][attribute] = None
		item_detail.append(item_list)

	return {"attributes": attributes, "values": item_detail}


def resolve_packing_separator(ipd_doc):
	dependent = get_dependent_attribute_details(ipd_doc.dependent_attribute_mapping)
	pack_stage_attrs = dependent["attr_list"].get(ipd_doc.pack_out_stage, {}).get("attributes") or []
	if len(pack_stage_attrs) != 1:
		frappe.throw(
			"Packing assortment needs the pack-out stage to keep exactly ONE box attribute "
			f"(the separator), but it keeps {pack_stage_attrs}."
		)
	return pack_stage_attrs[0]


def derive_assortment_attributes(ipd_doc, separator_attribute):
	assorted = []
	for attr in (ipd_doc.primary_item_attribute, ipd_doc.packing_attribute):
		if attr and attr != separator_attribute and attr not in assorted:
			assorted.append(attr)
	if not assorted:
		frappe.throw(
			f"No attribute is left to assort inside the box once the separator "
			f"({separator_attribute}) is set."
		)
	return assorted


def build_assortment_box_grid(
	separator_attribute,
	separator_values,
	assortment_attributes,
	assorted_value_lists,
	existing_qty=None,
):
	existing_qty = existing_qty or {}

	def cartesian(attr_list):
		combos = [{}]
		for attr in attr_list:
			combos = [
				dict(combo, **{attr: value})
				for combo in combos
				for value in assorted_value_lists[attr]
			]
		return combos

	row_template = cartesian(assortment_attributes)
	boxes = []
	for separator_value in separator_values:
		rows = []
		for combo in row_template:
			key = (separator_value, frozenset(combo.items()))
			rows.append(dict(combo, qty=existing_qty.get(key, 0)))
		boxes.append(
			{
				"box": separator_value,
				"separator_value": separator_value,
				"rows": rows,
			}
		)
	return boxes


@frappe.whitelist()
def get_packing_assortment_combination(doc_name, attributes=None):
	ipd_doc = frappe.get_doc("Item Production Detail", doc_name)
	separator_attribute = resolve_packing_separator(ipd_doc)
	assortment_attributes = derive_assortment_attributes(ipd_doc, separator_attribute)

	def values_for(attr):
		for row in ipd_doc.get("item_attributes") or []:
			if row.attribute == attr:
				return get_attr_mapping_details(row.mapping)
		frappe.throw(f"Attribute '{attr}' is not configured on this item.")

	separator_values = values_for(separator_attribute)
	assorted_value_lists = {attr: values_for(attr) for attr in assortment_attributes}

	existing = update_if_string_instance(ipd_doc.packing_assortment_json) or {}
	existing_qty = {}
	for box in existing.get("boxes", []):
		for row in box.get("rows", []):
			combo = {key: value for key, value in row.items() if key != "qty"}
			existing_qty[(box.get("separator_value"), frozenset(combo.items()))] = row.get("qty", 0)

	return {
		"assortment_attributes": assortment_attributes,
		"separator_attribute": separator_attribute,
		"boxes": build_assortment_box_grid(
			separator_attribute,
			separator_values,
			assortment_attributes,
			assorted_value_lists,
			existing_qty,
		),
	}


@frappe.whitelist()
def get_packing_size_values(doc_name):
	ipd_doc = frappe.get_doc("Item Production Detail", doc_name)
	return get_ipd_attribute_values(ipd_doc, ipd_doc.primary_item_attribute)


def get_ipd_attribute_values(ipd_doc, attribute):
	if not attribute:
		return []
	for row in ipd_doc.get("item_attributes") or []:
		if row.attribute == attribute:
			return get_attr_mapping_details(row.mapping)
	return []


@frappe.whitelist()
def get_mapping_attribute_values(attribute_mapping_value, attribute_no=None):
	mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", attribute_mapping_value)
	if attribute_no and len(mapping_doc.values) < int(attribute_no):
		frappe.throw(
			f"The Packing attribute number is {attribute_no} "
			f"But there is only {len(mapping_doc.values)} attributes are available"
		)

	attribute_value_list = []
	for index, attr in enumerate(mapping_doc.values):
		if not attribute_no:
			attribute_value_list.append({"stiching_attribute_value": attr.attribute_value})
		else:
			if index > int(attribute_no) - 1:
				break
			attribute_value_list.append({"attribute_value": attr.attribute_value})
	return attribute_value_list


@frappe.whitelist()
def get_stiching_in_stage_attributes(dependent_attribute_mapping, stiching_in_stage, item=None):
	attribute_details = get_dependent_attribute_details(dependent_attribute_mapping)
	return attribute_details["attr_list"].get(stiching_in_stage, {}).get("attributes") or []


@frappe.whitelist()
def get_combination(doc_name, attributes, combination_type, cloth_list=None):
	ipd_doc = frappe.get_doc("Item Production Detail", doc_name)
	attributes = update_if_string_instance(attributes) or []
	item_attributes = ipd_doc.get("item_attributes") or []
	packing_attr = ipd_doc.packing_attribute
	packing_attr_details = ipd_doc.get("packing_attribute_details") or []

	cloth_colours = [row.attribute_value for row in packing_attr_details]
	if ipd_doc.is_set_item:
		for row in ipd_doc.get("set_item_combination_details") or []:
			if row.attribute_value not in cloth_colours:
				cloth_colours.append(row.attribute_value)

	item_attr_val_list = get_combination_attr_list(
		attributes, packing_attr, cloth_colours, item_attributes
	)
	part_accessory_combination = {}
	accessory_list = []
	if combination_type == "Accessory":
		cloth_accessories = update_if_string_instance(ipd_doc.accessory_clothtype_json) or {}
		for cloth_accessory, cloth in cloth_accessories.items():
			accessory_list.append(cloth_accessory)
			part_accessory_combination.setdefault(cloth, []).append(cloth_accessory)
	else:
		cloth_list = update_if_string_instance(cloth_list)

	stich_attr = ipd_doc.stiching_attribute
	is_set_item = ipd_doc.is_set_item
	set_attr = ipd_doc.set_item_attribute if is_set_item else None
	pack_attr = ipd_doc.packing_attribute

	item_list = []
	if len(attributes) == 1:
		for attr_val in item_attr_val_list[attributes[0]]:
			if combination_type == "Cutting":
				item_list.append({attributes[0]: attr_val, "Dia": None, "Weight": None})
			elif combination_type == "Accessory":
				if attributes[0] == set_attr:
					if attr_val in part_accessory_combination:
						for accessory in part_accessory_combination[attr_val]:
							item_list.append(
								{
									attributes[0]: attr_val,
									"Accessory": accessory,
									"Dia": None,
									"Weight": None,
								}
							)
				else:
					for accessory in accessory_list:
						item_list.append(
							{
								attributes[0]: attr_val,
								"Accessory": accessory,
								"Dia": None,
								"Weight": None,
							}
						)
			else:
				item_list.append({attributes[0]: attr_val, "Cloth": None})
	elif is_set_item and pack_attr in attributes and set_attr in attributes and stich_attr in attributes:
		item_attr_list = item_attr_val_list.copy()
		del item_attr_list[pack_attr]
		del item_attr_list[stich_attr]

		set_data = {set_attr: {}}
		for value in item_attr_val_list[set_attr]:
			set_data[set_attr][value] = {pack_attr: [], stich_attr: []}
		item_attr_list[set_attr] = set_data[set_attr]
		item_attr_list = get_set_tri_struct(ipd_doc, item_attr_list, set_attr, pack_attr, stich_attr)

		set_attr_values = item_attr_list[set_attr]
		del item_attr_list[set_attr]
		attributes = pop_attributes(attributes, [set_attr, pack_attr, stich_attr])
		items = get_set_tri_combination(
			set_attr_values,
			set_attr,
			pack_attr,
			stich_attr,
			combination_type,
			part_accessory_combination,
		)
		item_list = make_comb_list(attributes, items, combination_type, item_attr_list)
		attributes.extend([set_attr, pack_attr, stich_attr])
	elif is_set_item and pack_attr in attributes and set_attr in attributes and stich_attr not in attributes:
		item_attr_list = item_attr_val_list.copy()
		del item_attr_list[pack_attr]

		item_attr_list[set_attr] = {value: [] for value in item_attr_val_list[set_attr]}
		for row in ipd_doc.get("set_item_combination_details") or []:
			if row.attribute_value not in item_attr_list[set_attr][row.set_item_attribute_value]:
				item_attr_list[set_attr][row.set_item_attribute_value].append(row.attribute_value)

		set_attr_values = item_attr_list[set_attr]
		del item_attr_list[set_attr]
		attributes = pop_attributes(attributes, [set_attr, pack_attr])
		items = get_comb_items(
			set_attr_values, set_attr, pack_attr, combination_type, part_accessory_combination
		)
		item_list = make_comb_list(attributes, items, combination_type, item_attr_list)
		attributes.extend([set_attr, pack_attr])
	elif is_set_item and stich_attr in attributes and set_attr in attributes and pack_attr not in attributes:
		item_attr_list = change_attr_list(
			item_attr_val_list, ipd_doc.get("stiching_item_details") or [], stich_attr, set_attr
		)
		set_attr_values = item_attr_list[set_attr]
		del item_attr_list[set_attr]
		attributes = pop_attributes(attributes, [set_attr, stich_attr])
		items = get_comb_items(
			set_attr_values, set_attr, stich_attr, combination_type, part_accessory_combination
		)
		item_list = make_comb_list(attributes, items, combination_type, item_attr_list)
		attributes.extend([set_attr, stich_attr])
	elif not is_set_item and pack_attr in attributes and stich_attr in attributes:
		item_attr_list = change_pack_stich_attr_list(
			item_attr_val_list,
			ipd_doc.get("stiching_item_combination_details") or [],
			stich_attr,
			pack_attr,
		)
		pack_attr_values = item_attr_list[pack_attr]
		del item_attr_list[pack_attr]
		attributes = pop_attributes(attributes, [pack_attr, stich_attr])
		items = get_comb_items(
			pack_attr_values, stich_attr, pack_attr, combination_type, part_accessory_combination
		)
		item_list = make_comb_list(attributes, items, combination_type, item_attr_list)
		attributes.extend([stich_attr, pack_attr])
	else:
		item_list = get_item_list(item_attr_val_list, attributes)
		items = []
		if is_set_item and combination_type == "Accessory":
			for item in item_list:
				if item[set_attr] in part_accessory_combination:
					for accessory in part_accessory_combination[item[set_attr]]:
						row = item.copy()
						row["Accessory"] = accessory
						items.append(row)
		elif combination_type == "Accessory":
			for item in item_list:
				for accessory in accessory_list:
					row = item.copy()
					row["Accessory"] = accessory
					items.append(row)
		else:
			items = item_list
		for item in items:
			add_combination_value(combination_type, item)
		item_list = items

	if combination_type == "Cutting":
		additional_attr = ["Dia", "Weight"]
	elif combination_type == "Accessory":
		additional_attr = ["Accessory", "Dia", "Weight"]
	else:
		additional_attr = ["Cloth"]

	return {
		"combination_type": combination_type,
		"attributes": attributes + additional_attr,
		"items": item_list,
		"select_list": accessory_list if combination_type == "Accessory" else cloth_list,
	}


def pop_attributes(attributes, attr_list):
	attributes = list(attributes)
	for attr in attr_list:
		if attr in attributes:
			attributes.pop(attributes.index(attr))
	return attributes


def get_set_tri_struct(ipd_doc, item_attr_list, set_attr, pack_attr, stich_attr):
	for row in ipd_doc.get("set_item_combination_details") or []:
		if row.attribute_value not in item_attr_list[set_attr][row.set_item_attribute_value][pack_attr]:
			item_attr_list[set_attr][row.set_item_attribute_value][pack_attr].append(row.attribute_value)

	for row in ipd_doc.get("stiching_item_details") or []:
		item_attr_list[set_attr][row.set_item_attribute_value][stich_attr].append(
			row.stiching_attribute_value
		)
	return item_attr_list


def get_set_tri_combination(
	set_attr_values, set_attr, pack_attr, stich_attr, combination_type, accessory_combination
):
	items = []
	for value in set_attr_values:
		for packing_value in set_attr_values[value][pack_attr]:
			for stiching_value in set_attr_values[value][stich_attr]:
				if combination_type == "Accessory":
					if value not in accessory_combination:
						continue
					for accessory in accessory_combination[value]:
						items.append(
							{
								set_attr: value,
								pack_attr: packing_value,
								stich_attr: stiching_value,
								"Accessory": accessory,
							}
						)
				else:
					items.append(
						{set_attr: value, pack_attr: packing_value, stich_attr: stiching_value}
					)
	return items


def get_comb_items(set_attr_values, attr1, attr2, combination_type, accessory_combination):
	items = []
	for attribute1, attribute2_values in set_attr_values.items():
		for attr2_value in attribute2_values:
			if combination_type == "Accessory":
				if attribute1 not in accessory_combination:
					continue
				for accessory in accessory_combination[attribute1]:
					items.append({attr1: attribute1, attr2: attr2_value, "Accessory": accessory})
			else:
				items.append({attr1: attribute1, attr2: attr2_value})
	return items


def make_comb_list(attributes, items, combination_type, item_attr_list):
	if len(attributes) == 0:
		for item in items:
			add_combination_value(combination_type, item)
		return items

	item_list = get_item_list(item_attr_list, attributes)
	final_list = []
	for fixed_item in items:
		for item in item_list:
			row = item | fixed_item
			add_combination_value(combination_type, row)
			final_list.append(row)
	return final_list


def get_item_list(item_attr_list, attributes):
	if not attributes:
		return []

	attrs_len = {}
	initial_attrs = {}
	for key, value in item_attr_list.items():
		attrs_len[key] = len(value)
		initial_attrs[key] = 0

	last_item = attributes[len(attributes) - 1]
	item_list = []
	check = False
	while True:
		temp = {}
		for item, item_values in item_attr_list.items():
			temp[item] = item_values[initial_attrs[item]]
			if item == last_item:
				initial_attrs[item] += 1
				if initial_attrs[item] == attrs_len[item]:
					initial_attrs = update_attr_combination(
						initial_attrs, attributes, last_item, attrs_len
					)
			if initial_attrs is None:
				check = True
		item_list.append(temp)
		if check:
			break
	return item_list


def change_attr_list(item_attr_val_list, stiching_item_details, stiching_attr, set_attr):
	attr_list = item_attr_val_list.copy()
	stiching_details = {}
	for row in stiching_item_details:
		stiching_details.setdefault(row.set_item_attribute_value, []).append(
			row.stiching_attribute_value
		)
	del attr_list[stiching_attr]
	attr_list[set_attr] = stiching_details
	return attr_list


def change_pack_stich_attr_list(item_attr_val_list, stiching_item_combination_details, stiching_attr, pack_attr):
	attr_list = item_attr_val_list.copy()
	panel_details = {}
	for row in stiching_item_combination_details:
		panel_details.setdefault(row.set_item_attribute_value, [])
		if row.attribute_value not in panel_details[row.set_item_attribute_value]:
			panel_details[row.set_item_attribute_value].append(row.attribute_value)
	del attr_list[stiching_attr]
	attr_list[pack_attr] = panel_details
	return attr_list


def add_combination_value(combination_type, item):
	if combination_type == "Cutting":
		item["Dia"] = None
		item["Weight"] = None
	elif combination_type == "Cloth":
		item["Cloth"] = None
	else:
		item["Dia"] = None
		item["Weight"] = None
	return item


@frappe.whitelist()
def get_stiching_accessory_combination(cloth_list, doc_name):
	ipd_doc = frappe.get_doc("Item Production Detail", doc_name)
	cloth_list = update_if_string_instance(cloth_list) or []
	combination_list = {"select_list": cloth_list, "attributes": [], "items": []}
	cloth_accessories = update_if_string_instance(ipd_doc.accessory_clothtype_json) or {}

	if ipd_doc.is_set_item:
		combination_list["is_set_item"] = 1
		combination_list["set_attr"] = ipd_doc.set_item_attribute
		combination_list["attributes"] = [
			"Accessory",
			ipd_doc.set_item_attribute,
			"Major Colour",
			"Accessory Colour",
			"Cloth",
		]
		part_colours = {}
		set_colours = {}
		for row in ipd_doc.get("set_item_combination_details") or []:
			set_colours.setdefault(row.index, {})
			set_colours[row.index][row.set_item_attribute_value] = row.attribute_value
			part_colours.setdefault(row.set_item_attribute_value, []).append(row.attribute_value)

		for accessory, part in cloth_accessories.items():
			for idx, colour in enumerate(part_colours.get(part, [])):
				row = {
					"accessory": accessory,
					ipd_doc.set_item_attribute: part,
					"major_colour": colour,
					"accessory_colour": None,
					"cloth_type": None,
				}
				if part != ipd_doc.major_attribute_value:
					row["major_attr_value"] = set_colours.get(idx, {}).get(ipd_doc.major_attribute_value)
				combination_list["items"].append(row)
	else:
		combination_list["is_set_item"] = 0
		combination_list["attributes"] = ["Accessory", "Major Colour", "Accessory Colour", "Cloth"]
		colours = [row.attribute_value for row in ipd_doc.get("packing_attribute_details") or []]
		for accessory in cloth_accessories:
			for colour in colours:
				combination_list["items"].append(
					{
						"accessory": accessory,
						"major_colour": colour,
						"accessory_colour": None,
						"cloth_type": None,
					}
				)
	return combination_list


def get_combination_attr_list(attributes, packing_attr, pack_details, item_attributes):
	item_attr_value_list = {}
	for item in item_attributes:
		if item.attribute in attributes:
			item_attr_value_list[item.attribute] = get_attr_mapping_details(item.mapping)
	item_attr_value_list[packing_attr] = pack_details

	item_attr_val_list = {}
	for attr in attributes:
		item_attr_val_list[attr] = item_attr_value_list[attr]
	return item_attr_val_list


def update_attr_combination(initial_attrs, attributes, last_item, attrs_len):
	for i in range(len(attributes) - 1, -1, -1):
		if attributes[i] == last_item:
			continue

		index = initial_attrs[attributes[i]] + 1
		if index < attrs_len[attributes[i]]:
			initial_attrs[attributes[i]] = index
			for j in range(len(attributes) - 1, -1, -1):
				if attributes[j] == attributes[i]:
					return initial_attrs
				initial_attrs[attributes[j]] = 0
	return None


@frappe.whitelist()
def get_attr_mapping_details(mapping):
	if not mapping:
		return []
	mapping_doc = frappe.get_cached_doc("Item Item Attribute Mapping", mapping)
	return [row.attribute_value for row in mapping_doc.get("values") or []]


@frappe.whitelist()
def duplicate_ipd(ipd, item=None):
	ipd_doc = frappe.get_doc("Item Production Detail", ipd)
	doc = frappe.new_doc("Item Production Detail")
	fields = [
		"item",
		"tech_pack_version",
		"pattern_version",
		"primary_item_attribute",
		"dependent_attribute",
		"dependent_attribute_mapping",
		"packing_process",
		"packing_attribute",
		"pack_in_stage",
		"pack_out_stage",
		"packing_combo",
		"packing_attribute_no",
		"auto_calculate",
		"stiching_process",
		"stiching_in_stage",
		"stiching_attribute",
		"stiching_out_stage",
		"stiching_major_attribute_value",
		"is_same_packing_attribute",
		"cutting_process",
		"emblishment_details_json",
		"cutting_cloths_json",
		"cutting_items_json",
		"cloth_accessory_json",
		"stiching_accessory_json",
		"accessory_clothtype_json",
		"based_on_other_attribute_mapping",
		"packing_mode",
		"packing_assortment_json",
	]
	for fieldname in fields:
		if ipd_doc.meta.get_field(fieldname) and doc.meta.get_field(fieldname):
			doc.set(fieldname, ipd_doc.get(fieldname))

	doc.item = item or ipd_doc.item
	copy_tables(
		ipd_doc,
		doc,
		[
			"item_attributes",
			"ipd_processes",
			"packing_attribute_details",
			"packing_size_details",
			"packing_assortment_attributes",
			"stiching_item_details",
			"stiching_item_combination_details",
			"cutting_attributes",
			"cloth_detail",
			"accessory_attributes",
			"cloth_attributes",
			"cutting_marker_groups",
		],
	)

	if ipd_doc.is_set_item:
		doc.is_set_item = ipd_doc.is_set_item
		doc.set_item_attribute = ipd_doc.set_item_attribute
		doc.major_attribute_value = ipd_doc.major_attribute_value
		copy_tables(ipd_doc, doc, ["set_item_combination_details"])

	items = []
	for source_row in ipd_doc.get("item_bom") or []:
		row = copy_child_row(source_row)
		row["attribute_mapping"] = None
		row["based_on_attribute_mapping"] = 1 if source_row.based_on_attribute_mapping else 0
		items.append(row)
	doc.set("item_bom", items)
	doc.save(ignore_permissions=True)

	for source_row, target_row in zip_longest(ipd_doc.get("item_bom") or [], doc.get("item_bom") or []):
		if (
			source_row
			and target_row
			and source_row.based_on_attribute_mapping
			and source_row.attribute_mapping
		):
			bom_doc = frappe.get_doc("Item BOM Attribute Mapping", source_row.attribute_mapping)
			new_bom_doc = frappe.copy_doc(bom_doc)
			if new_bom_doc.meta.get_field("item_production_detail"):
				new_bom_doc.item_production_detail = doc.name
			new_bom_doc.insert(ignore_permissions=True)
			target_row.attribute_mapping = new_bom_doc.name

	doc.save(ignore_permissions=True)
	return doc.name


def copy_tables(source, target, table_names):
	for table_name in table_names:
		if source.meta.get_field(table_name) and target.meta.get_field(table_name):
			target.set(table_name, [copy_child_row(row) for row in source.get(table_name) or []])


def copy_child_row(row):
	value = row.as_dict()
	for fieldname in [
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"parent",
		"parentfield",
		"parenttype",
		"doctype",
	]:
		value.pop(fieldname, None)
	return value

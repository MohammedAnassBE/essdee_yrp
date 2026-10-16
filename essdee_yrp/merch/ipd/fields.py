"""Field registry for the Merch IPD editor: what the browser may read and write."""

import frappe
from yrp.utils import update_if_string_instance

DOCTYPE = "YRP Item Production Detail"
ATTRIBUTE_VALUE = "YRP Item Attribute Value"

GARMENT_SECTIONS = (
	"item",
	"attributes",
	"packing",
	"set_item",
	"stitching",
	"cutting",
	"accessories",
	"processes",
	"review",
)
CLOTH_SECTIONS = (
	"item",
	"attributes",
	"processes",
	"yarn_ratio",
	"fabric_routes",
	"fabric_processes",
	"compacting",
	"review",
)
SECTION_LABELS = {
	"item": "Item & versions",
	"attributes": "Attributes & values",
	"packing": "Packing",
	"set_item": "Set item",
	"stitching": "Stitching",
	"cutting": "Cutting & cloth",
	"accessories": "Accessories & BOM",
	"processes": "Processes & embellishment",
	"review": "Review & approve",
	"yarn_ratio": "Yarn ratio",
	"fabric_routes": "Fabric routes",
	"fabric_processes": "Fabric processes",
	"compacting": "Compacting",
}

SCALAR, TABLE, JSON, LIST, VIRTUAL = "scalar", "table", "json", "list", "virtual"

WRITABLE = {
	"item": ("item", SCALAR),
	"description": ("item", SCALAR),
	"tech_pack_version": ("item", SCALAR),
	"pattern_version": ("item", SCALAR),
	"primary_item_attribute": ("attributes", SCALAR),
	"dependent_attribute": ("attributes", SCALAR),
	"item_attributes": ("attributes", TABLE),
	"packing_attribute": ("packing", SCALAR),
	"packing_combo": ("packing", SCALAR),
	"packing_attribute_no": ("packing", SCALAR),
	"auto_calculate": ("packing", SCALAR),
	"based_on_other_attribute_mapping": ("packing", SCALAR),
	"packing_mode": ("packing", SCALAR),
	"packing_process": ("packing", SCALAR),
	"pack_in_stage": ("packing", SCALAR),
	"pack_out_stage": ("packing", SCALAR),
	"packing_attribute_details": ("packing", TABLE),
	"packing_size_details": ("packing", TABLE),
	"packing_assortment_json": ("packing", JSON),
	"is_set_item": ("set_item", SCALAR),
	"set_item_attribute": ("set_item", SCALAR),
	"major_attribute_value": ("set_item", SCALAR),
	"set_item_detail": ("set_item", VIRTUAL),
	"stiching_attribute": ("stitching", SCALAR),
	"stiching_major_attribute_value": ("stitching", SCALAR),
	"is_same_packing_attribute": ("stitching", SCALAR),
	"stiching_attribute_quantity": ("stitching", SCALAR),
	"stiching_process": ("stitching", SCALAR),
	"stiching_in_stage": ("stitching", SCALAR),
	"stiching_out_stage": ("stitching", SCALAR),
	"stiching_item_details": ("stitching", TABLE),
	"stiching_item_detail": ("stitching", VIRTUAL),
	"marker_groups": ("stitching", VIRTUAL),
	"cutting_process": ("cutting", SCALAR),
	"additional_cloth": ("cutting", SCALAR),
	"enable_panel_wise_consumption_matrix": ("cutting", SCALAR),
	"cloth_detail": ("cutting", TABLE),
	"cutting_attributes": ("cutting", LIST),
	"cloth_attributes": ("cutting", LIST),
	"cutting_items_json": ("cutting", JSON),
	"cutting_cloths_json": ("cutting", JSON),
	"panel_wise_consumption_matrix_json": ("cutting", JSON),
	"panel_wise_cloth_mapping_json": ("cutting", JSON),
	"item_bom": ("accessories", TABLE),
	"accessory_attributes": ("accessories", LIST),
	"accessory_clothtype_json": ("accessories", JSON),
	"cloth_accessory_json": ("accessories", JSON),
	"stiching_accessory_json": ("accessories", JSON),
	"ipd_processes": ("processes", TABLE),
	"emblishment_details_json": ("processes", JSON),
	"yarn_ratio_details": ("yarn_ratio", TABLE),
	"fabric_routes": ("fabric_routes", TABLE),
	"fabric_processes": ("fabric_processes", TABLE),
	"fabric_value_mappings": ("fabric_processes", TABLE),
	"compacting_reference_details": ("compacting", TABLE),
}

ROW_FIELDS = {
	"item_attributes": ("attribute",),
	"packing_attribute_details": ("attribute_value", "quantity"),
	"packing_size_details": ("attribute_value", "quantity"),
	"stiching_item_details": (
		"stiching_attribute_value",
		"set_item_attribute_value",
		"quantity",
		"category",
		"is_default",
	),
	"cloth_detail": ("name1", "cloth", "required_gsm", "is_bom_item"),
	"item_bom": (
		"item",
		"qty_of_product",
		"qty_of_bom_item",
		"process_name",
		"dependent_attribute_value",
		"based_on_attribute_mapping",
		"wastage_pct",
	),
	"ipd_processes": ("process_name", "process_item", "in_stage", "out_stage"),
	"yarn_ratio_details": ("yarn_item", "ratio"),
	"fabric_routes": (
		"finished_colour",
		"finished_dia",
		"knitting_output_colour",
		"knitting_output_dia",
		"use_dyed_yarn",
	),
	"fabric_processes": ("sequence", "fabric_process", "input_item", "output_item", "quantity_ratio"),
	"fabric_value_mappings": ("sequence", "mapping_index", "attribute", "role", "from_value", "to_value"),
	"compacting_reference_details": ("colour", "input_dia", "compacting_dia", "notes"),
}
ROW_READ_ONLY = {"item_attributes": ("mapping",), "item_bom": ("uom", "attribute_mapping")}

READ_ONLY = (
	"version",
	"is_cloth_item",
	"copied_from",
	"approval_status",
	"approved_by",
	"dependent_attribute_mapping",
	"original_process_rows",
	"colour_yarn_recipes",
)
READ_ONLY_TABLE_FIELDS = {
	"colour_yarn_recipes": ("cloth_item", "colour", "yarn_item", "yarn_colour", "ratio")
}

SECTION_FIELDS = {}
for _key, (_section, _kind) in WRITABLE.items():
	SECTION_FIELDS.setdefault(_section, []).append(_key)
SECTION_FIELDS = {section: tuple(keys) for section, keys in SECTION_FIELDS.items()}

LIST_TABLES = {"cutting_attributes", "cloth_attributes", "accessory_attributes"}
VIRTUAL_TABLES = {
	"set_item_detail": "set_item_combination_details",
	"stiching_item_detail": "stiching_item_combination_details",
	"marker_groups": "cutting_marker_groups",
}


def sections_for(doc) -> tuple:
	return CLOTH_SECTIONS if doc.get("is_cloth_item") else GARMENT_SECTIONS


def supports_field(doc, key) -> bool:
	return section_of(key) in sections_for(doc) and not (
		doc.get("is_cloth_item") and key == "emblishment_details_json"
	)


def section_of(key: str) -> str | None:
	entry = WRITABLE.get(key)
	return entry[0] if entry else None


def kind_of(key: str) -> str | None:
	entry = WRITABLE.get(key)
	return entry[1] if entry else None


def meta_field(fieldname, doctype=DOCTYPE):
	return frappe.get_meta(doctype).get_field(fieldname)


def is_attribute_link(fieldname, doctype=DOCTYPE) -> bool:
	field = meta_field(fieldname, doctype)
	return bool(field and field.fieldtype == "Link" and field.options == ATTRIBUTE_VALUE)


def row_doctype(table):
	return meta_field(table).options


def json_value(raw):
	if raw in (None, ""):
		return None
	return update_if_string_instance(raw)


def is_panel_wise(doc) -> bool:
	return bool(frappe.utils.cint(doc.get("enable_panel_wise_consumption_matrix")))


def is_assortment_mode(doc) -> bool:
	return bool(frappe.utils.cint(doc.get("based_on_other_attribute_mapping"))) and not doc.get(
		"packing_mode"
	)


def json_write_block(doc, key) -> str | None:
	"""Why a JSON key cannot be written in the doc's current state, or None."""
	if key in ("cutting_items_json", "cutting_cloths_json") and is_panel_wise(doc):
		return "is derived from the panel-wise matrix while it is on"
	if key in ("panel_wise_consumption_matrix_json", "panel_wise_cloth_mapping_json") and not is_panel_wise(
		doc
	):
		return "is only used while the panel-wise matrix is on"
	if key == "packing_assortment_json" and not is_assortment_mode(doc):
		return "is only used for box assortment packing"
	return None


def writable_keys(doc) -> list[str]:
	"""Keys a client may send for this stored doc in its current state."""
	keys = []
	for key, (_section, kind) in WRITABLE.items():
		if not supports_field(doc, key) or (key == "item" and not doc.is_new()):
			continue
		if kind == JSON and (json_write_block(doc, key) or json_value(doc.get(key)) is None):
			continue
		if key == "set_item_detail" and not doc.get("is_set_item"):
			continue
		keys.append(key)
	return keys

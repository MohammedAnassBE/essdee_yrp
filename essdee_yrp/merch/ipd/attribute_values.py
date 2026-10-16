"""IPD-owned attribute value lists: where a value is used, and saving the list."""

import frappe
from frappe import _
from frappe.utils import cint, cstr
from yrp.attribute_links import value as attribute_value
from yrp.attribute_values import get_mapping_document
from yrp.yrp.doctype.yrp_item.yrp_item import get_global_attribute_values
from yrp.yrp.doctype.yrp_item_dependent_attribute_mapping.yrp_item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)

from essdee_yrp.ipd_ui import fetch_combination_items
from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.draft import build_draft
from essdee_yrp.merch.ipd.payload import (
	BOM_MAPPING_VALUE,
	LOT,
	MAPPING,
	attribute_context,
	document_attribute_ids,
	mapping_memo,
	prime_attribute_values,
	shared_mappings,
	visible_lot_count,
)

ITEM_JSON = (
	("cutting", "cutting_items_json", "Cutting consumption"),
	("cutting", "cutting_cloths_json", "Cloth by combination"),
	("accessories", "cloth_accessory_json", "Accessory consumption"),
)


def assert_editable(doc):
	doc.check_permission("write")
	if doc.approval_status == "Approved":
		frappe.throw(_("Approved IPDs are read only. Revert approval to edit."))


def attribute_row(doc, attribute):
	for row in doc.get("item_attributes") or []:
		if row.attribute == attribute:
			if not row.mapping:
				frappe.throw(_("Save the IPD before editing {0} values.").format(attribute))
			return row
	frappe.throw(_("{0} is not an attribute of this IPD.").format(attribute))


def combination(doc, key):
	raw = doc.get(key)
	data = (
		registry.json_value(raw)
		if raw
		else fetch_combination_items(doc.get(registry.VIRTUAL_TABLES[key]) or [])
	)
	return data or {}


def combination_places(doc, attribute):
	places = []
	for key, section, label, column_role in (
		("set_item_detail", "set_item", "Set combination", "set_item_attribute"),
		("stiching_item_detail", "stitching", "Stitching combination", "stiching_attribute"),
	):
		data = combination(doc, key)
		if attribute == doc.get("packing_attribute"):
			cells = [row.get("major_attribute") for row in data.get("values") or []]
			cells += [cell for row in data.get("values") or [] for cell in (row.get("val") or {}).values()]
			places.append((section, label, cells))
		if attribute == doc.get(column_role):
			places.append((section, label + " columns", data.get("attributes") or []))
	return places


def table_places(doc, attribute):
	specs = (
		("packing_attribute", "packing", "Packing rows", "packing_attribute_details", "attribute_value"),
		("primary_item_attribute", "packing", "Packing sizes", "packing_size_details", "attribute_value"),
		(
			"stiching_attribute",
			"stitching",
			"Stitching panels",
			"stiching_item_details",
			"stiching_attribute_value",
		),
		(
			"set_item_attribute",
			"stitching",
			"Stitching set parts",
			"stiching_item_details",
			"set_item_attribute_value",
		),
		("dependent_attribute", "accessories", "BOM stages", "item_bom", "dependent_attribute_value"),
		("dependent_attribute", "processes", "Process in stages", "ipd_processes", "in_stage"),
		("dependent_attribute", "processes", "Process out stages", "ipd_processes", "out_stage"),
	)
	return [
		(section, label, [attribute_value(row.get(fieldname)) for row in doc.get(table) or []])
		for role, section, label, table, fieldname in specs
		if attribute == doc.get(role)
	]


def header_places(doc, attribute):
	specs = (
		("dependent_attribute", "packing", "Pack stages", ("pack_in_stage", "pack_out_stage")),
		("dependent_attribute", "stitching", "Stitching stages", ("stiching_in_stage", "stiching_out_stage")),
		("set_item_attribute", "set_item", "Major part", ("major_attribute_value",)),
		("stiching_attribute", "stitching", "Major panel", ("stiching_major_attribute_value",)),
	)
	return [
		(section, label, [attribute_value(doc.get(fieldname)) for fieldname in fieldnames])
		for role, section, label, fieldnames in specs
		if attribute == doc.get(role)
	]


def json_places(doc, attribute):
	places = []
	for section, key, label in ITEM_JSON:
		items = (registry.json_value(doc.get(key)) or {}).get("items") or []
		places.append((section, label, [item.get(attribute) for item in items if isinstance(item, dict)]))
	places.append(stitching_accessory_place(doc, attribute))
	if attribute == doc.get("set_item_attribute"):
		places.append(
			(
				"accessories",
				"Accessory parts",
				list((registry.json_value(doc.get("accessory_clothtype_json")) or {}).values()),
			)
		)
	if attribute == doc.get("stiching_attribute"):
		embellishment = registry.json_value(doc.get("emblishment_details_json")) or {}
		places.append(
			(
				"processes",
				"Embellishment panels",
				[panel for panels in embellishment.values() for panel in panels or []],
			)
		)
		places.append(
			(
				"stitching",
				"Bundle groups",
				[
					panel
					for row in doc.get("cutting_marker_groups") or []
					for panel in (row.group_panels or "").split(",")
				],
			)
		)
	places += panel_matrix_places(doc, attribute)
	places += assortment_places(doc, attribute)
	return places


def stitching_accessory_place(doc, attribute):
	data = registry.json_value(doc.get("stiching_accessory_json")) or {}
	cells = []
	for item in data.get("items") or []:
		if attribute == doc.get("packing_attribute"):
			cells += [item.get("major_colour"), item.get("accessory_colour"), item.get("major_attr_value")]
		cells.append(item.get(attribute))
	return ("accessories", "Stitching accessories", cells)


def panel_matrix_places(doc, attribute):
	matrix = registry.json_value(doc.get("panel_wise_consumption_matrix_json")) or {}
	roles = (matrix.get("attributes") or {}) if isinstance(matrix, dict) else {}
	lists = {"primary": "primary_values", "panel": "panel_values", "packing": "packing_values"}
	return [
		("cutting", "Panel-wise consumption", list(matrix.get(key) or []))
		for role, key in lists.items()
		if roles.get(role) == attribute
	]


def assortment_places(doc, attribute):
	data = registry.json_value(doc.get("packing_assortment_json")) or {}
	cells = []
	for box in data.get("boxes") or []:
		if data.get("separator_attribute") == attribute:
			cells.append(box.get("separator_value"))
		cells += [row.get(attribute) for row in box.get("rows") or [] if (row.get("qty") or 0)]
	return [("packing", "Box assortment", cells)]


def dependent_places(doc, attribute):
	if attribute != doc.get("dependent_attribute") or not doc.get("dependent_attribute_mapping"):
		return []
	stages = (get_dependent_attribute_details(doc.dependent_attribute_mapping) or {}).get("attr_list") or {}
	return [("attributes", "Dependent stages", list(stages))]


def bom_mapping_places(doc, attribute):
	mappings = [row.attribute_mapping for row in doc.get("item_bom") or [] if row.attribute_mapping]
	if not mappings:
		return []
	raw = frappe.get_all(
		BOM_MAPPING_VALUE,
		filters={"parent": ["in", mappings], "attribute": attribute},
		pluck="attribute_value",
		limit_page_length=0,
	)
	prime_attribute_values(raw)
	return [("accessories", "BOM mappings", [attribute_value(value) for value in raw])]


def value_usage(doc, attribute, values):
	prime_attribute_values(document_attribute_ids(doc))
	places = (
		table_places(doc, attribute)
		+ header_places(doc, attribute)
		+ combination_places(doc, attribute)
		+ json_places(doc, attribute)
		+ dependent_places(doc, attribute)
		+ bom_mapping_places(doc, attribute)
	)
	lots = visible_lot_count(doc.name) if doc.name else 0
	usage = {}
	for value in values:
		entries = {}
		for section, label, cells in places:
			count = sum(1 for cell in cells if cell == value)
			if count:
				entry = entries.setdefault(
					(section, label), {"section": section, "label": _(label), "count": 0}
				)
				entry["count"] += count
		if entries and lots:
			entries[("lots", "lots")] = {"section": "lots", "label": _("Lots using this IPD"), "count": lots}
		usage[value] = list(entries.values())
	return usage


def get_usage(name, attribute, values, draft=None):
	doc = build_draft(name, draft or {}, ptype="read")
	return {"usage": value_usage(doc, attribute, [cstr(value) for value in values or []])}


def clean_values(values):
	seen, cleaned = set(), []
	for value in values or []:
		value = cstr(value).strip()
		if value and value.casefold() not in seen:
			seen.add(value.casefold())
			cleaned.append(value)
	return cleaned


def canonical_values(attribute, values):
	"""Map values onto the catalogue spelling; return (values, values not in the catalogue)."""
	catalogue = {value.casefold(): value for value in get_global_attribute_values(attribute)}
	canonical = [catalogue.get(value.casefold(), value) for value in values]
	return canonical, [value for value in canonical if value.casefold() not in catalogue]


def locked_mapping(mapping, mapping_modified):
	doc = get_mapping_document(mapping, for_update=True)
	if str(doc.modified) != cstr(mapping_modified):
		frappe.throw(
			_("The {0} values changed after you opened them. Refresh and try again.").format(
				doc.attribute_name
			),
			frappe.TimestampMismatchError,
		)
	return doc


def save_values(name, attribute, values, mapping_modified):
	doc = frappe.get_doc(registry.DOCTYPE, name, for_update=True)
	assert_editable(doc)
	row = attribute_row(doc, attribute)
	if cint(frappe.db.get_value("Item Attribute", attribute, "numeric_values")):
		frappe.throw(_("{0} values are numeric and are edited on the Item.").format(attribute))
	if row.mapping in shared_mappings(doc, [row.mapping]):
		frappe.throw(
			_("{0} values are shared with another document. Save the IPD to make its own copy.").format(
				attribute
			)
		)
	mapping = locked_mapping(row.mapping, mapping_modified)
	values, unknown = canonical_values(attribute, clean_values(values))
	if unknown:
		frappe.throw(
			_("{0} is not a {1} value. Pick values from the {1} list.").format(", ".join(unknown), attribute)
		)
	mapping.set("values", [{"attribute_value": value} for value in values])
	mapping.save(ignore_permissions=True)
	frappe.clear_document_cache(MAPPING, mapping.name)
	return attribute_result(doc, attribute)


def attribute_result(doc, attribute):
	with mapping_memo(doc) as mappings:
		entry = next(item for item in attribute_context(doc, mappings) if item["attribute"] == attribute)
	return {**entry, "grids_stale": stale_grids(doc, attribute)}


def stale_grids(doc, attribute):
	from essdee_yrp.merch.ipd.grids import GRID_KEYS

	if attribute == doc.get("packing_attribute"):
		return list(GRID_KEYS)
	stale = set()
	if attribute == doc.get("stiching_attribute"):
		stale.update(
			(
				"stitching_combination",
				"cutting_items",
				"cutting_cloths",
				"panel_wise_consumption",
				"panel_wise_cloth_mapping",
			)
		)
	if attribute == doc.get("set_item_attribute"):
		stale.update(
			(
				"set_combination",
				"stitching_combination",
				"cutting_items",
				"cutting_cloths",
				"cloth_accessory",
				"stiching_accessory",
			)
		)
	if attribute == doc.get("primary_item_attribute"):
		stale.update(("packing_sizes", "packing_assortment", "panel_wise_consumption"))
	if attribute == doc.get("dependent_attribute"):
		stale.add("packing_assortment")
	for key, grid in (
		("cutting_attributes", "cutting_items"),
		("cloth_attributes", "cutting_cloths"),
		("accessory_attributes", "cloth_accessory"),
	):
		if attribute in [row.attribute for row in doc.get(key) or []]:
			stale.add(grid)
	return [key for key in GRID_KEYS if key in stale]

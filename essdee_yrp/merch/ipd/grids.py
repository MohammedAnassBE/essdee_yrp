"""Grid skeletons for the IPD editor, built by the Desk generators over an in-memory doc."""

import frappe
from frappe.utils import cint
from yrp.attribute_links import value as attribute_value

from essdee_yrp import ipd_ui
from essdee_yrp.ipd_validations import clear_set_item_fields_when_disabled, save_combination_detail_fields
from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.payload import cutting_attribute_choices, dependent_context, mapping_of


def packing_rows(doc):
	return [
		{"attribute_value": attribute_value(row.attribute_value)}
		for row in doc.get("packing_attribute_details") or []
	]


def cloth_names(doc):
	return [row.name1 for row in doc.get("cloth_detail") or []]


def attribute_list(doc, key):
	return [row.attribute for row in doc.get(key) or [] if row.attribute]


def set_combination(doc):
	mapping = mapping_of(doc, doc.get("set_item_attribute"))
	if (
		not cint(doc.get("is_set_item"))
		or not mapping
		or not attribute_value(doc.get("major_attribute_value"))
	):
		return None
	return ipd_ui.build_new_combination(mapping, packing_rows(doc), doc.major_attribute_value)


def stitching_combination(doc):
	mapping = mapping_of(doc, doc.get("stiching_attribute"))
	major = attribute_value(doc.get("stiching_major_attribute_value"))
	if not mapping or not major or not doc.get("stiching_item_details"):
		return None
	return ipd_ui.build_new_combination(
		mapping, packing_rows(doc), major, doc.get("is_same_packing_attribute"), ipd_doc=doc
	)


def cutting_items(doc):
	attributes = attribute_list(doc, "cutting_attributes")
	if registry.is_panel_wise(doc) or not attributes:
		return None
	return ipd_ui.build_combination(doc, attributes, "Cutting")


def cutting_cloths(doc):
	attributes = attribute_list(doc, "cloth_attributes")
	if registry.is_panel_wise(doc) or not attributes or not doc.get("cloth_detail"):
		return None
	return ipd_ui.build_combination(doc, attributes, "Cloth", cloth_names(doc))


def cloth_accessory(doc):
	attributes = attribute_list(doc, "accessory_attributes")
	if not attributes or not registry.json_value(doc.get("accessory_clothtype_json")):
		return None
	return ipd_ui.build_combination(doc, attributes, "Accessory")


def stiching_accessory(doc):
	if not registry.json_value(doc.get("accessory_clothtype_json")):
		return None
	return ipd_ui.build_stiching_accessory_combination(doc, cloth_names(doc))


def packing_assortment(doc):
	if not registry.is_assortment_mode(doc) or not doc.get("dependent_attribute_mapping"):
		return None
	return ipd_ui.build_packing_assortment_combination(doc)


def packing_sizes(doc):
	if (
		not cint(doc.get("based_on_other_attribute_mapping"))
		or doc.get("packing_mode") != "Size Ratio Packing"
	):
		return None
	return ipd_ui.mapping_values(mapping_of(doc, doc.get("primary_item_attribute")))


def has_panel_context(doc):
	return (
		registry.is_panel_wise(doc)
		and attribute_value(doc.get("stiching_in_stage"))
		and doc.get("dependent_attribute")
	)


def panel_wise_grids(doc, include_saved):
	"""Consumption and cloth-mapping matrices, staged the way the Desk form renders them."""
	if not has_panel_context(doc):
		return None
	from essdee_yrp.panel_wise_cloth_mapping import make_panel_wise_cloth_mapping_matrix
	from essdee_yrp.panel_wise_consumption import make_panel_wise_matrix, panel_wise_payload

	matrix, context = make_panel_wise_matrix(doc, include_saved=include_saved)
	consumption = panel_wise_payload(matrix, context)
	staged = frappe.get_doc(doc.as_dict())
	staged.panel_wise_consumption_matrix_json = consumption["matrix"]
	cloth_matrix, _context = make_panel_wise_cloth_mapping_matrix(staged, include_saved=include_saved)
	return {"consumption": consumption, "cloth_mapping": {"matrix": cloth_matrix}}


def attribute_choices(doc):
	return cutting_attribute_choices(doc, dependent_context(doc))


BUILDERS = {
	"cutting_attribute_choices": attribute_choices,
	"set_combination": set_combination,
	"stitching_combination": stitching_combination,
	"cutting_items": cutting_items,
	"cutting_cloths": cutting_cloths,
	"cloth_accessory": cloth_accessory,
	"stiching_accessory": stiching_accessory,
	"packing_assortment": packing_assortment,
	"packing_sizes": packing_sizes,
}
PANEL_KEYS = ("panel_wise_consumption", "panel_wise_cloth_mapping")
GRID_KEYS = (*BUILDERS, *PANEL_KEYS)


def active_grid_keys(doc):
	"""Skeletons the editor loads up front; attribute choices already ship in the context."""
	if doc.get("is_cloth_item"):
		return []
	return [key for key in GRID_KEYS if key != "cutting_attribute_choices"]


def stored_panel_flag(doc):
	if doc.is_new():
		return True
	return bool(frappe.db.get_value(registry.DOCTYPE, doc.name, "enable_panel_wise_consumption_matrix"))


def build_grids(doc, keys, include_saved=None):
	"""({key: skeleton or None}, {key: error}); runs only the pure Desk mutators first."""
	unknown = sorted(set(keys) - set(GRID_KEYS))
	if unknown:
		frappe.throw(frappe._("Unknown grids: {0}").format(", ".join(unknown)))
	save_combination_detail_fields(doc)
	clear_set_item_fields_when_disabled(doc)
	grids, errors = {}, {}
	for key in [key for key in BUILDERS if key in keys]:
		capture(grids, errors, key, lambda key=key: BUILDERS[key](doc))
	if any(key in keys for key in PANEL_KEYS):
		saved = stored_panel_flag(doc) if include_saved is None else include_saved
		panel = {}
		capture(panel, errors, "panel_wise", lambda: panel_wise_grids(doc, saved))
		panel = panel.get("panel_wise") or {}
		if "panel_wise_consumption" in keys:
			grids["panel_wise_consumption"] = panel.get("consumption")
		if "panel_wise_cloth_mapping" in keys:
			grids["panel_wise_cloth_mapping"] = panel.get("cloth_mapping")
	return grids, errors


def capture(target, errors, key, build):
	message_start = len(frappe.get_message_log())
	try:
		target[key] = build()
	except frappe.ValidationError as error:
		target[key] = None
		errors[key] = frappe.utils.strip_html(str(error)) or frappe._("This grid cannot be built yet.")
		del frappe.local.message_log[message_start:]

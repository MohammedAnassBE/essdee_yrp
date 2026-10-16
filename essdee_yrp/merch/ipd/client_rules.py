"""Desk form rules the server save never enforces, gated the way the Desk widgets render."""

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.attribute_links import value as attribute_value

from essdee_yrp.ipd_ui import fetch_combination_items
from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.payload import client_mandatory_fields

REQUIRED_GSM = "Required GSM"
FILL_ALL = "Fill all the combinations"
WARNING_RULES = {"process_stages"}


def problem(rule, section, message, field=None, row_key=None, column=None, row_label=None):
	return {
		"rule": rule,
		"section": section,
		"message": message,
		"field": field,
		"row_key": row_key,
		"column": column,
		"row_label": row_label,
	}


def table_row_key(row):
	"""Stored rows by name; rows the draft added by position, as the editor keys them."""
	return row.name or f"new:{row.idx - 1}"


def is_blank(value):
	return value is None or (isinstance(value, str) and not value.strip())


def mandatory_fields(doc):
	found = []
	for fieldname in sorted(client_mandatory_fields(doc)):
		if is_blank(doc.get(fieldname)):
			label = _(registry.meta_field(fieldname).label)
			found.append(
				problem(
					"mandatory_depends_on",
					registry.section_of(fieldname),
					_("{0} is required.").format(label),
					fieldname,
				)
			)
	return found


def required_row_values(doc):
	found = []
	if doc.get("dependent_attribute"):
		for row in doc.get("item_bom") or []:
			if is_blank(row.get("dependent_attribute_value")):
				found.append(
					problem(
						"bom_dependent_value",
						"accessories",
						_("BOM row {0}: Dependent Attribute Value is required.").format(row.idx),
						"item_bom",
						table_row_key(row),
						"dependent_attribute_value",
						_("Row {0}").format(row.idx),
					)
				)
	if cint(doc.get("is_set_item")):
		for row in doc.get("stiching_item_details") or []:
			if is_blank(row.get("set_item_attribute_value")):
				panel = attribute_value(row.stiching_attribute_value)
				found.append(
					problem(
						"stitching_set_part",
						"stitching",
						_("Stitching panel {0}: choose its set part.").format(panel),
						"stiching_item_details",
						panel,
						"set_item_attribute_value",
					)
				)
	return found


def combination(doc, key):
	raw = doc.get(key)
	if raw:
		return registry.json_value(raw) or {}
	return fetch_combination_items(doc.get(registry.VIRTUAL_TABLES[key]) or [])


def blank_combination_cells(doc, key, rule, section):
	for row in combination(doc, key).get("values") or []:
		for column, cell in (row.get("val") or {}).items():
			if is_blank(cell):
				return [problem(rule, section, _(FILL_ALL), key, row.get("major_attribute"), column)]
	return []


def combination_cells(doc):
	found = []
	if cint(doc.get("is_set_item")):
		found += blank_combination_cells(doc, "set_item_detail", "set_combination_cells", "set_item")
	if doc.get("dependent_attribute"):
		found += blank_combination_cells(
			doc, "stiching_item_detail", "stitching_combination_cells", "stitching"
		)
	return found


def json_items(doc, key):
	data = registry.json_value(doc.get(key)) or {}
	return data if isinstance(data, dict) and data.get("items") else None


def item_key(item, attributes):
	return "\u001f".join(str(item.get(attribute) or "") for attribute in attributes)


def cutting_cells(doc):
	data = json_items(doc, "cutting_items_json")
	if not data:
		return []
	attributes = data.get("attributes") or []
	keys = [attribute for attribute in attributes if attribute not in ("Dia", "Weight", REQUIRED_GSM)]
	for item in data["items"]:
		for attribute in attributes:
			optional = attribute == REQUIRED_GSM
			if is_blank(item.get(attribute)) and not optional:
				return [
					problem(
						"cutting_cells",
						"cutting",
						_(FILL_ALL),
						"cutting_items_json",
						item_key(item, keys),
						attribute,
					)
				]
	return []


def cloth_cells(doc):
	data = json_items(doc, "cutting_cloths_json")
	if not data:
		return []
	names = [row.name1 for row in doc.get("cloth_detail") or []]
	attributes = data.get("attributes") or []
	keys = [attribute for attribute in attributes if attribute != "Cloth"]
	for item in data["items"]:
		if item.get("Cloth") not in names:
			message = _("Some Cloth items not in the select list")
			return [
				problem(
					"cloth_name", "cutting", message, "cutting_cloths_json", item_key(item, keys), "Cloth"
				)
			]
	for item in data["items"]:
		for attribute in attributes:
			if is_blank(item.get(attribute)):
				return [
					problem(
						"cloth_cells",
						"cutting",
						_(FILL_ALL),
						"cutting_cloths_json",
						item_key(item, keys),
						attribute,
					)
				]
	return []


def cloth_accessory_cells(doc):
	data = json_items(doc, "cloth_accessory_json")
	if not data:
		return []
	keys = [attribute for attribute in data.get("attributes") or [] if attribute not in ("Dia", "Weight")]
	for item in data["items"]:
		for attribute, cell in item.items():
			if is_blank(cell):
				return [
					problem(
						"cloth_accessory_cells",
						"accessories",
						_(FILL_ALL),
						"cloth_accessory_json",
						item_key(item, keys),
						attribute,
					)
				]
	return []


def stitching_accessory_key(data, item):
	part = item.get(data.get("set_attr")) if data.get("set_attr") else ""
	return "\u001f".join(
		str(value or "") for value in (item.get("accessory"), part, item.get("major_colour"))
	)


def stitching_accessory_cells(doc):
	data = json_items(doc, "stiching_accessory_json")
	if not data:
		return []
	names = [row.name1 for row in doc.get("cloth_detail") or []]
	for item in data["items"]:
		key = stitching_accessory_key(data, item)
		if is_blank(item.get("accessory_colour")):
			return [
				problem(
					"stitching_accessory_cells",
					"accessories",
					_(FILL_ALL),
					"stiching_accessory_json",
					key,
					"accessory_colour",
				)
			]
		if item.get("cloth_type") not in names:
			message = _("Some Cloths not in the Accessory Select List")
			return [
				problem(
					"stitching_accessory_cloth",
					"accessories",
					message,
					"stiching_accessory_json",
					key,
					"cloth_type",
				)
			]
	return []


def bundle_groups(doc):
	panels = [attribute_value(row.stiching_attribute_value) for row in doc.get("stiching_item_details") or []]
	if not panels:
		return []
	selected = []
	for row in doc.get("cutting_marker_groups") or []:
		for panel in [panel for panel in (row.group_panels or "").split(",") if panel]:
			if panel in selected:
				message = _("Panel {0} is grouped multiple times").format(panel)
				return [problem("bundle_groups", "stitching", message, "marker_groups", panel)]
			selected.append(panel)
	if selected and len(selected) != len(panels):
		return [problem("bundle_groups", "stitching", _("Select All the Panels"), "marker_groups")]
	return []


def panel_weights(doc):
	if not registry.is_panel_wise(doc):
		return []
	matrix = registry.json_value(doc.get("panel_wise_consumption_matrix_json")) or {}
	for panel in matrix.get("panels") or []:
		for row in panel.get("rows") or []:
			for colour, cell in (row.get("values") or {}).items():
				weight = (cell or {}).get("weight")
				if weight in (None, ""):
					continue
				if not is_positive_number(weight):
					message = _("Consumption must be greater than zero, for example 0.0300.")
					key = "\u001f".join((panel.get("group_id") or "", row.get("primary_value") or ""))
					return [
						problem(
							"panel_weights",
							"cutting",
							message,
							"panel_wise_consumption_matrix_json",
							key,
							colour,
						)
					]
	return []


def process_stages(doc):
	"""Process rows use one stage; legacy rows whose in and out stage differ are warnings."""
	found = []
	for row in doc.get("ipd_processes") or []:
		if (row.in_stage or None) != (row.out_stage or None):
			message = _("Process {0} has in stage {1} but out stage {2}. Use one stage for both.").format(
				row.process_name or row.idx, attribute_value(row.in_stage), attribute_value(row.out_stage)
			)
			found.append(
				problem(
					"process_stages",
					"processes",
					message,
					"ipd_processes",
					table_row_key(row),
					"in_stage",
					row.process_name or _("Row {0}").format(row.idx),
				)
			)
	return found


def is_positive_number(value):
	try:
		return float(value) > 0
	except TypeError, ValueError:
		return False


def widget_rules(doc):
	"""Desk renders most widgets only once the garment IPD has a dependent attribute."""
	rules = [combination_cells]
	if not doc.get("dependent_attribute"):
		return rules
	if not registry.is_panel_wise(doc):
		rules += [cutting_cells, cloth_cells]
	return [*rules, cloth_accessory_cells, stitching_accessory_cells, bundle_groups, panel_weights]


def problems(doc, sections=None):
	"""Every Desk client-only problem, optionally limited to the sections a patch touched."""
	if doc.is_new():
		return []
	found = process_stages(doc)
	if not doc.get("is_cloth_item"):
		found += mandatory_fields(doc) + required_row_values(doc)
		for rule in widget_rules(doc):
			found += rule(doc)
	if sections is not None:
		found = [entry for entry in found if entry["section"] in sections]
	return found

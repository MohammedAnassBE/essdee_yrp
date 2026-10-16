"""IPD document -> browser payload, loaded with a fixed number of batched queries."""

from contextlib import contextmanager

import frappe
from frappe.utils import get_fullname
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item.yrp_item import get_global_attribute_values
from yrp.yrp.doctype.yrp_item_dependent_attribute_mapping.yrp_item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import (
	get_colour_attribute,
	get_dia_attribute,
)
from essdee_yrp.ipd_ui import fetch_combination_items, get_approval_roles
from essdee_yrp.merch.ipd import fields as registry

MAPPING = "YRP Item Item Attribute Mapping"
MAPPING_VALUE = "YRP Item Item Attribute Mapping Value"
BOM_MAPPING = "YRP Item BOM Attribute Mapping"
BOM_MAPPING_ATTRIBUTE = "YRP Item BOM Attribute Mapping Attribute"
BOM_MAPPING_VALUE = "YRP Item BOM Attribute Mapping Value"
LOT = "SD YRP Lot"


def attribute_link_fields(doctype):
	return [
		field.fieldname
		for field in frappe.get_meta(doctype).fields
		if field.fieldtype == "Link" and field.options == registry.ATTRIBUTE_VALUE
	]


def document_attribute_ids(doc):
	ids = {doc.get(fieldname) for fieldname in attribute_link_fields(registry.DOCTYPE)}
	for table in frappe.get_meta(registry.DOCTYPE).get_table_fields():
		link_fields = attribute_link_fields(table.options)
		for row in doc.get(table.fieldname) or []:
			ids.update(row.get(fieldname) for fieldname in link_fields)
	return ids


def prime_attribute_values(ids):
	"""Resolve attribute-value ids in one query into yrp's request cache."""
	cache = getattr(frappe.local, "attribute_link_values", None)
	if cache is None:
		cache = frappe.local.attribute_link_values = {}
	missing = sorted({raw for raw in ids if isinstance(raw, str) and raw.startswith("IAV-")} - set(cache))
	if not missing:
		return
	for row in frappe.get_all(
		registry.ATTRIBUTE_VALUE,
		filters={"name": ["in", missing]},
		fields=["name", "attribute_name", "attribute_value"],
		limit_page_length=0,
	):
		cache[row.name] = frappe._dict(attribute_name=row.attribute_name, attribute_value=row.attribute_value)


def load_mappings(names):
	"""{mapping: {attribute_name, modified, raw}} for attribute mappings, two queries."""
	names = sorted({name for name in names if name})
	if not names:
		return {}
	mappings = {
		row.name: {"attribute_name": row.attribute_name, "modified": str(row.modified), "raw": []}
		for row in frappe.get_all(
			MAPPING, filters={"name": ["in", names]}, fields=["name", "attribute_name", "modified"]
		)
	}
	for row in frappe.get_all(
		MAPPING_VALUE,
		filters={"parent": ["in", names], "parenttype": MAPPING, "parentfield": "values"},
		fields=["parent", "attribute_value"],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	):
		if row.parent in mappings and row.attribute_value:
			mappings[row.parent]["raw"].append(row.attribute_value)
	return mappings


@contextmanager
def mapping_memo(doc):
	"""Serve every IPD mapping read in this block from one batched load."""
	previous = getattr(frappe.local, "ipd_mapping_values", None)
	mappings = load_mappings(row.mapping for row in doc.get("item_attributes") or [])
	prime_attribute_values(
		[*document_attribute_ids(doc), *(raw for mapping in mappings.values() for raw in mapping["raw"])]
	)
	frappe.local.ipd_mapping_values = {
		name: [attribute_value(raw) for raw in mapping["raw"]] for name, mapping in mappings.items()
	}
	try:
		yield mappings
	finally:
		frappe.local.ipd_mapping_values = previous


def plain(doctype, fieldname, raw):
	return attribute_value(raw) if fieldname in attribute_link_fields(doctype) else raw


def row_values(table, row, fieldnames):
	doctype = registry.row_doctype(table)
	return {
		"name": row.name,
		**{fieldname: plain(doctype, fieldname, row.get(fieldname)) for fieldname in fieldnames},
	}


def table_value(doc, table, fieldnames):
	return [row_values(table, row, fieldnames) for row in doc.get(table) or []]


def key_value(doc, key):
	kind = registry.kind_of(key)
	if kind == registry.SCALAR:
		return plain(registry.DOCTYPE, key, doc.get(key))
	if kind == registry.TABLE:
		return table_value(doc, key, (*registry.ROW_FIELDS[key], *registry.ROW_READ_ONLY.get(key, ())))
	if kind == registry.LIST:
		return [row.attribute for row in doc.get(key) or []]
	if kind == registry.JSON:
		return registry.json_value(doc.get(key))
	if key == "marker_groups":
		return [
			row.group_panels.split(",") for row in doc.get("cutting_marker_groups") or [] if row.group_panels
		]
	return fetch_combination_items(doc.get(registry.VIRTUAL_TABLES[key]) or [])


def document_values(doc):
	values = {
		key: key_value(doc, key)
		for key in registry.WRITABLE
		if registry.supports_field(doc, key)
	}
	if doc.get("is_cloth_item"):
		for key in ("additional_cloth", "stiching_attribute_quantity"):
			values[key] = key_value(doc, key)
	for key in registry.READ_ONLY:
		if key in registry.READ_ONLY_TABLE_FIELDS:
			values[key] = table_value(doc, key, registry.READ_ONLY_TABLE_FIELDS[key])
		elif key == "original_process_rows":
			values[key] = registry.json_value(doc.get(key))
		else:
			values[key] = doc.get(key)
	return values


def record(doc):
	return {
		"name": None if doc.is_new() else doc.name,
		"modified": None if doc.is_new() else str(doc.modified),
		"version": doc.get("version"),
		"approval_status": doc.get("approval_status") or "Not Approved",
		"approved_by": doc.get("approved_by"),
		"approved_by_name": get_fullname(doc.approved_by) if doc.get("approved_by") else None,
		"is_cloth_item": bool(doc.get("is_cloth_item")),
		"item": doc.get("item"),
		"item_name": frappe.db.get_value("Item", doc.item, "item_name") if doc.get("item") else None,
		"copied_from": doc.get("copied_from"),
	}


def attribute_roles(doc, attribute):
	roles = (
		("primary", "primary_item_attribute"),
		("dependent", "dependent_attribute"),
		("packing", "packing_attribute"),
		("stitching", "stiching_attribute"),
		("set", "set_item_attribute"),
	)
	return [role for role, fieldname in roles if attribute and doc.get(fieldname) == attribute]


def shared_mappings(doc, names):
	"""Mappings also used by an Item template or another IPD; variant rows only copy templates."""
	if not names:
		return set()
	item_filters = {"mapping": ["in", names], "parenttype": "Item", "variant_of": ["is", "not set"]}
	shared = set(frappe.get_all("Item Variant Attribute", filters=item_filters, pluck="mapping"))
	shared.update(
		frappe.get_all("YRP Item Item Attribute", filters={"mapping": ["in", names]}, pluck="mapping")
	)
	shared.update(
		frappe.get_all(
			"YRP IPD Item Attribute",
			filters={"mapping": ["in", names], "parent": ["!=", doc.name or ""]},
			pluck="mapping",
		)
	)
	return shared


def attribute_context(doc, mappings):
	rows = [row for row in doc.get("item_attributes") or [] if row.attribute]
	numeric = set(
		frappe.get_all(
			"Item Attribute",
			filters={"name": ["in", [row.attribute for row in rows] or [""]], "numeric_values": 1},
			pluck="name",
		)
	)
	shared = shared_mappings(doc, [row.mapping for row in rows if row.mapping])
	can_add = bool(frappe.has_permission("Item Attribute", "write"))
	return [
		{
			"attribute": row.attribute,
			"mapping": row.mapping,
			"mapping_modified": (mappings.get(row.mapping) or {}).get("modified"),
			"numeric": row.attribute in numeric,
			"values": list((frappe.local.ipd_mapping_values or {}).get(row.mapping) or []),
			"roles": attribute_roles(doc, row.attribute),
			"is_shared": row.mapping in shared,
			"can_add_values": can_add,
		}
		for row in rows
	]


def dependent_context(doc):
	if doc.get("dependent_attribute") and doc.get("dependent_attribute_mapping"):
		return get_dependent_attribute_details(doc.dependent_attribute_mapping)
	return {}


def mapping_of(doc, attribute):
	for row in doc.get("item_attributes") or []:
		if attribute and row.attribute == attribute:
			return row.mapping
	return None


def stage_values(doc):
	return list(
		(frappe.local.ipd_mapping_values or {}).get(mapping_of(doc, doc.get("dependent_attribute"))) or []
	)


def cutting_attribute_choices(doc, dependent):
	stage = attribute_value(doc.get("stiching_in_stage"))
	if not stage or not doc.get("dependent_attribute"):
		return []
	choices = list(((dependent.get("attr_list") or {}).get(stage) or {}).get("attributes") or [])
	if doc.get("is_set_item") and doc.get("set_item_attribute"):
		choices.append(doc.set_item_attribute)
	return choices


def bom_mapping_context(doc):
	"""{bom_row: mapping detail} for attribute-mapped BOM rows, four queries."""
	rows = [row for row in doc.get("item_bom") or [] if row.attribute_mapping]
	if not rows:
		return {}
	names = list({row.attribute_mapping for row in rows})
	heads = {
		row.name: row
		for row in frappe.get_all(BOM_MAPPING, filters={"name": ["in", names]}, fields=["name", "modified"])
	}
	attributes = frappe.get_all(
		BOM_MAPPING_ATTRIBUTE,
		filters={"parent": ["in", names], "parenttype": BOM_MAPPING},
		fields=["parent", "parentfield", "attribute", "same_attribute"],
		order_by="parent asc, parentfield asc, idx asc",
		limit_page_length=0,
	)
	values = frappe.get_all(
		BOM_MAPPING_VALUE,
		filters={"parent": ["in", names], "parenttype": BOM_MAPPING},
		fields=["parent", "index", "type", "attribute", "attribute_value", "quantity"],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	)
	prime_attribute_values(row.attribute_value for row in values)
	shared = shared_bom_mappings(doc, names)
	return {
		bom.name: bom_mapping_detail(
			bom.attribute_mapping,
			heads.get(bom.attribute_mapping),
			attributes,
			values,
			bom.attribute_mapping in shared,
		)
		for bom in rows
	}


def shared_bom_mappings(doc, names):
	"""Mappings referenced by more than one BOM row, here or in any other document."""
	references = frappe.get_all(
		"YRP Item BOM",
		filters={"attribute_mapping": ["in", names]},
		fields=["attribute_mapping", "parent", "parenttype"],
		limit_page_length=0,
	)
	counts = {}
	for row in references:
		counts[row.attribute_mapping] = counts.get(row.attribute_mapping, 0) + 1
	return {
		row.attribute_mapping
		for row in references
		if counts[row.attribute_mapping] > 1 or row.parent != doc.name or row.parenttype != registry.DOCTYPE
	}


def bom_mapping_detail(mapping, head, attributes, values, is_shared):
	own = [row for row in attributes if row.parent == mapping]
	item_side = [row for row in own if row.parentfield == "item_attributes"]
	bom_side = [row for row in own if row.parentfield == "bom_item_attributes"]
	same = {row.attribute for row in item_side if row.same_attribute} & {
		row.attribute for row in bom_side if row.same_attribute
	}
	return {
		"mapping": mapping,
		"mapping_modified": str(head.modified) if head else None,
		"item_attributes": [row.attribute for row in item_side],
		"bom_item_attributes": [row.attribute for row in bom_side],
		"same_attributes": sorted(same),
		"rows": [
			{
				"index": row.index,
				"type": row.type,
				"attribute": row.attribute,
				"attribute_value": attribute_value(row.attribute_value),
				"quantity": row.quantity,
			}
			for row in values
			if row.parent == mapping
		],
		"is_shared": is_shared,
	}


def select_options(doctype, fieldname):
	field = frappe.get_meta(doctype).get_field(fieldname)
	return [option for option in (field.options or "").split("\n") if option]


def context(doc, mappings):
	dependent = dependent_context(doc)
	return {
		"attributes": attribute_context(doc, mappings),
		"dependent": dependent,
		"stage_values": stage_values(doc),
		"cutting_attribute_choices": cutting_attribute_choices(doc, dependent),
		"bom_mappings": bom_mapping_context(doc),
		"options": {
			"stitching_categories": select_options("SD YRP Stiching Item Detail", "category"),
			"packing_modes": select_options(registry.DOCTYPE, "packing_mode"),
		},
		"cloth": cloth_context(doc),
	}


def cloth_context(doc):
	"""Settings-owned Colour/Dia attributes and their global values, for cloth IPDs only."""
	if not doc.get("is_cloth_item"):
		return None
	colour, dia = get_colour_attribute(), get_dia_attribute()
	return {
		"colour_attribute": colour,
		"dia_attribute": dia,
		"colour_values": get_global_attribute_values(colour),
		"dia_values": get_global_attribute_values(dia),
		"mapping_roles": select_options("SD YRP IPD Fabric Value Mapping", "role"),
	}


def used_by(doc):
	if not doc.get("item"):
		return []
	versions = frappe.get_list(
		registry.DOCTYPE,
		filters={"item": doc.item},
		fields=["name", "version", "approval_status"],
		order_by="version desc",
		limit_page_length=0,
	)
	lots = {}
	if versions and frappe.has_permission(LOT, "read"):
		for lot in frappe.get_list(
			LOT,
			filters={"production_detail": ["in", [row.name for row in versions]]},
			fields=["name", "production_detail"],
			order_by="name asc",
			limit_page_length=0,
		):
			lots.setdefault(lot.production_detail, []).append(lot.name)
	return [
		{
			"ipd": row.name,
			"version": row.version,
			"is_current": row.name == doc.name,
			"approval_status": row.approval_status,
			"lots": lots.get(row.name, []),
		}
		for row in versions
	]


def source(doc):
	name = doc.get("copied_from")
	if not name:
		return None
	if not frappe.db.exists(registry.DOCTYPE, name) or not frappe.has_permission(
		registry.DOCTYPE, "read", doc=name
	):
		return {"name": None, "hidden": True}
	return {
		"name": name,
		"approval_status": frappe.db.get_value(registry.DOCTYPE, name, "approval_status"),
		"lot_count": visible_lot_count(name),
	}


def visible_lot_count(ipd):
	"""Lots of an IPD the user may read; record-level permissions apply."""
	if not frappe.has_permission(LOT, "read"):
		return 0
	return len(frappe.get_list(LOT, filters={"production_detail": ipd}, pluck="name", limit_page_length=0))


def panel_wise(doc):
	"""Read view of the panel matrices; a broken configuration is reported, not raised."""
	if not registry.is_panel_wise(doc):
		return None
	from essdee_yrp.merch.ipd.grids import capture, panel_wise_grids

	result, errors = {}, {}
	capture(result, errors, "panel_wise", lambda: panel_wise_grids(doc, include_saved=True))
	return result["panel_wise"] or ({"error": errors["panel_wise"]} if errors else None)


def field_schema(doc):
	keys = [key for key, (_section, kind) in registry.WRITABLE.items() if kind == registry.SCALAR]
	schema = {}
	for key in (*keys, *registry.READ_ONLY):
		field = registry.meta_field(key)
		if not field:
			continue
		schema[key] = {
			"label": field.label,
			"fieldtype": field.fieldtype,
			"options": field.options,
			"reqd": bool(field.reqd) or key in client_mandatory_fields(doc),
			"read_only": key in registry.READ_ONLY or (key == "item" and not doc.is_new()),
		}
	return schema


def client_mandatory_fields(doc):
	"""Desk `mandatory_depends_on` evaluated for this document."""
	fields = set()
	if not doc.is_new() and not doc.get("is_cloth_item"):
		fields.update(("packing_combo", "packing_attribute_no", "packing_attribute"))
	if doc.get("is_set_item"):
		fields.update(("set_item_attribute", "major_attribute_value"))
	if doc.get("dependent_attribute_mapping") and not doc.is_new():
		fields.update(("pack_in_stage", "pack_out_stage"))
	return fields


def is_approver():
	return bool(set(get_approval_roles()) & set(frappe.get_roles()))


def build_payload(doc, editor=False):
	"""Workspace payload; the editor variant adds field schema and grid skeletons."""
	from essdee_yrp.merch.ipd.capabilities import get_capabilities, get_permissions

	message_start = len(frappe.get_message_log())
	permissions = get_permissions(doc)
	with mapping_memo(doc) as mappings:
		payload = {
			"record": record(doc),
			"permissions": permissions,
			"capabilities": get_capabilities(doc, permissions),
			"values": document_values(doc),
			"context": context(doc, mappings),
			"panel_wise": panel_wise(doc),
			"used_by": used_by(doc),
			"source": source(doc),
		}
		if editor:
			payload["fields"] = field_schema(doc)
			payload.update(editor_grids(doc))
	payload["messages"] = frappe.get_message_log()[message_start:]
	return payload


def editor_grids(doc):
	if doc.is_new() or doc.get("approval_status") == "Approved":
		return {"grids": {}, "grid_errors": {}}
	from essdee_yrp.merch.ipd.grids import active_grid_keys, build_grids

	grids, errors = build_grids(doc, active_grid_keys(doc))
	return {"grids": grids, "grid_errors": errors}

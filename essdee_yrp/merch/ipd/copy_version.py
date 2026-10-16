"""New IPD versions copied from an existing IPD, and their changes against the source."""

import frappe
from frappe import _
from frappe.utils import cstr

from essdee_yrp.ipd_ui import duplicate_ipd
from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.payload import (
	BOM_MAPPING,
	document_attribute_ids,
	key_value,
	prime_attribute_values,
	visible_lot_count,
)

COPY_SECTIONS = ("attributes", "packing", "set_item", "stitching", "cutting", "accessories", "processes")
LOCKED_SECTIONS = ("attributes", "packing", "set_item", "stitching")
COPY_REQUIRES = {"accessories": ("cutting",)}
DROPPED_FIELDS = {
	"cutting": {
		"tables": ("cloth_detail", "cutting_attributes", "cloth_attributes"),
		"json": ("cutting_items_json", "cutting_cloths_json", "panel_wise_consumption_matrix_json"),
		"values": {"enable_panel_wise_consumption_matrix": 0},
	},
	"accessories": {
		"tables": ("item_bom", "accessory_attributes"),
		"json": ("accessory_clothtype_json", "cloth_accessory_json", "stiching_accessory_json"),
		"values": {},
	},
	"processes": {"tables": ("ipd_processes",), "json": ("emblishment_details_json",), "values": {}},
}
SAVEPOINT = "merch_ipd_copy"


def load_source(source):
	doc = frappe.get_doc(registry.DOCTYPE, source)
	doc.check_permission("read")
	frappe.has_permission(registry.DOCTYPE, "create", throw=True)
	return doc


def next_version(item):
	return (
		frappe.db.sql(f"select max(version) from `tab{registry.DOCTYPE}` where item = %s", (item,))[0][0] or 0
	) + 1


def section_meta(doc, section):
	count = {
		"attributes": len(doc.get("item_attributes") or []),
		"packing": len(doc.get("packing_attribute_details") or []),
		"stitching": len(doc.get("stiching_item_details") or []),
		"cutting": len(doc.get("cloth_detail") or []),
		"accessories": len(doc.get("item_bom") or []),
		"processes": len(doc.get("ipd_processes") or []),
	}
	if section == "set_item":
		return doc.get("set_item_attribute") if doc.get("is_set_item") else _("off")
	labels = {
		"attributes": (_("{0} attribute"), _("{0} attributes")),
		"packing": (_("{0} packing row"), _("{0} packing rows")),
		"stitching": (_("{0} panel"), _("{0} panels")),
		"cutting": (_("{0} cloth"), _("{0} cloths")),
		"accessories": (_("{0} BOM row"), _("{0} BOM rows")),
		"processes": (_("{0} process"), _("{0} processes")),
	}
	one, many = labels[section]
	return (one if count[section] == 1 else many).format(count[section])


def copy_options(source):
	doc = load_source(source)
	locked = LOCKED_SECTIONS if not doc.get("is_cloth_item") else COPY_SECTIONS
	return {
		"source": {
			"name": doc.name,
			"item": doc.item,
			"item_name": frappe.db.get_value("Item", doc.item, "item_name"),
			"approval_status": doc.approval_status,
			"version": doc.version,
			"tech_pack_version": doc.tech_pack_version,
			"pattern_version": doc.pattern_version,
			"lot_count": visible_lot_count(doc.name),
		},
		"next_version": next_version(doc.item),
		"sections": [
			{
				"key": section,
				"label": _(registry.SECTION_LABELS[section]),
				"meta": section_meta(doc, section),
				"default": True,
				"requires": list(COPY_REQUIRES.get(section, ())),
				"locked": section in locked,
			}
			for section in COPY_SECTIONS
		],
	}


def close_sections(sections, cloth=False):
	if cloth:
		return set(COPY_SECTIONS)
	unknown = sorted(set(sections) - set(COPY_SECTIONS))
	if unknown:
		frappe.throw(_("Unknown sections: {0}").format(", ".join(unknown)))
	chosen = set(sections) | set(LOCKED_SECTIONS)
	for section, required in COPY_REQUIRES.items():
		if not set(required) <= chosen:
			chosen.discard(section)
	return chosen


def drop_section(doc, section):
	spec = DROPPED_FIELDS[section]
	for table in spec["tables"]:
		doc.set(table, [])
	for key in spec["json"]:
		doc.set(key, "{}")
	for key, value in spec["values"].items():
		doc.set(key, value)


def copy_ipd(source, tech_pack_version, pattern_version, sections, item=None):
	source_doc = load_source(source)
	versions = (cstr(tech_pack_version).strip(), cstr(pattern_version).strip())
	if not all(versions):
		frappe.throw(_("Enter the Tech Pack Version and the Pattern Version for the new version."))
	chosen = close_sections(sections or [], bool(source_doc.get("is_cloth_item")))
	frappe.db.savepoint(SAVEPOINT)
	try:
		name = copy_into_new_version(source, versions, chosen, item)
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		raise
	return {"name": name}


def copy_into_new_version(source, versions, chosen, item):
	doc = frappe.get_doc(registry.DOCTYPE, duplicate_ipd(source, item))
	doc.tech_pack_version, doc.pattern_version = versions
	doc.copied_from = source
	orphans = []
	for section in DROPPED_FIELDS:
		if section not in chosen:
			if section == "accessories":
				orphans = [
					row.attribute_mapping for row in doc.get("item_bom") or [] if row.attribute_mapping
				]
			drop_section(doc, section)
	doc.save()
	for mapping in orphans:
		frappe.delete_doc(BOM_MAPPING, mapping, ignore_permissions=True, force=True)
	return doc.name


def comparable(doc, key):
	value = key_value(doc, key)
	if registry.kind_of(key) == registry.TABLE:
		return [{field: row.get(field) for field in registry.ROW_FIELDS[key]} for row in value]
	return value


def ipd_changes(name):
	doc = frappe.get_doc(registry.DOCTYPE, name)
	doc.check_permission("read")
	source_name = doc.get("copied_from")
	if not source_name or not frappe.db.exists(registry.DOCTYPE, source_name):
		return {"source": None, "changes": []}
	source_doc = frappe.get_doc(registry.DOCTYPE, source_name)
	if not frappe.has_permission(registry.DOCTYPE, "read", doc=source_doc):
		return {"source": None, "changes": []}
	prime_attribute_values([*document_attribute_ids(doc), *document_attribute_ids(source_doc)])
	return {"source": source_name, "changes": list(section_changes(doc, source_doc))}


def section_changes(doc, source_doc):
	for section in registry.sections_for(doc):
		for key in registry.SECTION_FIELDS.get(section, ()):
			before, after = comparable(source_doc, key), comparable(doc, key)
			if before != after:
				field = registry.meta_field(key)
				label = _(field.label) if field and field.label else frappe.unscrub(key)
				yield {"section": section, "field": key, "label": label, "source": before, "current": after}

"""Shared helpers for the Merch IPD DB tests: snapshots, Desk-equivalent saves, users."""

import json
from contextlib import contextmanager

import frappe
from frappe.desk.form.load import run_onload
from yrp.attribute_links import value as attribute_value

from essdee_yrp.merch.ipd.fields import ATTRIBUTE_VALUE, DOCTYPE

META_FIELDS = {
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
}
VOLATILE_FIELDS = {"modified", "modified_by", "_comments", "_liked_by", "_assign", "_user_tags", "_seen"}
SAMPLES = {
	"panel_wise": "Casual Designer Vest - 4-18",
	"set_size_ratio": "441057-O.KIDS CAPYBARA VALENTINES BU-1",
	"set_item": "437807-Ladies Bow Frill-2",
	"standard": "Premium Black Thermal Mens - R/Neck 11900-5",
	"panel_grouped": "Hamic - White Vest RN-1",
	"cloth": "Cotton Poly 58/42 Jersey Fabric-1",
}
NO_VALUE_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold"}


def normalise(value):
	if value == "":
		return None
	if isinstance(value, float) and value.is_integer():
		return int(value)
	return value


def field_value(field, raw):
	if field.fieldtype == "JSON":
		if raw in (None, ""):
			return None
		return json.loads(raw) if isinstance(raw, str) else raw
	if field.fieldtype == "Link" and field.options == ATTRIBUTE_VALUE:
		return attribute_value(raw)
	return normalise(raw)


MAPPING_LINKS = {"mapping", "attribute_mapping", "dependent_attribute_mapping"}


def row_snapshot(row):
	snapshot = {}
	for field in frappe.get_meta(row.doctype).fields:
		if field.fieldtype in NO_VALUE_TYPES:
			continue
		if field.fieldname in MAPPING_LINKS:
			snapshot[field.fieldname] = bool(row.get(field.fieldname))
			continue
		if field.fieldtype in ("Table", "Table MultiSelect"):
			snapshot[field.fieldname] = [row_snapshot(child) for child in row.get(field.fieldname) or []]
		else:
			snapshot[field.fieldname] = field_value(field, row.get(field.fieldname))
	return snapshot


def doc_snapshot(doc):
	data = {}
	for field in frappe.get_meta(DOCTYPE).fields:
		if field.fieldtype in NO_VALUE_TYPES or field.fieldname in VOLATILE_FIELDS:
			continue
		if field.fieldtype in ("Table", "Table MultiSelect"):
			data[field.fieldname] = [row_snapshot(row) for row in doc.get(field.fieldname) or []]
		elif field.fieldname in MAPPING_LINKS:
			data[field.fieldname] = bool(doc.get(field.fieldname))
		else:
			data[field.fieldname] = field_value(field, doc.get(field.fieldname))
	return data


def mapping_snapshot(doc):
	mappings = {}
	for row in doc.get("item_attributes") or []:
		values = frappe.get_all(
			"YRP Item Item Attribute Mapping Value",
			filters={"parent": row.mapping or ""},
			pluck="attribute_value",
			order_by="idx asc",
		)
		mappings[row.attribute] = [attribute_value(value) for value in values]
	return mappings


def bom_mapping_snapshot(doc):
	result = []
	for row in doc.get("item_bom") or []:
		if not row.attribute_mapping:
			result.append(None)
			continue
		values = frappe.get_all(
			"YRP Item BOM Attribute Mapping Value",
			filters={"parent": row.attribute_mapping},
			fields=["index", "type", "attribute", "attribute_value", "quantity"],
			order_by="idx asc",
		)
		attributes = frappe.get_all(
			"YRP Item BOM Attribute Mapping Attribute",
			filters={"parent": row.attribute_mapping},
			fields=["parentfield", "attribute", "same_attribute"],
			order_by="parentfield asc, idx asc",
		)
		result.append(
			{
				"values": [
					{**value, "attribute_value": attribute_value(value.attribute_value)} for value in values
				],
				"attributes": attributes,
			}
		)
	return result


def snapshot(name):
	"""Every stored fact a Desk or web save can change, with Links resolved and JSON parsed."""
	doc = frappe.get_doc(DOCTYPE, name)
	compacting = frappe.db.get_value("SD YRP IPD Compacting", {"item_production_detail": name})
	return {
		"doc": doc_snapshot(doc),
		"mappings": mapping_snapshot(doc),
		"bom_mappings": bom_mapping_snapshot(doc),
		"compacting": row_snapshot(frappe.get_doc("SD YRP IPD Compacting", compacting))
		if compacting
		else None,
		"counts": {
			doctype: frappe.db.count(doctype)
			for doctype in (
				"YRP Item Attribute Value",
				"YRP Item Item Attribute Mapping",
				"YRP Item BOM Attribute Mapping",
				"YRP Item Dependent Attribute Mapping",
			)
		},
	}


def desk_validate_payload(doc):
	"""Apply what the Desk form's validate handler sends for an opened, untouched IPD."""
	from essdee_yrp.ipd_ui import get_stiching_in_stage_attributes
	from essdee_yrp.panel_wise_cloth_mapping import get_panel_wise_cloth_mapping_matrix
	from essdee_yrp.panel_wise_consumption import get_panel_wise_consumption_matrix

	run_onload(doc)
	onload = doc.get("__onload") or {}
	panel_ready = attribute_value(doc.stiching_in_stage) and doc.dependent_attribute
	if doc.enable_panel_wise_consumption_matrix and panel_ready:
		doc.panel_wise_consumption_matrix_json = get_panel_wise_consumption_matrix(doc)["matrix"]
		doc.panel_wise_cloth_mapping_json = get_panel_wise_cloth_mapping_matrix(doc)["matrix"]
	if doc.is_set_item:
		doc.set_item_detail = json.dumps(onload.get("set_item_detail") or {"attributes": [], "values": []})
	if (onload.get("stiching_item_detail") or {}).get("values"):
		doc.stiching_item_detail = json.dumps(onload["stiching_item_detail"])
	if panel_ready:
		choices = get_stiching_in_stage_attributes(
			doc.dependent_attribute_mapping, attribute_value(doc.stiching_in_stage)
		)
		if doc.is_set_item:
			choices.append(doc.set_item_attribute)
		multichecks = (
			["cloth_attributes"]
			if doc.enable_panel_wise_consumption_matrix
			else ["cutting_attributes", "cloth_attributes"]
		)
		if json.loads(doc.accessory_clothtype_json or "{}"):
			multichecks.append("accessory_attributes")
		for table in multichecks:
			checked = {row.attribute for row in doc.get(table) or []}
			doc.set(table, [{"attribute": attribute} for attribute in choices if attribute in checked])
	if doc.dependent_attribute and doc.get("stiching_item_details"):
		doc.marker_details = [
			{"selected": row.group_panels.split(",")} for row in doc.get("cutting_marker_groups") or []
		]


def desk_equivalent_save(name):
	doc = frappe.get_doc(DOCTYPE, name)
	desk_validate_payload(doc)
	doc.save()
	return doc


@contextmanager
def rolled_back(label="merch_ipd_test"):
	frappe.db.savepoint(label)
	try:
		yield
	finally:
		frappe.db.rollback(save_point=label)
		for cache in ("attribute_link_values", "attribute_link_names", "attribute_link_context"):
			if hasattr(frappe.local, cache):
				delattr(frappe.local, cache)


def unapprove(name):
	frappe.db.set_value(
		DOCTYPE, name, {"approval_status": "Not Approved", "approved_by": None}, update_modified=False
	)
	frappe.clear_document_cache(DOCTYPE, name)


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	for role in roles:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	return email


def payload_patch(payload, keys):
	return {key: payload["values"][key] for key in keys if key in payload["values"]}

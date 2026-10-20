from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cstr
from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details
from yrp.yrp.doctype.yrp_item_dependent_attribute_mapping.yrp_item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)

DEPENDENT_MAPPING_DOCTYPE = "YRP Item Dependent Attribute Mapping"


def dependent_details_payload(doc) -> list[dict]:
	"""Rows of the Desk dependent attribute widget, read through yrp."""
	if not (doc.get("dependent_attribute") and doc.get("dependent_attribute_mapping")):
		return []
	attr_list = get_dependent_attribute_details(doc.dependent_attribute_mapping)["attr_list"]
	return [
		{
			"value": value,
			"uom": config.get("uom"),
			"display_name": cstr(config.get("name")),
			"attributes": list(config.get("attributes") or []),
		}
		for value, config in attr_list.items()
	]


def parse_dependent_attribute(values, attributes: list[dict], primary_attribute, doc=None) -> str | None:
	"""Validate the requested Dependent Attribute with the Desk messages."""
	dependent = cstr(values.get("dependent_attribute")).strip() or None
	if not dependent:
		return None
	row = next((row for row in attributes if row["attribute"] == dependent), None)
	if not row:
		frappe.throw(_("Dependent Attribute must be in the standard Variant Attributes table."))
	if not primary_attribute:
		frappe.throw(_("Please set Primary Attribute for this Item."))
	if dependent == primary_attribute:
		frappe.throw(_("Dependent Attribute cannot be the same as the Primary Attribute."))
	has_stages = bool(doc and doc.get("dependent_attribute") == dependent and dependent_details_payload(doc))
	if not row["values"] and not has_stages:
		frappe.throw(_("Please configure values for Dependent Attribute {0}.").format(dependent))
	return dependent


def parse_dependent_details(raw) -> dict | None:
	if raw is None:
		return None
	if isinstance(raw, str):
		raw = frappe.parse_json(raw)
	if not isinstance(raw, list):
		frappe.throw(_("Dependent Attribute details must be a list."))
	return {
		cstr(row.get("value")).strip(): row
		for row in raw
		if isinstance(row, Mapping) and cstr(row.get("value")).strip()
	}


def stage_variant_name_collisions(details) -> list[tuple[str, str]]:
	"""Find stages with the same omitted or displayed name and attribute set."""
	seen, collisions = {}, []
	for stage, row in details.items():
		signature = (cstr(row.get("display_name")).strip(), frozenset(row.get("attributes") or []))
		if signature in seen:
			collisions.append((seen[signature], stage))
		else:
			seen[signature] = stage
	return collisions


def validate_stage_variant_names(details) -> None:
	for first, second in stage_variant_name_collisions(details):
		frappe.throw(
			_(
				"Stages {0} and {1} would create variants with the same name. Give one of them a Display Name or tick different attributes."
			).format(first, second)
		)


def release_dependent_attribute(doc) -> None:
	"""Clear the Dependent Attribute and delete its combination; yrp skips this once variants are gone."""
	doc.dependent_attribute = None
	if doc.get("dependent_attribute_mapping"):
		doc._delete_dependent_attribute_mapping()


def dependent_mapping_modified(doc) -> str | None:
	mapping = doc.get("dependent_attribute_mapping")
	return frappe.db.get_value(DEPENDENT_MAPPING_DOCTYPE, mapping, "modified") if mapping else None


def assert_dependent_mapping_unchanged(doc, expected_modified) -> None:
	"""Reject a save opened before a Desk combination edit, which leaves the Item untouched."""
	mapping = doc.get("dependent_attribute_mapping")
	if not mapping:
		return
	stored = frappe.db.get_value(DEPENDENT_MAPPING_DOCTYPE, mapping, "modified", for_update=True)
	if str(stored) != str(expected_modified or ""):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def apply_dependent_attribute(doc, dependent: str | None, requested_details: dict | None) -> None:
	"""Set the Dependent Attribute once the attribute mappings hold their final values."""
	if dependent and doc.dependent_attribute != dependent:
		doc.dependent_attribute = dependent
		doc.save()
	if dependent:
		sync_dependent_details(doc, requested_details)


def sync_dependent_details(doc, requested_details: dict | None) -> None:
	"""Save stage configuration through yrp; stored stages outlive picklist edits."""
	stored = {row["value"]: row for row in dependent_details_payload(doc)}
	values = list(requested_details) if requested_details is not None else [*stored]
	desired = {
		value: _detail_config(doc, value, _requested_row(doc, value, requested_details, stored))
		for value in values
	}
	if _comparable(desired) != _comparable(_stored_configs(stored)):
		update_dependent_attribute_details(doc.dependent_attribute_mapping, {"attr_list": desired})


def _requested_row(doc, value, requested_details, stored) -> Mapping:
	default = {"uom": doc.stock_uom, "display_name": "", "attributes": [doc.primary_attribute]}
	return (requested_details or {}).get(value) or stored.get(value) or default


def _detail_config(doc, value: str, row: Mapping) -> dict:
	uom = cstr(row.get("uom")).strip()
	if not uom or not frappe.db.exists("UOM", uom):
		frappe.throw(_("Select a valid UOM for {0} {1}.").format(doc.dependent_attribute, value))
	allowed = {attribute.attribute for attribute in doc.get("attributes") or []} - {doc.dependent_attribute}
	attributes = list(dict.fromkeys(row.get("attributes") or []))
	for attribute in attributes:
		if attribute not in allowed:
			frappe.throw(_("{0} is not a Variant Attribute of this Item.").format(attribute))
	return {"uom": uom, "name": cstr(row.get("display_name")).strip(), "attributes": attributes}


def _stored_configs(stored: dict) -> dict:
	return {
		value: {"uom": row["uom"], "name": row["display_name"], "attributes": row["attributes"]}
		for value, row in stored.items()
	}


def _comparable(configs: dict) -> dict:
	return {
		value: (config["uom"], cstr(config["name"]), frozenset(config["attributes"]))
		for value, config in configs.items()
	}

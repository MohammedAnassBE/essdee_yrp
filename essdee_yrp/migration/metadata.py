"""Targeted metadata sync required before Production API migration rehearsals."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.config import get_migration_settings
from essdee_yrp.migration.live import (
	F15SourceBridge,
	_validate_live_target_metadata,
	build_live_schema_analysis,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_FIELD_FIXTURE = PACKAGE_ROOT / "fixtures" / "custom_field.json"
PROPERTY_SETTER_FIXTURE = PACKAGE_ROOT / "fixtures" / "property_setter.json"
MODULE_TO_RELOAD_PACKAGE = {
	"Essdee YRP": "essdee_yrp",
	"YRP": "yrp",
}
NON_DEFINITION_KEYS = {
	"creation",
	"docstatus",
	"doctype",
	"dt",
	"idx",
	"modified",
	"modified_by",
	"name",
	"owner",
}


def sync_migration_metadata() -> dict:
	"""Load only migration schemas and their reviewed field/property overlays."""

	settings = get_migration_settings()
	if frappe.local.site != settings.target_site:
		raise MigrationError(f"Metadata sync must run on {settings.target_site}")
	plan, _payload = build_live_schema_analysis(
		settings, F15SourceBridge(settings)
	)
	target_doctypes = set(plan.target_schemas)
	reloaded = []
	unresolved = []

	# Load child schemas first so parent Table fields never point at an
	# unregistered DocType during this targeted reload.
	reload_order = sorted(
		target_doctypes,
		key=lambda doctype: (
			not bool(plan.target_schemas[doctype].get("istable")),
			doctype,
		),
	)
	for doctype in reload_order:
		schema = plan.target_schemas[doctype]
		module = str(schema.get("module") or "")
		package = MODULE_TO_RELOAD_PACKAGE.get(module)
		if not package:
			if not frappe.db.exists("DocType", doctype):
				unresolved.append(f"{doctype}: unsupported module {module!r}")
			continue
		frappe.reload_doc(package, "doctype", frappe.scrub(doctype), force=True)
		reloaded.append(doctype)

	custom_fields = defaultdict(list)
	for row in json.loads(CUSTOM_FIELD_FIXTURE.read_text()):
		doctype = row.get("dt")
		if doctype not in target_doctypes or row.get("module") != "Essdee YRP":
			continue
		definition = {
			key: value for key, value in row.items() if key not in NON_DEFINITION_KEYS
		}
		custom_fields[str(doctype)].append(definition)
	create_custom_fields(dict(custom_fields), update=True)

	property_setters = []
	for row in json.loads(PROPERTY_SETTER_FIXTURE.read_text()):
		if row.get("doc_type") not in target_doctypes:
			continue
		name = row["name"]
		if frappe.db.exists("Property Setter", name):
			doc = frappe.get_doc("Property Setter", name)
			doc.update(
				{
					key: value
					for key, value in row.items()
					if key not in NON_DEFINITION_KEYS
				}
			)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(row).insert(ignore_permissions=True)
		property_setters.append(name)

	frappe.db.commit()
	frappe.clear_cache()
	if unresolved:
		raise MigrationError("Unresolved migration metadata: " + "; ".join(unresolved))
	_validate_live_target_metadata(plan)
	return {
		"status": "Ready",
		"reloaded_doctypes": len(reloaded),
		"reloaded_doctype_names": reloaded,
		"synced_custom_fields": sum(len(rows) for rows in custom_fields.values()),
		"synced_property_setters": len(property_setters),
	}

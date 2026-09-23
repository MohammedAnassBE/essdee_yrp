"""Repository-schema planner shared by CLI and MRP Data Migration.

This module reads only version-controlled JSON files. It has no Frappe imports
and cannot connect to either the source or target site.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from essdee_yrp.migration.engine import DocTypeRule, MigrationPlan, build_plan
from essdee_yrp.migration.rules import DOCTYPE_RENAMES, RULES
from essdee_yrp.migration.transformers import (
	POST_TRANSFORMERS,
	TRANSFORMERS,
	VALUE_TRANSFORMERS,
)
from essdee_yrp.migration.schema import (
	apply_custom_field_fixture,
	apply_declared_stock_dimensions,
	apply_property_setter_fixture,
	load_schema_index,
)


APP_ROOT = Path(__file__).resolve().parents[2]
BENCH_ROOT = APP_ROOT.parents[1]
DEFAULT_SOURCE_ROOT = BENCH_ROOT.parent / "frappe-15" / "apps" / "production_api"
DEFAULT_TARGET_ROOTS = (
	BENCH_ROOT / "apps" / "erpnext",
	BENCH_ROOT / "apps" / "yrp",
	APP_ROOT,
)
SOURCE_SMS_SCHEMA_ROOT = (
	BENCH_ROOT.parent
	/ "frappe-15"
	/ "apps"
	/ "frappe"
	/ "frappe"
	/ "core"
	/ "doctype"
)
TARGET_SMS_SCHEMA_ROOT = (
	BENCH_ROOT / "apps" / "frappe" / "frappe" / "core" / "doctype"
)
TARGET_FRAPPE_ROOT = BENCH_ROOT / "apps" / "frappe" / "frappe"


def _frappe_doctype_root(module: str, folder: str) -> Path:
	return TARGET_FRAPPE_ROOT / module / "doctype" / folder


# Target metadata for the owner-approved Frappe live-data phase. These schemas
# are verification targets only; they are intentionally not added to the main
# Production API source plan, whose reset owns entire custom-app tables.
TARGET_APPROVED_FRAPPE_SCHEMA_ROOTS = tuple(
	_frappe_doctype_root(module, folder)
	for module, folder in (
		# Complete Address/Contact business inventories are migrated by the
		# supporting-master phase rather than the Production API schema graph.
		# Keep their parent and child schemas in the shared verification index so
		# SQL read-back can verify every selected value and child identity.
		("contacts", "address"),
		("contacts", "contact"),
		("core", "dynamic_link"),
		("contacts", "contact_email"),
		("contacts", "contact_phone"),
		("contacts", "address_template"),
		("core", "block_module"),
		("core", "custom_docperm"),
		("desk", "dashboard_settings"),
		("core", "defaultvalue"),
		("email", "email_account"),
		("email", "email_domain"),
		("email", "email_unsubscribe"),
		("email", "imap_folder"),
		("printing", "letter_head"),
		("desk", "list_view_settings"),
		("core", "module_profile"),
		("desk", "note"),
		("desk", "note_seen_by"),
		("desk", "notification_type"),
		("desk", "notification_type_preference"),
		("desk", "notification_settings"),
		("desk", "notification_subscribed_document"),
		("printing", "print_settings"),
		("core", "role"),
		("core", "system_settings"),
		("core", "user"),
		("core", "user_email"),
		("core", "user_social_login"),
		("core", "has_role"),
		("website", "website_settings"),
		("website", "top_bar_item"),
		("website", "website_route_redirect"),
		("desk", "workspace"),
		("desk", "workspace_chart"),
		("desk", "workspace_shortcut"),
		("desk", "workspace_link"),
		("desk", "workspace_quick_list"),
		("desk", "workspace_number_card"),
		("desk", "workspace_custom_block"),
	)
)
# Only frappe_tools configuration is part of the auxiliary one-pass
# source-data contract.  Spine is installed with clean defaults; all of its
# source data is excluded by owner decision.
SOURCE_AUXILIARY_SCHEMA_ROOTS = (
	BENCH_ROOT.parent / "frappe-15" / "apps" / "frappe_tools" / "frappe_tools"
	/ "frappe_tools" / "doctype" / "document_scanner_settings",
	BENCH_ROOT.parent / "frappe-15" / "apps" / "frappe_tools" / "frappe_tools"
	/ "frappe_tools" / "doctype" / "document_scanner_settings_items",
	BENCH_ROOT.parent / "frappe-15" / "apps" / "frappe_tools" / "frappe_tools"
	/ "frappe_tools" / "doctype" / "document_scanner_server_setting",
	BENCH_ROOT.parent / "frappe-15" / "apps" / "frappe_tools" / "frappe_tools"
	/ "frappe_tools" / "doctype" / "log_file_downloader",
)
TARGET_AUXILIARY_SCHEMA_ROOTS = (
	BENCH_ROOT / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
	/ "doctype" / "document_scanner_settings",
	BENCH_ROOT / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
	/ "doctype" / "document_scanner_settings_items",
	BENCH_ROOT / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
	/ "doctype" / "document_scanner_server_setting",
	BENCH_ROOT / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
	/ "doctype" / "log_file_downloader",
)
TARGET_PREFIXES_BY_MODULE = {
	"YRP": "YRP ",
	"YRP Stock": "YRP ",
	"Essdee YRP": "SD YRP ",
}

# These source schemas come from Frappe itself. Their unprefixed identities
# must win over a mechanically de-prefixed custom target with the same suffix.
SOURCE_IDENTITY_DOCTYPES = {
	"SMS Settings",
}

# These fields are installed by India Compliance, which is a required app on
# the combined target site. Its definitions are Python constants rather than
# fixture JSON, so the repository-only planner overlays the same field contract
# and the live preflight still verifies that the fields really exist.
INDIA_COMPLIANCE_TARGET_FIELDS = {
	"Item": (
		{"fieldname": "is_ineligible_for_itc", "fieldtype": "Check"},
	),
	"Supplier": (
		{"fieldname": "gstin", "fieldtype": "Autocomplete"},
		{"fieldname": "pan", "fieldtype": "Data"},
	),
}

DEFAULT_STOCK_DOCTYPES = [
	'YRP Stock Ledger Entry',
	'YRP Bin',
	'YRP Stock Entry Detail',
	'YRP Stock Update Detail',
	'YRP Stock Reconciliation Item',
	'Purchase Order Item',
	'YRP Stock Reservation Entry',
	'YRP Repost Item Valuation',
	'YRP Work Order Deliverables',
	'YRP Work Order Receivables',
	'YRP Delivery Challan Item',
	'YRP Goods Received Note Item',
	'YRP Inspection Entry Item',
]
DEFAULT_OPERATIONAL_DOCTYPES = [
	'YRP Work Order',
	'Purchase Order',
	'YRP Delivery Challan',
	'YRP Goods Received Note',
	'YRP Process Cost',
]
DEFAULT_ESSDEE_DIMENSIONS = [
	{
		"dimension_doctype": 'SD YRP Lot',
		"fieldname": "lot",
		"label": "Lot",
		"mandatory": 1,
		"is_production_group": 1,
	},
	{
		"dimension_doctype": 'YRP Received Type',
		"fieldname": "received_type",
		"label": "Received Type",
		"mandatory": 1,
		"is_production_group": 0,
	},
]


def build_schema_analysis(
	*,
	source_root: str | Path = DEFAULT_SOURCE_ROOT,
	target_roots: list[str | Path] | tuple[str | Path, ...] = DEFAULT_TARGET_ROOTS,
	source_schemas: Mapping[str, Mapping[str, Any]] | None = None,
	dimensions: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = DEFAULT_ESSDEE_DIMENSIONS,
	stock_doctypes: list[str] | tuple[str, ...] = DEFAULT_STOCK_DOCTYPES,
	operational_doctypes: list[str] | tuple[str, ...] = DEFAULT_OPERATIONAL_DOCTYPES,
	source_site: str | None = None,
	target_site: str | None = None,
) -> tuple[MigrationPlan, dict[str, Any]]:
	"""Build the source-to-target schema analysis.

	Repository metadata remains useful for offline review. Live migration runs
	pass the F15 bridge's effective schemas so source-side migrations and
	Property Setters cannot hide fields from the contract.
	"""

	# Production API stores populated SMS Settings.parameters rows even though
	# both parent and child schemas are provided by Frappe Core. The approved
	# auxiliary app contributes only the explicit frappe_tools schemas above.
	if source_schemas is None:
		source_schema_index = load_schema_index(
			source_root,
			SOURCE_SMS_SCHEMA_ROOT / "sms_settings",
			SOURCE_SMS_SCHEMA_ROOT / "sms_parameter",
			*SOURCE_AUXILIARY_SCHEMA_ROOTS,
		)
	else:
		source_schema_index = {
			str(name): dict(schema) for name, schema in source_schemas.items()
		}
	target_schemas = load_schema_index(
		*target_roots,
		TARGET_SMS_SCHEMA_ROOT / "sms_settings",
		TARGET_SMS_SCHEMA_ROOT / "sms_parameter",
		*TARGET_AUXILIARY_SCHEMA_ROOTS,
		*TARGET_APPROVED_FRAPPE_SCHEMA_ROOTS,
	)
	target_schemas = _apply_external_target_fields(target_schemas)
	fixture_roots = (
		BENCH_ROOT / "apps" / "yrp" / "yrp" / "fixtures",
		APP_ROOT / "essdee_yrp" / "fixtures",
	)
	for fixture_root in fixture_roots:
		custom_fields = fixture_root / "custom_field.json"
		property_setters = fixture_root / "property_setter.json"
		if custom_fields.is_file():
			target_schemas = apply_custom_field_fixture(target_schemas, custom_fields)
		if property_setters.is_file():
			target_schemas = apply_property_setter_fixture(
				target_schemas, property_setters
			)
	target_schemas = apply_declared_stock_dimensions(
		target_schemas,
		dimensions=dimensions,
		stock_doctypes=stock_doctypes,
		operational_doctypes=operational_doctypes,
	)
	doctype_map = _expanded_doctype_map(target_schemas)
	rules = _rules_for_commonized_schema(
		source_schema_index,
		target_schemas,
		doctype_map,
	)

	plan = build_plan(
		source_schema_index,
		target_schemas,
		rules=rules,
		doctype_map=doctype_map,
		transformers=TRANSFORMERS,
		value_transformers=VALUE_TRANSFORMERS,
		post_transformers=POST_TRANSFORMERS,
	)
	payload = _plan_payload(
		plan,
		len(source_schema_index),
		len(target_schemas),
		source_site=source_site,
		target_site=target_site,
	)
	return plan, payload


def _apply_external_target_fields(
	target_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
	result = {name: dict(schema) for name, schema in target_schemas.items()}
	for doctype, declared_fields in INDIA_COMPLIANCE_TARGET_FIELDS.items():
		schema = result.get(doctype)
		if not schema:
			continue
		fields = [dict(field) for field in schema.get("fields") or []]
		existing = {field.get("fieldname") for field in fields}
		fields.extend(
			dict(field)
			for field in declared_fields
			if field["fieldname"] not in existing
		)
		result[doctype] = {**schema, "fields": fields}
	return result


def _rules_for_commonized_schema(
	source_schemas: Mapping[str, Mapping[str, Any]],
	target_schemas: Mapping[str, Mapping[str, Any]],
	doctype_map: Mapping[str, str],
) -> dict[str, DocTypeRule]:
	"""Add the reviewed legacy attribute-value Link -> ERP Data conversion.

	Production API used ``Item Attribute Value`` as a standalone Link master.
	ERPNext stores the exact value string in Data fields. Apply that one
	semantic conversion wherever both schemas prove this exact shape; all other
	type/option differences remain strict planner blockers.
	"""

	rules = dict(RULES)
	for source_doctype, source_schema in source_schemas.items():
		rule = rules.get(
			source_doctype,
			DocTypeRule(target=doctype_map.get(source_doctype, source_doctype)),
		)
		if rule.custom_transformer:
			continue
		target_doctype = rule.target or doctype_map.get(source_doctype, source_doctype)
		target_schema = target_schemas.get(target_doctype)
		if not target_schema:
			continue
		target_fields = {
			str(field["fieldname"]): field
			for field in target_schema.get("fields") or []
			if field.get("fieldname")
		}
		allowed_type_changes = set(rule.allowed_type_changes)
		value_transformers = dict(rule.value_transformers)
		changed = False
		for source_field in source_schema.get("fields") or []:
			source_fieldname = source_field.get("fieldname")
			if (
				not source_fieldname
				or source_field.get("fieldtype") != "Link"
				or source_field.get("options") != "Item Attribute Value"
			):
				continue
			target_fieldname = rule.field_map.get(source_fieldname, source_fieldname)
			target_field = target_fields.get(target_fieldname)
			if not target_field or target_field.get("fieldtype") != "Data":
				continue
			allowed_type_changes.add(("Link", "Data"))
			value_transformers[source_fieldname] = "attribute_value_link_to_data"
			changed = True
		if changed:
			rules[source_doctype] = replace(
				rule,
				allowed_type_changes=frozenset(allowed_type_changes),
				value_transformers=value_transformers,
			)
	return rules


def _expanded_doctype_map(
	target_schemas: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
	"""Map every original app-owned source name to its namespaced target.

	Explicit historical renames win over the mechanical owner prefix. This is
	important for cases such as ``GRN Deliverable``, whose reviewed target was
	already named ``YRP GRN Deliverable`` before the namespace migration.
	"""

	doctype_map = {}
	for target_name, schema in target_schemas.items():
		prefix = TARGET_PREFIXES_BY_MODULE.get(str(schema.get("module") or ""))
		if prefix and target_name.startswith(prefix):
			doctype_map[target_name.removeprefix(prefix)] = target_name
	doctype_map.update(DOCTYPE_RENAMES)
	doctype_map.update({doctype: doctype for doctype in SOURCE_IDENTITY_DOCTYPES})
	return doctype_map


def _plan_payload(
	plan: MigrationPlan,
	source_doctype_count: int,
	target_doctype_count: int,
	*,
	source_site: str | None,
	target_site: str | None,
) -> dict[str, Any]:
	kinds = Counter(spec.kind for spec in plan.specs.values())
	group_by_doctype = {
		doctype: group_number
		for group_number, group in enumerate(plan.dependency_groups, start=1)
		for doctype in group
	}
	details = []
	for source_doctype, spec in sorted(
		plan.specs.items(), key=lambda row: (group_by_doctype[row[0]], row[0])
	):
		changed_field_map = {
			source: target
			for source, target in spec.field_map.items()
			if source != target
		}
		details.append(
			{
				"source_doctype": source_doctype,
				"target_doctype": spec.target,
				"migration_kind": spec.kind.title(),
				"dependency_group": group_by_doctype[source_doctype],
				"is_child": spec.is_child,
				"status": "Blocked" if spec.issues else "Ready",
				"issues": list(spec.issues),
				"dependencies": list(spec.dependencies),
				"field_map": changed_field_map,
				"table_option_map": dict(spec.table_option_map),
				"ignored_fields": dict(spec.ignored_fields),
				"custom_transformer": spec.custom_transformer,
				"post_transformer": spec.post_transformer,
				"value_transformers": dict(spec.value_transformers),
			}
		)
	return {
		"mode": "schema-only",
		"source_site": source_site,
		"target_site": target_site,
		"reads_site_data": False,
		"writes_site_data": False,
		"source_doctypes": source_doctype_count,
		"target_doctypes": target_doctype_count,
		"migration_kinds": dict(sorted(kinds.items())),
		"ready": plan.ready,
		"issue_count": len(plan.issues),
		"issues": list(plan.issues),
		"dependency_groups": [list(group) for group in plan.dependency_groups],
		"doctype_details": details,
	}

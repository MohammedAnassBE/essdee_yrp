"""Repository-schema planner shared by CLI and MRP Data Migration.

This module reads only version-controlled JSON files. It has no Frappe imports
and cannot connect to either the source or target site.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from essdee_yrp.migration.engine import MigrationPlan, build_plan
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
DEFAULT_TARGET_ROOTS = (BENCH_ROOT / "apps" / "yrp", APP_ROOT)
SOURCE_SMS_PARAMETER_ROOT = (
	BENCH_ROOT.parent
	/ "frappe-15"
	/ "apps"
	/ "frappe"
	/ "frappe"
	/ "core"
	/ "doctype"
	/ "sms_parameter"
)
TARGET_SMS_PARAMETER_ROOT = (
	BENCH_ROOT / "apps" / "frappe" / "frappe" / "core" / "doctype" / "sms_parameter"
)
TARGET_PREFIXES_BY_MODULE = {
	"YRP": "YRP ",
	"YRP Stock": "YRP ",
	"Essdee YRP": "SD YRP ",
}

DEFAULT_STOCK_DOCTYPES = [
	'YRP Stock Ledger Entry',
	'YRP Bin',
	'YRP Stock Entry Detail',
	'YRP Stock Update Detail',
	'YRP Stock Reconciliation Item',
	'YRP Purchase Order Item',
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
	'YRP Purchase Order',
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

	# Notification Template owns SMS Parameter rows even though the child schema
	# is provided by Frappe Core. Include that one explicit supporting schema;
	# no other upstream DocTypes are in the Production API migration scope.
	if source_schemas is None:
		source_schema_index = load_schema_index(source_root, SOURCE_SMS_PARAMETER_ROOT)
	else:
		source_schema_index = {
			str(name): dict(schema) for name, schema in source_schemas.items()
		}
	target_schemas = load_schema_index(*target_roots, TARGET_SMS_PARAMETER_ROOT)
	custom_fields = APP_ROOT / "essdee_yrp" / "fixtures" / "custom_field.json"
	property_setters = APP_ROOT / "essdee_yrp" / "fixtures" / "property_setter.json"
	if custom_fields.is_file():
		target_schemas = apply_custom_field_fixture(target_schemas, custom_fields)
	if property_setters.is_file():
		target_schemas = apply_property_setter_fixture(target_schemas, property_setters)
	target_schemas = apply_declared_stock_dimensions(
		target_schemas,
		dimensions=dimensions,
		stock_doctypes=stock_doctypes,
		operational_doctypes=operational_doctypes,
	)
	doctype_map = _expanded_doctype_map(target_schemas)

	plan = build_plan(
		source_schema_index,
		target_schemas,
		rules=RULES,
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

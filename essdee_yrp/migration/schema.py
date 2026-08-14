"""Filesystem-only DocType schema inventory helpers."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class SchemaError(RuntimeError):
	pass


def load_schema_index(*roots: str | Path) -> dict[str, dict[str, Any]]:
	"""Load DocType JSON without importing or connecting to Frappe."""

	index: dict[str, dict[str, Any]] = {}
	locations: dict[str, Path] = {}
	for root_value in roots:
		root = Path(root_value).expanduser().resolve()
		if not root.is_dir():
			raise SchemaError(f"schema root does not exist: {root}")
		for path in sorted(root.rglob("*.json")):
			try:
				value = json.loads(path.read_text())
			except (OSError, json.JSONDecodeError):
				continue
			if not isinstance(value, dict) or value.get("doctype") != "DocType" or not value.get("name"):
				continue
			name = str(value["name"])
			if name in index:
				if _data_signature(index[name]) != _data_signature(value):
					raise SchemaError(
						f"conflicting DocType {name!r}: {locations[name]} and {path}"
					)
				continue
			index[name] = value
			locations[name] = path
	return index


def apply_custom_field_fixture(
	schemas: dict[str, dict[str, Any]], fixture_path: str | Path
) -> dict[str, dict[str, Any]]:
	"""Overlay packaged Custom Fields; never reads live site metadata."""

	path = Path(fixture_path).expanduser().resolve()
	rows = json.loads(path.read_text())
	result = deepcopy(schemas)
	for row in rows:
		doctype = row.get("dt")
		fieldname = row.get("fieldname")
		if not doctype or not fieldname or doctype not in result:
			continue
		fields = list(result[doctype].get("fields") or [])
		fields = [field for field in fields if field.get("fieldname") != fieldname]
		fields.append(
			{
				key: deepcopy(value)
				for key, value in row.items()
				if key
				not in {
					"doctype",
					"dt",
					"name",
					"owner",
					"creation",
					"modified",
					"modified_by",
				}
			}
		)
		result[doctype]["fields"] = fields
	return result


def apply_property_setter_fixture(
	schemas: dict[str, dict[str, Any]], fixture_path: str | Path
) -> dict[str, dict[str, Any]]:
	"""Apply field-level packaged Property Setters relevant to data shape."""

	path = Path(fixture_path).expanduser().resolve()
	rows = json.loads(path.read_text())
	result = deepcopy(schemas)
	for row in rows:
		doctype = row.get("doc_type")
		fieldname = row.get("field_name")
		property_name = row.get("property")
		if not doctype or not fieldname or not property_name or doctype not in result:
			continue
		for field in result[doctype].get("fields") or ():
			if field.get("fieldname") == fieldname:
				field[property_name] = _coerce_property_value(row.get("value"), row.get("property_type"))
				break
	return result


def apply_declared_stock_dimensions(
	schemas: dict[str, dict[str, Any]],
	*,
	dimensions: list[dict[str, Any]],
	stock_doctypes: list[str],
	operational_doctypes: list[str],
) -> dict[str, dict[str, Any]]:
	"""Overlay code-owned dimension fields without consulting target site data."""

	result = deepcopy(schemas)
	for dimension in dimensions:
		targets = list(stock_doctypes)
		if dimension.get("is_production_group"):
			targets.extend(operational_doctypes)
		for doctype in targets:
			if doctype not in result:
				continue
			fieldname = str(dimension["fieldname"])
			fields = list(result[doctype].get("fields") or [])
			if any(field.get("fieldname") == fieldname for field in fields):
				continue
			fields.append(
				{
					"fieldname": fieldname,
					"fieldtype": "Link",
					"label": dimension.get("label") or fieldname.replace("_", " ").title(),
					"options": dimension["dimension_doctype"],
					"reqd": int(bool(dimension.get("mandatory"))),
					"description": "Code-declared migration profile; live metadata must be reverified",
				}
			)
			result[doctype]["fields"] = fields
	return result


def _coerce_property_value(value: Any, property_type: str | None) -> Any:
	if property_type in {"Check", "Int"}:
		try:
			return int(value)
		except (TypeError, ValueError):
			return value
	if property_type in {"Float", "Currency", "Percent"}:
		try:
			return float(value)
		except (TypeError, ValueError):
			return value
	return value


def _data_signature(schema: dict[str, Any]) -> tuple[Any, ...]:
	return (
		bool(schema.get("istable")),
		bool(schema.get("issingle")),
		tuple(
			(
				field.get("fieldname"),
				field.get("fieldtype"),
				field.get("options"),
			)
			for field in schema.get("fields") or ()
		),
	)

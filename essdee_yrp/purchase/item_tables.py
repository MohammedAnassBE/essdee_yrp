from collections.abc import Mapping
from math import isfinite

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from essdee_yrp.purchase.item_dependent_attribute import (
	dependent_details_payload,
	parse_dependent_details,
)

SCALAR_FIELDS = (
	"secondary_unit_of_measure",
	"po_excess_allowed_percentage",
	"is_cloth_item",
	"product_category",
	"is_ineligible_for_itc",
)
TABLE_COLUMNS = {
	"uoms": ("uom", "conversion_factor"),
	"additional_parameters": ("additional_parameter_key", "additional_parameter_value"),
	"yarn_ratio_details": ("yarn_item", "ratio"),
}
TABLE_KEYS = {
	**{field: columns[0] for field, columns in TABLE_COLUMNS.items()},
	"categories": "item_category",
}


def table_field_schemas() -> dict:
	fields = {}
	item_meta = frappe.get_meta("Item")
	for fieldname, columns in {**TABLE_COLUMNS, "categories": ("item_category",)}.items():
		field = item_meta.get_field(fieldname)
		meta = frappe.get_meta(field.options)
		label_field = item_meta.get_field("uom_conversion_details_column") if fieldname == "uoms" else field
		fields[fieldname] = {
			"label": label_field.label,
			"columns": {column: {"label": meta.get_field(column).label} for column in columns},
		}
	return fields


def table_values(doc=None) -> dict:
	values = {field: doc.get(field) if doc else None for field in SCALAR_FIELDS}
	for fieldname, columns in TABLE_COLUMNS.items():
		values[fieldname] = (
			[{key: row.get(key) for key in ("name", *columns)} for row in (doc.get(fieldname) or [])]
			if doc
			else []
		)
	values["categories"] = [row.item_category for row in doc.get("categories") or []] if doc else []
	return values


def _rows(raw, fieldname) -> list:
	if isinstance(raw, str):
		raw = frappe.parse_json(raw)
	if not isinstance(raw, list) or any(not isinstance(row, Mapping) for row in raw):
		frappe.throw(
			_("{0} must be a list of rows.").format(frappe.get_meta("Item").get_field(fieldname).label)
		)
	return raw


def _number(value, message) -> float:
	try:
		number = float(value or 0)
	except TypeError, ValueError:
		frappe.throw(message)
	if not isfinite(number):
		frappe.throw(message)
	return number


def _parse_uoms(raw, stock_uom) -> list[dict]:
	rows, seen = [], set()
	for index, row in enumerate(_rows(raw, "uoms"), 1):
		uom = cstr(row.get("uom")).strip()
		if not uom or not frappe.db.exists("UOM", uom):
			frappe.throw(_("Select a valid UOM in UOM Conversion Details row {0}.").format(index))
		if uom in seen:
			frappe.throw(
				_("Unit of Measure {0} has been entered more than once in Conversion Factor Table").format(
					uom
				)
			)
		seen.add(uom)
		message = _("Conversion factor for UOM {0} must be greater than 0.").format(uom)
		factor = _number(row.get("conversion_factor"), message)
		if uom == stock_uom and factor != 1:
			frappe.throw(
				_("Conversion factor for default Unit of Measure must be 1 in row {0}").format(index)
			)
		if factor <= 0:
			frappe.throw(message)
		rows.append({"uom": uom, "conversion_factor": factor})
	if stock_uom not in seen:
		rows.insert(0, {"uom": stock_uom, "conversion_factor": 1})
	return rows


def _parse_parameters(raw) -> list[dict]:
	rows, seen = [], set()
	for index, row in enumerate(_rows(raw, "additional_parameters"), 1):
		key = cstr(row.get("additional_parameter_key")).strip()
		value = cstr(row.get("additional_parameter_value")).strip() or None
		key = frappe.db.get_value("YRP Additional Parameter Key", {"name": key}, "name") if key else None
		if not key:
			frappe.throw(_("Row {0}: select an Additional Parameter Key.").format(index))
		if key.casefold() in seen:
			frappe.throw(_("Additional Parameter Key {0} is repeated.").format(key))
		seen.add(key.casefold())
		value_key = value and cstr(frappe.db.get_value("YRP Additional Parameter Value", value, "key"))
		if value and value_key.casefold() != key.casefold():
			frappe.throw(_("Additional Parameter Value {0} does not belong to Key {1}.").format(value, key))
		rows.append({"additional_parameter_key": key, "additional_parameter_value": value})
	return rows


def parse_item_tables(values, stock_uom, doc=None) -> dict:
	"""Validate the editor's final tables before any mapping writes."""
	final = {**table_values(doc), **values}
	parsed = {field: final.get(field) or None for field in SCALAR_FIELDS}
	message = _("PO Excess Allowed Percentage must be greater than or equal to 0.")
	parsed["po_excess_allowed_percentage"] = _number(final.get("po_excess_allowed_percentage"), message)
	if parsed["po_excess_allowed_percentage"] < 0:
		frappe.throw(message)
	for field in ("is_cloth_item", "is_ineligible_for_itc"):
		parsed[field] = cint(final.get(field))
	parsed["uoms"] = _parse_uoms(final.get("uoms") or [], stock_uom)
	parsed["additional_parameters"] = _parse_parameters(final.get("additional_parameters") or [])
	parsed["yarn_ratio_details"] = [
		{column: row.get(column) for column in TABLE_COLUMNS["yarn_ratio_details"]}
		for row in _rows(final.get("yarn_ratio_details") or [], "yarn_ratio_details")
	]
	parsed["categories"] = _parse_categories(final.get("categories") or [])
	return parsed


def _parse_categories(raw) -> list[dict]:
	if not isinstance(raw, list) or any(not isinstance(value, str) or not value for value in raw):
		frappe.throw(_("YRP Categories must be a list of Item Categories."))
	return [{"item_category": value} for value in dict.fromkeys(raw)]


def final_dependent_details(values, attributes, dependent, stock_uom, doc=None) -> dict:
	"""Resolve the same defaults and retained rows as the Desk combination."""
	if not dependent:
		return {}
	requested = parse_dependent_details(values.get("dependent_details")) or {}
	stored = _stored_details(doc, dependent)
	picklist = next(row["values"] for row in attributes if row["attribute"] == dependent)
	dependent_values = [*stored, *(v for v in requested if v in picklist and v not in stored)] if stored else picklist
	allowed = {row["attribute"] for row in attributes} - {dependent}
	default = {"uom": stock_uom, "attributes": [values.get("primary_attribute")]}
	rows = {value: requested.get(value) or stored.get(value) or default for value in dependent_values}
	_validate_details(rows, dependent, allowed)
	return rows


def _stored_details(doc, dependent) -> dict:
	if not doc or doc.dependent_attribute != dependent:
		return {}
	return {row["value"]: row for row in dependent_details_payload(doc)}


def _validate_details(rows, dependent, allowed) -> None:
	for value, row in rows.items():
		if not row.get("uom") or not frappe.db.exists("UOM", row["uom"]):
			frappe.throw(_("Select a valid UOM for {0} {1}.").format(dependent, value))
		if not row.get("attributes"):
			frappe.throw(_("Stage {0} must use at least one attribute.").format(value))
		for attribute in row.get("attributes") or []:
			if attribute not in allowed:
				frappe.throw(_("{0} is not a Variant Attribute of this Item.").format(attribute))


def validate_stage_conversions(details, uoms, stock_uom) -> None:
	positive = {row["uom"] for row in uoms if row["conversion_factor"] > 0}
	for stage, row in details.items():
		uom = row.get("uom")
		if uom != stock_uom and uom not in positive:
			frappe.throw(
				_(
					"Stage {0} uses UOM {1}, but UOM Conversion Details has no {1} → {2} conversion. Add a {1} conversion first."
				).format(stage, uom, stock_uom)
			)


def apply_item_tables(doc, parsed) -> None:
	for field in SCALAR_FIELDS:
		doc.set(field, parsed[field])
	for field, key in TABLE_KEYS.items():
		_replace_rows(doc, field, key, parsed[field])


def _replace_rows(doc, field, key, requested) -> None:
	"""Keep child identities and unedited columns where the natural key matches."""
	existing = {row.get(key): row for row in reversed(doc.get(field) or [])}
	rows = []
	for index, values in enumerate(requested, 1):
		row = existing.pop(values[key], None)
		if row is not None:
			row.update(values)
			row.idx = index
		rows.append(row if row is not None else values)
	doc.set(field, rows)


def finished_goods_packing(item):
	if not item:
		return None
	pieces = frappe.db.get_value("SD YRP FG Item Master", {"item": item}, "pcs_per_box")
	return pieces if flt(pieces) > 0 else None


@frappe.whitelist()
def search_item_editor_links(doctype, txt="", key=None) -> list[dict]:
	"""Search Item-owned setup masters under Item editor permission."""
	frappe.has_permission("Item", ptype="read", throw=True)
	allowed = {"YRP Additional Parameter Key", "YRP Additional Parameter Value", "SD YRP Product Category"}
	if doctype not in allowed:
		frappe.throw(_("Unsupported Item editor link."), frappe.PermissionError)
	filters = {"name": ["like", f"%{cstr(txt).strip()}%"]}
	if doctype == "YRP Additional Parameter Value":
		if not key:
			frappe.throw(_("Set Additional Parameter Key first"))
		filters["key"] = key
	return [
		{"name": name, "label": name}
		for name in frappe.get_list(doctype, filters=filters, pluck="name", order_by="name", limit=20)
	]

from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate, nowdate
from yrp.attribute_links import value as actual_attribute_value
from yrp.attribute_value_identity import attribute_value_name
from yrp.attribute_values import ensure_value_master, get_mapping_values
from yrp.yrp.doctype.yrp_item.yrp_item import (
	_item_family_has_yrp_stock,
	ensure_global_attribute_values,
	get_global_attribute_values,
	search_item_attribute_values,
	template_has_variants,
)
from yrp.yrp_retail.pricing import lock_pricing_policy

from essdee_yrp.item_validations import validate as validate_cloth_item
from essdee_yrp.purchase.item_dependent_attribute import (
	apply_dependent_attribute,
	assert_dependent_mapping_unchanged,
	dependent_details_payload,
	dependent_mapping_modified,
	parse_dependent_attribute,
	release_dependent_attribute,
	validate_stage_variant_names,
)
from essdee_yrp.purchase.item_price_workspace import get_price_tiers
from essdee_yrp.purchase.item_tables import (
	SCALAR_FIELDS,
	apply_item_tables,
	final_dependent_details,
	finished_goods_packing,
	parse_item_tables,
	table_field_schemas,
	table_values,
	validate_stage_conversions,
)
from essdee_yrp.purchase.item_usage import has_item_transactions
from essdee_yrp.web_common import assert_expected_modified, parse_mapping, permission_flags

ITEM_DOCTYPE = "Item"
MAPPING_DOCTYPE = "YRP Item Item Attribute Mapping"
ATTRIBUTE_VALUE_DOCTYPE = "YRP Item Attribute Value"
EDITOR_FIELDS = (
	"name",
	"brand",
	"item_group",
	"stock_uom",
	"gst_hsn_code",
	"description",
	"disabled",
	"primary_attribute",
	"dependent_attribute",
	*SCALAR_FIELDS,
	"categories",
	"yrp_details_section",
)


def _parse_list(value, label: str) -> list:
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} is not valid JSON.").format(label))
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(label))
	return value


def _clean_attribute_values(attribute: str, values) -> list[str]:
	cleaned = []
	seen = set()
	for raw_value in _parse_list(values, _("Attribute values")):
		link_name = None
		if isinstance(raw_value, Mapping):
			link_name = cstr(raw_value.get("name")).strip() or None
			label = cstr(raw_value.get("label") or raw_value.get("value")).strip()
		else:
			label = cstr(raw_value).strip()
		if not label:
			continue
		if link_name:
			linked = frappe.db.get_value(
				ATTRIBUTE_VALUE_DOCTYPE,
				link_name,
				["attribute_name", "attribute_value"],
				as_dict=True,
			)
			if not linked or linked.attribute_name != attribute or linked.attribute_value != label:
				frappe.throw(
					_("Attribute Value {0} belongs to another Item Attribute.").format(label)
				)
		if label not in seen:
			seen.add(label)
			cleaned.append(label)
	return _canonical_attribute_values(attribute, cleaned)


def _canonical_attribute_values(attribute: str, labels: list[str]) -> list[str]:
	"""Reuse the stored spelling of a value that differs only by case."""
	if not labels:
		return []
	existing = _global_value_labels(attribute)
	known = set(existing)
	by_casefold = {}
	for label in existing:
		by_casefold.setdefault(cstr(label).casefold(), label)
	canonical = []
	for label in labels:
		if label not in known:
			label = by_casefold.setdefault(label.casefold(), label)
		if label not in canonical:
			canonical.append(label)
	return canonical


def _parse_attributes(values) -> list[dict]:
	rows = _parse_list(values or [], _("Attributes"))
	parsed = []
	seen = set()
	for row in rows:
		if not isinstance(row, Mapping):
			frappe.throw(_("Attribute rows must be objects."))
		attribute = cstr(row.get("attribute")).strip()
		if not attribute or not frappe.db.exists("Item Attribute", attribute):
			frappe.throw(_("Select a valid Item Attribute."))
		if attribute in seen:
			frappe.throw(_("Item Attribute {0} is repeated.").format(attribute))
		seen.add(attribute)
		parsed.append(
			{
				"attribute": attribute,
				"values": _clean_attribute_values(attribute, row.get("values") or []),
				"mapping_modified": row.get("mapping_modified"),
			}
		)
	return parsed


def _validate_item_basics(values, *, require_name=True) -> None:
	if require_name and not cstr(values.get("name")).strip():
		frappe.throw(_("Item Name is required."))
	group = frappe.db.get_value(
		"Item Group", values.get("item_group"), ["name", "is_group"], as_dict=True
	)
	if not group or cint(group.is_group):
		frappe.throw(_("Select a leaf Item Group."))
	uom = frappe.db.get_value("UOM", values.get("stock_uom"), ["name", "secondary_only"], as_dict=True)
	if not uom:
		frappe.throw(_("Select a valid Unit."))
	if cint(uom.secondary_only):
		frappe.throw(_("{0} can only be used as a Secondary UOM.").format(uom.name))


def _legacy_item_code(name, brand=None) -> str:
	name = cstr(name).strip()
	brand = cstr(brand).strip()
	if not brand:
		return name
	first_word = name.split(" ")[0]
	return name if first_word.lower() == brand.lower() else f"{brand} {name}"


def _field_schema(fieldname: str) -> dict:
	item_fieldname = "item_name" if fieldname == "name" else fieldname
	field = frappe.get_meta(ITEM_DOCTYPE).get_field(item_fieldname)
	return {
		"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
		"required": fieldname in {"name", "item_group", "stock_uom"},
	}


def _value_option(attribute: str, label: str) -> dict:
	return {"name": attribute_value_name(attribute, label), "label": label}


def _global_value_labels(attribute: str) -> list[str]:
	if frappe.db.get_value("Item Attribute", attribute, "numeric_values"):
		return frappe.get_all(
			ATTRIBUTE_VALUE_DOCTYPE,
			filters={"attribute_name": attribute},
			pluck="attribute_value",
			order_by="creation asc",
			limit=0,
		)
	return get_global_attribute_values(attribute)


def _mapping_payload(attribute_row) -> dict:
	mapping_name = attribute_row.get("mapping")
	stored_values = get_mapping_values(mapping_name) if mapping_name else []
	return {
		"attribute": attribute_row.attribute,
		"mapping": mapping_name,
		"mapping_modified": (
			frappe.db.get_value(MAPPING_DOCTYPE, mapping_name, "modified") if mapping_name else None
		),
		"values": [_value_option(attribute_row.attribute, label) for label in stored_values],
		"all_values_allowed": not stored_values,
		"value_count": len(_global_value_labels(attribute_row.attribute)),
	}


def _editor_options() -> dict:
	return {
		"item_groups": frappe.get_all(
			"Item Group",
			filters={"is_group": 0},
			fields=["name as value", "item_group_name as label"],
			order_by="item_group_name asc",
			limit=0,
		),
		"uoms": frappe.get_all(
			"UOM",
			filters={"secondary_only": 0},
			fields=["name as value", "uom_name as label"],
			order_by="name asc",
			limit=0,
		),
		"numeric_attributes": frappe.get_all(
			"Item Attribute", filters={"numeric_values": 1}, pluck="name", limit=0
		),
		"categories": frappe.get_all("YRP Item Category", pluck="name", order_by="name", limit=0),
	}


PRICE_STATE_ORDER = {"Approval Pending": 2, "Draft": 3}


def _price_rank(price) -> tuple:
	"""Current approved prices first, then pending, then the rest."""
	today = getdate(nowdate())
	if price.workflow_state == "Approved" and price.docstatus == 1:
		if price.from_date and getdate(price.from_date) > today:
			return (1,)
		if not price.to_date or getdate(price.to_date) >= today:
			return (0,)
	return (PRICE_STATE_ORDER.get(price.workflow_state, 4),)


def _item_prices(item: str) -> list[dict]:
	if not frappe.has_permission("YRP Item Price", ptype="read"):
		return []
	prices = frappe.get_list(
		"YRP Item Price",
		filters={"item_name": item},
		fields=[
			"name",
			"supplier",
			"supplier_name",
			"uom",
			"from_date",
			"to_date",
			"depends_on_attribute",
			"attribute",
			"tax",
			"workflow_state",
			"docstatus",
		],
		order_by="from_date desc, creation desc",
		limit=0,
	)
	if not prices:
		return []
	tiers_by_price = get_price_tiers([price.name for price in prices])
	for price in prices:
		price["tiers"] = tiers_by_price[price.name]
		price["is_current"] = _price_rank(price) == (0,)
	return sorted(prices, key=_price_rank)


def _editor_payload(doc=None) -> dict:
	is_existing = bool(doc and not doc.is_new())
	variant_count = frappe.db.count("Item", {"variant_of": doc.name}) if is_existing else 0
	stock_locked = bool(is_existing and _item_family_has_yrp_stock(doc.name))
	fields = {fieldname: _field_schema(fieldname) for fieldname in EDITOR_FIELDS}
	fields.update(table_field_schemas())
	fields["stock_uom"]["read_only"] = is_existing
	values = {
		**table_values(doc),
		"name": doc.item_name if doc else None,
		"brand": doc.brand if doc else None,
		"item_group": doc.item_group if doc else None,
		"stock_uom": doc.stock_uom if is_existing else None,
		"gst_hsn_code": doc.get("gst_hsn_code") if doc else None,
		"description": doc.description if doc else None,
		"disabled": cint(doc.disabled) if doc else 0,
		"primary_attribute": doc.primary_attribute if doc else None,
		"dependent_attribute": doc.get("dependent_attribute") if doc else None,
		"dependent_details": dependent_details_payload(doc) if is_existing else [],
		"dependent_mapping_modified": dependent_mapping_modified(doc) if is_existing else None,
		"attributes": [_mapping_payload(row) for row in doc.get("attributes") or []] if doc else [],
	}
	permissions = permission_flags(
		ITEM_DOCTYPE,
		("read", "create", "write"),
		doc if is_existing else None,
	)
	permissions["can_write_item_attribute"] = bool(frappe.has_permission("Item Attribute", ptype="write"))
	return {
		"values": values,
		"fields": fields,
		"options": _editor_options(),
		"variant_count": variant_count,
		"attributes_locked": bool(variant_count),
		"attribute_lock_message": _(
			"Attributes are locked because variants exist. Values can still be added or removed."
		)
		if variant_count
		else "",
		"primary_attribute_locked": stock_locked,
		"primary_attribute_lock_message": _(
			"Primary Attribute is locked because YRP stock exists for this Item."
		)
		if stock_locked
		else "",
		"dependent_attribute_locked": stock_locked,
		"dependent_attribute_lock_message": _(
			"Dependent Attribute is locked because YRP stock exists for this Item."
		)
		if stock_locked
		else "",
		"has_item_transactions": bool(is_existing and has_item_transactions(doc.name)),
		"fg_pcs_per_box": finished_goods_packing(doc.name) if is_existing else None,
		"item_prices": _item_prices(doc.name) if is_existing else [],
		"modified": doc.modified if is_existing else None,
		"permissions": permissions,
	}


def _reject_variant(doc) -> None:
	if doc.variant_of:
		frappe.throw(_("Variant items are not shown here."))


@frappe.whitelist()
def get_item_editor(name: str | None = None) -> dict:
	if name:
		doc = frappe.get_doc(ITEM_DOCTYPE, name)
		frappe.has_permission(ITEM_DOCTYPE, ptype="read", doc=doc, throw=True)
		_reject_variant(doc)
		return _editor_payload(doc)
	frappe.has_permission(ITEM_DOCTYPE, ptype="create", throw=True)
	return _editor_payload(frappe.new_doc(ITEM_DOCTYPE))


@frappe.whitelist()
def search_attribute_values(attribute: str, txt: str = "", item: str | None = None) -> list[dict]:
	if item:
		frappe.has_permission(ITEM_DOCTYPE, ptype="read", doc=item, throw=True)
	labels = search_item_attribute_values(txt=txt, attribute=attribute, item=item)
	if not labels and frappe.db.get_value("Item Attribute", attribute, "numeric_values"):
		mapping_values = (
			search_item_attribute_values(attribute=attribute, item=item) if txt else []
		)
		if not mapping_values:
			needle = cstr(txt).lower()
			labels = [
				label
				for label in _global_value_labels(attribute)
				if needle in cstr(label).lower()
			][:99]
	if not item:
		labels = _exact_value_first(attribute, txt, labels)
	return [_value_option(attribute, label) for label in labels]


def _exact_value_first(attribute: str, txt: str, labels: list[str]) -> list[str]:
	needle = cstr(txt).strip().casefold()
	if not needle or any(cstr(label).casefold() == needle for label in labels):
		return labels
	exact = next(
		(label for label in _global_value_labels(attribute) if cstr(label).casefold() == needle),
		None,
	)
	return [exact, *labels[:98]] if exact else labels


@frappe.whitelist()
def get_item_attribute_counts(items) -> dict[str, int]:
	requested = list(dict.fromkeys(cstr(name).strip() for name in _parse_list(items, _("Items"))))
	requested = [name for name in requested if name]
	if len(requested) > 100:
		frappe.throw(_("Attribute counts can be loaded for at most 100 Items at a time."))
	if not requested:
		return {}
	frappe.has_permission(ITEM_DOCTYPE, ptype="read", throw=True)
	visible = frappe.get_list(
		ITEM_DOCTYPE,
		filters={"name": ["in", requested], "variant_of": ["is", "not set"]},
		pluck="name",
		limit=0,
	)
	counts = dict.fromkeys(visible, 0)
	if not visible:
		return counts
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={
			"parent": ["in", visible],
			"parenttype": ITEM_DOCTYPE,
			"parentfield": "attributes",
		},
		fields=["parent", {"COUNT": "name", "as": "attribute_count"}],
		group_by="parent",
	):
		counts[row.parent] = cint(row.attribute_count)
	return counts


def _require_mapping_create_permissions(attributes) -> None:
	if not attributes:
		return
	frappe.has_permission(MAPPING_DOCTYPE, ptype="create", throw=True)
	frappe.has_permission(MAPPING_DOCTYPE, ptype="write", throw=True)


def _ensure_requested_values(attribute: str, labels: list[str]) -> None:
	existing = set(_global_value_labels(attribute))
	missing = [label for label in labels if label not in existing]
	if missing:
		ensure_global_attribute_values(attribute, missing)


def _fill_mapping(mapping_name: str, attribute: str, labels: list[str]) -> None:
	_ensure_requested_values(attribute, labels)
	mapping = frappe.get_doc(MAPPING_DOCTYPE, mapping_name)
	frappe.has_permission(MAPPING_DOCTYPE, ptype="write", doc=mapping, throw=True)
	_write_mapping_values(mapping, attribute, labels)


def _parse_attribute_rules(values, attributes: list[dict], doc=None) -> tuple[str | None, str | None]:
	primary_attribute = cstr(values.get("primary_attribute")).strip() or None
	if primary_attribute and primary_attribute not in {row["attribute"] for row in attributes}:
		frappe.throw(_("Primary Attribute must be one of the selected Attributes."))
	return primary_attribute, parse_dependent_attribute(values, attributes, primary_attribute, doc)


@frappe.whitelist(methods=["POST"])
def create_item(values) -> dict:
	values = parse_mapping(values, _("Item values"))
	frappe.has_permission(ITEM_DOCTYPE, ptype="create", throw=True)
	lock_pricing_policy()
	_validate_item_basics(values)
	attributes = _parse_attributes(values.get("attributes") or [])
	_require_mapping_create_permissions(attributes)
	primary_attribute, dependent_attribute = _parse_attribute_rules(values, attributes)
	tables = parse_item_tables(values, values.get("stock_uom"))
	details = final_dependent_details(values, attributes, dependent_attribute, values.get("stock_uom"))
	validate_stage_conversions(details, tables["uoms"], values.get("stock_uom"))
	validate_stage_variant_names(details)

	item_code = _legacy_item_code(values.get("name"), values.get("brand"))
	if frappe.db.exists(ITEM_DOCTYPE, item_code):
		frappe.throw(_("Item {0} already exists.").format(item_code))
	doc = frappe.get_doc(
		{
			"doctype": ITEM_DOCTYPE,
			"item_code": item_code,
			"item_name": item_code,
			"brand": values.get("brand") or None,
			"item_group": values.get("item_group"),
			"stock_uom": values.get("stock_uom"),
			"gst_hsn_code": values.get("gst_hsn_code") or None,
			"description": values.get("description") or None,
			"disabled": cint(values.get("disabled")),
			"country_of_origin": frappe.db.get_default("country"),
			"is_stock_item": 1,
			"is_purchase_item": 1,
			"is_sales_item": 0,
			"has_variants": int(bool(attributes)),
			"variant_based_on": "Item Attribute" if attributes else None,
			"primary_attribute": primary_attribute,
			"attributes": [{"attribute": row["attribute"]} for row in attributes],
		}
	)
	doc.name = item_code
	apply_item_tables(doc, tables)
	validate_cloth_item(doc)
	doc.insert()
	doc.reload()
	for requested, attribute_row in zip(attributes, doc.get("attributes") or [], strict=True):
		_fill_mapping(attribute_row.mapping, requested["attribute"], requested["values"])
	apply_dependent_attribute(doc, dependent_attribute, details)
	return {"name": doc.name}


def _load_locked_item(name: str, expected_modified):
	preflight = frappe.get_doc(ITEM_DOCTYPE, name)
	frappe.has_permission(ITEM_DOCTYPE, ptype="write", doc=preflight, throw=True)
	_reject_variant(preflight)
	doc = frappe.get_doc(ITEM_DOCTYPE, name, for_update=True)
	frappe.has_permission(ITEM_DOCTYPE, ptype="write", doc=doc, throw=True)
	_reject_variant(doc)
	assert_expected_modified(doc, expected_modified)
	return doc


@frappe.whitelist(methods=["POST"])
def set_item_disabled(name: str, disabled, expected_modified) -> dict:
	doc = _load_locked_item(name, expected_modified)
	doc.disabled = cint(disabled)
	doc.save()
	return get_item_editor(doc.name)


def _stored_attributes(doc) -> dict[str, dict]:
	stored = {}
	for row in doc.get("attributes") or []:
		mapping_values = get_mapping_values(row.mapping) if row.get("mapping") else []
		stored[row.attribute] = {
			"mapping": row.get("mapping"),
			"stored_values": mapping_values,
			"effective_values": mapping_values or _global_value_labels(row.attribute),
		}
	return stored


def _attribute_rows_changed(doc, attributes: list[dict]) -> bool:
	return [row.attribute for row in doc.get("attributes") or []] != [
		row["attribute"] for row in attributes
	] or bool(doc.has_variants) != bool(attributes)


def _validate_attribute_rule_stock_lock(doc, primary_attribute, dependent_attribute) -> None:
	requested = {"primary_attribute": primary_attribute, "dependent_attribute": dependent_attribute}
	changed = [field for field, value in requested.items() if (doc.get(field) or None) != value]
	if changed and _item_family_has_yrp_stock(doc.name):
		frappe.throw(
			_("Cannot change {0} after YRP stock exists for Item {1}.").format(", ".join(changed), doc.name)
		)


def _price_references_value(item: str, attribute: str, removed_values: set[str]) -> bool:
	if not removed_values:
		return False
	parents = frappe.get_all(
		"YRP Item Price",
		filters={"item_name": item, "depends_on_attribute": 1, "attribute": attribute},
		pluck="name",
	)
	if not parents:
		return False
	links = frappe.get_all(
		"YRP Item Price Value",
		filters={"parent": ["in", parents]},
		pluck="attribute_value",
	)
	return any(actual_attribute_value(link) in removed_values for link in links)


def _price_references_attribute(item: str, attributes: set[str]) -> bool:
	return bool(
		attributes
		and frappe.db.exists(
			"YRP Item Price",
			{
				"item_name": item,
				"depends_on_attribute": 1,
				"attribute": ["in", list(attributes)],
			},
		)
	)


def _lock_changed_mapping(mapping_name: str, expected_modified):
	preflight = frappe.get_doc(MAPPING_DOCTYPE, mapping_name)
	frappe.has_permission(MAPPING_DOCTYPE, ptype="write", doc=preflight, throw=True)
	mapping = frappe.get_doc(MAPPING_DOCTYPE, mapping_name, for_update=True)
	frappe.has_permission(MAPPING_DOCTYPE, ptype="write", doc=mapping, throw=True)
	assert_expected_modified(mapping, expected_modified)
	return mapping


@frappe.whitelist(methods=["POST"])
def update_item(name: str, values, expected_modified) -> dict:
	values = parse_mapping(values, _("Item values"))
	lock_pricing_policy()
	doc = _load_locked_item(name, expected_modified)
	assert_dependent_mapping_unchanged(doc, values.get("dependent_mapping_modified"))
	validated_values = {**values, "stock_uom": doc.stock_uom}
	_validate_item_basics(validated_values)
	attributes = _parse_attributes(values.get("attributes") or [])
	primary_attribute = cstr(values.get("primary_attribute")).strip() or None
	dependent_attribute = cstr(values.get("dependent_attribute")).strip() or None
	tables = parse_item_tables(values, doc.stock_uom, doc)
	stored = _stored_attributes(doc)
	if _attribute_rows_changed(doc, attributes) and template_has_variants(doc.name):
		variant_count = frappe.db.count("Item", {"variant_of": doc.name})
		frappe.throw(
			_(
				"Locked: variants exist ({0}). Attribute rows cannot be added, removed, reordered or replaced. Values can still be added or removed."
			).format(variant_count)
		)
	_validate_attribute_rule_stock_lock(doc, primary_attribute, dependent_attribute)

	stored_names = list(stored)
	requested_names = [row["attribute"] for row in attributes]
	crosses_template_boundary = bool(stored_names) != bool(requested_names)
	if crosses_template_boundary and (
		_item_family_has_yrp_stock(doc.name) or frappe.db.exists("YRP Item Price", {"item_name": doc.name})
	):
		frappe.throw(_("The Item attribute list cannot change after stock or prices exist."))
	removed_attributes = set(stored_names) - set(requested_names)
	if _price_references_attribute(doc.name, removed_attributes):
		frappe.throw(_("A price tier still references an Item Attribute being removed."))

	locked_mappings = {}
	for row in attributes:
		stored_row = stored.get(row["attribute"])
		if not stored_row or stored_row["stored_values"] == row["values"]:
			continue
		requested_values = row["values"] or _global_value_labels(row["attribute"])
		removed = set(stored_row["effective_values"]) - set(requested_values)
		if _price_references_value(doc.name, row["attribute"], removed):
			frappe.throw(_("A price tier still references a value being removed."))
		if stored_row["mapping"]:
			locked_mappings[row["attribute"]] = _lock_changed_mapping(
				stored_row["mapping"], row.get("mapping_modified")
			)

	before = doc.as_dict()
	primary_attribute, dependent_attribute = _parse_attribute_rules(values, attributes, doc)
	details = final_dependent_details(values, attributes, dependent_attribute, doc.stock_uom, doc)
	validate_stage_conversions(details, tables["uoms"], doc.stock_uom)
	validate_stage_variant_names(details)
	apply_item_tables(doc, tables)
	validate_cloth_item(doc)
	for row in attributes:
		_ensure_requested_values(row["attribute"], row["values"])
	for attribute, mapping in locked_mappings.items():
		_write_mapping_values(mapping, attribute, _requested_values(attributes, attribute))

	_set_item_values(doc, values, attributes, stored)
	doc.primary_attribute = primary_attribute
	if (doc.get("dependent_attribute") or None) != dependent_attribute:
		release_dependent_attribute(doc)
	if doc.as_dict() != before or not all(row.get("mapping") for row in doc.get("attributes") or []):
		doc.save()
		doc.reload()

	for requested, attribute_row in zip(attributes, doc.get("attributes") or [], strict=True):
		stored_row = stored.get(requested["attribute"])
		if requested["attribute"] in locked_mappings or (
			stored_row and stored_row["stored_values"] == requested["values"]
		):
			continue
		mapping = frappe.get_doc(MAPPING_DOCTYPE, attribute_row.mapping)
		frappe.has_permission(MAPPING_DOCTYPE, ptype="write", doc=mapping, throw=True)
		_write_mapping_values(mapping, requested["attribute"], requested["values"])
	apply_dependent_attribute(doc, dependent_attribute, details)
	return get_item_editor(doc.name)


def _requested_values(attributes: list[dict], attribute: str) -> list[str]:
	return next(row["values"] for row in attributes if row["attribute"] == attribute)


def _write_mapping_values(mapping, attribute: str, labels: list[str]) -> None:
	mapping.set(
		"values",
		[{"attribute_value": ensure_value_master(attribute, label)} for label in labels],
	)
	mapping.save()


def _set_item_values(doc, values, attributes: list[dict], stored: dict) -> None:
	doc.item_name = cstr(values.get("name")).strip()
	doc.brand = values.get("brand") or None
	doc.item_group = values.get("item_group")
	doc.gst_hsn_code = values.get("gst_hsn_code") or None
	doc.description = values.get("description") or None
	doc.disabled = cint(values.get("disabled"))
	doc.has_variants = int(bool(attributes))
	if bool(attributes) != bool(stored):
		doc.variant_based_on = "Item Attribute" if attributes else None
	existing_attribute_rows = {row.attribute: row for row in doc.get("attributes") or []}
	attribute_rows = []
	for index, row in enumerate(attributes, start=1):
		attribute_row = existing_attribute_rows.get(row["attribute"])
		if attribute_row is None:
			attribute_row = {
				"attribute": row["attribute"],
				"mapping": stored.get(row["attribute"], {}).get("mapping"),
			}
		else:
			attribute_row.idx = index
		attribute_rows.append(attribute_row)
	doc.set("attributes", attribute_rows)

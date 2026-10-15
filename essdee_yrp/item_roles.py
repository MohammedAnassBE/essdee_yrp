"""Shared Item structure and inheritance rules."""

VARIANT_INHERITED_FIELDS = (
	"item_group",
	"stock_uom",
	"is_stock_item",
	"is_purchase_item",
	"is_sales_item",
	"disabled",
	"brand",
	"description",
	"secondary_unit_of_measure",
	"purchase_uom",
	"sales_uom",
	"weight_per_unit",
	"weight_uom",
	"hsn_code",
	"po_excess_allowed_percentage",
)


def get_item_structural_role(document) -> str:
	if int(document.get("has_variants") or 0):
		return "template"
	return "variant" if document.get("variant_of") else "standalone"


def get_canonical_item_names(names) -> dict[str, str]:
	"""Resolve database spelling, rejecting ambiguous casefold identities."""
	import frappe

	names = list(dict.fromkeys(name for name in names if name))
	if not names:
		return {}
	canonical = {}
	for name in frappe.get_all("Item", filters={"name": ["in", names]}, pluck="name"):
		key = name.casefold()
		if key in canonical and canonical[key] != name:
			raise ValueError(f"Ambiguous Item names: {canonical[key]} and {name}")
		canonical[key] = name
	return canonical


def resolve_variant_target_role(variant_name, parent_name, attribute_rows, parent_role) -> str:
	"""Resolve physical variants against the authoritative parent role."""
	if not parent_name or not parent_role:
		raise ValueError(f"Missing parent Item {parent_name} for Item Variant {variant_name}")
	if parent_role == "variant":
		raise ValueError(f"Item Variant {variant_name} cannot have variant parent {parent_name}")
	if not any(row.get("attribute_value") not in (None, "") for row in attribute_rows):
		return "merge_into_parent" if variant_name.casefold() == parent_name.casefold() else "standalone"
	return "variant" if parent_role == "template" else "standalone"


def get_variant_inherited_values(parent):
	return {field: parent.get(field) for field in VARIANT_INHERITED_FIELDS if field in parent}


def strip_item_migration_context(document):
	"""Remove live-only parent context before writes or comparisons."""
	document.pop("_source_item_parent", None)
	return document

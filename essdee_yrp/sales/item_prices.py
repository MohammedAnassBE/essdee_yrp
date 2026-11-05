"""Sales Item Price grid for the /web Sales workspace: one rate type per save, per piece."""

import frappe
from frappe import _
from frappe.utils import flt
from yrp import attribute_links as attribute_db

from essdee_yrp.product_sales import get_pack_out_settings

DOCTYPE = "SD YRP Sales Item Price"
PIECE_UOM = "Piece"
PRICE_TYPES = (
	{"value": "mrp_rate", "label": _("MRP Rate")},
	{"value": "rate", "label": _("Distributor Rate")},
	{"value": "retail_rate", "label": _("Retail Rate")},
)
PRICE_FIELDS = tuple(row["value"] for row in PRICE_TYPES)


def get_variant_rows(item=None, priced_only=True, variants=None, limit=None):
	"""Enabled variants keyed by the template primary attribute, at the pack-out stage when staged."""
	conditions = []
	if item:
		conditions.append("t.name = %(item)s")
	if variants is not None:
		conditions.append("v.name in %(variants)s")
	if priced_only:
		conditions.append(f"exists (select 1 from `tab{DOCTYPE}` s where s.item_variant = v.name)")
	where = "".join(f" and {condition}" for condition in conditions)
	rows = frappe.db.sql(
		f"""
		select t.name as item, t.item_name, v.name as variant, p.attribute_value as size,
			t.custom_size_range as size_range
		from `tabItem` v
		join `tabItem` t on t.name = v.variant_of and t.disabled = 0
		join `tabItem Variant Attribute` p on p.parent = v.name and p.parenttype = 'Item'
			and p.attribute = t.primary_attribute
		left join `tabItem Variant Attribute` d on d.parent = v.name and d.parenttype = 'Item'
			and d.attribute = t.dependent_attribute
		where v.disabled = 0 and ifnull(t.primary_attribute, '') != ''
			and (ifnull(t.dependent_attribute, '') = '' or d.attribute_value = %(stage)s)
			and not exists (
				select 1 from `tabItem Variant Attribute` x where x.parent = v.name and x.parenttype = 'Item'
				and x.attribute not in (t.primary_attribute, ifnull(t.dependent_attribute, ''))
			){where}
		order by t.item_name, t.name, p.idx, v.name
		{"limit %(limit)s" if limit else ""}
		""",
		{
			"item": item,
			"variants": tuple(variants or ("",)),
			"stage": get_pack_out_settings().stage,
			"limit": limit,
		},
		as_dict=True,
	)
	for row in rows:
		row.size = attribute_db.value(row.size)
	return rows


def get_size_orders(size_ranges):
	if not size_ranges:
		return {}
	orders = {}
	for row in attribute_db.get_all(
		"SD YRP FG Item Size",
		filters={"parent": ["in", list(size_ranges)], "parenttype": "SD YRP FG Item Size Range"},
		fields=["parent", "attribute_value", "idx"],
	):
		orders.setdefault(row.parent, {})[row.attribute_value] = row.idx
	return orders


def build_items(rows, prices, size_orders):
	items = {}
	for row in rows:
		entry = items.setdefault(
			row.item,
			{
				"item": row.item,
				"item_name": row.item_name,
				"sizes": [],
				"variants": {},
				"prices": {field: {} for field in PRICE_FIELDS},
				"missing": [],
				"order": size_orders.get(row.size_range) or {},
			},
		)
		if row.size in entry["variants"]:
			frappe.throw(_("Item {0} has more than one sales variant for {1}.").format(row.item, row.size))
		entry["sizes"].append(row.size)
		entry["variants"][row.size] = row.variant
		price = prices.get(row.variant)
		if not price:
			entry["missing"].append(row.size)
		for field in PRICE_FIELDS:
			entry["prices"][field][row.size] = flt(price.get(field)) if price else 0
	for entry in items.values():
		order = entry.pop("order")
		position = {size: (order.get(size, 9999), index) for index, size in enumerate(entry["sizes"])}
		entry["sizes"].sort(key=position.get)
		entry["missing"].sort(key=position.get)
	return list(items.values())


def get_prices(variants):
	if not variants:
		return {}
	rows = frappe.get_all(
		DOCTYPE,
		filters={"item_variant": ["in", list(variants)]},
		fields=["name", "item_variant", *PRICE_FIELDS],
	)
	return {row.item_variant: row for row in rows}


@frappe.whitelist()
def get_item_price_grid(item=None):
	frappe.has_permission(DOCTYPE, "read", throw=True)
	rows = get_variant_rows(item=item or None, priced_only=not item)
	prices = get_prices({row.variant for row in rows})
	size_orders = get_size_orders({row.size_range for row in rows if row.size_range})
	return {
		"uom": PIECE_UOM,
		"price_types": list(PRICE_TYPES),
		"permissions": {
			"can_write": bool(frappe.has_permission(DOCTYPE, "write")),
			"can_create": bool(frappe.has_permission(DOCTYPE, "create")),
		},
		"items": build_items(rows, prices, size_orders),
	}


@frappe.whitelist(methods=["POST"])
def save_item_prices(price_type, prices):
	"""Upsert one rate type for the given {variant: rate}; new rows are per Piece."""
	if price_type not in PRICE_FIELDS:
		frappe.throw(_("Select a valid Rate Type."))
	prices = frappe.parse_json(prices) or {}
	if not isinstance(prices, dict):
		frappe.throw(_("Prices must map each Item Variant to a rate."))
	invalid = [variant for variant, rate in prices.items() if flt(rate) < 0]
	if invalid:
		frappe.throw(_("Rate cannot be negative for {0}.").format(", ".join(invalid)))
	eligible = (
		{row.variant for row in get_variant_rows(priced_only=False, variants=list(prices))}
		if prices
		else set()
	)
	unknown = sorted(set(prices) - eligible)
	if unknown:
		frappe.throw(_("Not a sales Item Variant: {0}").format(", ".join(unknown)))
	existing = get_prices(prices)
	result = {"created": 0, "updated": 0}
	for variant, rate in prices.items():
		row = existing.get(variant)
		doc = frappe.get_doc(DOCTYPE, row.name) if row else frappe.new_doc(DOCTYPE)
		if not row:
			doc.update({"item_variant": variant, "uom": PIECE_UOM})
		doc.set(price_type, flt(rate))
		doc.save()
		result["updated" if row else "created"] += 1
	return result

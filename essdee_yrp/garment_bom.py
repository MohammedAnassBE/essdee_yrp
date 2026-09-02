"""Essdee garment accessory BOM calculation.

YRP's matrix engine remains responsible for generic process inputs.  This
module keeps the legacy Essdee meaning of ``Item BOM.dependent_attribute_value``:
an accessory attached to the packed stage is scaled by the garment's packing
conversion before it is added to a Lot BOM.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt
from yrp.yrp.doctype.item.item import get_or_create_variant
from yrp.yrp.doctype.item_bom.item_bom import validate_bom_item_variant_mapping


def calculate_essdee_accessory_bom(
	ipd_name, variant_demands, lot_doc, process_names=None
):
	"""Return Production API-compatible accessory rows for an Essdee Lot."""
	ipd = frappe.get_doc("Item Production Detail", ipd_name)
	demands = _normalize_variant_demands(ipd, variant_demands)
	aggregated = {}
	total_quantity = sum(demand["qty"] for demand in demands)
	process_filter = None if process_names is None else set(process_names)

	for bom_row in ipd.get("item_bom") or []:
		if process_filter is not None and bom_row.process_name not in process_filter:
			continue
		validate_bom_item_variant_mapping(bom_row)
		wastage_factor = 1 + flt(bom_row.get("wastage_pct")) / 100
		if bom_row.based_on_attribute_mapping and bom_row.attribute_mapping:
			for demand in demands:
				mapped = _resolve_mapping(bom_row.attribute_mapping, demand["attrs"])
				if not mapped:
					continue
				qty_of_product = _qty_of_product(ipd, lot_doc, bom_row)
				qty_of_bom = flt(mapped.get("qty_of_bom_item")) or flt(
					bom_row.qty_of_bom_item
				)
				quantity = demand["qty"] * qty_of_bom / qty_of_product
				_add_row(
					aggregated,
					bom_row,
					mapped.get("bom_attrs") or {},
					quantity * wastage_factor,
				)
			continue

		qty_of_product = _qty_of_product(ipd, lot_doc, bom_row)
		basis_quantity = total_quantity
		if (
			bom_row.dependent_attribute_value
			and bom_row.dependent_attribute_value == lot_doc.get("pack_out_stage")
			and ipd.get("is_set_item")
		):
			# This is the legacy set-garment rule in Production API's mode-A path.
			basis_quantity /= 2
		quantity = basis_quantity * flt(bom_row.qty_of_bom_item) / qty_of_product
		_add_row(aggregated, bom_row, {}, quantity * wastage_factor)

	return list(aggregated.values())


def _normalize_variant_demands(ipd, variant_demands):
	variant_demands = (
		frappe.parse_json(variant_demands)
		if isinstance(variant_demands, str)
		else variant_demands
	)
	if isinstance(variant_demands, dict):
		variant_demands = [variant_demands]

	demands = []
	for row in variant_demands or []:
		variant = row.get("item_variant") or row.get("variant") or row.get("name")
		quantity = flt(
			row.get("qty") or row.get("quantity") or row.get("required_qty")
		)
		if not variant or quantity <= 0:
			continue
		variant_doc = frappe.get_cached_doc("Item Variant", variant)
		if variant_doc.item != ipd.item:
			frappe.throw(
				_("Item Variant {0} does not belong to IPD item {1}.").format(
					variant, ipd.item
				)
			)
		demands.append(
			{
				"item_variant": variant,
				"qty": quantity,
				"attrs": {
					attribute.attribute: attribute.attribute_value
					for attribute in variant_doc.get("attributes") or []
				},
			}
		)

	if not demands:
		frappe.throw(_("Please provide at least one Item Variant with Qty greater than zero."))
	return demands


def _qty_of_product(ipd, lot_doc, bom_row):
	qty_of_product = flt(bom_row.qty_of_product)
	stage = bom_row.dependent_attribute_value
	pack_in_stage = lot_doc.get("pack_in_stage")
	pack_out_stage = lot_doc.get("pack_out_stage")

	if stage and stage != pack_in_stage:
		qty_of_product = _packing_uom_conversion(ipd.item, lot_doc.get("packing_uom"))
		if stage == pack_out_stage:
			packing_combo = flt(ipd.get("packing_combo"))
			if packing_combo <= 0:
				frappe.throw(
					_("Packing Combo must be greater than zero on Item Production Detail {0}.").format(
						ipd.name
					)
				)
			qty_of_product *= packing_combo

	if qty_of_product <= 0:
		frappe.throw(
			_("Qty of Product must be greater than zero for BOM item {0}.").format(
				bom_row.item
			)
		)
	return qty_of_product


def _packing_uom_conversion(item, packing_uom):
	item_doc = frappe.get_cached_doc("Item", item)
	from_uom = item_doc.default_unit_of_measure
	to_uom = packing_uom or from_uom
	if from_uom == to_uom:
		return 1.0

	factors = {
		row.uom: flt(row.conversion_factor)
		for row in item_doc.get("uom_conversion_details") or []
		if row.uom
	}
	from_factor = factors.get(from_uom)
	to_factor = factors.get(to_uom)
	if not from_factor or not to_factor:
		frappe.throw(
			_("Missing UOM conversion from {0} to {1} on Item {2}.").format(
				from_uom, to_uom, item
			)
		)
	return from_factor / to_factor


def _resolve_mapping(mapping_name, variant_attrs):
	mapping = frappe.get_cached_doc("Item BOM Attribute Mapping", mapping_name)
	same_attributes = _same_attributes(mapping)
	required_bom_attributes = {
		row.attribute for row in mapping.get("bom_item_attributes") or []
	}
	item_key_attributes = [
		row.attribute
		for row in mapping.get("item_attributes") or []
		if row.attribute not in same_attributes
	]
	variant_key = {
		attribute: variant_attrs[attribute]
		for attribute in item_key_attributes
		if attribute in variant_attrs
	}
	rows_by_index = defaultdict(list)
	for row in mapping.get("values") or []:
		rows_by_index[row.index].append(row)

	for rows in rows_by_index.values():
		item_side = {
			row.attribute: row.attribute_value
			for row in rows
			if row.type == "item" and row.attribute not in same_attributes
		}
		if item_side != variant_key:
			continue
		bom_attrs = {
			row.attribute: row.attribute_value for row in rows if row.type == "bom"
		}
		for attribute in same_attributes:
			if variant_attrs.get(attribute):
				bom_attrs[attribute] = variant_attrs[attribute]
		missing_attributes = required_bom_attributes.difference(bom_attrs)
		if missing_attributes:
			frappe.throw(
				_("BOM mapping {0} is missing BOM values for: {1}.").format(
					mapping_name, ", ".join(sorted(missing_attributes))
				)
			)
		quantity = next((flt(row.quantity) for row in rows if flt(row.quantity)), 0)
		return {"bom_attrs": bom_attrs, "qty_of_bom_item": quantity}
	return None


def _same_attributes(mapping):
	item_same = {
		row.attribute
		for row in mapping.get("item_attributes") or []
		if row.same_attribute
	}
	return {
		row.attribute
		for row in mapping.get("bom_item_attributes") or []
		if row.same_attribute and row.attribute in item_same
	}


def _add_row(aggregated, bom_row, attrs, quantity):
	item_variant = get_or_create_variant(bom_row.item, attrs)
	uom = bom_row.uom or frappe.db.get_value(
		"Item", bom_row.item, "default_unit_of_measure"
	)
	key = (bom_row.process_name, item_variant, uom)
	if key not in aggregated:
		aggregated[key] = {
			"source": "Essdee Item BOM",
			"process_name": bom_row.process_name,
			"item": bom_row.item,
			"item_variant": item_variant,
			"required_qty": 0.0,
			"uom": uom,
			"attrs": attrs,
		}
	aggregated[key]["required_qty"] += flt(quantity)

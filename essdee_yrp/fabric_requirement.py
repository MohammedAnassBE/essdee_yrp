# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt
"""Phase 1 SPLIT — cloth demand for a garment Lot.

Native PORT of production_api's calculate_cloth / get_cloth_combination /
get_stitching_combination (+ the get_calculated_bom cloth-aggregation block).
production_api is a read-only REFERENCE: this is a copy, never an import. The
only deviations from the source are (a) JSON fields read via the local `_as_json`
port of update_if_string_instance so an essdee garment IPD that leaves the
accessory JSON blank does not crash, (b) the aggregate key is reordered to
(cloth Item, dia, colour) — the shape the fabric engine's Lot requirement wants,
(c) an incomplete garment IPD raises a clear operator-facing error via
`_validate_garment_ipd` instead of dying with KeyError: 'items' (25 live
empty-draft IPDs exist, 10 of them with live Lots), and (d) unmapped cloth
labels in `_aggregate_demand` RAISE instead of being silently dropped — the
auto-builder must never under-demand silently.

Accessory cloth demand (cloth_accessory_json / accessory_clothtype_json, present
on 66% of live garment IPDs) is IN scope: calculate_accessory is ported
(production_api get_calculated_bom parity, item_production_detail.py:618-624)
and its kg aggregates into the same (cloth Item, dia, colour) demand the CPDs
are seeded from.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt


def _as_json(value):
    """Local port of production_api.utils.update_if_string_instance: a JSON str,
    list, or dict -> the parsed object; anything falsy -> {}."""
    if isinstance(value, str):
        if not value:
            return {}
        value = json.loads(value)
    if not value:
        return {}
    return value


def get_key(item, attrs):
    key = []
    for attr in attrs:
        key.append(item[attr])
    return tuple(key)


def add_cloth_detail(weight, cloth_type, cloth_colour, dia, type, accessory_name=None):
    d = {
        "cloth_type": cloth_type,
        "colour": cloth_colour,
        "dia": dia,
        "quantity": weight,
        "type": type,
    }
    if accessory_name:
        d["accessory_name"] = accessory_name
    return d


def get_stich_details(ipd_doc):
    stich_details = {}
    for i in ipd_doc.stiching_item_details:
        stich_details[i.stiching_attribute_value] = i.set_item_attribute_value
    return stich_details


def get_cloth_combination(ipd_doc):
    cutting_attributes = [i.attribute for i in ipd_doc.cutting_attributes]
    cloth_attributes = [i.attribute for i in ipd_doc.cloth_attributes]
    accessory_attributes = [i.attribute for i in ipd_doc.accessory_attributes]
    cutting_combination = {}
    cloth_combination = {}
    accessory_combination = {}
    cutting_items = _as_json(ipd_doc.cutting_items_json)
    cutting_cloths = _as_json(ipd_doc.cutting_cloths_json)
    accessory_items = _as_json(ipd_doc.get("cloth_accessory_json"))

    for item in cutting_items.get("items") or []:
        cutting_combination[get_key(item, cutting_attributes)] = (item["Dia"], item["Weight"])
    for item in cutting_cloths.get("items") or []:
        cloth_combination[get_key(item, cloth_attributes)] = item["Cloth"]
    accessory_attributes.append("Accessory")
    if accessory_items:
        for item in accessory_items["items"]:
            accessory_combination[get_key(item, accessory_attributes)] = (item["Dia"], item["Weight"])

    return {
        "cutting_attributes": cutting_attributes,
        "cloth_attributes": cloth_attributes,
        "accessory_attributes": accessory_attributes,
        "cutting_combination": cutting_combination,
        "cloth_combination": cloth_combination,
        "accessory_combination": accessory_combination,
    }


def get_stitching_combination(ipd_doc):
    part_panel_comb = {}
    if ipd_doc.is_set_item:
        part_panel_comb = get_stich_details(ipd_doc)

    stitching_combination = {}
    for detail in ipd_doc.stiching_item_combination_details:
        key = detail.major_attribute_value
        if ipd_doc.is_set_item:
            key = (key, part_panel_comb[detail.set_item_attribute_value])
        stitching_combination.setdefault(key, {})
        stitching_combination[key][detail.set_item_attribute_value] = detail.attribute_value

    return {
        "stitching_attribute": ipd_doc.stiching_attribute,
        "stitching_attribute_count": {
            i.stiching_attribute_value: i.quantity for i in ipd_doc.stiching_item_details},
        "is_same_packing_attribute": ipd_doc.is_same_packing_attribute,
        "stitching_combination": stitching_combination,
    }


def get_accessory_colour(ipd_doc, variant_attrs, accessory):
    if ipd_doc.is_set_item:
        part = variant_attrs[ipd_doc.set_item_attribute]
        colour = variant_attrs[ipd_doc.packing_attribute]
        stiching_accessory_json = _as_json(ipd_doc.get("stiching_accessory_json"))
        for row in stiching_accessory_json.get("items") or []:
            check = True
            if variant_attrs.get("set_colour") and row.get("major_attr_value"):
                check = variant_attrs.get("set_colour") == row["major_attr_value"]
            if row["accessory"] == accessory and row["major_colour"] == colour \
                    and row[ipd_doc.set_item_attribute] == part and check:
                return row["accessory_colour"], row["cloth_type"]
    else:
        colour = variant_attrs[ipd_doc.packing_attribute]
        stiching_accessory_json = _as_json(ipd_doc.get("stiching_accessory_json"))
        for row in stiching_accessory_json.get("items") or []:
            if row["accessory"] == accessory and row["major_colour"] == colour:
                return row["accessory_colour"], row["cloth_type"]
    frappe.throw(_(
        "No accessory colour mapping for accessory {0} / colour {1} on garment "
        "IPD {2} — fill the Stitching tab's accessory combination.").format(
        accessory, variant_attrs.get(ipd_doc.packing_attribute),
        ipd_doc.get("name") or ""))


def calculate_accessory(ipd_doc, cloth_combination, stitching_combination, attrs, qty):
    accessory_detail = []
    cloth_accessory_json = _as_json(ipd_doc.get("accessory_clothtype_json"))
    if ipd_doc.stiching_attribute in cloth_combination["accessory_attributes"] and cloth_accessory_json:
        for stiching_attr, attr_qty in stitching_combination["stitching_attribute_count"].items():
            attrs[ipd_doc.stiching_attribute] = stiching_attr
            for accessory_name, accessory_cloth in cloth_accessory_json.items():
                attrs["Accessory"] = accessory_name
                key = get_key(attrs, cloth_combination["accessory_attributes"])
                if cloth_combination["accessory_combination"].get(key):
                    dia, accessory_weight = cloth_combination["accessory_combination"][key]
                    accessory_colour, cloth = get_accessory_colour(ipd_doc, attrs, accessory_name)
                    weight = accessory_weight * qty * attr_qty
                    accessory_detail.append(
                        add_cloth_detail(weight, cloth, accessory_colour, dia, "accessory",
                                         accessory_name=accessory_name))
    elif cloth_accessory_json:
        for accessory_name, accessory_cloth in cloth_accessory_json.items():
            attrs["Accessory"] = accessory_name
            key = get_key(attrs, cloth_combination["accessory_attributes"])
            if cloth_combination["accessory_combination"].get(key):
                dia, accessory_weight = cloth_combination["accessory_combination"][key]
                accessory_colour, cloth = get_accessory_colour(ipd_doc, attrs, accessory_name)
                weight = accessory_weight * qty
                accessory_detail.append(
                    add_cloth_detail(weight, cloth, accessory_colour, dia, "accessory",
                                     accessory_name=accessory_name))
    return accessory_detail


def calculate_cloth(ipd_doc, variant_attrs, qty, cloth_combination, stitching_combination):
    attrs = variant_attrs.copy()
    if stitching_combination["stitching_attribute"] in cloth_combination["cloth_attributes"] \
            and stitching_combination["stitching_attribute"] not in cloth_combination["cutting_attributes"]:
        frappe.throw(
            f"Cannot calculate cloth quantity without "
            f"{stitching_combination['stitching_attribute']} in Cloth Weight Combination.")
    cloth_detail = []
    # Hardening (deviation): colour label sets drift between sibling IPD versions
    # of the same style ('Military Green' vs 'M Green' across Aishwarya siblings),
    # so a lot rebuilt after IPD edits can miss keys — every direct-index lookup
    # below is a .get() with a clear operator-facing throw, never a bare KeyError.
    if stitching_combination["stitching_attribute"] in cloth_combination["cutting_attributes"]:
        for stiching_attr, attr_qty in stitching_combination["stitching_attribute_count"].items():
            attrs[ipd_doc.stiching_attribute] = stiching_attr
            cloth_key = get_key(attrs, cloth_combination["cloth_attributes"])
            cutting_key = get_key(attrs, cloth_combination["cutting_attributes"])
            stich_key = attrs[ipd_doc.packing_attribute]
            if ipd_doc.is_set_item:
                stich_key = (stich_key, attrs[ipd_doc.set_item_attribute])
            if cloth_combination["cutting_combination"].get(cutting_key) \
                    and stiching_attr in stitching_combination["stitching_combination"].get(stich_key, {}):
                dia, weight = cloth_combination["cutting_combination"][cutting_key]
                cloth_type = cloth_combination["cloth_combination"].get(cloth_key)
                if not cloth_type:
                    frappe.throw(_(
                        "No cloths row for {0} in the garment IPD's Cutting tab "
                        "cloth combination — add the missing row.").format(cloth_key))
                weight = weight * qty * attr_qty
                cloth_colour = stitching_combination["stitching_combination"][stich_key][stiching_attr]
                cloth_detail.append(add_cloth_detail(weight, cloth_type, cloth_colour, dia, "cloth"))
    else:
        cutting_key = get_key(attrs, cloth_combination["cutting_attributes"])
        cutting_row = cloth_combination["cutting_combination"].get(cutting_key)
        if not cutting_row:
            frappe.throw(_(
                "No cutting row for {0} in the garment IPD's Cutting tab cloth "
                "weight combination — add the missing row.").format(cutting_key))
        dia, weight = cutting_row
        cloth_key = get_key(attrs, cloth_combination["cloth_attributes"])
        cloth_type = cloth_combination["cloth_combination"].get(cloth_key)
        if not cloth_type:
            frappe.throw(_(
                "No cloths row for {0} in the garment IPD's Cutting tab cloth "
                "combination — add the missing row.").format(cloth_key))
        weight = weight * qty
        cloth_detail.append(
            add_cloth_detail(weight, cloth_type, attrs[ipd_doc.packing_attribute], dia, "cloth"))
    accessory_detail = calculate_accessory(ipd_doc, cloth_combination, stitching_combination, attrs, qty)
    return cloth_detail + accessory_detail


def _aggregate_demand(item_detail, variant_rows, cloth_combination, stitching_combination,
                      cloth_label_to_item):
    """variant_rows: list of (attr_values dict, pieces qty). Returns
    {(cloth Item, dia, colour): kg}. Rows whose cloth LABEL (name1) is not in
    cloth_label_to_item RAISE — deliberate deviation from production_api: the
    auto-builder must never under-demand silently."""
    cloth_details = {}
    unmapped = set()
    for attr_values, qty in variant_rows:
        for c1 in calculate_cloth(item_detail, attr_values, qty, cloth_combination, stitching_combination):
            if c1["cloth_type"] not in cloth_label_to_item:
                unmapped.add(c1["cloth_type"])
                continue
            key = (cloth_label_to_item[c1["cloth_type"]], c1["dia"], c1["colour"])
            cloth_details.setdefault(key, 0)
            cloth_details[key] += c1["quantity"]
    if unmapped:
        frappe.throw(_(
            "Cloth label(s) {0} on garment IPD {1} have no matching row in the "
            "IPD's Cloth Detail table — fill the Cloth Detail rows (name + cloth "
            "Item) before building.").format(
            ", ".join(sorted(unmapped)), item_detail.get("name") or ""))
    return cloth_details


def _validate_garment_ipd(item_detail):
    """Incomplete-IPD guard: 25 live garment IPDs are empty drafts and 10 live
    Lots point at them (34178, F0124-45/52/53, F0624-64/70, F0924-18/22,
    F1024-41, 36224) — without this guard the port dies with KeyError: 'items'
    (2 of them also NULL packing_attribute -> attrs[None])."""
    incomplete = (
        not _as_json(item_detail.get("cutting_items_json")).get("items")
        or not _as_json(item_detail.get("cutting_cloths_json")).get("items")
        or not item_detail.get("packing_attribute")
        or (
            item_detail.get("stiching_attribute")
            in [a.attribute for a in item_detail.cutting_attributes]
            and not item_detail.get("stiching_item_combination_details")
        )
    )
    if incomplete:
        frappe.throw(_(
            "Garment IPD {0} is incomplete — fill the Cutting tab (cloth weights "
            "+ cloth mapping), packing attribute and stitching combinations "
            "before building cloth programs.").format(item_detail.get("name") or ""))


def compute_cloth_demand(lot_name):
    """Phase 1 SPLIT entrypoint: {(cloth Item, dia, colour): kg} for a garment Lot,
    driven by its garment IPD's Cutting tab and the Lot's lot_order_details."""
    lot_doc = frappe.get_cached_doc("Lot", lot_name)
    item_detail = frappe.get_cached_doc("Item Production Detail", lot_doc.production_detail)
    _validate_garment_ipd(item_detail)
    cloth_combination = get_cloth_combination(item_detail)
    # Non-blocking sanity: cutting Weight is kg/piece; >1.0 almost always means
    # grams were entered (5 live gram-scale IPDs, worst EC - Ryan Hoodie 34700-1
    # Weight=257) — warn, but compute exactly as entered.
    suspicious = [(key, w) for key, (d, w) in cloth_combination["cutting_combination"].items()
                  if flt(w) > 1.0]
    if suspicious:
        frappe.msgprint(
            "Garment IPD {}: cutting Weight looks gram-scale (kg/piece expected): {}. "
            "Demand is computed exactly as entered — fix the IPD if this is wrong.".format(
                item_detail.name,
                ", ".join("{}={}".format(k, w) for k, w in suspicious[:5])),
            indicator="orange")
    stitching_combination = get_stitching_combination(item_detail)
    # include ALL cloths (mimic get_calculated_bom's `if doctype:` branch) so no
    # demanded cloth is dropped for lacking is_bom_item.
    cloth_label_to_item = {c.name1: c.cloth for c in item_detail.cloth_detail if c.cloth}

    variant_rows = []
    for item in lot_doc.lot_order_details:
        qty = flt(item.quantity)
        if not qty:
            continue
        variant_doc = frappe.get_cached_doc("Item Variant", item.item_variant)
        attr_values = {x.attribute: x.attribute_value for x in variant_doc.attributes}
        if item_detail.dependent_attribute and attr_values.get(item_detail.dependent_attribute):
            del attr_values[item_detail.dependent_attribute]
        variant_rows.append((attr_values, qty))

    return _aggregate_demand(
        item_detail, variant_rows, cloth_combination, stitching_combination, cloth_label_to_item)

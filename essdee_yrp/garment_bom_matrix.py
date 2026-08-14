"""Generate Essdee garment Cutting matrices from the garment IPD definition.

The old Production API calculated cloth requirements directly from the IPD's
Cutting/Stitching JSON every time a Lot BOM was calculated.  In YRP the
equivalent per-unit rule is materialized as an ``IPD Process Matrix`` and the
generic YRP BOM engine scales that rule for each Lot variant demand.

These matrices are generated records, never user-authored records.  The
generator replaces only Cutting matrices for the explicitly requested finished
Item Variants; matrices for other processes and variants are left untouched.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_requirement import (
    _validate_garment_ipd,
    calculate_cloth,
    get_cloth_combination,
    get_stitching_combination,
)

MATRIX_CHILD_DOCTYPES = (
    "IPD Matrix Attribute",
    "IPD Matrix Combination",
    "IPD Matrix Combination Attribute",
)


def regenerate_for_lots(lot_names):
    """Regenerate the required garment BOM matrices for explicit Lots.

    This is the bounded backfill/verification entry point.  It groups Lots by
    IPD so a shared finished variant is generated only once.
    """
    lot_names = frappe.parse_json(lot_names) if isinstance(lot_names, str) else lot_names
    if isinstance(lot_names, str):
        lot_names = [lot_names]
    lot_names = list(dict.fromkeys(lot_names or []))
    if not lot_names:
        frappe.throw(_("Provide at least one Lot."))

    variants_by_ipd = defaultdict(set)
    for lot_name in lot_names:
        lot = frappe.get_doc("Lot", lot_name)
        if not lot.production_detail:
            frappe.throw(_("Lot {0} does not have an Item Production Detail.").format(lot.name))
        for row in lot.get("lot_order_details") or []:
            if row.item_variant and flt(row.quantity) > 0:
                variants_by_ipd[lot.production_detail].add(row.item_variant)

    result = {}
    for ipd_name, variants in variants_by_ipd.items():
        result[ipd_name] = regenerate_garment_bom_matrices(ipd_name, sorted(variants))
    return result


def regenerate_garment_bom_matrices(ipd_name, item_variants):
    """Replace generated Cutting matrices for the requested finished variants."""
    ipd = frappe.get_doc("Item Production Detail", ipd_name)
    if ipd.get("is_cloth_item") or frappe.db.get_value("Item", ipd.item, "is_cloth_item"):
        frappe.throw(_("{0} is a cloth IPD; use the fabric-process generator.").format(ipd.name))
    _validate_garment_ipd(ipd)
    if not ipd.cutting_process:
        frappe.throw(_("Mention Cutting Process on garment IPD {0}.").format(ipd.name))

    variants = list(dict.fromkeys(item_variants or []))
    if not variants:
        frappe.throw(_("Provide at least one finished Item Variant for IPD {0}.").format(ipd.name))

    matrix_docs = []
    for variant in variants:
        cloth_rows, output_attrs = _get_variant_cloth_rows(ipd, variant)
        if not cloth_rows:
            if any(row.is_bom_item for row in ipd.get("cloth_detail") or []):
                frappe.throw(
                    _("No BOM cloth requirement was generated for {0}.").format(variant)
                )
            # Some legacy IPDs intentionally have no cloth marked Is BOM Item.
            # Keep an output-only matrix so the generic engine can still run
            # their Item BOM accessories without inventing a cloth input.
            matrix_docs.append(_build_matrix(ipd, variant, output_attrs, None, []))
            continue
        for cloth_item, rows in _group_by_cloth_item(cloth_rows).items():
            matrix_docs.append(_build_matrix(ipd, variant, output_attrs, cloth_item, rows))

    _delete_generated_matrices(ipd.name, ipd.cutting_process, variants)
    created = []
    for matrix in matrix_docs:
        matrix.insert(ignore_permissions=True)
        created.append(matrix.name)
    return created


def _get_variant_cloth_rows(ipd, item_variant):
    variant = frappe.get_cached_doc("Item Variant", item_variant)
    if variant.item != ipd.item:
        frappe.throw(
            _("Item Variant {0} does not belong to IPD item {1}.").format(
                item_variant, ipd.item
            )
        )

    output_attrs = {
        row.attribute: row.attribute_value
        for row in variant.get("attributes") or []
        if row.attribute != ipd.dependent_attribute
    }
    cloth_combination = get_cloth_combination(ipd)
    stitching_combination = get_stitching_combination(ipd)
    cloth_label_to_item = {
        row.name1: row.cloth
        for row in ipd.get("cloth_detail") or []
        if row.name1 and row.cloth and row.is_bom_item
    }

    aggregated = defaultdict(float)
    for requirement in calculate_cloth(
        ipd,
        output_attrs,
        1,
        cloth_combination,
        stitching_combination,
    ):
        cloth_item = cloth_label_to_item.get(requirement["cloth_type"])
        if not cloth_item:
            # Production API deliberately excluded Cloth Detail rows that were
            # not marked Is BOM Item from Lot.bom_summary.
            continue
        attrs = {
            ipd.packing_attribute: requirement["colour"],
            "Dia": requirement["dia"],
        }
        key = (cloth_item, tuple(sorted(attrs.items())))
        aggregated[key] += flt(requirement["quantity"])

    rows = []
    for (cloth_item, attrs), quantity in aggregated.items():
        rows.append(
            {
                "item": cloth_item,
                "attrs": dict(attrs),
                "quantity": quantity,
                "uom": frappe.db.get_value("Item", cloth_item, "default_unit_of_measure"),
            }
        )
    return rows, output_attrs


def _group_by_cloth_item(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["item"]].append(row)
    return grouped


def _build_matrix(ipd, item_variant, output_attrs, cloth_item, cloth_rows):
    matrix = frappe.new_doc("IPD Process Matrix")
    matrix.ipd = ipd.name
    matrix.process_name = ipd.cutting_process
    matrix.reference_item_variant = item_variant
    matrix.input_item = cloth_item
    matrix.output_item = ipd.item

    item_attributes = set()
    if cloth_item:
        item_attributes = {
            row.attribute
            for row in frappe.get_cached_doc("Item", cloth_item).get("attributes") or []
        }
    input_attributes = sorted(
        {
            attribute
            for row in cloth_rows
            for attribute in row["attrs"]
            if attribute in item_attributes
        }
    )
    ipd_attributes = {row.attribute for row in ipd.get("item_attributes") or []}
    output_attrs = {
        attribute: value
        for attribute, value in output_attrs.items()
        if attribute in ipd_attributes and attribute != ipd.dependent_attribute
    }

    for attribute in input_attributes:
        matrix.append("input_attributes", {"attribute": attribute})
    for attribute in sorted(output_attrs):
        matrix.append("output_attributes", {"attribute": attribute})

    group_index = 1
    for combo_index, row in enumerate(cloth_rows, start=1):
        matrix.append(
            "combinations",
            {
                "group_index": group_index,
                "group_name": item_variant,
                "side": "Input",
                "item": cloth_item,
                "combo_index": combo_index,
                "quantity": row["quantity"],
                "uom": row["uom"],
                "wastage_pct": 0,
            },
        )
        for attribute, value in row["attrs"].items():
            matrix.append(
                "combination_attributes",
                {
                    "group_index": group_index,
                    "side": "Input",
                    "combo_index": combo_index,
                    "attribute": attribute,
                    "attribute_value": value,
                },
            )

    matrix.append(
        "combinations",
        {
            "group_index": group_index,
            "group_name": item_variant,
            "side": "Output",
            "item": ipd.item,
            "combo_index": 1,
            "quantity": 1,
            "uom": frappe.db.get_value("Item", ipd.item, "default_unit_of_measure"),
            "wastage_pct": 0,
        },
    )
    for attribute, value in output_attrs.items():
        matrix.append(
            "combination_attributes",
            {
                "group_index": group_index,
                "side": "Output",
                "combo_index": 1,
                "attribute": attribute,
                "attribute_value": value,
            },
        )
    return matrix


def _delete_generated_matrices(ipd_name, process_name, item_variants):
    names = frappe.get_all(
        "IPD Process Matrix",
        filters={
            "ipd": ipd_name,
            "process_name": process_name,
            "reference_item_variant": ["in", item_variants],
        },
        pluck="name",
    )
    if not names:
        return

    parent_filter = {
        "parent": ["in", names],
        "parenttype": "IPD Process Matrix",
    }
    for child_doctype in MATRIX_CHILD_DOCTYPES:
        frappe.db.delete(child_doctype, parent_filter)
    frappe.db.delete("IPD Process Matrix", {"name": ["in", names]})
    frappe.clear_document_cache("IPD Process Matrix")

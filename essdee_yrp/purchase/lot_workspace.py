import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_read_context import attribute_read_scope

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import get_colour_attribute
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
	build_order_item_stages,
	fetch_item_details,
	get_ocr_details,
)
from essdee_yrp.fabric_program import fetch_fabric_program_details
from essdee_yrp.web_common import permission_flags

HEADER_FIELDS = (
	"version",
	"capacity_planning",
	"primary_item_attribute",
	"production_order",
	"item",
	"assigned_person",
	"season",
	"size_set_colour",
	"production_detail",
	"cloth_excess_percentage",
	"uom",
	"expected_delivery_date",
	"has_transferred",
	"is_transferred",
	"transferred_lot",
)
ORDER_DETAIL_FACTS = ("pack_in_stage", "pack_out_stage", "packing_uom", "total_order_quantity")
BOM_FACTS = ("total_quantity", "last_calculated_time")
ATTRIBUTE_VALUE_FIELDS = {"pack_out_stage", "pack_in_stage"}
ORDER_STAGES = (
	("quantity", _("Order")),
	("cut_qty", _("Cut")),
	("stich_qty", _("Stitched")),
	("pack_qty", _("Packed")),
)
FABRIC_ENTRY_KEYS = (
	"cloth_item",
	"production_detail",
	"plan_status",
	"plan_built_on",
	"dyed_yarn_colours",
	"requirement",
	"program",
	"steps",
)
CONVERSION_FIELDS = (
	"production_detail",
	"process_stage_index",
	"process_name",
	"planned_item",
	"actual_item",
	"actual_quantity",
	"stock_uom",
	"source_grn_count",
)


@frappe.whitelist()
def get_lot_workspace(name: str) -> dict:
	with attribute_read_scope():
		return _build_lot_workspace(name)


def _build_lot_workspace(name: str) -> dict:
	doc = frappe.get_doc("SD YRP Lot", name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"has_cloth_program": bool(doc.get("lot_fabric_programs")),
		"modified": str(doc.modified),
		"status": doc.status or "Open",
		"permissions": permission_flags("SD YRP Lot", ("write", "create"), doc),
		"header": get_facts(doc, HEADER_FIELDS),
		"details": get_facts(doc, ORDER_DETAIL_FACTS + BOM_FACTS),
		"order_items": get_order_items(doc),
		"order_details": get_order_details(doc),
		"bom": get_bom(doc),
		"ocr": get_ocr(doc),
		"fabrics": get_fabrics(doc),
		"other_conversions": get_other_conversions(doc),
	}


def get_facts(doc, fieldnames):
	facts = []
	for fieldname in fieldnames:
		raw_value = doc.get(fieldname)
		value = raw_value
		if fieldname == "assigned_person":
			value = doc.get("assigned_person_name") or value
		if not value:
			continue
		if fieldname in ATTRIBUTE_VALUE_FIELDS:
			value = _attribute_value(value)
		field = doc.meta.get_field(fieldname)
		fact = {
			"fieldname": fieldname,
			"label": doc.meta.get_label(fieldname),
			"fieldtype": field.fieldtype,
			"value": value,
			**link_fact_metadata(doc, field),
		}
		if value != raw_value and field.fieldtype in ("Link", "Dynamic Link"):
			fact["link_name"] = raw_value
		facts.append(fact)
	return facts


def link_fact_metadata(doc, field):
	if field.fieldtype == "Dynamic Link":
		return {"options": field.options, "link_doctype": doc.get(field.options)}
	if field.fieldtype == "Link":
		return {"options": field.options}
	return {}


def get_order_items(doc):
	if not doc.production_detail or not doc.get("items"):
		return None
	details = fetch_item_details(doc.get("items"), doc.production_detail)
	return {
		"item": details["item"],
		"uom": details.get("default_uom"),
		"attributes": details.get("final_state_attr") or [],
		"sizes": details["primary_attribute_values"] if details.get("primary_attribute") else [],
		"items": [{"attributes": r["attributes"], "values": r["values"]} for r in details["items"]],
	}


def get_order_details(doc):
	if not doc.production_detail or not doc.get("lot_order_details"):
		return None
	ipd_doc = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
	stage_groups = build_order_item_stages(
		doc.lot_order_details, ipd_doc, tuple(key for key, _label in ORDER_STAGES)
	)
	stages = [
		{"key": key, "label": label}
		for key, label in ORDER_STAGES
		if key == "quantity" or any(group["total_sum"] for group in stage_groups[key])
	]
	return {
		"colour_attribute": get_colour_attribute(),
		"stages": stages,
		"groups": merge_order_stages(stage_groups, stages, doc),
	}


def merge_order_stages(stage_groups, stages, doc):
	groups = []
	for index, base in enumerate(stage_groups["quantity"]):
		parts = {stage["key"]: stage_groups[stage["key"]][index] for stage in stages}
		sizes = base["primary_attribute_values"] if base.get("primary_attribute") else ["default"]
		groups.append(
			{
				"attributes": base["attributes"],
				"sizes": sizes,
				"items": [_merge_order_row(row, i, parts, sizes, doc) for i, row in enumerate(base["items"])],
				"size_totals": {key: group["size_wise_total"] for key, group in parts.items()},
				"totals": {key: group["total_sum"] for key, group in parts.items()},
			}
		)
	return groups


def _merge_order_row(row, index, parts, sizes, doc):
	rows = {key: group["items"][index] for key, group in parts.items()}
	return {
		"attributes": row["attributes"],
		"colour_note": colour_note(doc, row),
		"values": {size: {key: r["values"][size]["qty"] for key, r in rows.items()} for size in sizes},
		"totals": {key: r["total_qty"] for key, r in rows.items()},
	}


def colour_note(doc, row):
	if doc.version not in ("V2", "V3") or not row["is_set_item"]:
		return None
	if row["attributes"].get(row["set_attr"]) != row["major_attr_value"]:
		return row["item_keys"].get("major_colour")
	return None


def bom_rows(rows):
	return [
		{
			"item": r.item_name,
			"process_name": r.process_name,
			"required_qty": flt(r.required_qty),
			"uom": r.uom,
		}
		for r in rows or []
	]


def get_bom(doc):
	summary = bom_rows(doc.get("bom_summary"))
	additional = bom_rows(doc.get("bom_additional_items"))
	if not summary and not additional:
		return None
	return {
		"precision": cint(frappe.get_meta("SD YRP Lot BOM").get_field("required_qty").precision),
		"summary": summary,
		"additional": additional,
	}


def get_ocr(doc):
	if not doc.item or not doc.production_detail:
		return None
	payload = get_ocr_details(doc.name)
	return payload if payload.get("processes") or flt(payload.get("total_dispatch")) else None


def get_fabrics(doc):
	fabrics = doc.get("lot_fabric_details") or []
	entries = {e["cloth_item"]: e for e in fetch_fabric_program_details(doc)} if fabrics else {}
	return [_fabric_card(doc, fabric, entries.get(fabric.cloth_item)) for fabric in fabrics]


def _fabric_card(doc, fabric, entry):
	if entry is None:
		entry = {
			"cloth_item": fabric.cloth_item,
			"production_detail": fabric.production_detail,
			"plan_status": fabric.plan_status,
			**{key: [] for key in ("dyed_yarn_colours", "requirement", "program", "steps")},
		}
	return {
		**{key: entry.get(key) for key in FABRIC_ENTRY_KEYS},
		"plan_error": fabric.plan_error,
		"conversions": conversion_rows(doc, {fabric.production_detail}),
		"legacy_colour_program": [
			_legacy_colour_row(r)
			for r in doc.get("lot_colour_programs") or []
			if r.cloth_item == fabric.cloth_item
		],
	}


def _legacy_colour_row(row):
	return {
		"dia": _attribute_value(row.dia),
		"colour": _attribute_value(row.colour),
		"weight": flt(row.weight),
		"received_weight": flt(row.received_weight),
		"compacted_weight": flt(row.compacted_weight),
	}


def conversion_rows(doc, production_details, unmatched=False):
	rows = sorted(doc.get("lot_fabric_conversions") or [], key=lambda r: r.idx)
	return [
		{key: r.get(key) for key in CONVERSION_FIELDS}
		for r in rows
		if (r.production_detail in production_details) != unmatched
	]


def get_other_conversions(doc):
	production_details = {r.production_detail for r in doc.get("lot_fabric_details") or []}
	return conversion_rows(doc, production_details, unmatched=True)

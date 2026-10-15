"""Web contract for SD YRP Lotwise Item Profit documents."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.product_development import lotwise_costing
from essdee_yrp.product_development.web_workspace import (
	LOTWISE,
	child_rows_for_save,
	size_labels,
)
from essdee_yrp.web_common import assert_expected_modified, parse_mapping, permission_flags

COMMANDS = {
	"recalculate": lotwise_costing.calculate_all,
	"load_product_sizes": lotwise_costing.load_product_sizes,
	"load_item_sizes": lotwise_costing.load_item_sizes,
	"add_rate": lotwise_costing.add_rate,
	"build_piece_cloth_weight": lotwise_costing.build_piece_cloth_weight,
	"calculate_cloth_qty": lotwise_costing.calculate_cloth_qty,
	"apply_discount_template": lambda doc: lotwise_costing.apply_additional_cost_template(
		doc, "trade_discounts_template"
	),
	"apply_other_cost_template": lambda doc: lotwise_costing.apply_additional_cost_template(
		doc, "other_costs_template"
	),
	"apply_production_cost_template": lotwise_costing.apply_production_cost_template,
	"fetch_lot_qty": lotwise_costing.fetch_lot_qty,
}
LOTWISE_FIELDS = (
	"item",
	"product",
	"lot",
	"lot_costing_type",
	"disabled",
	"gst",
	"additional_rate",
	"trade_discounts_template",
	"other_costs_template",
	"production_cost_template",
)
LOTWISE_TABLES = (
	"qty_rate_chart",
	"cloth_value",
	"piece_cloth_weight",
	"cmt",
	"packing_materials",
	"trims",
	"trade_discounts",
	"other_costs",
)
LOTWISE_LINK_FILTERS = {
	"trade_discounts_template": {"type": "Discounts"},
	"other_costs_template": {"type": "Other"},
}
SIZE_TABLES = ("qty_rate_chart", "piece_cloth_weight")


def costing_types() -> list[str]:
	options = frappe.get_meta(LOTWISE).get_field("lot_costing_type").options or ""
	return [option for option in options.split("\n") if option]


def record_payload(doc) -> tuple[dict, dict[str, str]]:
	record = doc.as_dict()
	labels = size_labels(
		[row for table in SIZE_TABLES for row in doc.get(table) or []], fieldname="size"
	)
	for table in SIZE_TABLES:
		for row in record.get(table) or []:
			row["size"] = labels.get(row.get("size"), row.get("size"))
	return record, labels


def workspace_payload(doc) -> dict:
	record, labels = record_payload(doc)
	return {
		"record": record,
		"size_labels": labels,
		"modified": str(doc.modified) if not doc.is_new() else "",
		"permissions": permission_flags(
			LOTWISE,
			("read", "create", "write", "delete", "print"),
			None if doc.is_new() else doc,
		),
		"costing_types": costing_types(),
		"link_filters": LOTWISE_LINK_FILTERS,
		"commands": [*COMMANDS, "calculate_rate"],
	}


@frappe.whitelist()
def get_lotwise_workspace(name: str | None = None, product: str | None = None) -> dict:
	if name:
		doc = frappe.get_doc(LOTWISE, name)
		doc.check_permission("read")
		return workspace_payload(doc)
	frappe.has_permission(LOTWISE, "create", throw=True)
	doc = frappe.new_doc(LOTWISE)
	if product:
		doc.product = product
		lotwise_costing.load_product_sizes(doc)
	return workspace_payload(doc)


def apply_lotwise_values(doc, values: dict) -> None:
	for fieldname in LOTWISE_FIELDS:
		if fieldname in values:
			doc.set(fieldname, values[fieldname])
	for table in LOTWISE_TABLES:
		if table in values:
			doc.set(table, child_rows_for_save(doc, table, values[table]))


def draft_doc(values: dict, name: str | None):
	if name:
		doc = frappe.get_doc(LOTWISE, name)
		doc.check_permission("write")
	else:
		frappe.has_permission(LOTWISE, "create", throw=True)
		doc = frappe.new_doc(LOTWISE)
	apply_lotwise_values(doc, values)
	return doc


def doc_for_save(name: str | None, expected_modified: str | None):
	if not name:
		frappe.has_permission(LOTWISE, "create", throw=True)
		return frappe.new_doc(LOTWISE)
	doc = frappe.get_doc(LOTWISE, name, for_update=True)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	return doc


def calculate_rate(doc, payload) -> None:
	percent = parse_mapping(payload or {}, _("Payload")).get("percent")
	if not isinstance(percent, (int, float)) or isinstance(percent, bool):
		frappe.throw(_("Markdown Percent must be a number."))
	lotwise_costing.calculate_backwards_rate(doc, flt(percent))


@frappe.whitelist()
def run_lotwise_command(values, command: str, payload=None, name: str | None = None) -> dict:
	doc = draft_doc(parse_mapping(values, _("Values")), name)
	if command == "calculate_rate":
		calculate_rate(doc, payload)
	elif isinstance(command, str) and command in COMMANDS:
		COMMANDS[command](doc)
	else:
		frappe.throw(_("Unsupported Lotwise command {0}.").format(frappe.bold(command)))
	record, labels = record_payload(doc)
	return {"record": record, "size_labels": labels}


@frappe.whitelist()
def save_lotwise_item_profit(
	values, name: str | None = None, expected_modified: str | None = None
) -> dict:
	doc = doc_for_save(name, expected_modified)
	apply_lotwise_values(doc, parse_mapping(values, _("Values")))
	doc.save() if name else doc.insert()
	return workspace_payload(doc)


@frappe.whitelist()
def delete_lotwise_item_profit(name: str, expected_modified: str | None = None) -> dict:
	doc = frappe.get_doc(LOTWISE, name, for_update=True)
	doc.check_permission("delete")
	assert_expected_modified(doc, expected_modified)
	frappe.delete_doc(LOTWISE, name)
	return {"deleted": True}

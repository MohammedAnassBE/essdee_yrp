import frappe
from frappe import _

from essdee_yrp.cut_panel_store import web_workspace as cut_panel_store
from essdee_yrp.fabric_store import web_workspace as fabric_store
from essdee_yrp.merch import web_workspace as merch
from essdee_yrp.purchase import web_capabilities as purchase

# Fabric Store sections the Purchase department shows; its reports come with them.
PURCHASE_STORE_SECTIONS = ("purchase_orders", "stock_transfers")


@frappe.whitelist()
def get_capabilities() -> dict:
	"""Merch and Purchase capabilities in one payload; each section keeps its source's DocType checks."""
	merch_capabilities = merch.get_capabilities()
	store_sections = fabric_store.get_capabilities()["sections"]
	sections = {key: section for key, section in merch_capabilities["sections"].items() if key != "reports"}
	for key, section in purchase.get_capabilities()["sections"].items():
		sections[key] = {**section, **sections.get(key, {})}
	for key in PURCHASE_STORE_SECTIONS:
		if key in store_sections:
			sections[key] = {"can_read": True, **store_sections[key]}
	box_stickers = cut_panel_store.get_capabilities()["sections"].get("box_stickers")
	if box_stickers:
		sections["box_stickers"] = box_stickers

	reports = {**store_sections.get("reports", {}).get("reports", {}), **merch_capabilities["reports"]}
	sections["reports"] = {
		"label": _("Reports"),
		"can_read": any(report["can_read"] for report in reports.values()),
		"can_create": False,
	}
	return {"sections": sections, "reports": reports}

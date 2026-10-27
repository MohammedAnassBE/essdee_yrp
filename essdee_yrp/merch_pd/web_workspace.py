import frappe

from essdee_yrp.merch_purchase import web_workspace as merch_purchase
from essdee_yrp.product_development import web_workspace as product_development
from essdee_yrp.web_common import report_access_scope

MERCH_PD_SECTIONS = ("lots", "item_production_details", "purchase_orders", "bill_tracking", "lotwise_item_profits")


@frappe.whitelist()
@report_access_scope()
def get_capabilities() -> dict:
	"""Lot, Item Production Detail, Purchase Order, Vendor Bill Tracking and Lotwise Item Profit; each keeps its source's DocType checks."""
	sources = {**merch_purchase.get_capabilities()["sections"], **product_development.get_capabilities()["sections"]}
	return {"sections": {key: sources[key] for key in MERCH_PD_SECTIONS if key in sources}}

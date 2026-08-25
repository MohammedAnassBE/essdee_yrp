# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from essdee_yrp.lot_pricing import sync_unprinted_box_sticker_prices
from essdee_yrp.production_order_workflow import lock_production_orders
from yrp.utils import get_variant_attr_details


class PPOPriceRequest(Document):
	pass


def _require_system_manager(action):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(f"Only System Manager can {action} price changes")


def _pending_request(name, action):
	_require_system_manager(action)
	doc = frappe.get_doc("PPO Price Request", name)
	doc.check_permission("write")
	if doc.status != "Pending":
		frappe.throw(f"Cannot {action} a request with status '{doc.status}'")
	return doc


@frappe.whitelist()
def approve_ppo_price_request(name):
	doc = _pending_request(name, "approve")
	lock_production_orders(doc.production_order)
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_at = frappe.utils.now_datetime()
	doc.save()
	_apply_price_to_production_order(doc)
	_apply_price_to_box_sticker_prints(doc)
	frappe.db.set_value(
		"Production Order",
		doc.production_order,
		"price_approval_status",
		"",
		update_modified=False,
	)
	return {"status": "success"}


@frappe.whitelist()
def reject_ppo_price_request(name):
	doc = _pending_request(name, "reject")
	doc.status = "Rejected"
	doc.approved_by = frappe.session.user
	doc.approved_at = frappe.utils.now_datetime()
	doc.save()
	frappe.db.set_value(
		"Production Order",
		doc.production_order,
		"price_approval_status",
		"",
		update_modified=False,
	)
	return {"status": "success"}


def _apply_price_to_production_order(price_request):
	production_order = frappe.get_doc(
		"Production Order", price_request.production_order
	)
	primary = frappe.db.get_value("Item", production_order.item, "primary_attribute")
	rows = {
		get_variant_attr_details(row.item_variant).get(primary): row
		for row in production_order.production_order_details
	}
	for detail in price_request.price_details:
		row = rows.get(detail.size)
		if not row:
			frappe.throw(
				f"Size {detail.size} is no longer present in {production_order.name}"
			)
		if row.get("production_order_mrp") in (None, ""):
			row.production_order_mrp = row.mrp
		row.mrp = detail.new_mrp
		row.wholesale_price = detail.new_wholesale_price
		row.retail_price = detail.new_retail_price
	production_order.flags.allow_ppo_price_approval = True
	production_order.save(ignore_permissions=True)


def _apply_price_to_box_sticker_prints(price_request):
	for lot in frappe.get_all(
		"Lot",
		filters={"production_order": price_request.production_order},
		pluck="name",
	):
		sync_unprinted_box_sticker_prices(lot, price_request.production_order)

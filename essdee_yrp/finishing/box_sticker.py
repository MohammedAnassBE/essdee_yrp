"""Essdee Box Sticker side effects for submitted packing Work Orders."""

import copy
import math

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.lot_pricing import get_effective_lot_price_map
from essdee_yrp.production_order_alternative import _lock_production_orders
from yrp.utils import get_variant_attr_details


def build_box_sticker_details(production_order_sizes, quantity_by_size, price_by_size):
	"""Build deterministic sticker rows from the resolved PPO/Lot price snapshot."""
	sizes = []
	for size in production_order_sizes:
		if size not in sizes:
			sizes.append(size)
	for size in quantity_by_size:
		if size not in sizes:
			sizes.append(size)

	details = []
	for size in sizes:
		quantity = flt(quantity_by_size.get(size))
		if quantity > 0 or size in production_order_sizes:
			details.append(
				{
					"size": size,
					"quantity": quantity,
					"mrp": flt(price_by_size.get(size)),
					"allow_excess_quantity": 1 if quantity <= 0 else 0,
					"allow_excess_percentage": 5,
				}
			)
	return details


def get_missing_box_sticker_prices(work_order):
	"""Return produced sizes that have no effective PPO/Lot MRP."""
	work_order = _work_order(work_order)
	production_order = frappe.db.get_value('SD YRP Lot', work_order.lot, "production_order")
	if not production_order or frappe.db.get_value(
		'YRP Production Order', production_order, "skip_box_sticker_print"
	):
		return []
	primary_attribute = frappe.db.get_value('YRP Item', work_order.item, "primary_attribute")
	if not primary_attribute:
		return []
	quantity_by_size = _quantity_by_size(work_order, primary_attribute)
	price_by_size = get_effective_lot_price_map(work_order.lot, production_order)
	return sorted(
		size
		for size, quantity in quantity_by_size.items()
		if quantity > 0 and flt(price_by_size.get(size)) <= 0
	)


def auto_create_box_sticker_print(work_order):
	"""Create submitted box and piece sticker documents for a packing Work Order."""
	work_order = _work_order(work_order)
	production_order = frappe.db.get_value('SD YRP Lot', work_order.lot, "production_order")
	if not production_order or frappe.db.get_value(
		'YRP Production Order', production_order, "skip_box_sticker_print"
	):
		return []

	_lock_production_orders(production_order)
	primary_attribute = frappe.db.get_value('YRP Item', work_order.item, "primary_attribute")
	if not primary_attribute or not frappe.db.exists('SD YRP FG Item Master', work_order.item):
		return []
	if frappe.db.exists(
		'SD YRP Box Sticker Print',
		{
			"lot": work_order.lot,
			"docstatus": 1,
			"against": 'YRP Work Order',
			"against_id": ["!=", ""],
		},
	):
		return []

	missing_prices = get_missing_box_sticker_prices(work_order)
	if missing_prices:
		frappe.throw(
			_("MRP is missing for Lot {0} in sizes: {1}. Update the Production Order or Lot price before submitting.").format(
				work_order.lot, ", ".join(missing_prices)
			)
		)

	production_order_doc = frappe.get_doc('YRP Production Order', production_order)
	production_order_sizes = []
	for row in production_order_doc.production_order_details:
		size = get_variant_attr_details(row.item_variant).get(primary_attribute)
		if size:
			production_order_sizes.append(size)
	quantity_by_size = _quantity_by_size(work_order, primary_attribute)
	price_by_size = get_effective_lot_price_map(
		work_order.lot, production_order, for_update=True
	)
	details = build_box_sticker_details(
		production_order_sizes, quantity_by_size, price_by_size
	)
	if not details:
		return []

	production_detail = frappe.db.get_value(
		'SD YRP Lot', work_order.lot, "production_detail"
	)
	is_set_item, pieces_per_box = (0, 0)
	if production_detail:
		is_set_item, pieces_per_box = frappe.db.get_value(
			'YRP Item Production Detail',
			production_detail,
			["is_set_item", "packing_combo"],
		) or (0, 0)
	settings = frappe.get_cached_doc('SD YRP MRP Settings')
	if is_set_item:
		box_format = settings.set_item_box_sticker
		print_formats = [box_format, settings.set_item_piece_sticker]
	else:
		box_format = settings.non_set_box_sticker
		print_formats = [box_format, settings.non_set_piece_sticker]
	print_formats = list(dict.fromkeys(value for value in print_formats if value))
	if not print_formats:
		frappe.msgprint(
			_("No Box Sticker Print Formats are configured in MRP Settings"),
			indicator="orange",
			alert=True,
		)
		return []

	created = []
	for print_format in print_formats:
		print_details = copy.deepcopy(details)
		if print_format == box_format and flt(pieces_per_box) > 0:
			for row in print_details:
				row["quantity"] = math.ceil(flt(row["quantity"]) / flt(pieces_per_box))
		box_sticker = frappe.new_doc('SD YRP Box Sticker Print')
		box_sticker.update(
			{
				"lot": work_order.lot,
				"fg_item": work_order.item,
				"piece_per_box": frappe.db.get_value(
					'SD YRP FG Item Master', work_order.item, "pcs_per_box"
				),
				"print_format": print_format,
				"against": 'YRP Work Order',
				"against_id": work_order.name,
			}
		)
		box_sticker.set("box_sticker_print_details", print_details)
		box_sticker.insert(ignore_permissions=True)
		box_sticker.flags.ignore_permissions = True
		box_sticker.submit()
		created.append(box_sticker.name)
	return created


def cancel_box_sticker_prints(work_order):
	"""Cancel only the submitted stickers generated for this Work Order."""
	work_order = _work_order(work_order)
	for name in frappe.get_all(
		'SD YRP Box Sticker Print',
		filters={
			"against": 'YRP Work Order',
			"against_id": work_order.name,
			"docstatus": 1,
		},
		pluck="name",
	):
		doc = frappe.get_doc('SD YRP Box Sticker Print', name)
		doc.flags.ignore_permissions = True
		doc.cancel()


def _quantity_by_size(work_order, primary_attribute):
	quantities = {}
	for row in work_order.get("work_order_calculated_items") or []:
		size = get_variant_attr_details(row.item_variant).get(primary_attribute)
		if size:
			quantities[size] = quantities.get(size, 0) + flt(row.quantity)
	return quantities


def _work_order(value):
	return frappe.get_doc('YRP Work Order', value) if isinstance(value, str) else value

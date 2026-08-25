# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

from yrp.stock.dimensions import apply_dimension_defaults, get_dimension_fieldnames
from yrp.stock.uom import apply_item_uom


class LotTransfer(Document):
	def before_validate(self):
		from yrp.stock.utils import apply_posting_datetime

		apply_posting_datetime(self)
		apply_dimension_defaults(self.items)

	def validate(self):
		if not self.get("items"):
			frappe.throw(_("Add at least one item to transfer."))
		for row in self.items:
			self._validate_row(row)

	def _validate_row(self, row):
		if row.from_lot == row.to_lot:
			frappe.throw(_("Row {0}: From Lot and To Lot must be different.").format(row.idx))
		if flt(row.qty) <= 0:
			frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))

		from yrp.yrp.doctype.item.item import (
			validate_cancelled_item,
			validate_disabled,
			validate_is_stock_item,
		)

		parent_item = frappe.db.get_value("Item Variant", row.item, "item")
		if not parent_item:
			frappe.throw(_("Row {0}: Item Variant {1} does not exist.").format(row.idx, row.item))
		validate_disabled(parent_item)
		validate_is_stock_item(parent_item)
		validate_cancelled_item(parent_item)

		from yrp.stock.utils import get_stock_balance

		apply_item_uom(row, item_field="item")
		row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
		if not flt(row.rate):
			dimensions = {
				fieldname: row.get(fieldname) for fieldname in get_dimension_fieldnames()
			}
			dimensions["lot"] = row.from_lot
			row.rate = get_stock_balance(
				row.item,
				row.warehouse,
				posting_date=self.posting_date,
				posting_time=self.posting_time,
				with_valuation_rate=True,
				uom=row.uom,
				**dimensions,
			)[1]
		row.stock_uom_rate = flt(row.rate) / (flt(row.conversion_factor) or 1)
		row.amount = flt(row.rate) * flt(row.qty)

	def on_submit(self):
		self._update_stock_ledger()
		self._repost_future_entries()

	def before_cancel(self):
		self.ignore_linked_doctypes = (
			"Stock Ledger Entry",
			"Repost Item Valuation",
		)
		self._update_stock_ledger()

	def on_cancel(self):
		self._repost_future_entries()

	def _update_stock_ledger(self):
		from yrp.stock.stock_ledger import make_sl_entries

		entries = []
		for row in self.items:
			transfer_key = f"Lot Transfer:{self.name}:{row.name}"
			entries.append(
				self._stock_row(
					row,
					row.from_lot,
					-row.stock_qty,
					0,
					transfer_key=transfer_key,
					transfer_role="outgoing",
				)
			)
			entries.append(
				self._stock_row(
					row,
					row.to_lot,
					row.stock_qty,
					row.stock_uom_rate,
					transfer_key=transfer_key,
					transfer_role="incoming",
				)
			)
		if self.docstatus == 2:
			entries.reverse()
		make_sl_entries(entries, cancel=self.docstatus == 2, force_inline=True)

	def _stock_row(
		self, row, lot, qty, rate, transfer_key=None, transfer_role=None
	):
		entry = frappe._dict(
			{
				"item": row.item,
				"warehouse": cstr(row.warehouse),
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_detail_no": row.name,
				"qty": flt(qty),
				"uom": row.stock_uom,
				"rate": flt(rate),
				"outgoing_rate": flt(row.stock_uom_rate) if qty < 0 else 0,
				"is_cancelled": 1 if self.docstatus == 2 else 0,
				"_transfer_key": transfer_key,
				"_transfer_role": transfer_role,
			}
		)
		for fieldname in get_dimension_fieldnames():
			entry[fieldname] = row.get(fieldname)
		entry.lot = cstr(lot)
		return entry

	def _repost_future_entries(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)


def get_lot_transfer_target_lot(items):
	target_lots = {row.to_lot for row in items if flt(row.qty) > 0 and row.to_lot}
	if len(target_lots) != 1:
		frappe.throw(_("Make DC requires all Lot Transfer items to have one target Lot"))
	return target_lots.pop()


def get_lot_transfer_items_for_target_lot(items, target_lot):
	target_items = [
		row for row in items if row.to_lot == target_lot and flt(row.qty) > 0
	]
	if not target_items:
		frappe.throw(_("Lot Transfer has no items for target Lot {0}").format(target_lot))
	return target_items


def get_lot_transfer_delivery_items(transfer_items, work_order_items, target_lot):
	"""Overlay the physical Lot Transfer quantity on exact WO deliverable rows."""

	transfer_qty = {}
	transfer_uom = {}
	received_types = {}
	for row in transfer_items:
		if flt(row.qty) <= 0:
			continue
		transfer_qty[row.item] = flt(transfer_qty.get(row.item)) + flt(row.qty)
		transfer_uom.setdefault(row.item, row.uom)
		received_types.setdefault(row.item, row.get("received_type"))
		if transfer_uom[row.item] != row.uom:
			frappe.throw(_("Item {0} has multiple UOMs in the Lot Transfer").format(row.item))

	delivery_items = []
	first_matching_row = {}
	for source in work_order_items:
		item = frappe._dict(source.as_dict())
		item.lot = target_lot
		item.received_type = received_types.get(item.item_variant)
		item.ref_doctype = "Work Order Deliverables"
		item.ref_docname = item.name
		item.comments = None
		item.delivered_quantity = 0
		available_qty = max(flt(item.pending_quantity), 0)
		item.qty = available_qty

		remaining_qty = flt(transfer_qty.get(item.item_variant))
		if remaining_qty > 0:
			first_matching_row.setdefault(item.item_variant, len(delivery_items))
			if transfer_uom[item.item_variant] != item.uom:
				frappe.throw(
					_(
						"UOM mismatch for Item {0}: Lot Transfer uses {1}, "
						"but Work Order uses {2}"
					).format(item.item_variant, transfer_uom[item.item_variant], item.uom)
				)
			delivered_qty = min(remaining_qty, available_qty)
			item.delivered_quantity = delivered_qty
			item.qty = delivered_qty
			transfer_qty[item.item_variant] = remaining_qty - delivered_qty
		delivery_items.append(item)

	items_not_in_work_order = []
	for item_variant, quantity in transfer_qty.items():
		excess_qty = flt(quantity, 3)
		if excess_qty <= 0:
			continue
		if item_variant in first_matching_row:
			item = delivery_items[first_matching_row[item_variant]]
			item.delivered_quantity = flt(item.delivered_quantity + excess_qty, 3)
			item.qty = item.delivered_quantity
			continue
		items_not_in_work_order.append(item_variant)

	if items_not_in_work_order:
		frappe.throw(
			_(
				"The following Lot Transfer items are not in the selected Work Order "
				"deliverables: {0}"
			).format(", ".join(sorted(items_not_in_work_order)))
		)
	return [row for row in delivery_items if flt(row.qty) > 0]


@frappe.whitelist()
def get_delivery_challan_details(doc_name, work_order, from_location, target_lot=None):
	"""Build F16 Delivery Challan defaults for one target Lot in a bulk transfer."""

	lot_transfer = frappe.get_doc("Lot Transfer", doc_name)
	lot_transfer.check_permission("read")
	if lot_transfer.docstatus != 1:
		frappe.throw(_("Submit the Lot Transfer before making a Delivery Challan"))
	if not from_location or not frappe.db.exists("Supplier", from_location):
		frappe.throw(_("Select a valid From Location"))

	work_order_doc = frappe.get_doc("Work Order", work_order)
	work_order_doc.check_permission("read")
	if (
		work_order_doc.docstatus != 1
		or work_order_doc.open_status != "Open"
		or work_order_doc.is_delivered
	):
		frappe.throw(_("Select an open, submitted Work Order"))

	transfer_items = lot_transfer.items
	if target_lot:
		transfer_items = get_lot_transfer_items_for_target_lot(
			transfer_items, target_lot
		)
	else:
		target_lot = get_lot_transfer_target_lot(transfer_items)
	if work_order_doc.lot != target_lot:
		frappe.throw(
			_("Work Order {0} must belong to target Lot {1}").format(
				work_order, target_lot
			)
		)

	items = get_lot_transfer_delivery_items(
		transfer_items, work_order_doc.deliverables, target_lot
	)
	from yrp.stock.save_stock_items import group_items_for_ui
	from yrp.yrp.doctype.supplier.supplier import get_primary_address
	from frappe.contacts.doctype.address.address import get_address_display

	from_address = get_primary_address(from_location)
	if not from_address:
		frappe.throw(
			_("Primary Address is not configured for From Location {0}").format(
				from_location
			)
		)
	supplier_address = work_order_doc.supplier_address or get_primary_address(
		work_order_doc.supplier
	)
	if not supplier_address:
		frappe.throw(
			_("Primary Address is not configured for Supplier {0}").format(
				work_order_doc.supplier
			)
		)

	return {
		"items": items,
		"item_details": group_items_for_ui(items, "Delivery Challan"),
		"work_order": work_order_doc.name,
		"lot": target_lot,
		"item": work_order_doc.item,
		"production_detail": work_order_doc.production_detail,
		"process_name": work_order_doc.process_name,
		"includes_packing": work_order_doc.includes_packing,
		"is_internal_unit": work_order_doc.is_internal_unit,
		"from_location": from_location,
		"from_address": from_address,
		"from_address_details": get_address_display(from_address),
		"supplier": work_order_doc.supplier,
		"supplier_name": work_order_doc.supplier_name,
		"supplier_address": supplier_address,
		"supplier_address_details": get_address_display(supplier_address),
	}

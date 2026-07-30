# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt


class LotTransfer(Document):
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

		from yrp.stock.utils import get_conversion_factor, get_stock_balance

		details = get_conversion_factor(row.item, row.uom)
		row.stock_uom = details.get("stock_uom")
		row.conversion_factor = details.get("conversion_factor")
		row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
		if not flt(row.rate):
			row.rate = get_stock_balance(
				row.item,
				row.warehouse,
				posting_date=self.posting_date,
				posting_time=self.posting_time,
				with_valuation_rate=True,
				lot=row.from_lot,
				received_type=row.received_type,
				uom=row.uom,
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
			entries.append(self._stock_row(row, row.from_lot, -row.stock_qty, 0))
			entries.append(
				self._stock_row(
					row,
					row.to_lot,
					row.stock_qty,
					row.stock_uom_rate,
				)
			)
		if self.docstatus == 2:
			entries.reverse()
		make_sl_entries(entries, cancel=self.docstatus == 2)

	def _stock_row(self, row, lot, qty, rate):
		return frappe._dict(
			{
				"item": row.item,
				"warehouse": cstr(row.warehouse),
				"received_type": row.received_type,
				"lot": cstr(lot),
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
			}
		)

	def _repost_future_entries(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)

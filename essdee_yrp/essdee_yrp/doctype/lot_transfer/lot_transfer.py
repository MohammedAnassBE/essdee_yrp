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

		from yrp.stock.uom import resolve_item_uom
		from yrp.stock.utils import get_stock_balance

		details = resolve_item_uom(row.item)
		row.uom = details.uom
		row.stock_uom = details.stock_uom
		row.conversion_factor = details.conversion_factor
		row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
		source_dimensions = self._stock_dimensions(row, row.from_lot)
		row.stock_dimensions = frappe.as_json(source_dimensions)
		_stock_balance, stock_uom_rate = get_stock_balance(
			row.item,
			row.warehouse,
			posting_date=self.posting_date,
			posting_time=self.posting_time,
			with_valuation_rate=True,
			**source_dimensions,
		)
		row.stock_uom_rate = flt(stock_uom_rate)
		row.rate = flt(stock_uom_rate) * flt(row.conversion_factor)
		row.amount = flt(row.stock_uom_rate) * flt(row.stock_qty)

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
			transfer_key = f"{self.name}:{row.name}"
			entries.append(
				self._stock_row(
					row,
					row.from_lot,
					-row.stock_qty,
					0,
					transfer_key,
					"outgoing",
				)
			)
			entries.append(
				self._stock_row(
					row,
					row.to_lot,
					row.stock_qty,
					row.stock_uom_rate,
					transfer_key,
					"incoming",
				)
			)
		if self.docstatus == 2:
			entries.reverse()
		transfer_rates = make_sl_entries(entries, cancel=self.docstatus == 2)
		if self.docstatus != 2:
			for row in self.items:
				actual_rate = flt(transfer_rates.get(f"{self.name}:{row.name}"))
				if not actual_rate:
					continue
				values = {
					"stock_uom_rate": actual_rate,
					"rate": actual_rate * flt(row.conversion_factor),
					"amount": actual_rate * flt(row.stock_qty),
				}
				row.update(values)
				frappe.db.set_value(
					row.doctype,
					row.name,
					values,
					update_modified=False,
				)

	def _stock_row(self, row, lot, qty, rate, transfer_key, transfer_role):
		return frappe._dict(
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
				**self._stock_dimensions(row, lot),
			}
		)

	def _stock_dimensions(self, row, lot):
		from yrp.stock.dimensions import get_dimension_fieldnames

		values = {}
		for fieldname in get_dimension_fieldnames():
			if fieldname == "lot":
				values[fieldname] = cstr(lot)
			else:
				values[fieldname] = row.get(fieldname)
		return values

	def _repost_future_entries(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)

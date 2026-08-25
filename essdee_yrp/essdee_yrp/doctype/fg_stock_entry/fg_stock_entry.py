# Copyright (c) 2024, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt

from yrp.stock.dimensions import apply_dimension_defaults, get_dimension_fieldnames
from yrp.stock.uom import apply_item_uom
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.item_price.item_price import get_item_variant_price


class FGStockEntry(Document):
	def before_validate(self):
		if not self.items:
			frappe.throw(_("Add at least one item."))
		if not frappe.db.exists("Warehouse", self.warehouse):
			frappe.throw(
				_("Location {0} is not a Warehouse.").format(frappe.bold(self.warehouse))
			)
		apply_dimension_defaults(self.items)
		for row in self.items:
			self._prepare_row(row)

	def _prepare_row(self, row):
		if flt(row.qty) <= 0:
			frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))
		apply_item_uom(row, item_field="item_variant")
		row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
		if not flt(row.rate):
			dimensions = {
				fieldname: row.get(fieldname) for fieldname in get_dimension_fieldnames()
			}
			row.rate = get_stock_balance(
				row.item_variant,
				self.warehouse,
				posting_date=self.posting_date,
				posting_time=self.posting_time,
				with_valuation_rate=True,
				uom=row.uom,
				**dimensions,
			)[1]
			if not flt(row.rate):
				row.rate = get_item_variant_price(row.item_variant, variant_uom=row.uom)
		if not self.consumed and flt(row.rate) <= 0:
			frappe.throw(
				_("Row {0}: A positive valuation rate is required for stock receipt.").format(
					row.idx
				)
			)

	def before_submit(self):
		_validate_warehouse_user(self.warehouse)

	def on_submit(self):
		if self.yrp_stock_entry:
			linked = frappe.get_doc("Stock Entry", self.yrp_stock_entry)
			if linked.docstatus == 1 and linked.against_id == self.name:
				return
			frappe.throw(_("The linked YRP Stock Entry is not valid for this document."))

		stock_entry = self._make_yrp_stock_entry()
		stock_entry.insert()
		stock_entry.submit()
		self.db_set("yrp_stock_entry", stock_entry.name, update_modified=False)

	def before_cancel(self):
		self.ignore_linked_doctypes = (
			"Stock Entry",
			"Stock Ledger Entry",
			"Repost Item Valuation",
		)
		if self.yrp_stock_entry:
			stock_entry = frappe.get_doc("Stock Entry", self.yrp_stock_entry)
			if stock_entry.docstatus == 1:
				if stock_entry.against != self.doctype or stock_entry.against_id != self.name:
					frappe.throw(_("The linked YRP Stock Entry belongs to another document."))
				# The child Stock Entry is generated and owned by this FG voucher. Its
				# backlink must not prevent the parent-controlled cancellation.
				stock_entry.ignore_linked_doctypes = (self.doctype,)
				stock_entry.cancel()
			return

		# Migrated F15 vouchers have direct SLEs and no generated Stock Entry.
		# Cancel those through the F16 engine without restoring the legacy engine.
		if frappe.db.exists(
			"Stock Ledger Entry",
			{
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"is_cancelled": 0,
			},
		):
			self._cancel_migrated_ledger_entries()

	def _make_yrp_stock_entry(self):
		frappe.has_permission("Stock Entry", "create", throw=True)
		doc = frappe.new_doc("Stock Entry")
		doc.purpose = "Material Consumed" if self.consumed else "Material Receipt"
		doc.edit_posting_date_and_time = 1
		doc.posting_date = self.posting_date
		doc.posting_time = self.posting_time
		doc.against = self.doctype
		doc.against_id = self.name
		doc.comments = self.comments
		if self.consumed:
			doc.from_warehouse = self.warehouse
		else:
			doc.to_warehouse = self.warehouse

		detail_meta = frappe.get_meta("Stock Entry Detail")
		for source in self.items:
			values = {
				"item": source.item_variant,
				"qty": source.qty,
				"uom": source.uom,
				"rate": flt(source.rate) / (flt(source.conversion_factor) or 1),
			}
			for fieldname in get_dimension_fieldnames():
				if detail_meta.get_field(fieldname):
					values[fieldname] = source.get(fieldname)
			doc.append("items", values)
		return doc

	def _cancel_migrated_ledger_entries(self):
		from yrp.stock.stock_ledger import make_sl_entries

		entries = []
		for row in self.items:
			entry = frappe._dict(
				item=row.item_variant,
				warehouse=self.warehouse,
				posting_date=self.posting_date,
				posting_time=self.posting_time,
				voucher_type=self.doctype,
				voucher_no=self.name,
				voucher_detail_no=row.name,
				uom=row.stock_uom,
				qty=flt(row.stock_qty) * (-1 if self.consumed else 1),
				rate=(flt(row.rate) / (flt(row.conversion_factor) or 1))
				if not self.consumed
				else 0,
				outgoing_rate=(flt(row.rate) / (flt(row.conversion_factor) or 1))
				if self.consumed
				else 0,
			)
			for fieldname in get_dimension_fieldnames():
				entry[fieldname] = row.get(fieldname)
			entries.append(entry)
		entries.reverse()
		make_sl_entries(entries, cancel=True)


def _validate_warehouse_user(warehouse: str):
	frappe.get_doc("Warehouse", warehouse).check_user_permission()


def _parse_list(value):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return value or []


@frappe.whitelist()
def create_FG_ste(
	received_by,
	dc_number,
	warehouse,
	posting_date,
	posting_time,
	items_list,
	comments,
	created_user,
	consumed=False,
	customer=None,
	supplier=None,
	stock_entry=None,
):
	frappe.has_permission("FG Stock Entry", "create", throw=True)
	doc = frappe.new_doc("FG Stock Entry")
	doc.update(
		{
			"received_by": received_by,
			"dc_number": dc_number,
			"supplier": supplier,
			"warehouse": warehouse,
			"customer": customer,
			"consumed": cint(consumed),
			"stock_entry": stock_entry,
			"posting_date": posting_date,
			"posting_time": posting_time,
			"created_sms_user": created_user,
			"comments": comments,
		}
	)
	detail_meta = frappe.get_meta("FG Stock Entry Detail")
	for source in _parse_list(items_list):
		row = {
			"item_variant": source.get("item_variant"),
			"qty": source.get("qty"),
			"uom": source.get("uom"),
			"rate": source.get("rate") or 0,
			"stock_entry_quantity": flt(source.get("stock_entry_quantity")),
			"row": source.get("row"),
			"col": source.get("col"),
		}
		for fieldname in get_dimension_fieldnames():
			if detail_meta.get_field(fieldname):
				row[fieldname] = source.get(fieldname)
		doc.append("items", row)
	doc.insert()
	doc.submit()
	return doc.name


@frappe.whitelist()
def get_stock_entry_detail(stock_entry: str):
	doc = frappe.get_doc("FG Stock Entry", stock_entry)
	doc.check_permission("read")
	items = []
	groups = {}
	for row in doc.items:
		item = {
			"item_variant": row.item_variant,
			"qty": row.qty,
			"row": row.row,
			"col": row.col,
			"uom": row.uom,
		}
		for fieldname in get_dimension_fieldnames():
			item[fieldname] = row.get(fieldname)
		groups.setdefault((row.row, row.col), []).append(item)
	items.extend(groups.values())
	return {
		"stock_entry_name": doc.name,
		"supplier": doc.supplier,
		"warehouse": doc.warehouse,
		"received_by": doc.received_by,
		"comments": doc.comments,
		"posting_date": doc.posting_date,
		"posting_time": doc.posting_time,
		"user": doc.created_sms_user,
		"dc_number": doc.dc_number,
		"items": items,
		"created_at": doc.creation,
		"docstatus": doc.docstatus,
		"consumed": bool(doc.consumed),
		"customer": doc.customer,
		"stock_entry": doc.stock_entry,
		"yrp_stock_entry": doc.yrp_stock_entry,
	}


@frappe.whitelist()
def fg_stock_entry_cancel(stock_entry: str):
	doc = frappe.get_doc("FG Stock Entry", stock_entry)
	doc.check_permission("cancel")
	doc.cancel()
	return doc.name


@frappe.whitelist()
def get_inward_stock(item, warehouselist=None, start_date=None, end_date=None):
	return get_inward_outward_entry(
		item, warehouselist, start_date, end_date, is_inward=True
	)


@frappe.whitelist()
def get_outward_stock(item, warehouselist=None, start_date=None, end_date=None):
	return get_inward_outward_entry(
		item, warehouselist, start_date, end_date, is_inward=False
	)


def get_inward_outward_entry(
	item, warehouselist=None, start_date=None, end_date=None, is_inward=True
):
	frappe.has_permission("FG Stock Entry", "read", throw=True)
	warehouses = _parse_list(warehouselist)
	filters = {"docstatus": 1, "consumed": 0 if is_inward else 1}
	if warehouses:
		filters["warehouse"] = ["in", warehouses]
	if start_date and end_date:
		filters["creation"] = [
			"between",
			[f"{cstr(start_date)} 00:00:00", f"{cstr(end_date)} 23:59:59"],
		]
	parents = frappe.get_list("FG Stock Entry", filters=filters, pluck="name")
	if not parents:
		return []
	return frappe.db.sql(
		"""
		SELECT d.qty AS pending_qty, d.`row`, d.col,
			p.creation AS st_entry_date, p.posting_date, p.posting_time,
			p.customer, p.supplier, p.warehouse, p.received_by,
			d.lot, p.dc_number, d.item_variant, d.uom,
			iv.item AS item_name, p.name AS stock_entry,
			d.received_type
		FROM `tabFG Stock Entry Detail` d
		INNER JOIN `tabFG Stock Entry` p ON p.name = d.parent
		INNER JOIN `tabItem Variant` iv ON iv.name = d.item_variant
		WHERE p.name IN %(parents)s AND iv.item = %(item)s
		ORDER BY p.posting_date DESC, p.posting_time DESC, p.creation DESC
		""",
		{"parents": parents, "item": item},
		as_dict=True,
	)

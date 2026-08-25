# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from itertools import groupby

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

from yrp.stock.dimensions import (
	apply_dimension_defaults,
	get_dimension_fieldnames,
)
from yrp.stock.uom import apply_item_uom
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.item.item import (
	get_attribute_details,
	get_or_create_variant,
	get_variant,
)


VALUATION_RATE_PRECISION = 9


class ItemConversion(Document):
	def onload(self):
		from_items = fetch_item_conversion_items(self.get("from_items"))
		to_items = fetch_item_conversion_items(self.get("to_items"))
		self.set("print_from_item_details", json.dumps(from_items))
		self.set("print_to_item_details", json.dumps(to_items))
		self.set_onload("from_item_details", from_items)
		self.set_onload("to_item_details", to_items)

	def before_validate(self):
		from yrp.stock.utils import apply_posting_datetime

		apply_posting_datetime(self)
		if self.get("from_item_details") is not None:
			self.set("from_items", save_item_conversion_items(self.from_item_details))
		if self.get("to_item_details") is not None:
			self.set("to_items", save_item_conversion_items(self.to_item_details))
		if not self.from_items:
			frappe.throw(_("Add From Items to continue"), title=_("Item Conversion"))
		if not self.to_items:
			frappe.throw(_("Add To Items to continue"), title=_("Item Conversion"))

		apply_dimension_defaults(self.from_items)
		apply_dimension_defaults(self.to_items)

	def validate(self):
		if not self.warehouse:
			frappe.throw(_("Location is mandatory"))
		if not frappe.db.exists("Warehouse", self.warehouse):
			frappe.throw(
				_("Location {0} is not a Warehouse.").format(frappe.bold(self.warehouse))
			)
		if not self.from_item:
			frappe.throw(_("From Item is mandatory"))
		if not self.to_item:
			frappe.throw(_("To Item is mandatory"))

		self.validate_single_item_rows()
		self.validate_items(
			"from_items", _("From Items"), self.from_item, rate_source="stock_valuation"
		)
		self.set_single_target_rate()
		self.validate_items(
			"to_items", _("To Items"), self.to_item, rate_source="user"
		)
		self.calculate_totals()

	def before_submit(self):
		self.validate_valuation_match()
		_validate_warehouse_user(self.warehouse)

	def on_submit(self):
		self.update_stock_ledger()
		self.make_repost_action()

	def before_cancel(self):
		self.ignore_linked_doctypes = (
			"Stock Ledger Entry",
			"Repost Item Valuation",
		)
		self.update_stock_ledger(cancel=True)

	def on_cancel(self):
		self.make_repost_action()

	def validate_single_item_rows(self):
		if len(self.from_items) != 1:
			frappe.throw(_("Item Conversion requires exactly one From Item row."))
		if len(self.to_items) != 1:
			frappe.throw(_("Item Conversion requires exactly one To Item row."))

	def set_single_target_rate(self):
		target_rows = [row for row in self.to_items if flt(row.qty) > 0]
		from_value = sum(flt(row.amount) for row in self.from_items)
		if len(target_rows) == 1 and from_value > 0:
			target_rows[0].rate = flt(
				from_value / flt(target_rows[0].qty), VALUATION_RATE_PRECISION
			)

	def validate_items(self, table_field, table_label, expected_item, rate_source):
		messages = []
		for row in self.get(table_field):
			prefix = _("Table {0} Row # {1}:").format(table_label, row.idx)
			item_template = self.validate_item(row.item, row, messages)
			if item_template and item_template != expected_item:
				messages.append(
					_("{0} Item {1} does not match selected item {2}").format(
						prefix, item_template, expected_item
					)
				)
			if not flt(row.qty):
				messages.append(_("{0} Quantity is mandatory").format(prefix))
			if flt(row.qty) < 0:
				messages.append(_("{0} Negative Quantity is not allowed").format(prefix))
			if flt(row.rate) < 0:
				messages.append(
					_("{0} Negative Valuation Rate is not allowed").format(prefix)
				)

			apply_item_uom(row, item_field="item")
			row.stock_qty = flt(
				flt(row.qty) * flt(row.conversion_factor),
				self.precision("stock_qty", row),
			)
			if flt(row.qty) > 0 and rate_source == "stock_valuation":
				row.rate = self.get_existing_valuation_rate(row)
				if not flt(row.rate):
					messages.append(
						_(
							"{0} Could not find an existing valuation rate for Item {1}."
						).format(prefix, row.item)
					)
			if flt(row.qty) > 0 and not flt(row.rate) and rate_source == "user":
				messages.append(_("{0} Rate is mandatory").format(prefix))

			row.rate = flt(row.rate, VALUATION_RATE_PRECISION)
			row.stock_uom_rate = flt(
				flt(row.rate) / (flt(row.conversion_factor) or 1),
				VALUATION_RATE_PRECISION,
			)
			row.amount = flt(
				flt(row.rate) * flt(row.qty), self.precision("amount", row)
			)

		if messages:
			frappe.throw("<br>".join(messages), title=_("Item Conversion"))

	def validate_item(self, item, row, messages):
		from yrp.yrp.doctype.item.item import (
			validate_cancelled_item,
			validate_disabled,
			validate_is_stock_item,
		)

		try:
			item_template = frappe.get_cached_value("Item Variant", item, "item")
			if not item_template:
				frappe.throw(_("Item Variant {0} does not exist.").format(item))
			validate_disabled(item_template)
			validate_is_stock_item(item_template)
			validate_cancelled_item(item_template)
			return item_template
		except Exception as exc:
			messages.append(_("Row # {0}: {1}").format(row.idx, cstr(exc)))
			return None

	def get_existing_valuation_rate(self, row):
		dimensions = {
			fieldname: row.get(fieldname) for fieldname in get_dimension_fieldnames()
		}
		return get_stock_balance(
			row.item,
			self.warehouse,
			posting_date=self.posting_date,
			posting_time=self.posting_time,
			with_valuation_rate=True,
			uom=row.uom,
			**dimensions,
		)[1]

	def calculate_totals(self):
		self.from_total_amount = flt(
			sum(flt(item.amount) for item in self.from_items),
			self.precision("from_total_amount"),
		)
		self.to_total_amount = flt(
			sum(flt(item.amount) for item in self.to_items),
			self.precision("to_total_amount"),
		)
		self.difference_amount = flt(
			flt(self.from_total_amount) - flt(self.to_total_amount),
			self.precision("difference_amount"),
		)

	def validate_valuation_match(self):
		if flt(self.difference_amount, self.precision("difference_amount")):
			frappe.throw(
				_(
					"From Items total ({0}) must match To Items total ({1}). Difference: {2}"
				).format(
					self.from_total_amount,
					self.to_total_amount,
					self.difference_amount,
				)
			)

	def update_stock_ledger(self, cancel: bool = False):
		from yrp.stock.stock_ledger import make_sl_entries

		transfer_key = f"Item Conversion:{self.name}:value"
		entries = [
			self.get_sl_entry(
				self.from_items[0],
				qty=-flt(self.from_items[0].stock_qty),
				rate=0,
				outgoing_rate=flt(self.from_items[0].stock_uom_rate),
				transfer_key=transfer_key,
				transfer_role="outgoing",
			),
			self.get_sl_entry(
				self.to_items[0],
				qty=flt(self.to_items[0].stock_qty),
				rate=flt(self.to_items[0].stock_uom_rate),
				transfer_key=transfer_key,
				transfer_role="incoming",
			),
		]
		if cancel:
			entries.reverse()
		make_sl_entries(entries, cancel=cancel, force_inline=True)

	def get_sl_entry(
		self, row, qty, rate, outgoing_rate=0, transfer_key=None, transfer_role=None
	):
		entry = frappe._dict(
			item=row.item,
			warehouse=self.warehouse,
			posting_date=self.posting_date,
			posting_time=self.posting_time,
			voucher_type=self.doctype,
			voucher_no=self.name,
			voucher_detail_no=row.name,
			uom=row.stock_uom,
			qty=qty,
			rate=rate,
			outgoing_rate=outgoing_rate,
			remarks=row.remarks,
			_transfer_key=transfer_key,
			_transfer_role=transfer_role,
		)
		for fieldname in get_dimension_fieldnames():
			entry[fieldname] = row.get(fieldname)
		return entry

	def make_repost_action(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)


def _validate_warehouse_user(warehouse: str):
	frappe.get_doc("Warehouse", warehouse).check_user_permission()


@frappe.whitelist()
def get_item_conversion_valuation_rate(
	item,
	attributes=None,
	lot=None,
	received_type=None,
	uom=None,
	warehouse=None,
	posting_date=None,
	posting_time=None,
	dimensions=None,
):
	frappe.has_permission("Item Conversion", "read", throw=True)
	attributes = frappe.parse_json(attributes) if isinstance(attributes, str) else attributes
	attributes = attributes or {}
	variant_name = get_variant(item, attributes)
	if not variant_name or not warehouse:
		return {"item_variant": variant_name, "qty": 0, "rate": 0}

	dimension_values = (
		frappe.parse_json(dimensions) if isinstance(dimensions, str) else dimensions
	) or {}
	if "lot" in get_dimension_fieldnames():
		dimension_values["lot"] = lot
	if "received_type" in get_dimension_fieldnames():
		dimension_values["received_type"] = received_type
	qty, rate = get_stock_balance(
		variant_name,
		warehouse,
		posting_date=posting_date,
		posting_time=posting_time,
		with_valuation_rate=True,
		uom=uom,
		**{
			fieldname: dimension_values.get(fieldname)
			for fieldname in get_dimension_fieldnames()
		},
	)
	return {
		"item_variant": variant_name,
		"qty": flt(qty),
		"rate": flt(rate, VALUATION_RATE_PRECISION),
	}


def fetch_item_conversion_items(items) -> list[dict]:
	rows = [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in items or []]
	rows.sort(key=lambda row: row.get("row_index") or 0)
	result = []
	for _row_index, variants_iter in groupby(
		rows, key=lambda row: row.get("row_index") or 0
	):
		variants = list(variants_iter)
		variant_doc = frappe.get_doc("Item Variant", variants[0]["item"])
		details = get_attribute_details(variant_doc.item)
		item = {
			"name": variant_doc.item,
			"lot": variants[0].get("lot"),
			"attributes": _variant_attributes(variant_doc, details),
			"primary_attribute": details.get("primary_attribute"),
			"values": {},
			"default_uom": variants[0].get("uom") or details.get("default_uom"),
			"secondary_uom": variants[0].get("secondary_uom")
			or details.get("secondary_uom"),
			"received_type": variants[0].get("received_type"),
			"remarks": variants[0].get("remarks"),
		}
		primary_attribute = details.get("primary_attribute")
		if primary_attribute:
			item["values"] = {
				value: {"qty": 0, "rate": 0}
				for value in details.get("primary_attribute_values") or []
			}
			for variant in variants:
				current = frappe.get_doc("Item Variant", variant["item"])
				primary_value = next(
					(
						row.attribute_value
						for row in current.attributes
						if row.attribute == primary_attribute
					),
					None,
				)
				if primary_value:
					item["values"][primary_value] = _conversion_value(variant)
		else:
			item["values"]["default"] = _conversion_value(variants[0])

		group_key = (
			tuple(details.get("attributes") or []),
			details.get("primary_attribute"),
		)
		group = next((row for row in result if row["_key"] == group_key), None)
		if not group:
			group = {
				"_key": group_key,
				"attributes": details.get("attributes") or [],
				"primary_attribute": details.get("primary_attribute"),
				"primary_attribute_values": details.get("primary_attribute_values") or [],
				"items": [],
			}
			result.append(group)
		group["items"].append(item)
	for group in result:
		group.pop("_key", None)
	return result


def _variant_attributes(variant, details) -> dict:
	allowed = set(details.get("attributes") or [])
	return {
		row.attribute: row.attribute_value
		for row in variant.attributes
		if row.attribute in allowed
	}


def _conversion_value(row) -> dict:
	set_combination = row.get("set_combination") or {}
	if isinstance(set_combination, str):
		set_combination = frappe.parse_json(set_combination)
	return {
		"qty": row.get("qty", 0),
		"rate": row.get("rate", 0),
		"secondary_qty": row.get("secondary_qty", 0),
		"secondary_uom": row.get("secondary_uom"),
		"set_combination": set_combination,
	}


def save_item_conversion_items(item_details) -> list[dict]:
	item_details = (
		frappe.parse_json(item_details) if isinstance(item_details, str) else item_details
	) or []
	rows = []
	row_index = 0
	for table_index, group in enumerate(item_details):
		for item in group.get("items") or []:
			attributes = dict(item.get("attributes") or {})
			primary_attribute = item.get("primary_attribute")
			values = item.get("values") or {}
			for attribute_value, value in values.items():
				if not flt(value.get("qty")):
					continue
				row_attributes = dict(attributes)
				if primary_attribute and attribute_value != "default":
					row_attributes[primary_attribute] = attribute_value
				variant = get_or_create_variant(item.get("name"), row_attributes)
				rows.append(
					{
						"item": variant.name if hasattr(variant, "name") else variant,
						"lot": item.get("lot"),
						"uom": item.get("default_uom"),
						"qty": flt(value.get("qty")),
						"rate": flt(value.get("rate")),
						"table_index": table_index,
						"row_index": row_index,
						"remarks": item.get("remarks"),
						"received_type": item.get("received_type"),
						"secondary_qty": flt(value.get("secondary_qty")),
						"secondary_uom": value.get("secondary_uom")
						or item.get("secondary_uom"),
						"set_combination": value.get("set_combination") or {},
					}
				)
			row_index += 1
	return rows

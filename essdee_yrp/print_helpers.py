"""Jinja helpers for the Essdee-owned operational print formats.

The source layouts came from the F15 MRP application, but F16 production sites
install ``yrp`` + ``essdee_yrp`` without ``production_api``.  These adapters
therefore build the old print shape from YRP's canonical stock grouping API
instead of importing an uninstalled customer application.
"""

from collections import OrderedDict
from datetime import datetime

import frappe
from frappe.utils import flt, getdate, money_in_words


def get_created_date(value):
	if not value:
		return ""
	return getdate(value).strftime("%d-%m-%Y")


def get_current_user_time():
	return [frappe.session.user, datetime.now().strftime("%c")]


def get_user_signature(user):
	if not user or not frappe.db.exists("DocType", "Signature"):
		return None
	return frappe.db.get_value(
		"Signature",
		{"user": user, "docstatus": 1},
		"signature",
	)


def get_ipd_pf_details(ipd):
	return frappe.get_doc("Item Production Detail", ipd)


def get_supplier_address_display(supplier):
	"""Essdee-owned print adapter for a YRP Supplier's primary address."""
	if not supplier:
		return ""
	from yrp.yrp.doctype.supplier.supplier import get_supplier_address_display as get_address

	return get_address(supplier) or ""


def _supplier_name(supplier):
	if not supplier:
		return ""
	return frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier


def _work_order_lot(rows):
	for row in rows or []:
		parent = row.get("parent")
		if parent:
			return frappe.db.get_value("Work Order", parent, "lot") or ""
	return ""


def _group_items(rows, parent_doctype, *, lot=None):
	from yrp.stock.save_stock_items import group_items_for_ui

	groups = group_items_for_ui(rows or [], parent_doctype)
	for group in groups:
		group_lot = lot or ""
		for item in group.get("items") or []:
			dimensions = item.get("dimensions") or {}
			item["lot"] = dimensions.get("lot") or item.get("lot") or lot or ""
			group_lot = group_lot or item["lot"]
			item_comments = item.get("comments") or ""
			for detail in (item.get("values") or {}).values():
				qty = flt(detail.get("qty"))
				detail.setdefault("received", qty)
				detail.setdefault("delivered_quantity", qty)
				detail.setdefault(
					"secondary_received",
					flt(detail.get("secondary_qty")),
				)
				detail.setdefault("tax", flt(detail.get("tax")))
				detail.setdefault("rate", flt(detail.get("rate")))
				detail.setdefault("comments", item_comments)
				item["secondary_uom"] = (
					item.get("secondary_uom")
					or detail.get("secondary_uom")
					or ""
				)
		group["lot"] = group_lot
	return groups


def fetch_stock_entry_items(items, ipd=None):
	"""Return the F15 print shape from F16 Stock Entry rows."""
	return _group_items(items, "Stock Entry")


def fetch_grn_purchase_item_details(items, docstatus=0):
	"""Return grouped GRN rows with the aliases used by the Essdee layout."""
	rows = list(items or [])
	if int(docstatus or 0) != 0:
		rows = [row for row in rows if flt(row.get("quantity")) > 0]
	return _group_items(rows, "Goods Received Note")


def get_dc_structure(doc_name):
	doc = frappe.get_doc("Delivery Challan", doc_name)
	lot = (
		frappe.db.get_value("Work Order", doc.work_order, "lot")
		if doc.get("work_order")
		else None
	)
	items = _group_items(doc.get("items") or [], "Delivery Challan", lot=lot)
	expected_delivery_date = (
		frappe.db.get_value(
			"Work Order",
			doc.work_order,
			"expected_delivery_date",
		)
		if doc.get("work_order")
		else None
	)
	return items, expected_delivery_date


def _generic_work_order_items(items):
	"""Build the garment print's item-grid shape for fabric work orders.

	Fabric work orders intentionally do not carry a garment
	``production_detail``. Their calculated rows already contain the physical
	item variants and quantities, so the print adapter groups those rows
	directly without inventing a garment IPD.
	"""
	from yrp.yrp.doctype.item.item import get_attribute_details

	rows = [
		row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
		for row in (items or [])
	]
	if not rows:
		return []

	row_groups = OrderedDict()
	for index, row in enumerate(rows):
		row_index = row.get("row_index")
		key = row_index if row_index not in (None, "") else f"__row_{index}"
		row_groups.setdefault(key, []).append(row)

	output_groups = OrderedDict()
	for variants in row_groups.values():
		first = variants[0]
		variant_name = first.get("item_variant")
		parent_item = frappe.db.get_value("Item Variant", variant_name, "item")
		if not parent_item:
			continue

		attr_details = get_attribute_details(parent_item)
		primary = attr_details.get("primary_attribute") or ""
		primary_values = list(attr_details.get("primary_attribute_values") or [])
		attribute_names = list(attr_details.get("attributes") or [])
		group_key = (
			tuple(attribute_names),
			primary,
			tuple(primary_values),
		)
		group = output_groups.setdefault(
			group_key,
			{
				"attributes": attribute_names,
				"primary_attribute": primary,
				"primary_attribute_values": primary_values,
				"items": [],
				"lot": _work_order_lot(rows),
			},
		)

		first_variant = frappe.get_cached_doc("Item Variant", variant_name)
		first_attrs = {
			row.attribute: row.attribute_value
			for row in (first_variant.attributes or [])
		}
		entry = {
			"name": parent_item,
			"attributes": {
				attribute: first_attrs.get(attribute, "")
				for attribute in attribute_names
			},
			"values": {},
			"default_uom": attr_details.get("default_uom") or "",
		}
		if primary and primary_values:
			entry["values"] = {value: {"qty": 0} for value in primary_values}
			for row in variants:
				variant = frappe.get_cached_doc("Item Variant", row.get("item_variant"))
				attributes = {
					value.attribute: value.attribute_value
					for value in (variant.attributes or [])
				}
				primary_value = attributes.get(primary)
				if primary_value:
					entry["values"].setdefault(primary_value, {"qty": 0})
					entry["values"][primary_value]["qty"] += flt(row.get("quantity"))
		else:
			entry["values"]["default"] = {
				"qty": sum(flt(row.get("quantity")) for row in variants),
			}
		group["items"].append(entry)

	return list(output_groups.values())


def fetch_order_item_details(
	items,
	production_detail=None,
	process=None,
	includes_packing=False,
):
	"""Print-safe Work Order adapter for garment and fabric work orders."""
	if production_detail:
		from essdee_yrp.essdee_yrp.doctype.lot.lot import (
			fetch_order_item_details as fetch_garment_items,
		)

		return fetch_garment_items(
			items,
			production_detail,
			process=process,
			includes_packing=includes_packing,
		)
	return _generic_work_order_items(items)


def prepare_print_document(doc, method=None, settings=None):
	"""Add transient F15 layout aliases to the F16 YRP documents.

	The aliases exist only for rendering. They are never saved and therefore do
	not expand or duplicate the canonical F16 DocType schema.
	"""
	if doc.doctype == "Delivery Challan":
		doc.from_location_name = _supplier_name(doc.get("from_location"))
		doc.from_address_details = get_supplier_address_display(doc.get("from_location"))
		doc.supplier_name = _supplier_name(doc.get("supplier"))
		doc.supplier_address_details = get_supplier_address_display(doc.get("supplier"))
	elif doc.doctype == "Goods Received Note":
		doc.supplier_name = _supplier_name(doc.get("supplier"))
		doc.supplier_address_display = get_supplier_address_display(doc.get("supplier"))
		doc.grn_date = doc.get("posting_date")
		doc.show_delivery_details = 0
		doc.total_tax = 0
		doc.grand_total = flt(doc.get("total"))
		doc.in_words = money_in_words(doc.grand_total, "INR")
		doc.approved_by = doc.get("approved_by") or doc.get("modified_by")
	elif doc.doctype == "Work Order":
		doc.supplier_address_details = (
			doc.get("supplier_address_details")
			or get_supplier_address_display(doc.get("supplier"))
		)
		doc.delivery_address_details = (
			doc.get("delivery_address_details")
			or get_supplier_address_display(doc.get("delivery_location"))
		)
		if not doc.get("production_detail") and not doc.get("work_order_calculated_items"):
			doc.work_order_calculated_items = [
				frappe._dict(
					item_variant=row.item_variant,
					quantity=row.qty,
					row_index=row.row_index,
					table_index=row.table_index,
					parent=doc.name,
				)
				for row in (doc.get("receivables") or [])
				if row.get("item_variant") and flt(row.get("qty")) > 0
			]
	elif doc.doctype == "Stock Entry":
		doc.transfer_supplier = (
			doc.get("transfer_supplier")
			or doc.get("from_supplier")
			or doc.get("to_supplier")
		)
		doc.approved_by = doc.get("approved_by") or doc.get("modified_by")

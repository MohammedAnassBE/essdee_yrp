"""Jinja helpers for the Essdee-owned operational print formats.

The source layouts came from the F15 MRP application, but F16 production sites
install ``yrp`` + ``essdee_yrp`` without ``production_api``.  These adapters
therefore build the old print shape from YRP's canonical stock grouping API
instead of importing an uninstalled customer application.
"""

import re
from collections import OrderedDict
from datetime import datetime

import frappe
from frappe.utils import flt, getdate, money_in_words
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.merch.ipd.payload import prime_attribute_values


def get_value_with_pad(value, pad):
	"""Pad like MRP: ``ljust(pad - len(value))``; ZPL layouts were positioned against that width."""

	value = str(value or "")
	pad = int(pad or 0)
	return value.ljust(pad - len(value), " ") if len(value) < pad else value


def get_item_size(item, item_size, text_size):
	"""Return the configured printer font size for an item-name length."""

	text_sizes = list(text_size or [])
	if not text_sizes:
		return None
	length = len(str(item or ""))
	for index, maximum_length in enumerate(item_size or []):
		if length <= int(maximum_length) and index < len(text_sizes):
			return text_sizes[index]
	return text_sizes[-1]


def get_created_date(value):
	if not value:
		return ""
	return getdate(value).strftime("%d-%m-%Y")


def get_current_user_time():
	return [frappe.session.user, datetime.now().strftime("%d-%m-%Y %H:%M")]


def get_user_signature(user):
	"""The user's submitted MRP signature, else the ERP one: this helper replaces essdee's of the same name."""
	if not user:
		return None
	for doctype in ("SD YRP Signature", "SD Signature"):
		if frappe.db.exists("DocType", doctype):
			signature = frappe.db.get_value(doctype, {"user": user, "docstatus": 1}, "signature")
			if signature:
				return signature
	return None


def get_ipd_pf_details(ipd):
	"""The IPD with attribute values as text, so panels match the embellishment JSON's names."""
	doc = frappe.get_doc("YRP Item Production Detail", ipd)
	set_attribute_display_values(doc)
	return doc


def get_supplier_address_display(supplier):
	"""A YRP Supplier's primary address, else its only (or only Billing/Shipping) address."""
	if not supplier:
		return ""
	from yrp.party_addresses import get_party_address
	from yrp.yrp.doctype.yrp_supplier.yrp_supplier import get_supplier_address_display as get_address

	return get_address(supplier) or _address_display(get_party_address(supplier))


def get_warehouse_name(warehouse):
	if not warehouse:
		return ""
	doc = frappe.get_doc("Warehouse", warehouse)
	doc.check_permission("read")
	return doc.get("warehouse_name") or doc.name


def get_warehouse_address_display(warehouse):
	if not warehouse:
		return ""
	doc = frappe.get_doc("Warehouse", warehouse)
	doc.check_permission("read")
	return get_supplier_address_display(doc.get("supplier")) if doc.get("supplier") else ""


def _supplier_name(supplier):
	if not supplier:
		return ""
	return frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier


def _work_order_lot(rows):
	for row in rows or []:
		parent = row.get("parent")
		if parent:
			return frappe.db.get_value("YRP Work Order", parent, "lot") or ""
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
				item["secondary_uom"] = item.get("secondary_uom") or detail.get("secondary_uom") or ""
		group["lot"] = group_lot
	return groups


def fetch_stock_entry_items(items, ipd=None):
	"""Group Stock Entry rows into tables exactly like F15's fetch_stock_entry_items.

	Rows go in ``row_index`` text order. F15's groups never stored the dependent attribute, so an
	item that has one (Stage) gets a table per row; other rows join the first table with the same
	attributes, and a sized row only joins a table of its own item.
	"""
	entries = [
		(source, item)
		for source in _group_items(items, "YRP Stock Entry")
		for item in source.get("items") or []
	]
	entries.sort(key=lambda entry: str(entry[1].get("row_index") or ""))
	sort_attributes = len(entries) > 1
	groups = []
	for source, item in entries:
		index = get_stock_entry_group_index(groups, source, item.get("name"))
		if index == -1:
			attributes = list(source.get("attributes") or [])
			if sort_attributes:
				# F15's get_item_group_index sorted attribute lists in place once a second row was grouped.
				attributes.sort()
			groups.append({**source, "attributes": attributes, "dependent_attribute": None, "items": [item]})
		else:
			groups[index]["items"].append(item)
	return groups


def get_stock_entry_group_index(groups, details, item_name):
	"""F15's get_item_group_index for a Stock Entry row's attribute details."""
	index = next(
		(
			position
			for position, group in enumerate(groups)
			if sorted(group.get("attributes") or []) == sorted(details.get("attributes") or [])
			and (group.get("primary_attribute") or "") == (details.get("primary_attribute") or "")
			and not details.get("dependent_attribute")
		),
		-1,
	)
	if (
		index == -1
		or not details.get("primary_attribute")
		or groups[index]["items"][0].get("name") == item_name
	):
		return index
	return next(
		(position for position, group in enumerate(groups) if group["items"][0].get("name") == item_name), -1
	)


def fetch_grn_purchase_item_details(items, docstatus=0):
	"""Return grouped GRN rows with the aliases used by the Essdee layout."""
	rows = list(items or [])
	if int(docstatus or 0) != 0:
		rows = [row for row in rows if flt(row.get("quantity")) > 0]
	return sort_grouped_attributes(_group_items(rows, "YRP Goods Received Note"))


def sort_grouped_attributes(groups):
	"""F15's get_item_group_index sorted attribute columns in place once a second row was grouped."""
	if sum(len(group.get("items") or []) for group in groups) > 1:
		for group in groups:
			group["attributes"] = sorted(group.get("attributes") or [])
	return groups


def check_key_value_in_dict_or_list_of_dict(key, value):
	"""Return whether a print payload contains a non-empty key."""
	if isinstance(value, dict):
		return bool(value.get(key))
	if isinstance(value, list):
		return any(isinstance(row, dict) and row.get(key) for row in value)
	return False


def parse_json(value):
	if not value:
		return None
	return frappe.parse_json(value) if isinstance(value, str) else value


def get_item_from_variant(variant):
	return get_parent_item(variant)


def fetch_item_details(items, include_id=False):
	"""Build MRP's Purchase Order print grid from the F16 grouping service.

	Rows are ordered and grouped like MRP: ``row_index`` sorted as text, and a
	size-wise item only shares a table with earlier rows of the same item.
	"""
	from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details
	from yrp.yrp.doctype.yrp_purchase_order.yrp_purchase_order import get_item_group_index

	delivery_dates = {}
	for row in items or []:
		key = str(row.get("row_index") or "")
		dates = (delivery_dates.get(key), row.get("schedule_date"))
		delivery_dates[key] = max(filter(None, dates), default=None)
	entries = [item for group in _group_items(items, "Purchase Order") for item in group.get("items") or []]
	groups = []
	for item in sorted(entries, key=lambda entry: str(entry.get("row_index") or "")):
		details = get_attribute_details(item["name"])
		details = dict(details, attributes=list(details.get("attributes") or []))
		delivery_date = delivery_dates.get(str(item.get("row_index") or "")) or item.get("schedule_date")
		item["delivery_date"] = str(delivery_date) if delivery_date else ""
		item["secondary_uom"] = item.get("secondary_uom") or details.get("secondary_uom")
		for detail in (item.get("values") or {}).values():
			detail["pending_qty"] = detail.get("pending_quantity", 0)
			detail["cancelled_qty"] = detail.get("cancelled_quantity", 0)
			detail["tax"] = detail.get("tax") or item.get("tax") or 0
			if include_id:
				detail.setdefault("ref_doctype", "Purchase Order Item")
		index = get_item_group_index(groups, details)
		if index == -1:
			groups.append({**details, "items": [item]})
		else:
			groups[index]["items"].append(item)
	return groups


def get_cloth_program_print_data(lot):
	"""Return a print matrix from the saved F16 cloth-program rows.

	Printing must never recalculate or mutate a Lot. The saved program rows are
	the authoritative quantities created by ``build_cloth_programs``; raw demand
	is read only to split the displayed required/excess totals.
	"""
	from essdee_yrp.fabric_requirement import compute_cloth_demand

	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("read")
	additions_payload = parse_json(lot_doc.get("cloth_program_additions")) or {}
	addition_by_route = {}
	for row in additions_payload.get("routes") or []:
		key = (
			row.get("cloth_item"),
			_attribute_value(row.get("dia")),
			_attribute_value(row.get("colour")) or None,
		)
		addition_by_route[key] = addition_by_route.get(key, 0) + flt(row.get("additional_weight"))

	grouped = OrderedDict()
	for row in lot_doc.get("lot_fabric_programs") or []:
		cloth = grouped.setdefault(
			row.cloth_item,
			{"cloth_item": row.cloth_item, "routes": [], "colours": set()},
		)
		colour = _attribute_value(row.colour) or "No Colour"
		cloth["colours"].add(colour)
		cloth["routes"].append(
			{
				"dia": _attribute_value(row.dia) or "No Dia",
				"colour": colour,
				"weight": flt(row.weight),
				"addition": addition_by_route.get(
					(row.cloth_item, _attribute_value(row.dia), _attribute_value(row.colour) or None), 0
				),
			}
		)

	tables = []
	for cloth in grouped.values():
		colours = sorted(cloth["colours"])
		colour_totals = {colour: 0 for colour in colours}
		route_rows = OrderedDict()
		additions = {colour: 0 for colour in colours}
		for row in cloth["routes"]:
			route = route_rows.setdefault(
				_attribute_value(row["dia"]),
				{
					"fabric_type": "Main Fabric",
					"dia": _attribute_value(row["dia"]),
					"weights": {colour: 0 for colour in colours},
					"total": 0,
				},
			)
			route["weights"][_attribute_value(row["colour"])] += row["weight"]
			route["total"] += row["weight"]
			colour_totals[_attribute_value(row["colour"])] += row["weight"]
			additions[_attribute_value(row["colour"])] += row["addition"]
		fabric_total = sum(colour_totals.values())
		fabric_group = {
			"fabric_type": "Main Fabric",
			"routes": list(route_rows.values()),
			"colour_totals": colour_totals,
			"additions": additions,
			"additional_total": sum(additions.values()),
			"total": fabric_total,
		}
		tables.append(
			{
				"cloth_item": cloth["cloth_item"],
				"colours": colours,
				"routes": list(route_rows.values()),
				"fabric_groups": [fabric_group],
				"colour_totals": colour_totals,
				"total": fabric_total,
			}
		)

	program_weight = sum(table["total"] for table in tables)
	manual_weight = sum(group["additional_total"] for table in tables for group in table["fabric_groups"])
	try:
		required_weight = sum(
			flt(weight) for weight in compute_cloth_demand(lot_doc.name, apply_allowance=False).values()
		)
	except frappe.ValidationError, frappe.DoesNotExistError:
		required_weight = max(program_weight - manual_weight, 0)

	cpd_values = []
	for row in lot_doc.get("lot_fabric_details") or []:
		if row.production_detail:
			value = flt(
				attribute_db.get_value(
					"YRP Item Production Detail", row.production_detail, "cloth_per_kg_yarn"
				)
			)
			if value and value not in cpd_values:
				cpd_values.append(value)

	return {
		"item": lot_doc.get("item"),
		"production_detail": lot_doc.get("production_detail"),
		"extra_percentage": flt(lot_doc.get("cloth_excess_percentage")),
		"cloth_per_kg_yarn": cpds[0] if (cpds := cpd_values) and len(cpds) == 1 else "Per cloth",
		"uses_compacting_details": False,
		"tables": tables,
		"display_totals": {
			"required_weight": round(required_weight, 3),
			"extra_weight": round(max(program_weight - required_weight - manual_weight, 0), 3),
			"manual_additional_weight": round(manual_weight, 3),
			"program_weight": round(program_weight, 3),
		},
	}


def get_dc_structure(doc_name):
	doc = frappe.get_doc("YRP Delivery Challan", doc_name)
	lot = frappe.db.get_value("YRP Work Order", doc.work_order, "lot") if doc.get("work_order") else None
	items = _group_items(doc.get("items") or [], "YRP Delivery Challan", lot=lot)
	if sum(len(group.get("items") or []) for group in items) > 1:
		# F15's get_item_group_index sorted attribute lists in place once a second row was grouped.
		for group in items:
			group["attributes"] = sorted(group.get("attributes") or [])
	expected_delivery_date = (
		frappe.db.get_value(
			"YRP Work Order",
			doc.work_order,
			"expected_delivery_date",
		)
		if doc.get("work_order")
		else None
	)
	return items, expected_delivery_date


def get_grn_structure(doc_name):
	"""Group GRN rows like MRP's Work Order GRN print: one row per item and received type."""
	doc = frappe.get_doc("YRP Goods Received Note", doc_name)
	rows = doc.get("items") or []
	type_positions = {}
	for position, row in enumerate(rows):
		type_positions.setdefault((str(row.get("row_index") or ""), row.get("received_type") or ""), position)
	groups = _group_items(rows, "YRP Goods Received Note", lot=doc.get("lot"))
	for group in groups:
		group["items"] = merge_received_types(group.get("items") or [], type_positions)
	return sort_grouped_attributes(groups)


def merge_received_types(items, type_positions=None):
	"""Merge the received-type splits of an item row, listing types in MRP's row order.

	Every size holds a quantity for every type, 0 when it has none: MRP's grid emits a size cell only
	for the types a size has, so a type missing from one size shifted that row's cells left.
	"""
	type_positions = type_positions or {}
	merged = OrderedDict()
	for item in items:
		received_type = (item.get("dimensions") or {}).get("received_type") or ""
		key = (
			item.get("name"),
			frappe.as_json(item.get("attributes")),
			str(item.get("set_combination") or ""),
		)
		target = merged.setdefault(key, {**item, "types": [], "values": {}, "type_positions": {}})
		position = type_positions.get((str(item.get("row_index") or ""), received_type), len(type_positions))
		if received_type not in target["types"]:
			target["types"].append(received_type)
		target["type_positions"][received_type] = min(
			position, target["type_positions"].get(received_type, position)
		)
		for attribute_value, detail in (item.get("values") or {}).items():
			cell = target["values"].setdefault(attribute_value, {**detail, "types": {}})
			if detail.get("ref_docname") or flt(detail.get("received")):
				cell["types"][received_type] = cell["types"].get(received_type, 0.0) + flt(
					detail.get("received")
				)
	for target in merged.values():
		positions = target.pop("type_positions")
		target["types"].sort(key=positions.get)
		for cell in target["values"].values():
			cell["types"] = {
				received_type: cell["types"].get(received_type, 0.0) for received_type in target["types"]
			}
	return list(merged.values())


def _generic_work_order_items(items):
	"""Build the garment print's item-grid shape for fabric work orders.

	Fabric work orders intentionally do not carry a garment
	``production_detail``. Their calculated rows already contain the physical
	item variants and quantities, so the print adapter groups those rows
	directly without inventing a garment IPD.
	"""
	from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details

	rows = [row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row) for row in (items or [])]
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
		parent_item = get_parent_item(variant_name)
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

		first_variant = frappe.get_cached_doc("Item", variant_name)
		first_attrs = {
			row.attribute: _attribute_value(row.attribute_value) for row in (first_variant.attributes or [])
		}
		entry = {
			"name": parent_item,
			"attributes": {attribute: first_attrs.get(attribute, "") for attribute in attribute_names},
			"values": {},
			"default_uom": attr_details.get("default_uom") or "",
		}
		if primary and primary_values:
			entry["values"] = {value: {"qty": 0} for value in primary_values}
			for row in variants:
				variant = frappe.get_cached_doc("Item", row.get("item_variant"))
				attributes = {
					value.attribute: _attribute_value(value.attribute_value)
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
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
			fetch_order_item_details as fetch_garment_items,
		)

		return fetch_garment_items(
			items,
			production_detail,
			process=process,
			includes_packing=includes_packing,
		)
	return _generic_work_order_items(items)


def set_attribute_display_values(doc):
	"""Replace stored IAV links with their display values on a document being printed."""
	registered = attribute_db.fields()
	targets = [
		(row, fieldname)
		for row in (doc, *doc.get_all_children())
		for fieldname in registered.get(row.doctype, ())
	]
	prime_attribute_values(row.get(fieldname) for row, fieldname in targets)
	for row, fieldname in targets:
		row.set(fieldname, _attribute_value(row.get(fieldname)))


def get_dc_grn_letter_head(doc):
	"""The DC's own letter head, else MRP's DC/GRN letter head, which F15 stamped on submit."""
	return doc.get("letter_head") or frappe.db.get_single_value("SD YRP MRP Settings", "dc_grn_letter_head") or ""


MRP_ADDRESS_TEMPLATE = (
	"{{ address_line1 }}, {% if address_line2 %}{{ address_line2 }}{% endif -%}<br>"
	"{{ city }}, {% if state %}{{ state }}{% endif -%}{% if pincode %} - {{ pincode }}{% endif -%}"
)


def _address_display(address):
	"""A linked Address in MRP's party-address layout, which has no address title line."""
	if not address:
		return ""
	doc = frappe.get_cached_doc("Address", address)
	doc.check_permission("read")
	return frappe.render_template(MRP_ADDRESS_TEMPLATE, doc.as_dict())


def strip_party_name_line(address_display, party_name):
	"""Drop a leading address line that only repeats the party name printed above it."""
	lines = re.split(r"(<br\s*/?>|\n)", address_display or "", maxsplit=1)
	if party_name and lines[0].strip().rstrip(",").strip() == party_name.strip():
		return lines[2].lstrip() if len(lines) > 2 else ""
	return address_display or ""


def get_party_address_display(party_name, stored_display, address, party):
	"""The stored F15 snapshot, else the linked address, else the party's primary address."""
	display = stored_display or _address_display(address) or get_supplier_address_display(party)
	return strip_party_name_line(display, party_name)


def prepare_delivery_challan_print(doc):
	"""Print the stored party names and address snapshots like F15, filling only missing ones."""
	doc.letter_head = get_dc_grn_letter_head(doc)
	for party, name_field, address, details in (
		("from_location", "from_location_name", "from_address", "from_address_details"),
		("supplier", "supplier_name", "supplier_address", "supplier_address_details"),
	):
		doc.set(name_field, doc.get(name_field) or _supplier_name(doc.get(party)))
		doc.set(
			details,
			get_party_address_display(
				doc.get(name_field), doc.get(details), doc.get(address), doc.get(party)
			),
		)


def get_stock_entry_locations(doc):
	"""F15's From/To parties: the warehouse's supplier on its own side, else the transfer supplier."""
	transfer_supplier = doc.get("transfer_supplier")
	from_location = transfer_supplier or doc.get("from_supplier")
	to_location = transfer_supplier or doc.get("to_supplier")
	if doc.get("purpose") in ("Send to Warehouse", "Material Issue"):
		from_location = doc.get("from_supplier") or _warehouse_supplier(doc.get("from_warehouse"))
	if doc.get("purpose") in ("Send to Warehouse", "Material Receipt"):
		to_location = doc.get("to_supplier") or _warehouse_supplier(doc.get("to_warehouse"))
	return from_location, to_location


def _warehouse_supplier(warehouse):
	return frappe.db.get_value("Warehouse", warehouse, "supplier") if warehouse else None


def prepare_stock_entry_print(doc):
	doc.from_location, doc.to_location = get_stock_entry_locations(doc)
	for side in ("from", "to"):
		location = doc.get(f"{side}_location")
		name = frappe.db.get_value("Supplier", location, "supplier_name") if location else ""
		doc.set(f"{side}_location_name", name)
		doc.set(f"{side}_address_details", get_supplier_address_display(location))


def prepare_print_document(doc, method=None, settings=None):
	"""Add transient F15 layout aliases to the F16 YRP documents.

	The aliases exist only for rendering. They are never saved and therefore do
	not expand or duplicate the canonical F16 DocType schema.
	"""
	if doc.doctype == "YRP Delivery Challan":
		prepare_delivery_challan_print(doc)
	elif doc.doctype == "YRP Goods Received Note":
		doc.letter_head = get_dc_grn_letter_head(doc)
		doc.supplier_name = doc.get("supplier_name") or _supplier_name(doc.get("supplier"))
		doc.supplier_address_display = get_party_address_display(
			doc.supplier_name,
			doc.get("supplier_address_display"),
			doc.get("supplier_address"),
			doc.get("supplier"),
		)
		doc.delivery_location_name = doc.get("delivery_location_name") or _supplier_name(
			doc.get("delivery_location")
		)
		doc.delivery_address_display = get_party_address_display(
			doc.delivery_location_name,
			doc.get("delivery_address_display"),
			doc.get("delivery_address"),
			doc.get("delivery_location"),
		)
		doc.grn_date = doc.get("grn_date") or doc.get("posting_date")
		doc.show_delivery_details = 0
		doc.total_tax = 0
		doc.grand_total = flt(doc.get("total"))
		doc.in_words = money_in_words(doc.grand_total, "INR")
		doc.approved_by = doc.get("approved_by") or doc.get("modified_by")
	elif doc.doctype == "YRP Work Order":
		doc.supplier_address_details = doc.get("supplier_address_details") or get_supplier_address_display(
			doc.get("supplier")
		)
		doc.delivery_address_details = doc.get("delivery_address_details") or get_supplier_address_display(
			doc.get("delivery_location")
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
	elif doc.doctype == "YRP Stock Entry":
		prepare_stock_entry_print(doc)
		doc.transfer_supplier = (
			doc.get("transfer_supplier") or doc.get("from_supplier") or doc.get("to_supplier")
		)
		doc.approved_by = doc.get("approved_by") or doc.get("modified_by")

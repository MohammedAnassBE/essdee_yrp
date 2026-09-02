# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

"""Clearing Rework workflow migrated from Production API.

The legacy page wrote zero-rate ledger entries directly. This implementation
keeps the same operator workflow while routing every Received Type conversion
through YRP's dimension-aware stock engine at the source bucket's live rate.
"""

from __future__ import annotations

import json
from io import BytesIO

import frappe
import openpyxl
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime, nowdate, nowtime
from yrp.utils import get_variant_attr_details

QTY_TOLERANCE = 0.0001


class SDYRPGRNReworkItem(Document):
	def on_trash(self):
		if self.get("grn_reworked_item_details") or self.get("grn_rejected_item_details"):
			frappe.throw(
				_("GRN Rework Item {0} has stock conversions and cannot be deleted.").format(
					self.name
				)
			)


def _json(value):
	if isinstance(value, str):
		try:
			return json.loads(value or "{}")
		except (TypeError, ValueError):
			return {}
	return value or {}


def _received_type_defaults():
	return (
		frappe.db.get_single_value('YRP YRP Stock Settings', "default_received_type"),
		frappe.db.get_single_value(
			'YRP YRP Stock Settings', "default_rejected_received_type"
		),
	)


def _actual_receipt_warehouse(grn_item, fallback):
	"""Return the warehouse where this GRN row actually posted.

	Internal-unit receipts post to Transit Warehouse first, so ``to_warehouse``
	is not necessarily the live stock bucket.
	"""
	warehouse = frappe.db.get_value(
		'YRP Stock Ledger Entry',
		{
			"voucher_type": 'YRP Goods Received Note',
			"voucher_no": grn_item.parent,
			"voucher_detail_no": grn_item.name,
			"is_cancelled": 0,
			"qty": (">", 0),
		},
		"warehouse",
		order_by="posting_datetime desc, creation desc",
	)
	return warehouse or fallback


def sync_grn_rework(doc, method=None):
	"""Create one idempotent rework source per GRN logical matrix row."""
	del method
	if isinstance(doc, str):
		doc = frappe.get_doc('YRP Goods Received Note', doc)
	if doc.docstatus != 1 or doc.get("is_return") or doc.get("is_rework"):
		return []

	accepted, rejected = _received_type_defaults()
	if not accepted or not rejected:
		frappe.throw(
			_("Configure default Accepted and Rejected Received Types in YRP Stock Settings.")
		)

	groups = {}
	for row in doc.get("items") or []:
		quantity = flt(row.get("quantity"))
		received_type = row.get("received_type") or accepted
		if quantity <= QTY_TOLERANCE or received_type in {accepted, rejected}:
			continue
		if frappe.db.exists('SD YRP GRN Rework Item Detail', {"source_grn_item": row.name}):
			continue
		groups.setdefault(row.get("row_index") or row.name, []).append(row)

	created = []
	for rows in groups.values():
		rework = frappe.new_doc('SD YRP GRN Rework Item')
		rework.update(
			{
				"naming_series": "RW-",
				"grn_number": doc.name,
				"lot": doc.get("lot"),
				"item": doc.get("item"),
				"warehouse": _actual_receipt_warehouse(rows[0], doc.to_warehouse),
			}
		)
		for row in rows:
			rework.append(
				"grn_rework_item_details",
				{
					"source_grn_item": row.name,
					"item_variant": row.item_variant,
					"received_type": row.get("received_type"),
					"quantity": flt(row.quantity),
					"rejection": 0,
					"reworked": 0,
					"completed": 0,
					"uom": row.uom,
					"set_combination": frappe.as_json(_json(row.get("set_combination"))),
				},
			)
		rework.insert(ignore_permissions=True)
		created.append(rework.name)
	return created


@frappe.whitelist()
def sync_grn_rework_for_name(grn_number):
	"""Permission-checked backfill for an already submitted GRN."""
	grn = frappe.get_doc('YRP Goods Received Note', grn_number)
	grn.check_permission("read")
	if not frappe.has_permission('SD YRP GRN Rework Item', "create"):
		frappe.throw(_("Not permitted to create GRN Rework Items."), frappe.PermissionError)
	return sync_grn_rework(grn)


def before_grn_cancel(doc, method=None):
	del method
	for name in frappe.get_all(
		'SD YRP GRN Rework Item', filters={"grn_number": doc.name}, pluck="name"
	):
		rework = frappe.get_doc('SD YRP GRN Rework Item', name)
		if rework.get("grn_reworked_item_details") or rework.get("grn_rejected_item_details"):
			frappe.throw(
				_(
					"Goods Received Note {0} has cleared rework in {1}; "
					"reverse that rework before cancelling."
				).format(doc.name, name)
			)


def on_grn_cancel(doc, method=None):
	del method
	for name in frappe.get_all(
		'SD YRP GRN Rework Item', filters={"grn_number": doc.name}, pluck="name"
	):
		frappe.delete_doc('SD YRP GRN Rework Item', name, ignore_permissions=True)


def _page_permissions():
	return {
		"can_read": bool(frappe.has_permission('SD YRP GRN Rework Item', "read")),
		"can_write": bool(frappe.has_permission('SD YRP GRN Rework Item', "write")),
	}


@frappe.whitelist()
def get_rework_items(
	lot=None,
	item=None,
	colour=None,
	grn_number=None,
	show_reworked=0,
	received_type=None,
):
	permissions = _page_permissions()
	if not permissions["can_read"]:
		frappe.throw(_("Not permitted to read GRN Rework Items."), frappe.PermissionError)

	filters = {}
	if lot:
		filters["lot"] = lot
	if item:
		filters["item"] = item
	if grn_number:
		filters["grn_number"] = grn_number

	show_reworked = cint(show_reworked)
	data = {
		"report_detail": {},
		"types": [],
		"total_detail": {},
		"total_sum": 0,
		"total_rejection": 0,
		"total_rejection_detail": {},
		"permissions": permissions,
	}
	for name in frappe.get_all(
		'SD YRP GRN Rework Item', filters=filters, pluck="name", order_by="creation desc"
	):
		doc = frappe.get_doc('SD YRP GRN Rework Item', name)
		doc.check_permission("read")
		ipd = frappe.get_cached_value('SD YRP Lot', doc.lot, "production_detail")
		if not ipd:
			continue
		pack_attr, primary_attr, is_set_item, set_attr = frappe.get_cached_value(
			'YRP Item Production Detail',
			ipd,
			[
				"packing_attribute",
				"primary_item_attribute",
				"is_set_item",
				"set_item_attribute",
			],
		)
		detail = {
			"grn_number": doc.grn_number,
			"date": doc.creation,
			"lot": doc.lot,
			"item": doc.item,
			"warehouse": doc.warehouse,
			"rework_detail": {},
			"size": primary_attr,
			"types": {},
			"total": 0,
			"rejection_detail": {},
			"total_rejection": 0,
		}
		for row in doc.get("grn_rework_item_details") or []:
			if bool(row.completed) != bool(show_reworked):
				continue
			if received_type and row.received_type != received_type:
				continue
			attrs = get_variant_attr_details(row.item_variant)
			if colour and colour.lower() not in str(attrs.get(pack_attr, "")).lower():
				continue
			key_parts = [row.received_type, attrs.get(pack_attr, "")]
			if is_set_item:
				key_parts.append(attrs.get(set_attr, ""))
			key = "-".join(str(value or "") for value in key_parts)
			qty = flt(row.quantity) if show_reworked else flt(row.quantity) - flt(row.reworked)
			detail["rework_detail"].setdefault(key, {"changed": 0, "items": []})
			detail["rework_detail"][key]["items"].append(
				{
					primary_attr: attrs.get(primary_attr, ""),
					"rework_qty": qty,
					"reworked_qty": flt(row.reworked),
					"rejected": flt(row.rejection),
					"rework": 0,
					"set_combination": _json(row.set_combination),
					"row_name": row.name,
					"variant": row.item_variant,
					"received_type": row.received_type,
					"uom": row.uom,
				}
			)
			if row.received_type not in data["types"]:
				data["types"].append(row.received_type)
			data["total_detail"][row.received_type] = (
				data["total_detail"].get(row.received_type, 0) + qty
			)
			data["total_rejection_detail"][row.received_type] = (
				data["total_rejection_detail"].get(row.received_type, 0) + flt(row.rejection)
			)
			data["total_sum"] += qty
			data["total_rejection"] += flt(row.rejection)
			detail["types"][row.received_type] = detail["types"].get(row.received_type, 0) + qty
			detail["rejection_detail"][row.received_type] = (
				detail["rejection_detail"].get(row.received_type, 0) + flt(row.rejection)
			)
			detail["total"] += qty
			detail["total_rejection"] += flt(row.rejection)
		for group in detail["rework_detail"].values():
			group["items"].sort(key=lambda row: _size_sort_key(row.get(primary_attr)))
		if detail["rework_detail"]:
			data["report_detail"][name] = detail

	if grn_number:
		return data, next(iter(data["report_detail"]), None)
	return data


def _size_sort_key(value):
	text = str(value or "")
	try:
		return (0, float(text.split()[0]))
	except (TypeError, ValueError):
		return (1, text)


def _load_action_rows(payload):
	rows = _json(payload)
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Select at least one Rework row."))
	row_names = [row.get("row_name") for row in rows if row.get("row_name")]
	parents = set(
		frappe.get_all(
			'SD YRP GRN Rework Item Detail',
			filters={"name": ("in", row_names)},
			pluck="parent",
		)
	)
	if len(row_names) != len(rows) or len(parents) != 1:
		frappe.throw(_("All selected Rework rows must belong to one source document."))
	parent = frappe.get_doc('SD YRP GRN Rework Item', parents.pop(), for_update=True)
	parent.check_permission("write")
	by_name = {row.name: row for row in parent.grn_rework_item_details}
	if any(name not in by_name for name in row_names):
		frappe.throw(_("One or more Rework rows no longer exist. Refresh and try again."))
	return rows, parent, by_name


@frappe.whitelist()
def update_partial_quantity(data, lot=None):
	rows, parent, by_name = _load_action_rows(data)
	if lot and lot != parent.lot:
		frappe.throw(_("Lot does not match the Rework source."))
	accepted, _rejected = _received_type_defaults()
	conversions = []
	for posted in rows:
		source = by_name[posted["row_name"]]
		if source.completed:
			frappe.throw(_("Rework row {0} is already completed.").format(source.name))
		qty = flt(posted.get("rework"))
		remaining = flt(source.quantity) - flt(source.reworked)
		if qty < -QTY_TOLERANCE or qty > remaining + QTY_TOLERANCE:
			frappe.throw(
				_("Reworked quantity for {0} must be between 0 and {1}.").format(
					source.item_variant, remaining
				)
			)
		if qty + flt(source.rejection) > remaining + QTY_TOLERANCE:
			frappe.throw(
				_(
					"Reworked and provisional Rejection quantities for {0} cannot exceed {1}."
				).format(source.item_variant, remaining)
			)
		if qty <= QTY_TOLERANCE:
			continue
		conversions.append((source, accepted, qty))
		source.reworked = flt(source.reworked) + qty
		parent.append(
			"grn_reworked_item_details",
			{
				"item_variant": source.item_variant,
				"quantity": qty,
				"received_type": source.received_type,
				"uom": source.uom,
				"reworked_time": now_datetime(),
				"set_combination": source.set_combination or {},
			},
		)
	if not conversions:
		frappe.throw(_("Enter a Reworked quantity greater than zero."))
	parent.save()
	_post_conversions(parent, conversions)
	_rebuild_finishing(parent.lot)
	return {
		"name": parent.name,
		"converted": sum(qty for _row, _target, qty in conversions),
	}


@frappe.whitelist()
def update_rejected_quantity(rejection_data, completed=0, lot=None):
	rows, parent, by_name = _load_action_rows(rejection_data)
	if lot and lot != parent.lot:
		frappe.throw(_("Lot does not match the Rework source."))
	completed = cint(completed)
	accepted, rejected = _received_type_defaults()
	conversions = []
	for posted in rows:
		source = by_name[posted["row_name"]]
		if source.completed:
			frappe.throw(_("Rework row {0} is already completed.").format(source.name))
		remaining = flt(source.quantity) - flt(source.reworked)
		rejected_qty = flt(posted.get("rejected"))
		if rejected_qty < -QTY_TOLERANCE or rejected_qty > remaining + QTY_TOLERANCE:
			frappe.throw(
				_("Rejected quantity for {0} must be between 0 and {1}.").format(
					source.item_variant, remaining
				)
			)
		source.rejection = rejected_qty
		if not completed:
			continue
		accepted_qty = remaining - rejected_qty
		if accepted_qty > QTY_TOLERANCE:
			conversions.append((source, accepted, accepted_qty))
			parent.append(
				"grn_reworked_item_details",
				{
					"item_variant": source.item_variant,
					"quantity": accepted_qty,
					"received_type": source.received_type,
					"uom": source.uom,
					"reworked_time": now_datetime(),
					"set_combination": source.set_combination or {},
				},
			)
		if rejected_qty > QTY_TOLERANCE:
			conversions.append((source, rejected, rejected_qty))
			parent.append(
				"grn_rejected_item_details",
				{
					"item_variant": source.item_variant,
					"quantity": rejected_qty,
					"received_type": source.received_type,
					"uom": source.uom,
					"rejected_time": now_datetime(),
					"set_combination": source.set_combination or {},
				},
			)
		source.completed = 1
	if completed:
		parent.completed = int(all(row.completed for row in parent.grn_rework_item_details))
	parent.save()
	if conversions:
		_post_conversions(parent, conversions)
		_rebuild_finishing(parent.lot)
	return {"name": parent.name, "completed": parent.completed}


def _post_conversions(parent, conversions):
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.stock.stock_ledger import make_sl_entries
	from yrp.stock.utils import get_last_sle_rate, get_stock_balance

	entries = []
	for sequence, (row, target_type, qty) in enumerate(conversions, start=1):
		dimensions = _source_dimensions(parent, row, get_dimension_fieldnames())
		warehouse = _source_warehouse(
			parent, row, dimensions, qty, get_stock_balance
		)
		rate, _matched = get_last_sle_rate(
			row.item_variant, warehouse=warehouse, **dimensions
		)
		stock_uom = frappe.get_cached_value(
			'YRP Item',
			frappe.get_cached_value('YRP Item Variant', row.item_variant, "item"),
			"default_unit_of_measure",
		) or row.uom
		base = {
			"item": row.item_variant,
			"warehouse": warehouse,
			"uom": stock_uom,
			"voucher_type": 'SD YRP GRN Rework Item',
			"voucher_no": parent.name,
			"voucher_detail_no": row.name,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"is_cancelled": 0,
		}
		for fieldname in get_dimension_fieldnames():
			base[fieldname] = dimensions.get(fieldname)
		transfer_key = f"GRN Rework Item:{parent.name}:{row.name}:{sequence}"
		entries.append(
			{
				**base,
				"qty": -flt(qty),
				"rate": 0,
				"outgoing_rate": flt(rate),
				"_transfer_key": transfer_key,
				"_transfer_role": "outgoing",
			}
		)
		incoming = dict(base)
		incoming["received_type"] = target_type
		entries.append(
			{
				**incoming,
				"qty": flt(qty),
				# The paired outgoing FIFO result is authoritative. This zero is
				# replaced by the stock engine before the incoming SLE is posted.
				"rate": 0,
				"_transfer_key": transfer_key,
				"_transfer_role": "incoming",
			}
		)
	make_sl_entries(entries, force_inline=True)


def _source_dimensions(parent, row, dimension_fieldnames):
	values = {}
	if row.get("source_grn_item") and frappe.db.exists(
		'YRP Goods Received Note Item', row.source_grn_item
	):
		source = frappe.get_doc('YRP Goods Received Note Item', row.source_grn_item)
		values.update({fieldname: source.get(fieldname) for fieldname in dimension_fieldnames})
	if "lot" in dimension_fieldnames:
		values["lot"] = values.get("lot") or parent.lot
	if "received_type" in dimension_fieldnames:
		values["received_type"] = row.received_type
	return values


def _source_warehouse(parent, row, dimensions, qty, get_stock_balance):
	candidates = [parent.warehouse]
	if parent.grn_number:
		final_warehouse = frappe.db.get_value(
			'YRP Goods Received Note', parent.grn_number, "to_warehouse"
		)
		if final_warehouse and final_warehouse not in candidates:
			candidates.append(final_warehouse)
	balances = {}
	for warehouse in candidates:
		balance = get_stock_balance(row.item_variant, warehouse, **dimensions)
		if isinstance(balance, tuple):
			balance = balance[0]
		balances[warehouse] = flt(balance)
		if flt(balance) + QTY_TOLERANCE >= flt(qty):
			return warehouse
	frappe.throw(
		_("Cannot clear {0} {1}: source stock is unavailable ({2}).").format(
			flt(qty), row.item_variant, ", ".join(f"{key}: {value}" for key, value in balances.items())
		)
	)


def _rebuild_finishing(lot):
	from essdee_yrp.finishing.rebuild import rebuild_finishing_plan

	for name in frappe.get_all('SD YRP Finishing Plan', filters={"lot": lot}, pluck="name"):
		rebuild_finishing_plan(name, check_permission=False)


@frappe.whitelist()
def download_xl(data):
	if not frappe.has_permission('SD YRP GRN Rework Item', "read"):
		frappe.throw(_("Not permitted to export GRN Rework Items."), frappe.PermissionError)
	data = _json(data)
	workbook = openpyxl.Workbook(write_only=True)
	sheet = workbook.create_sheet("Rework Details", 0)
	types = data.get("types") or []
	sheet.append(
		["Series No", "Date", "GRN Number", 'SD YRP Lot', 'YRP Item', "Colour", *types, "Total"]
	)
	for series, detail in (data.get("report_detail") or {}).items():
		first_key = next(iter(detail.get("rework_detail") or {}), "")
		colour = "-".join(first_key.split("-")[1:])
		row = [
			series,
			str(detail.get("date") or "")[:10],
			detail.get("grn_number"),
			detail.get("lot"),
			detail.get("item"),
			colour,
		]
		for received_type in types:
			row.append(
				flt(detail.get("types", {}).get(received_type))
				- flt(detail.get("rejection_detail", {}).get(received_type))
			)
		row.append(flt(detail.get("total")) - flt(detail.get("total_rejection")))
		sheet.append(row)
	output = BytesIO()
	workbook.save(output)
	frappe.local.response.filename = "rework_details.xlsx"
	frappe.local.response.filecontent = output.getvalue()
	frappe.local.response.type = "binary"


GRNReworkItem = SDYRPGRNReworkItem

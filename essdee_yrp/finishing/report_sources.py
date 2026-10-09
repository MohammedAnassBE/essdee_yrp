"""Frappe 15 Finishing report read models (Rejection, Rework, Ironing) on the YRP doctypes."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
from yrp import attribute_links as attribute_db
from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	get_ipd_primary_values,
)

from essdee_yrp.report_helpers import _normalize_multiselect_filter

REWORK_DOCTYPE = "SD YRP GRN Rework Item"
IPD_FIELDS = ("packing_attribute", "primary_item_attribute", "is_set_item", "set_item_attribute")


def require_read(doctype):
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to read {0}.").format(_(doctype)), frappe.PermissionError)


def lot_ipd(lot):
	"""Return the lot's Item Production Detail name and its attribute settings."""
	ipd = attribute_db.get_cached_value("SD YRP Lot", lot, "production_detail")
	if not ipd:
		return None, None
	values = attribute_db.get_cached_value("YRP Item Production Detail", ipd, list(IPD_FIELDS))
	return ipd, dict(zip(IPD_FIELDS, values, strict=True))


def colour_key(received_type, attributes, ipd):
	key = f"{received_type}-{attributes.get(ipd['packing_attribute'])}"
	if ipd["is_set_item"]:
		key += f"-{attributes.get(ipd['set_item_attribute'])}"
	return key


def rejected_rows_in_range(doc, start_date, end_date, colour):
	rows = []
	for row in doc.grn_rejected_item_details or []:
		rejected_time = str(row.rejected_time) if row.rejected_time else ""
		if start_date and rejected_time and rejected_time < start_date:
			continue
		if end_date and rejected_time and rejected_time > f"{end_date} 23:59:59":
			continue
		if colour and colour not in (row.item_variant or ""):
			continue
		rows.append(row)
	return rows


def build_rejection_report(entries, start_date=None, end_date=None, colour=None):
	"""Group rejected rework rows by source document exactly like the Frappe 15 page."""
	data = {"report_detail": {}, "types": [], "total_detail": {}, "total_sum": 0}
	for doc, ipd in entries:
		rows = rejected_rows_in_range(doc, start_date, end_date, colour)
		if not rows:
			continue
		times = [str(row.rejected_time) for row in rows if row.rejected_time]
		detail = data["report_detail"].setdefault(
			doc.name,
			{
				"grn_number": doc.grn_number,
				"date": min(times) if times else str(doc.creation),
				"lot": doc.lot,
				"item": doc.item,
				"size": ipd["primary_item_attribute"],
				"types": {},
				"total": 0,
				"rejection_detail": {},
			},
		)
		for row in rows:
			add_rejected_row(data, detail, row, ipd)
	return data


def add_rejected_row(data, detail, row, ipd):
	attributes = get_variant_attr_details(row.item_variant)
	received_type = row.received_type
	qty = flt(row.quantity)
	if received_type not in data["types"]:
		data["types"].append(received_type)
	data["total_detail"][received_type] = data["total_detail"].get(received_type, 0) + qty
	data["total_sum"] += qty
	detail["types"][received_type] = detail["types"].get(received_type, 0) + qty
	detail["total"] += qty
	group = detail["rejection_detail"].setdefault(colour_key(received_type, attributes, ipd), {"items": []})
	group["items"].append(
		{
			ipd["primary_item_attribute"]: attributes.get(ipd["primary_item_attribute"]),
			"rejected_qty": qty,
			"variant": row.item_variant,
			"received_type": received_type,
		}
	)


def get_rejection_items(start_date=None, end_date=None, lot=None, item=None, colour=None):
	require_read(REWORK_DOCTYPE)
	conditions, values = [], {}
	if start_date:
		conditions.append("detail.rejected_time >= %(start_date)s")
		values["start_date"] = start_date
	if end_date:
		conditions.append("detail.rejected_time <= %(end_date)s")
		values["end_date"] = f"{end_date} 23:59:59"
	for field, value in (("lot", lot), ("item", item)):
		if value:
			conditions.append(f"source.{field} = %({field})s")
			values[field] = value
	if colour:
		conditions.append("detail.item_variant LIKE %(colour)s")
		values["colour"] = f"%{colour}%"
	where = " AND ".join(["1 = 1", *conditions])
	names = frappe.db.sql(
		f"""
		SELECT source.name FROM `tabSD YRP GRN Rework Item` source
		JOIN `tabSD YRP GRN Rejected Item Detail` detail ON detail.parent = source.name
		WHERE {where} GROUP BY source.name ORDER BY source.name
		""",
		values,
		pluck=True,
	)
	return build_rejection_report(readable_rework_entries(names), start_date, end_date, colour)


def readable_rework_entries(names):
	entries = []
	for name in names:
		doc = frappe.get_doc(REWORK_DOCTYPE, name)
		if not doc.has_permission("read"):
			continue
		_ipd_name, ipd = lot_ipd(doc.lot)
		if ipd:
			entries.append((doc, ipd))
	return entries


def build_rework_completion(rows, ipd, primary_values, default_received_type):
	"""Size-wise reworked pieces per colour, as the Frappe 15 Rework Completion page shows."""
	data = {}
	for row in rows:
		attributes = get_variant_attr_details(row.item_variant)
		combination = update_if_string_instance(update_if_string_instance(row.set_combination)) or {}
		colour = combination.get("major_colour")
		part = None
		if ipd["is_set_item"]:
			colour = f"{attributes.get(ipd['packing_attribute'])}({combination.get('major_colour')})"
			part = attributes.get(ipd["set_item_attribute"])
		size = attributes.get(ipd["primary_item_attribute"])
		entry = data.setdefault(
			colour,
			{
				"values": {},
				"part": part,
				"type_wise_total": {},
				"size_wise_total": {},
				"colour_total": {"total": 0},
			},
		)
		qty = flt(row.quantity)
		cell = entry["values"].setdefault(size, {})
		cell[default_received_type] = cell.get(default_received_type, 0) + qty
		entry["size_wise_total"][size] = entry["size_wise_total"].get(size, 0) + qty
		entry["type_wise_total"][default_received_type] = (
			entry["type_wise_total"].get(default_received_type, 0) + qty
		)
		entry["colour_total"]["total"] += qty
	return {
		"primary_values": primary_values,
		"types": [default_received_type],
		"data": data,
		"is_set_item": ipd["is_set_item"],
		"set_attr": ipd["set_item_attribute"],
	}


def get_rework_completion(lot, process):
	require_read(REWORK_DOCTYPE)
	if not lot or not process:
		frappe.throw(_("Select a Lot and a Process."))
	ipd_name, ipd = lot_ipd(lot)
	if not ipd:
		frappe.throw(_("Lot {0} has no Item Production Detail.").format(lot))
	grns = frappe.get_list(
		"YRP Goods Received Note",
		filters={"against": "YRP Work Order", "docstatus": 1, "lot": lot, "process_name": process},
		pluck="name",
	)
	sources = (
		frappe.get_list(REWORK_DOCTYPE, filters={"grn_number": ["in", grns]}, pluck="name") if grns else []
	)
	rows = (
		frappe.get_all(
			"SD YRP GRN Reworked Item Detail",
			filters={"parent": ["in", sources], "parenttype": REWORK_DOCTYPE, "quantity": [">", 0]},
			fields=["item_variant", "quantity", "uom", "parent", "set_combination"],
			order_by="parent asc, idx asc",
		)
		if sources
		else []
	)
	default_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	return build_rework_completion(rows, ipd, get_ipd_primary_values(ipd_name), default_type)


def build_rework_groups(entries, show_reworked=0, colour=None):
	"""Item/Lot groups of colour x GRN x Received Type rows (Frappe 15 Rework Group Details)."""
	show_reworked = cint(show_reworked)
	groups = {}
	for doc, ipd, primary_values in entries:
		rows = [
			row
			for row in doc.grn_rework_item_details or []
			if bool(cint(row.completed)) == bool(show_reworked)
		]
		if colour and not any(
			colour in (row.item_variant or "") for row in doc.grn_rework_item_details or []
		):
			continue
		if not rows:
			continue
		group = groups.setdefault(
			f"{doc.item}/{doc.lot}",
			{
				"item": doc.item,
				"lot": doc.lot,
				"sizes": primary_values,
				"size_attr": ipd["primary_item_attribute"],
				"is_set_item": ipd["is_set_item"],
				"rows_dict": {},
			},
		)
		for row in rows:
			add_group_row(group, doc, row, ipd, show_reworked)
	for group in groups.values():
		rows_dict = group.pop("rows_dict")
		group["rows"] = [rows_dict[key] for key in sorted(rows_dict)]
	return {"groups": groups}


def add_group_row(group, doc, row, ipd, show_reworked):
	attributes = get_variant_attr_details(row.item_variant)
	colour = attributes.get(ipd["packing_attribute"], "")
	part = attributes.get(ipd["set_item_attribute"], "") if ipd["is_set_item"] else None
	size = attributes.get(ipd["primary_item_attribute"], "")
	key = f"{colour}|{part or ''}|{doc.grn_number}|{row.received_type}"
	entry = group["rows_dict"].setdefault(
		key,
		{
			"colour": colour,
			"part": part,
			"grn_number": doc.grn_number,
			"received_type": row.received_type,
			"lot": doc.lot,
			"received": {},
			"rejection": {},
			"reworked": {},
			"items": [],
		},
	)
	qty = flt(row.quantity) if show_reworked else flt(row.quantity) - flt(row.reworked)
	for bucket, value in (
		("received", qty),
		("rejection", flt(row.rejection)),
		("reworked", flt(row.reworked)),
	):
		entry[bucket][size] = entry[bucket].get(size, 0) + value
	entry["items"].append(
		{
			ipd["primary_item_attribute"]: size,
			"rework_qty": qty,
			"reworked_qty": flt(row.reworked),
			"rejected": flt(row.rejection),
			"rework": 0,
			"set_combination": update_if_string_instance(row.set_combination),
			"row_name": row.name,
			"variant": row.item_variant,
			"received_type": row.received_type,
			"uom": row.uom,
		}
	)


def get_rework_group_items(lot=None, item=None, colour=None, show_reworked=0):
	require_read(REWORK_DOCTYPE)
	filters = {"completed": 1 if cint(show_reworked) else 0}
	if lot:
		filters["lot"] = lot
	if item:
		filters["item"] = item
	entries = []
	primary_values = {}
	for name in frappe.get_list(REWORK_DOCTYPE, filters=filters, pluck="name", order_by="name asc"):
		doc = frappe.get_doc(REWORK_DOCTYPE, name)
		ipd_name, ipd = lot_ipd(doc.lot)
		if not ipd:
			continue
		if ipd_name not in primary_values:
			primary_values[ipd_name] = get_ipd_primary_values(ipd_name)
		entries.append((doc, ipd, primary_values[ipd_name]))
	data = build_rework_groups(entries, show_reworked, colour)
	data["permissions"] = {"can_write": bool(frappe.has_permission(REWORK_DOCTYPE, "write"))}
	return data


def ironing_row_key(attributes, colour_attr, part_attr, is_set_item):
	colour = attributes.get(colour_attr, "")
	part = attributes.get(part_attr, "") if is_set_item else None
	if not colour and not part:
		return None, colour, part
	return ((part, colour) if is_set_item else colour), colour, part


def build_ironing_report(challans, ipds, colour_attr, default_part_attr):
	"""Lot blocks of colour (and part) x size delivered quantities (Frappe 15 Ironing DPR)."""
	blocks = {}
	for challan in challans:
		ipd = ipds.get(challan["ipd"]) or {}
		is_set_item = cint(ipd.get("is_set_item"))
		part_attr = ipd.get("set_item_attribute") or default_part_attr
		sizes = ipd.get("primary_values") or []
		block = blocks.setdefault(
			(str(challan["actual_date"]), challan["lot"]),
			{
				"date": str(challan["actual_date"]),
				"lot": challan["lot"],
				"item": challan["item"],
				"primary_attributes": sizes,
				"rows": {},
			},
		)
		block["attributes"] = [colour_attr, part_attr] if is_set_item else [colour_attr]
		for item in challan["items"]:
			key, colour, part = ironing_row_key(
				get_variant_attr_details(item.item_variant), colour_attr, part_attr, is_set_item
			)
			if key is None:
				continue
			target = block["rows"].setdefault(key, {"colour": colour, "part": part, "total_qty": 0})
			size = get_variant_attr_details(item.item_variant).get(ipd.get("primary_item_attribute") or "")
			for value in sizes:
				target[value] = target.get(value, 0) + (flt(item.delivered_quantity) if value == size else 0)
			target["total_qty"] += flt(item.delivered_quantity) if size in sizes else 0
	return ironing_result(blocks)


def ironing_result(blocks):
	result = []
	for block in blocks.values():
		rows = list(block.pop("rows").values())
		if not rows:
			continue
		for index, row in enumerate(rows, 1):
			row["s_no"] = index
		result.append({**block, "rows": rows})
	return result


def ironing_filters(date, dc_name, from_date, to_date, summary, lot, item):
	filters = {"includes_packing": 1, "docstatus": 1, "process_name": ["in", ironing_processes()]}
	if cint(summary):
		if not from_date or not to_date:
			frappe.throw(_("From Date and To Date are required for Summary"))
		if getdate(from_date) > getdate(to_date):
			frappe.throw(_("From Date cannot be after To Date"))
		filters["actual_date"] = ["between", [from_date, to_date]]
	elif date:
		filters["actual_date"] = date
	elif not dc_name:
		frappe.throw(_("Date is required"))
	if dc_name:
		filters["name"] = dc_name
	for field, value in (("lot", lot), ("item", item)):
		values = _normalize_multiselect_filter(value)
		if values:
			filters[field] = ["in", values]
	return filters


def ironing_processes():
	ironing = frappe.db.get_single_value("SD YRP MRP Settings", "finishing_plan_ironing_process")
	if not ironing:
		frappe.throw(_("Set the Finishing Plan Ironing Process in MRP Settings."))
	parents = frappe.get_all(
		"YRP Process Details", filters={"process_name": ironing, "parenttype": "YRP Process"}, pluck="parent"
	)
	return [ironing, *parents]


def get_ironing_dpr(date=None, lot=None, item=None, dc_name=None, from_date=None, to_date=None, summary=0):
	require_read("YRP Delivery Challan")
	rows = frappe.get_list(
		"YRP Delivery Challan",
		filters=ironing_filters(date, dc_name, from_date, to_date, summary, lot, item),
		fields=["name", "actual_date", "lot", "item"],
		order_by="actual_date asc, lot asc, name asc",
	)
	items = {}
	for row in frappe.get_all(
		"YRP Delivery Challan Item",
		filters={"parent": ["in", [row.name for row in rows] or [""]], "parenttype": "YRP Delivery Challan"},
		fields=["parent", "item_variant", "delivered_quantity"],
		order_by="parent asc, idx asc",
	):
		items.setdefault(row.parent, []).append(row)
	ipds, challans = {}, []
	for row in rows:
		ipd_name, ipd = lot_ipd(row.lot)
		if ipd_name and ipd_name not in ipds:
			ipds[ipd_name] = {**ipd, "primary_values": get_ipd_primary_values(ipd_name)}
		challans.append(
			{
				"name": row.name,
				"actual_date": row.actual_date or date,
				"lot": row.lot,
				"item": row.item,
				"ipd": ipd_name,
				"items": items.get(row.name, []),
			}
		)
	settings = frappe.get_cached_doc("SD YRP IPD Settings")
	return build_ironing_report(
		challans, ipds, settings.default_packing_attribute, settings.default_set_item_attribute
	)

"""PPO report service for the Sales web workspace.

The old report in ``production_api`` reads legacy doctypes.  This module keeps
the useful report shape while reading only the current F16 YRP schema.
"""

from __future__ import annotations

import json
from collections import OrderedDict, defaultdict
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import flt, now_datetime
from frappe.utils.xlsxutils import make_xlsx

from yrp.utils import get_variant_attr_details
from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details


DOCTYPE = "YRP Production Order"
ORDER_FIELDS = (
	"name",
	"item",
	"fabric",
	"dia",
	"gsm",
	"production_detail",
	"production_term",
	"posting_date",
	"delivery_date",
	"dont_deliver_after",
	"lead_time_given",
	"docstatus",
	"status",
	"comments",
	"comment_log",
)


def empty_report() -> dict:
	return {
		"orders": [],
		"size_groups": [],
		"max_columns": 0,
		"summary": {"total_orders": 0, "total_quantity": 0, "size_groups": 0},
	}


def _mapping(value, label: str) -> dict:
	if not value:
		return {}
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} is not valid JSON.").format(label))
	if not isinstance(value, Mapping):
		frappe.throw(_("{0} must be an object.").format(label))
	return dict(value)


def _value(row, key, default=None):
	if isinstance(row, Mapping):
		return row.get(key, default)
	getter = getattr(row, "get", None)
	return getter(key, default) if callable(getter) else getattr(row, key, default)


def _date(value) -> str:
	return str(value) if value else ""


def normalize_item_filter(item) -> list[str]:
	"""Normalize the multi-select value used by the original PPO report."""
	if not item:
		return []
	if isinstance(item, str):
		try:
			item = frappe.parse_json(item)
		except Exception:
			pass
	if isinstance(item, str):
		item = item.split(",")
	if not isinstance(item, (list, tuple)):
		item = [item]
	result = []
	for value in item:
		value = str(value or "").strip()
		if value and value not in result:
			result.append(value)
	return result


def _quantity_text(value) -> str:
	value = flt(value)
	return str(int(value)) if value == int(value) else str(value)


def group_transfer_movements(rows) -> list[dict]:
	"""Collapse size-level transfer history into the movements shown in PPO."""
	movements = OrderedDict()
	for row in rows or []:
		transfer_reference = _value(row, "transfer_reference") or _value(row, "name")
		movement = _value(row, "movement") or ""
		counterpart = _value(row, "counterpart_production_order") or ""
		key = (transfer_reference, movement, counterpart)
		if key not in movements:
			movements[key] = {
				"transfer_reference": transfer_reference,
				"movement": movement,
				"counterpart_production_order": counterpart,
				"approved_on": _date(_value(row, "approved_on")),
				"approved_by": _value(row, "approved_by") or "",
				"requested_by": _value(row, "requested_by") or "",
				"reason": _value(row, "reason") or "",
				"sizes": OrderedDict(),
				"quantity": 0,
			}
		entry = movements[key]
		size = _value(row, "size") or "Unknown"
		quantity = flt(_value(row, "quantity"))
		entry["sizes"][size] = flt(entry["sizes"].get(size)) + quantity
		entry["quantity"] += quantity

	result = []
	for entry in movements.values():
		is_reduced = entry["movement"] == "Reduced"
		sign = -1 if is_reduced else 1
		entry["signed_sizes"] = {size: sign * quantity for size, quantity in entry["sizes"].items()}
		entry["signed_quantity"] = sign * entry["quantity"]
		preposition = "to" if is_reduced else "from"
		entry["summary"] = f"{entry['movement']} {_quantity_text(entry['quantity'])} {preposition} {entry['counterpart_production_order']}"
		size_summary = ", ".join(f"{size}: {_quantity_text(quantity)}" for size, quantity in entry["sizes"].items())
		entry["detail_summary"] = f"{entry['summary']} ({size_summary})" if size_summary else entry["summary"]
		result.append(entry)
	return result


def _report_permission() -> None:
	if not frappe.has_permission(DOCTYPE, ptype="report"):
		frappe.throw(_("You are not permitted to view the PPO Report."), frappe.PermissionError)


def _order_filters(filters: Mapping) -> dict:
	status = filters.get("status")
	status_to_docstatus = {"Draft": 0, "Submitted": 1, "Cancelled": 2}
	result = {}
	if status in status_to_docstatus:
		result["docstatus"] = status_to_docstatus[status]
	else:
		result["docstatus"] = ["!=", 2]
		if status:
			result["status"] = status

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if from_date and to_date:
		result["delivery_date"] = ["between", [from_date, to_date]]
	elif from_date:
		result["delivery_date"] = [">=", from_date]
	elif to_date:
		result["delivery_date"] = ["<=", to_date]
	return result


def load_size_types() -> list[dict]:
	parents = frappe.get_all(
		"SD YRP FG Item Size Type",
		fields=["name", "size_type"],
		order_by="size_type asc, name asc",
	)
	if not parents:
		return []
	parent_names = [_value(row, "name") for row in parents]
	details = frappe.get_all(
		"SD YRP FG Item Size Type Detail",
		filters={"parent": ["in", parent_names]},
		fields=["parent", "size_type_value", "size", "idx"],
		order_by="parent asc, idx asc",
	)
	linked_values = list(dict.fromkeys(_value(row, "size_type_value") for row in details if _value(row, "size_type_value")))
	value_labels = {
		_value(row, "name"): _value(row, "attribute_value")
		for row in frappe.get_all(
			"YRP Item Attribute Value",
			filters={"name": ["in", linked_values]},
			fields=["name", "attribute_value"],
		)
	} if linked_values else {}
	by_parent = defaultdict(list)
	for row in details:
		by_parent[_value(row, "parent")].append(row)
	result = []
	for parent in parents:
		name = _value(parent, "name")
		rows = sorted(
			by_parent.get(name, []),
			key=lambda row: (_size_position(_value(row, "size")), int(_value(row, "idx") or 0)),
		)
		sizes = [
			value_labels.get(_value(row, "size_type_value"), _value(row, "size_type_value"))
			for row in rows
			if _value(row, "size_type_value")
		]
		if sizes:
			result.append({"label": _value(parent, "size_type") or name, "sizes": sizes})
	return result


def _size_position(value) -> int:
	try:
		return int(str(value or "").rsplit(" ", 1)[-1])
	except ValueError:
		return 999


def _attributes(value) -> dict:
	if not value:
		return {}
	if isinstance(value, Mapping):
		return dict(value)
	try:
		parsed = json.loads(value)
	except (TypeError, ValueError, json.JSONDecodeError):
		return {}
	if isinstance(parsed, Mapping):
		return dict(parsed)
	if isinstance(parsed, list):
		return {
			row.get("attribute"): row.get("attribute_value")
			for row in parsed
			if isinstance(row, Mapping) and row.get("attribute")
		}
	return {}


def _matched_size_group(values: list, size_types: list[dict]) -> dict:
	wanted = {str(value) for value in values if value not in (None, "")}
	for group in sorted(size_types, key=lambda row: (str(row.get("label") or ""), tuple(row.get("sizes") or []))):
		available = {str(value) for value in group.get("sizes") or []}
		if wanted and wanted <= available:
			return {"label": group.get("label") or "", "sizes": list(group.get("sizes") or [])}
	fallback = list(dict.fromkeys(str(value) for value in values if value not in (None, "")))
	return {"label": "", "sizes": fallback}


def attach_variant_primary_values(details, primary_attribute_by_parent) -> list[dict]:
	"""Fill the primary value for migrated rows whose ``attributes_json`` is empty."""
	variant_attributes = {}
	result = []
	for source in details or []:
		row = dict(source) if isinstance(source, Mapping) else dict(source.as_dict())
		primary_attribute = primary_attribute_by_parent.get(row.get("parent")) or "Size"
		attrs = _attributes(row.get("attributes_json"))
		primary_value = attrs.get(primary_attribute) or attrs.get("Size")
		variant = row.get("item_variant")
		if not primary_value and variant:
			if variant not in variant_attributes:
				variant_attributes[variant] = get_variant_attr_details(variant)
			variant_attrs = variant_attributes[variant]
			primary_value = variant_attrs.get(primary_attribute) or variant_attrs.get("Size")
		row["primary_value"] = primary_value
		result.append(row)
	return result


def build_report(orders, details, size_types, item_attributes, transfer_history_by_order=None) -> dict:
	if not orders:
		return empty_report()
	transfer_history_by_order = transfer_history_by_order or {}

	details_by_parent = defaultdict(list)
	for row in details or []:
		details_by_parent[_value(row, "parent")].append(row)

	grouped_orders = []
	used_groups = OrderedDict()
	for source in orders:
		name = _value(source, "name")
		item = _value(source, "item")
		attribute_details = item_attributes.get(item) or {}
		primary_attribute = attribute_details.get("primary_attribute") or "Size"
		qty = defaultdict(float)
		for detail in details_by_parent.get(name, []):
			attrs = _attributes(_value(detail, "attributes_json"))
			primary_value = attrs.get(primary_attribute) or attrs.get("Size") or _value(detail, "primary_value")
			if primary_value not in (None, ""):
				qty[str(primary_value)] += flt(_value(detail, "quantity"))

		configured_values = list(attribute_details.get("primary_attribute_values") or [])
		values = configured_values or list(qty)
		group = _matched_size_group(values, size_types)
		group_key = (group["label"], tuple(group["sizes"]))
		used_groups.setdefault(group_key, group)
		total = sum(qty.values())
		status = _value(source, "status") or ({0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(int(_value(source, "docstatus") or 0), ""))
		transfer_movements = group_transfer_movements(transfer_history_by_order.get(name, []))
		comments = "\n".join(
			value for value in [str(_value(source, "comments") or "").strip(), str(_value(source, "comment_log") or "").strip()] if value
		)
		grouped_orders.append(
			{
				"name": name,
				"item": item,
				"fabric": _value(source, "fabric") or "",
				"dia": _value(source, "dia") or "",
				"gsm": flt(_value(source, "gsm")),
				"production_detail": _value(source, "production_detail") or "",
				"production_term": _value(source, "production_term") or "",
				"posting_date": _date(_value(source, "posting_date")),
				"delivery_date": _date(_value(source, "delivery_date")),
				"dont_deliver_after": _date(_value(source, "dont_deliver_after")),
				"lead_time": int(_value(source, "lead_time_given") or 0),
				"status": status,
				"comments": comments,
				"transfer_movements": transfer_movements,
				"transfer_summary": "\n".join(row["detail_summary"] for row in transfer_movements),
				"group_label": group["label"],
				"group_sizes": group["sizes"],
				"qty": dict(qty),
				"total": total,
			}
		)

	groups = list(used_groups.values())
	max_columns = max((len(group["sizes"]) for group in groups), default=0)
	for order in grouped_orders:
		order["qty_by_position"] = [
			order["qty"].get(order["group_sizes"][index], 0) if index < len(order["group_sizes"]) else 0
			for index in range(max_columns)
		]
		order.pop("qty", None)
	grouped_orders.sort(key=lambda row: (row["delivery_date"], row["name"]))
	return {
		"orders": grouped_orders,
		"size_groups": groups,
		"max_columns": max_columns,
		"summary": {
			"total_orders": len(grouped_orders),
			"total_quantity": sum(order["total"] for order in grouped_orders),
			"size_groups": len(groups),
		},
	}


@frappe.whitelist()
def get_ppo_report(filters=None) -> dict:
	_report_permission()
	filters = _mapping(filters, _("Report filters"))
	query_filters = _order_filters(filters)
	selected_items = normalize_item_filter(filters.get("item"))
	product_category = filters.get("product_category")
	if selected_items and product_category:
		items = frappe.get_all(
			"Item",
			filters={"name": ["in", selected_items], "product_category": product_category},
			pluck="name",
		)
		if not items:
			return empty_report()
		query_filters["item"] = ["in", items]
	elif selected_items:
		query_filters["item"] = ["in", selected_items]
	elif product_category:
		items = frappe.get_all(
			"Item",
			filters={"product_category": product_category},
			pluck="name",
		)
		if not items:
			return empty_report()
		query_filters["item"] = ["in", items]

	orders = frappe.get_all(
		DOCTYPE,
		filters=query_filters,
		fields=list(ORDER_FIELDS),
		order_by="delivery_date asc, name asc",
	)
	if not orders:
		return empty_report()

	names = [_value(row, "name") for row in orders]
	transfer_history_by_order = defaultdict(list)
	for row in frappe.get_all(
		"SD YRP PPO Quantity Transfer History",
		filters={"parent": ["in", names], "parenttype": DOCTYPE},
		fields=[
			"name", "parent", "transfer_reference", "movement", "counterpart_production_order",
			"size", "quantity", "requested_by", "requested_on", "approved_by", "approved_on", "reason", "idx",
		],
		order_by="approved_on asc, idx asc",
	):
		transfer_history_by_order[_value(row, "parent")].append(row)
	details = frappe.get_all(
		"YRP Production Order Detail",
		filters={"parent": ["in", names]},
		fields=["parent", "item_variant", "attributes_json", "quantity", "idx"],
		order_by="parent asc, idx asc",
	)
	item_attributes = {}
	for item in dict.fromkeys(_value(row, "item") for row in orders if _value(row, "item")):
		item_attributes[item] = get_attribute_details(item)
	item_by_order = {_value(row, "name"): _value(row, "item") for row in orders}
	primary_attribute_by_parent = {
		name: (item_attributes.get(item) or {}).get("primary_attribute") or "Size"
		for name, item in item_by_order.items()
	}
	details = attach_variant_primary_values(details, primary_attribute_by_parent)
	return build_report(orders, details, load_size_types(), item_attributes, transfer_history_by_order)


def pivot_dispatch_rows(rows) -> dict:
	grouped = OrderedDict()
	sizes = set()
	for source in rows or []:
		date = _date(_value(source, "date"))
		lot = _value(source, "lot") or ""
		size = str(_value(source, "size") or "Unknown")
		quantity = flt(_value(source, "quantity"))
		key = (date, lot)
		if key not in grouped:
			grouped[key] = {"date": date, "lot": lot, "sizes": {}, "total": 0}
		grouped[key]["sizes"][size] = grouped[key]["sizes"].get(size, 0) + quantity
		grouped[key]["total"] += quantity
		sizes.add(size)
	return {
		"sizes": sorted(sizes),
		"rows": sorted(grouped.values(), key=lambda row: (row["date"], row["lot"])),
	}


def load_dispatch_rows(finishing_plans, lot_by_plan=None) -> list[dict]:
	"""Load both supported F16 dispatch paths using bounded batch queries."""
	if not finishing_plans:
		return []
	lot_by_plan = lot_by_plan or {}
	result = []

	dispatches = frappe.get_all(
		"SD YRP Finishing Plan Dispatch",
		filters={"docstatus": 1, "stock_entry": ["is", "set"]},
		fields=["name", "stock_entry"],
	)
	dispatch_names = [_value(row, "name") for row in dispatches]
	if dispatch_names:
		children = frappe.get_all(
			"SD YRP Finishing Plan Dispatch Item",
			filters={"parent": ["in", dispatch_names], "against_id": ["in", finishing_plans]},
			fields=["parent", "against_id", "lot", "item_variant", "quantity"],
		)
		stock_by_dispatch = {_value(row, "name"): _value(row, "stock_entry") for row in dispatches}
		stock_names = [name for name in stock_by_dispatch.values() if name]
		stock_dates = {
			_value(row, "name"): _value(row, "posting_date")
			for row in frappe.get_all(
				"YRP Stock Entry",
				filters={"name": ["in", stock_names], "docstatus": 1, "purpose": "Material Issue"},
				fields=["name", "posting_date"],
			)
		} if stock_names else {}
		for row in children:
			stock_entry = stock_by_dispatch.get(_value(row, "parent"))
			if stock_entry not in stock_dates:
				continue
			result.append(
				{
					"plan": _value(row, "against_id"),
					"date": stock_dates[stock_entry],
					"lot": _value(row, "lot") or lot_by_plan.get(_value(row, "against_id"), ""),
					"item_variant": _value(row, "item_variant"),
					"quantity": _value(row, "quantity"),
				}
			)

	direct_entries = frappe.get_all(
		"YRP Stock Entry",
		filters={
			"against": "SD YRP Finishing Plan",
			"against_id": ["in", finishing_plans],
			"purpose": "Material Issue",
			"docstatus": 1,
		},
		fields=["name", "against_id", "posting_date"],
	)
	direct_names = [_value(row, "name") for row in direct_entries]
	if direct_names:
		entry_by_name = {_value(row, "name"): row for row in direct_entries}
		for row in frappe.get_all(
			"YRP Stock Entry Detail",
			filters={"parent": ["in", direct_names]},
			fields=["parent", "item", "qty"],
		):
			entry = entry_by_name.get(_value(row, "parent")) or {}
			plan = _value(entry, "against_id")
			result.append(
				{
					"plan": plan,
					"date": _value(entry, "posting_date"),
					"lot": lot_by_plan.get(plan, ""),
					"item_variant": _value(row, "item"),
					"quantity": _value(row, "qty"),
				}
			)

	variant_sizes = {}
	for variant in dict.fromkeys(row.get("item_variant") for row in result if row.get("item_variant")):
		attributes = get_variant_attr_details(variant)
		variant_sizes[variant] = attributes.get("Size") or next(iter(attributes.values()), "Unknown")
	for row in result:
		row["size"] = variant_sizes.get(row.get("item_variant"), "Unknown")
	return result


@frappe.whitelist()
def get_ppo_dispatch_summary(production_order: str) -> dict:
	_report_permission()
	lots = frappe.get_all(
		"SD YRP Lot",
		filters={"production_order": production_order},
		pluck="name",
	)
	if not lots:
		return {"sizes": [], "rows": []}
	plans = frappe.get_all(
		"SD YRP Finishing Plan",
		filters={"lot": ["in", lots]},
		fields=["name", "lot"],
	)
	plan_names = [_value(row, "name", row if isinstance(row, str) else None) for row in plans]
	plan_names = [name for name in plan_names if name]
	if not plan_names:
		return {"sizes": [], "rows": []}
	lot_by_plan = {
		_value(row, "name"): _value(row, "lot")
		for row in plans
		if not isinstance(row, str)
	}
	return pivot_dispatch_rows(load_dispatch_rows(plan_names, lot_by_plan))


@frappe.whitelist()
def get_ppo_dispatch_summary_bulk(production_orders) -> dict:
	"""Return dispatch summaries for many PPOs with one bounded batch load."""
	_report_permission()
	production_orders = normalize_item_filter(production_orders)
	result = {name: {"sizes": [], "rows": []} for name in production_orders}
	if not production_orders:
		return result
	lots = frappe.get_all(
		"SD YRP Lot",
		filters={"production_order": ["in", production_orders]},
		fields=["name", "production_order"],
	)
	lot_to_order = {_value(row, "name"): _value(row, "production_order") for row in lots}
	if not lot_to_order:
		return result
	plans = frappe.get_all(
		"SD YRP Finishing Plan",
		filters={"lot": ["in", list(lot_to_order)]},
		fields=["name", "lot"],
	)
	plan_to_order = {
		_value(row, "name"): lot_to_order.get(_value(row, "lot"))
		for row in plans
		if lot_to_order.get(_value(row, "lot"))
	}
	if not plan_to_order:
		return result
	lot_by_plan = {_value(row, "name"): _value(row, "lot") for row in plans}
	rows_by_order = defaultdict(list)
	for row in load_dispatch_rows(list(plan_to_order), lot_by_plan):
		production_order = plan_to_order.get(_value(row, "plan"))
		if production_order:
			rows_by_order[production_order].append(row)
	for production_order in production_orders:
		result[production_order] = pivot_dispatch_rows(rows_by_order.get(production_order, []))
	return result


def _xlsx_rows(report: Mapping) -> list[list]:
	orders = report.get("orders") or []
	max_columns = int(report.get("max_columns") or 0)
	rows = []
	for group in report.get("size_groups") or []:
		rows.append(
			["", "", "", "", "", "", "", "", "", "", "", group.get("label") or ""]
			+ [(group.get("sizes") or [])[index] if index < len(group.get("sizes") or []) else "" for index in range(max_columns)]
			+ ["", "", ""]
		)
	rows.append(
		["#", "PPO", "Item", "Fabric", "Dia", "GSM", "Posting Date", "Delivery Date", "Don't Deliver After", "Lead Time", "Status", "Size Group"]
		+ [""] * max_columns
		+ ["Total", "Quantity Transfer", "Comments"]
	)
	for index, order in enumerate(orders, 1):
		rows.append(
			[
				index,
				order.get("name"),
				order.get("item"),
				order.get("fabric"),
				order.get("dia"),
				order.get("gsm"),
				order.get("posting_date"),
				order.get("delivery_date"),
				order.get("dont_deliver_after"),
				order.get("lead_time"),
				order.get("status"),
				order.get("group_label"),
			]
			+ [value or "" for value in order.get("qty_by_position") or []]
			+ [order.get("total") or 0, order.get("transfer_summary") or "", order.get("comments") or ""]
		)
	footer = [""] * 11 + ["Total"]
	footer.extend(
		sum(flt(order.get("qty_by_position", [])[index]) for order in orders if index < len(order.get("qty_by_position") or [])) or ""
		for index in range(max_columns)
	)
	footer.extend([sum(flt(order.get("total")) for order in orders), "", ""])
	rows.append(footer)
	return rows


@frappe.whitelist()
def download_ppo_report(from_date=None, to_date=None, product_category=None, status=None, item=None):
	_report_permission()
	report = get_ppo_report(
		{
			"from_date": from_date,
			"to_date": to_date,
			"product_category": product_category,
			"status": status,
			"item": item,
		}
	)
	xlsx_file = make_xlsx(_xlsx_rows(report), "PPO Report")
	timestamp = now_datetime().strftime("%d-%m-%Y_%H-%M-%S")
	frappe.response["filename"] = f"PPO_Report_{timestamp}.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"

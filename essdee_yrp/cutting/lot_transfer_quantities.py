"""Quantity-only editing for draft balance-cloth Lot Transfers raised from a Cutting Plan."""

from __future__ import annotations

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, flt

LOT_TRANSFER_DOCTYPE = "SD YRP Lot Transfer"
PRECISION = 3


def get_plan_cloth_balances(plan):
	balances = defaultdict(float)
	labels = {}
	for row in plan.get("cutting_plan_cloth_details") or []:
		if not row.cloth_item_variant:
			continue
		balances[row.cloth_item_variant] = flt(
			balances[row.cloth_item_variant] + flt(row.balance_weight, PRECISION), PRECISION
		)
		labels.setdefault(
			row.cloth_item_variant,
			" · ".join(
				cstr(value).strip()
				for value in (row.cloth_type, row.cloth_item_variant)
				if cstr(value).strip()
			),
		)
	return balances, labels


def get_quantity_rows(plan, doc):
	"""Editable rows when every item is balance cloth of this plan's Lot, else None."""
	if doc.doctype != LOT_TRANSFER_DOCTYPE or doc.docstatus != 0:
		return None
	if not frappe.has_permission(doc.doctype, "write", doc=doc):
		return None
	balances, labels = get_plan_cloth_balances(plan)
	rows = []
	for row in doc.get("items") or []:
		if row.from_lot != plan.lot or row.item not in balances:
			return None
		rows.append(
			{
				"name": row.name,
				"item": row.item,
				"label": labels.get(row.item) or row.item,
				"from_lot": row.from_lot,
				"to_lot": row.to_lot,
				"uom": row.uom,
				"qty": flt(row.qty, PRECISION),
				"available": balances[row.item],
			}
		)
	return rows or None


def parse_requested_quantities(rows, known_names):
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	requested = {}
	for row in rows or []:
		name = (row or {}).get("name")
		if name not in known_names:
			frappe.throw(_("Row {0} does not belong to this Lot Transfer.").format(name))
		if name in requested:
			frappe.throw(_("Row {0} was sent more than once.").format(name))
		qty = flt(row.get("qty"), PRECISION)
		if qty <= 0:
			frappe.throw(_("Quantity must be greater than zero. Delete the row to skip it."))
		requested[name] = qty
	if not requested:
		frappe.throw(_("Keep at least one row. Delete the Lot Transfer to transfer nothing."))
	return requested


def validate_against_balance(editable_rows, requested):
	totals = defaultdict(float)
	for row in editable_rows:
		if row["name"] in requested:
			totals[row["item"]] += requested[row["name"]]
	for row in editable_rows:
		total = flt(totals.get(row["item"]), PRECISION)
		if total > row["available"]:
			frappe.throw(
				_("{0}: quantity {1} is more than the available balance {2}.").format(
					row["label"], total, row["available"]
				)
			)


def apply_quantities(plan, doc, rows):
	if doc.doctype != LOT_TRANSFER_DOCTYPE:
		frappe.throw(_("Only Lot Transfer quantities can be changed here."))
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a Draft Lot Transfer quantity can be changed."))
	editable_rows = get_quantity_rows(plan, doc)
	if not editable_rows:
		frappe.throw(_("This Lot Transfer does not move this Cutting Plan's balance cloth."))
	requested = parse_requested_quantities(rows, {row["name"] for row in editable_rows})
	validate_against_balance(editable_rows, requested)
	kept = [row for row in doc.items if row.name in requested]
	for index, row in enumerate(kept, start=1):
		row.qty = requested[row.name]
		row.idx = index
	doc.set("items", kept)
	doc.save()
	return doc

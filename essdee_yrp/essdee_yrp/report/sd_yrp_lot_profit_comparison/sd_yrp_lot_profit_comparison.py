"""Source-compatible migrated lot profit comparison report."""

import frappe
from frappe import _


def get_columns1():
	return [
		{
			"fieldname": "item",
			"label": "Item",
			"fieldtype": "Link",
			"options": "SD YRP FG Item Master",
			"width": 250,
		},
		{"fieldname": "lot", "label": "Lot", "fieldtype": "Link", "options": "SD YRP Lot", "width": 150},
		{"fieldname": "Costing_qty", "label": "Costing Qty", "fieldtype": "Float", "width": 100},
		{"fieldname": "Costing_profit", "label": "Costing Profit %", "fieldtype": "Float", "width": 100},
		{"fieldname": "Planned Qty_qty", "label": "Planned Qty", "fieldtype": "Float", "width": 100},
		{"fieldname": "Planned Qty_profit", "label": "Planned Profit %", "fieldtype": "Float", "width": 100},
		{"fieldname": "Cutting Qty_qty", "label": "Cutting Qty", "fieldtype": "Float", "width": 100},
		{"fieldname": "Cutting Qty_profit", "label": "Cutting Profit %", "fieldtype": "Float", "width": 100},
		{"fieldname": "Final Qty_qty", "label": "Final Qty", "fieldtype": "Float", "width": 100},
		{"fieldname": "Final Qty_profit", "label": "Final Profit %", "fieldtype": "Float", "width": 100},
	]


def execute(filters=None):
	return get_columns1(), get_data(frappe._dict(filters or {}))


def get_data(filters):
	conditions = []
	for field in ("lot", "item"):
		if filters.get(field):
			conditions.append(f"{field} = %({field})s")
	if filters.get("from_date") and filters.get("to_date"):
		# MRP's Python `and` drops the lower bound; preserve historical parity.
		conditions.append("creation <= %(to_date)s")
	where = "WHERE " + " AND ".join(conditions) if conditions else ""
	entries = frappe.db.sql(
		f"""SELECT name, item, lot, lot_costing_type, total_qty,
			profit_percent_markdown, creation
		FROM `tabSD YRP Lotwise Item Profit` {where}
		ORDER BY item, creation DESC""",
		filters,
		as_dict=True,
	)
	return combine_revisions(entries)


def combine_revisions(entries):
	"""Interleave newest revisions of each costing type within an item/lot."""
	groups = {}
	for entry in entries:
		groups.setdefault(entry.item, {}).setdefault(entry.lot, []).append(entry)
	data = []
	for lots in groups.values():
		for revisions in lots.values():
			rows = []
			for entry in revisions:
				kind = entry.lot_costing_type
				for row in rows:
					if f"{kind}_profit" not in row:
						break
				else:
					row = dict(entry)
					rows.append(row)
				row.update(
					{
						f"{kind}_profit": entry.profit_percent_markdown,
						f"{kind}_qty": entry.total_qty,
						f"{kind}_name": entry.name,
					}
				)
			data.extend(rows)
	return data

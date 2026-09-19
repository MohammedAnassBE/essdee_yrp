"""Stock Entry actions owned by the Essdee workflow."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime


def _row_dict(row):
	as_dict = getattr(row, "as_dict", None)
	return frappe._dict(as_dict() if callable(as_dict) else dict(row))


def _matching_deliverables(stock_row, deliverables, production_dimensions):
	item_matches = [
		row for row in deliverables if row.get("item_variant") == stock_row.get("item")
	]
	if not item_matches:
		return []

	if (
		stock_row.get("against") == "Work Order Deliverables"
		and stock_row.get("against_id_detail")
	):
		exact = [
			row for row in item_matches
			if row.get("name") == stock_row.get("against_id_detail")
		]
		if exact:
			return exact

	dimension_matches = []
	for row in item_matches:
		matches = True
		for fieldname in production_dimensions:
			stock_value = stock_row.get(fieldname)
			target_value = row.get(fieldname)
			if stock_value and target_value and stock_value != target_value:
				matches = False
				break
		if matches:
			dimension_matches.append(row)
	return dimension_matches


def _delivery_row(stock_row, target, quantity, dimension_fields):
	stock_quantity = flt(stock_row.get("qty"))
	secondary_quantity = 0
	if stock_quantity:
		secondary_quantity = flt(stock_row.get("secondary_qty")) * flt(quantity) / stock_quantity

	row = {
		"item_variant": stock_row.get("item"),
		"qty": flt(quantity),
		"delivered_quantity": flt(quantity),
		"uom": target.get("uom") or stock_row.get("uom"),
		"secondary_qty": flt(secondary_quantity, 3),
		"secondary_uom": stock_row.get("secondary_uom") or target.get("secondary_uom"),
		"pending_quantity": flt(target.get("pending_quantity")),
		"ref_doctype": "Work Order Deliverables",
		"ref_docname": target.get("name"),
		"table_index": target.get("table_index"),
		"row_index": target.get("row_index"),
		"set_combination": target.get("set_combination"),
		"comments": stock_row.get("remarks"),
	}
	for fieldname in dimension_fields:
		if stock_row.get(fieldname):
			row[fieldname] = stock_row.get(fieldname)
	return row


def build_delivery_rows(stock_rows, work_order, dimension_fields, production_dimensions):
	"""Map Stock Entry quantities to exact Work Order Deliverable rows."""
	deliverables = [_row_dict(row) for row in work_order.get("deliverables") or []]
	available_by_deliverable = {
		row.get("name") or id(row): max(flt(row.get("pending_quantity")), 0)
		for row in deliverables
	}
	rows = []
	for raw_stock_row in stock_rows or []:
		stock_row = _row_dict(raw_stock_row)
		quantity = flt(stock_row.get("qty"))
		if quantity <= 0:
			continue

		for fieldname in production_dimensions:
			stock_value = stock_row.get(fieldname)
			work_order_value = work_order.get(fieldname)
			if stock_value and work_order_value and stock_value != work_order_value:
				frappe.throw(
					_("Stock Entry item {0} belongs to {1}, but Work Order {2} belongs to {3}.").format(
						stock_row.get("item"), stock_value, work_order.name, work_order_value
					)
				)

		matches = _matching_deliverables(stock_row, deliverables, production_dimensions)
		if not matches:
			frappe.throw(
				_("Stock Entry item {0} is not a deliverable of Work Order {1}.").format(
					stock_row.get("item"), work_order.name
				)
			)

		stock_uom = stock_row.get("uom")
		for target in matches:
			if stock_uom and target.get("uom") and stock_uom != target.get("uom"):
				frappe.throw(
					_("UOM mismatch for {0}: Stock Entry uses {1}, but Work Order uses {2}.").format(
						stock_row.get("item"), stock_uom, target.get("uom")
					)
				)

		remaining = quantity
		created_indexes = []
		for target in matches:
			target_key = target.get("name") or id(target)
			available = available_by_deliverable[target_key]
			allocated = min(remaining, available)
			if allocated <= 0:
				continue
			rows.append(_delivery_row(stock_row, target, allocated, dimension_fields))
			created_indexes.append(len(rows) - 1)
			available_by_deliverable[target_key] -= allocated
			remaining -= allocated
			if remaining <= 0:
				break

		# YRP permits an excess DC against a fully delivered WO. Preserve that
		# contract by assigning any quantity above pending to the first matching
		# deliverable, just as Production API's Lot Transfer → DC flow does.
		if remaining > 0:
			if created_indexes:
				row = rows[created_indexes[0]]
				row["qty"] = flt(row["qty"]) + remaining
				row["delivered_quantity"] = row["qty"]
				if flt(stock_row.get("secondary_qty")) and quantity:
					row["secondary_qty"] = flt(
						flt(stock_row.get("secondary_qty")) * flt(row["qty"]) / quantity,
						3,
					)
			else:
				rows.append(_delivery_row(stock_row, matches[0], remaining, dimension_fields))

	if not rows:
		frappe.throw(_("Stock Entry has no positive quantity to make a Delivery Challan."))
	return rows


def _warehouse_for_location(location, stock_entry):
	preferred = []
	if stock_entry.get("from_supplier") == location and stock_entry.get("from_warehouse"):
		preferred.append(stock_entry.from_warehouse)
	if stock_entry.get("to_supplier") == location and stock_entry.get("to_warehouse"):
		preferred.append(stock_entry.to_warehouse)

	for warehouse in preferred:
		if frappe.db.exists(
			"Warehouse",
			{"name": warehouse, "supplier": location, "disabled": 0},
		):
			return warehouse

	warehouses = frappe.get_all(
		"Warehouse",
		filters={"supplier": location, "disabled": 0},
		pluck="name",
		order_by="name asc",
	)
	if not warehouses:
		frappe.throw(_("No enabled Warehouse is configured for location {0}.").format(location))
	if len(warehouses) > 1:
		frappe.throw(
			_("Location {0} has multiple enabled Warehouses; use a Stock Entry location with one clear Warehouse.").format(
				location
			)
		)
	return warehouses[0]


def _validate_location(location, label):
	if not location or not frappe.db.exists("Supplier", {"name": location, "disabled": 0}):
		frappe.throw(_("Select a valid {0}.").format(label))


@frappe.whitelist()
def make_delivery_challan(stock_entry, work_order, from_location, to_location):
	"""Create a draft DC from a submitted Stock Entry and redirect-ready name."""
	frappe.has_permission("Delivery Challan", "create", throw=True)

	entry = frappe.get_doc("Stock Entry", stock_entry)
	entry.check_permission("read")
	if entry.docstatus != 1:
		frappe.throw(_("Submit Stock Entry {0} before making a Delivery Challan.").format(entry.name))

	order = frappe.get_doc("Work Order", work_order)
	order.check_permission("read")
	if order.docstatus != 1 or order.open_status != "Open" or order.is_delivered:
		frappe.throw(_("Select an open, submitted Work Order that is not fully delivered."))

	_validate_location(from_location, _("From Location"))
	_validate_location(to_location, _("To Location"))

	from yrp.stock.dimensions import get_dimension_fieldnames, get_stock_dimensions

	dimension_fields = get_dimension_fieldnames()
	production_dimensions = [
		dimension["fieldname"]
		for dimension in get_stock_dimensions()
		if dimension.get("is_production_group")
	]
	rows = build_delivery_rows(
		entry.get("items") or [],
		order,
		dimension_fields,
		production_dimensions,
	)

	from_warehouse = _warehouse_for_location(from_location, entry)
	to_warehouse = _warehouse_for_location(to_location, entry)

	delivery_challan = frappe.new_doc("Delivery Challan")
	delivery_challan.update(
		{
			"work_order": order.name,
			"posting_date": nowdate(),
			"posting_time": nowtime(),
			"from_location": from_location,
			"supplier": to_location,
			"from_warehouse": from_warehouse,
			"to_warehouse": to_warehouse,
			"comments": _("Created from Stock Entry {0}").format(entry.name),
		}
	)
	for row in rows:
		delivery_challan.append("items", row)
	delivery_challan.insert()
	return {"name": delivery_challan.name}

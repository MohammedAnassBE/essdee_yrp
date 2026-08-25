# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import math
from itertools import zip_longest

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, getdate, nowdate


class BoxStickerPrint(Document):
	def before_validate(self):
		total = sum(row.quantity or 0 for row in self.box_sticker_print_details)
		if total == 0 and not any(
			row.allow_excess_quantity for row in self.box_sticker_print_details
		):
			frappe.throw(_("Enter the quantity"))


@frappe.whitelist()
def get_fg_details(fg_item, lot=None):
	frappe.get_doc("FG Item Master", fg_item).check_permission("read")
	sizes, mrp = frappe.db.get_value(
		"FG Item Master", fg_item, ["available_sizes", "mrp"]
	) or ("", "")
	sizes = (sizes or "").split(",")
	result = []
	if not mrp:
		previous = frappe.get_list(
			"Box Sticker Print",
			filters={"fg_item": fg_item},
			order_by="creation desc",
			pluck="name",
			limit=1,
		)
		if previous:
			doc = frappe.get_doc("Box Sticker Print", previous[0])
			doc.check_permission("read")
			return [{"size": row.size, "mrp": row.mrp} for row in doc.box_sticker_print_details]
		mrp = ""
	prices = mrp.split(",")
	for size, price in zip_longest(sizes, prices, fillvalue=None):
		result.append({"size": size, "mrp": price})
	return result


@frappe.whitelist()
def get_print_format(doc, print_items, printer_type):
	doc = frappe.get_doc("Box Sticker Print", doc)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the Box Sticker Print before printing"))
	_lock_linked_production_order(doc.lot)
	print_format = frappe.get_doc("ZPL Raw Print Format", doc.print_format)
	print_format.check_permission("read")
	raw_code = _raw_code(print_format, printer_type)
	label_count = int(print_format.labels_per_row or 0)
	if label_count <= 0:
		frappe.throw(_("Labels Per Row must be greater than zero"))
	items = frappe.parse_json(print_items) if isinstance(print_items, str) else print_items
	prepared = []
	for item in items or []:
		quantity = int(item.get("quantity") or 0)
		if quantity <= 0:
			continue
		row = frappe.db.sql(
			"""
				SELECT parent, size, mrp, printed_quantity, quantity,
					allow_excess_quantity, allow_excess_percentage
				FROM `tabBox Sticker Print Detail`
				WHERE name = %s
				FOR UPDATE
			""",
			(item.get("doc_name"),),
			as_dict=True,
		)
		if not row or row[0].parent != doc.name:
			frappe.throw(_("Invalid Box Sticker Print detail"))
		row = row[0]
		printed = int(row.printed_quantity or 0)
		allowed = int(row.quantity or 0)
		requested_total = printed + quantity
		if requested_total > allowed and not row.allow_excess_quantity:
			allowed += int(
				math.ceil(allowed * int(row.allow_excess_percentage or 0) / 100)
			)
			if requested_total > allowed:
				frappe.throw(_("Not applicable to print more than the required quantity"))
		labels = int(math.ceil(quantity / label_count))
		item = dict(item)
		item["size"] = doc.size or row.size
		item["mrp"] = row.mrp
		prepared.append((item, printed, labels))

	templates = ""
	for item, printed, labels in prepared:
		templates += get_template(
			doc, item, raw_code, label_count, doc.fg_item
		)
		frappe.db.set_value(
			"Box Sticker Print Detail",
			item["doc_name"],
			"printed_quantity",
			printed + labels * label_count,
		)
	return templates


def get_template(doc, item, raw_code, label_count, fg_item):
	box_mrp = "{:.2f}".format((doc.piece_per_box or 0) * float(item["mrp"]))
	mrp = "{:.2f}".format(float(item["mrp"]))
	print_quantity = int(math.ceil(int(item["quantity"]) / int(label_count)))
	date = getdate(add_to_date(nowdate(), days=15))
	months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
	mfd_year = f"{months[date.month - 1]}/{date.year}"
	if not doc.use_item_name:
		fg_item = frappe.db.get_value("FG Item Master", fg_item, "display_name") or fg_item
	return frappe.render_template(
		raw_code,
		{
			"print_quantity": print_quantity,
			"item_name": fg_item,
			"piece_price": mrp,
			"box_price": box_mrp,
			"piece_size": item["size"],
			"mfdate": f"{mfd_year}/{doc.lot}",
			"mfdateyear": mfd_year,
			"dpi": 203,
		},
	)


@frappe.whitelist()
def override_print_quantity(print_items, print_format):
	items = frappe.parse_json(print_items) if isinstance(print_items, str) else print_items
	format_doc = frappe.get_doc("ZPL Raw Print Format", print_format)
	format_doc.check_permission("read")
	label_count = int(format_doc.labels_per_row or 0)
	if label_count <= 0:
		frappe.throw(_("Labels Per Row must be greater than zero"))
	for item in sorted(items or [], key=lambda value: value.get("doc_name") or ""):
		row = frappe.db.sql(
			"""
				SELECT d.printed_quantity, d.parent
				FROM `tabBox Sticker Print Detail` d
				WHERE d.name = %s
				FOR UPDATE
			""",
			(item.get("doc_name"),),
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Invalid Box Sticker Print detail"))
		parent = frappe.get_doc("Box Sticker Print", row[0].parent)
		parent.check_permission("write")
		_lock_linked_production_order(parent.lot)
		labels = int(math.ceil(int(item.get("quantity") or 0) / label_count))
		new_quantity = int(row[0].printed_quantity or 0) - labels * label_count
		if new_quantity < 0:
			frappe.throw(_("Printed quantity cannot be negative"))
		frappe.db.set_value(
			"Box Sticker Print Detail",
			item["doc_name"],
			"printed_quantity",
			new_quantity,
		)


@frappe.whitelist()
def get_raw_code(doc_name):
	doc = frappe.get_doc("Box Sticker Print", doc_name)
	doc.check_permission("read")
	print_format = frappe.get_doc("ZPL Raw Print Format", doc.print_format)
	print_format.check_permission("read")
	if not doc.box_sticker_print_details:
		frappe.throw(_("Add at least one Box Sticker Print row"))
	item = doc.box_sticker_print_details[0].as_dict()
	item.quantity = 1
	item.size = doc.size or item.size
	return {
		"code": get_template(
			doc,
			item,
			_raw_code(print_format, "300dpi"),
			print_format.labels_per_row,
			doc.fg_item,
		),
		"height": print_format.height,
		"width": print_format.width,
	}


@frappe.whitelist()
def get_printer(printers):
	available = frappe.parse_json(printers) if isinstance(printers, str) else printers
	configured = frappe.db.get_single_value("MRP Settings", "printer_list")
	if not configured:
		return available
	allowed = {printer.strip() for printer in configured.split(",") if printer.strip()}
	return [printer for printer in available or [] if printer in allowed]


def _raw_code(print_format, printer_type):
	for row in print_format.zpl_raw_print_format_details:
		if row.printer_type == printer_type:
			return row.raw_code
	frappe.throw(_("Print Format resolution {0} is not defined").format(printer_type))


def _lock_linked_production_order(lot):
	production_order = frappe.db.get_value("Lot", lot, "production_order")
	if production_order:
		from essdee_yrp.production_order_alternative import _lock_production_orders

		_lock_production_orders(production_order)

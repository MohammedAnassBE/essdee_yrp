# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import math

import frappe
from frappe import _
from frappe.model.document import Document


class SalesPieceStickerPrint(Document):
	pass


@frappe.whitelist()
def get_print_format(doc_name: str | None = None) -> str:
	doc = frappe.get_single("Sales Piece Sticker Print")
	doc.check_permission("read")
	print_format = frappe.get_doc("ZPL Raw Print Format", doc.print_format)
	print_format.check_permission("read")
	resolution = "200dpi" if doc.brand == "Essdee" else "300dpi"
	raw_code = next(
		(
			row.raw_code
			for row in print_format.zpl_raw_print_format_details
			if row.printer_type == resolution
		),
		None,
	)
	if not raw_code:
		frappe.throw(
			_("Print Format resolution {0} is not defined.").format(resolution)
		)
	label_count = int(print_format.labels_per_row or 0)
	if label_count <= 0:
		frappe.throw(_("Labels Per Row must be greater than zero."))
	return "".join(
		get_template(row, raw_code, label_count, doc.brand)
		for row in doc.sales_piece_sticker_print_details
		if int(row.quantity or 0) > 0
	)


def get_template(item, raw_code: str, label_count: int, brand: str) -> str:
	return frappe.render_template(
		raw_code,
		{
			"print_quantity": int(math.ceil(float(item.quantity) / label_count)),
			"mrp_price": f"{float(item.mrp_price or 0):.2f}",
			"offer_price": f"{float(item.offer_price or 0):.2f}",
			"sku": str(item.sku or ""),
			"dpi": 203,
			"brand": brand,
		},
	)

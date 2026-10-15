# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, get_url

PRODUCT_IMAGE = "SD YRP Product Image"


class SDYRPProductImage(Document):
	pass


def duplicate_title_message(title: str) -> str:
	return _("Product Image \"{0}\" already exists. Pick it from the library instead.").format(title)


def insert_product_image(image_title: str, title_header: str):
	image_title = cstr(image_title).strip()
	if not image_title:
		frappe.throw(_("Image Title is required."))
	if frappe.db.exists(PRODUCT_IMAGE, image_title):
		frappe.throw(duplicate_title_message(image_title), frappe.DuplicateEntryError)
	try:
		return frappe.get_doc(
			{"doctype": PRODUCT_IMAGE, "image_title": image_title, "title_header": title_header}
		).insert()
	except frappe.DuplicateEntryError:
		frappe.throw(duplicate_title_message(image_title), frappe.DuplicateEntryError)


@frappe.whitelist()
def create_product_image(image_title: str, title_header: str) -> dict:
	frappe.has_permission(PRODUCT_IMAGE, "create", throw=True)
	if not cstr(title_header).strip():
		frappe.throw(_("Title Header is required."))
	doc = insert_product_image(image_title, title_header)
	return {
		"name": doc.name,
		"image_title": doc.image_title,
		"title_header": doc.title_header,
	}


@frappe.whitelist()
def get_image_list(query: str = "") -> list[dict]:
	"""Return only Product Images the session user can read."""

	query = cstr(query).strip()
	records = frappe.get_list(
		PRODUCT_IMAGE,
		filters={"name": ["like", f"%{query}%"]},
		fields=["name", "image", "title_header"],
		order_by="modified desc",
		limit=50,
	)
	return [
		{
			"image_url": get_url(row.image) if row.image else "",
			"image_title": row.title_header,
			"image_name": row.name,
		}
		for row in records
	]


ProductImage = SDYRPProductImage

# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cstr, get_url


class ProductImage(Document):
	pass


@frappe.whitelist()
def get_image_list(query: str = "") -> list[dict]:
	"""Return only Product Images the session user can read."""

	query = cstr(query).strip()
	records = frappe.get_list(
		"Product Image",
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

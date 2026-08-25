# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FGItemSizeRange(Document):
	def validate(self):
		if not self.uid:
			frappe.throw(_("UID is required."))


def get_sizes(size_range: str) -> list[str]:
	doc = frappe.get_doc("FG Item Size Range", size_range)
	doc.check_permission("read")
	return [row.attribute_value for row in doc.sizes if row.attribute_value]

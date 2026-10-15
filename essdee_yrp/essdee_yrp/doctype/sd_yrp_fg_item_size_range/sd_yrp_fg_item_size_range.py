# Copyright (c) 2023, Essdee and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from yrp.attribute_links import value as _attribute_value


class SDYRPFGItemSizeRange(Document):
	def validate(self):
		from essdee_yrp.product_sales import size_value_domains, validate_range_rows
		coverage=None
		if self.get('size_type'):
			type_doc=frappe.get_doc('SD YRP FG Item Size Type',self.size_type)
			coverage={r.size_type_value for r in type_doc.fg_item_size_type_details}
		try:
			validate_range_rows(self.sizes,size_value_domains({r.attribute_value for r in self.sizes}),coverage)
		except ValueError as exc:
			frappe.throw(str(exc))
		if not self.uid:
			frappe.throw(_("UID is required."))


def get_sizes(size_range: str) -> list[str]:
	doc = frappe.get_doc("SD YRP FG Item Size Range", size_range)
	doc.check_permission("read")
	return [
		_attribute_value(row.attribute_value) for row in doc.sizes if _attribute_value(row.attribute_value)
	]


FGItemSizeRange = SDYRPFGItemSizeRange

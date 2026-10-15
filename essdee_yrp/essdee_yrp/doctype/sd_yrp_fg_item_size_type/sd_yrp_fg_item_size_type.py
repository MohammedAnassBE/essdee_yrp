# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SDYRPFGItemSizeType(Document):
	def validate(self):
		from essdee_yrp.product_sales import size_value_domains, validate_slot_rows
		rows=self.fg_item_size_type_details
		try:
			validate_slot_rows(rows,size_value_domains({r.size_type_value for r in rows}))
		except ValueError as exc:
			frappe.throw(str(exc))


FGItemSizeType = SDYRPFGItemSizeType

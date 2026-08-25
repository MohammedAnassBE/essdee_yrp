# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from essdee_yrp.sewing.config import validate_sewing_input_orders


class MRPSettings(Document):
	def validate(self):
		validate_sewing_input_orders(self.sewing_plan_input_orders)

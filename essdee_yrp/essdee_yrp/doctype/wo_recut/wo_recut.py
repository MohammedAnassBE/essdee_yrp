# Copyright (c) 2026, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from yrp.stock.save_stock_items import group_items_for_ui, ungroup_items_from_ui
from yrp.utils import update_if_string_instance


class WORecut(Document):
	def onload(self):
		if not self.is_new():
			self.set_onload(
				"recut_item_details",
				group_items_for_ui(
					self.get("wo_recut_details") or [], "Work Order Deliverables"
				),
			)

	def before_validate(self):
		if self.docstatus == 1 or not self.get("recut_item_details"):
			return
		grouped = update_if_string_instance(self.recut_item_details)
		rows = ungroup_items_from_ui(grouped, "Work Order Deliverables")
		self.set(
			"wo_recut_details",
			[
				{
					"item_variant": row["item_variant"],
					"quantity": row["qty"],
					"table_index": row["table_index"],
					"row_index": row["row_index"],
				}
				for row in rows
			],
		)

	def validate(self):
		work_order = frappe.get_doc("Work Order", self.work_order)
		work_order.check_permission("read")
		if work_order.docstatus != 1 or work_order.open_status != "Open":
			frappe.throw(
				_("Work Order {0} must be submitted and open.").format(
					frappe.bold(work_order.name)
				)
			)
		if work_order.get("is_rework"):
			frappe.throw(_("A WO Recut cannot be created from a rework Work Order."))
		if self.lot and self.lot != work_order.lot:
			frappe.throw(_("WO Recut Lot must match Work Order {0}.").format(work_order.name))
		self.lot = work_order.lot
		if self.docstatus == 1 and not any(
			flt(row.quantity) > 0 for row in self.get("wo_recut_details") or []
		):
			frappe.throw(_("Enter a Recut quantity greater than zero."))

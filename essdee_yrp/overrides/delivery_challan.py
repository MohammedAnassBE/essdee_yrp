"""Current-read counter lifecycle for exact-source fabric Delivery Challans."""

import frappe
from frappe import _
from frappe.utils import flt

from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	DeliveryChallan,
	_find_matching_row,
)


class EssdeeDeliveryChallan(DeliveryChallan):
	"""Serialize exact-source validation and pending updates on one WO image."""

	def before_submit(self):
		self._lock_exact_source_work_order()
		super().before_submit()

	def before_cancel(self):
		self._lock_exact_source_work_order()
		super().before_cancel()

	def validate_against_work_order_pending(self):
		wo = self.flags.get("essdee_locked_work_order")
		if not wo:
			return super().validate_against_work_order_pending()
		for row in self.items:
			target = _find_matching_row(
				wo.deliverables, row, "Work Order Deliverables"
			)
			if not target:
				frappe.throw(_(
					"Row {0}: no matching Work Order Deliverable found for {1}."
				).format(row.idx, row.item_variant))
			row.ref_doctype = "Work Order Deliverables"
			row.ref_docname = target.name
			row.pending_quantity = target.pending_quantity

	def update_work_order_deliverables(self, cancel=False):
		wo = self.flags.get("essdee_locked_work_order")
		if not wo:
			return super().update_work_order_deliverables(cancel=cancel)
		changed = False
		for row in self.items:
			target = _find_matching_row(
				wo.deliverables, row, "Work Order Deliverables"
			)
			if not target:
				continue
			qty = flt(row.delivered_quantity or row.qty)
			pending = (
				flt(target.pending_quantity) + qty
				if cancel else flt(target.pending_quantity) - qty
			)
			target.pending_quantity = flt(pending)
			target.db_set("pending_quantity", target.pending_quantity, update_modified=False)
			changed = True
		if changed:
			_update_locked_work_order_status(wo)

	def _lock_exact_source_work_order(self):
		if not self.work_order or not _has_exact_source_rows(self.work_order):
			return
		# for_update=True loads and locks the parent and every child row. Keeping
		# this object on the voucher means validation and on_submit update the
		# same current state after any preceding concurrent DC has committed.
		self.flags.essdee_locked_work_order = frappe.get_doc(
			"Work Order", self.work_order, for_update=True
		)


def _has_exact_source_rows(work_order):
	return bool(frappe.db.sql(
		"""
		SELECT name
		FROM `tabWork Order Deliverables`
		WHERE parent = %s
			AND COALESCE(source_grn_item, '') != ''
		LIMIT 1
		""",
		(work_order,),
	))


def _update_locked_work_order_status(wo):
	wo.set_status()
	wo.db_set("status", wo.status, update_modified=False)
	wo.db_set("is_delivered", wo.is_delivered, update_modified=False)

"""Essdee's mapped Work Order GRN valuation lifecycle.

Essdee owns the fabric/IPD calculation that maps each consumed input to the
exact received GRN row. Base YRP owns the stock posting, actual FIFO/Moving
Average valuation, persisted production lineage, and cancellation reversal.
"""

import frappe
from frappe import _

from essdee_yrp.fabric_grn import (
	apply_work_order_stock_update,
	calculate_consumption_plan,
	is_calculable_fabric_grn,
	load_submitted_consumption_plan,
	populate_grn_deliverables,
)
from yrp.yrp.doctype.goods_received_note.goods_received_note import (
	GoodsReceivedNote,
)


class EssdeeGoodsReceivedNote(GoodsReceivedNote):
	"""Extend only regular Essdee fabric Work Order receipts."""

	def before_submit(self):
		if self._uses_essdee_deliverable_consumption():
			_lock_work_order(self.against_id)
			plan = calculate_consumption_plan(self)
			populate_grn_deliverables(self, plan)
			self.flags.essdee_deliverable_consumption = plan
		super().before_submit()

	def before_cancel(self):
		if self._uses_essdee_deliverable_consumption():
			_lock_work_order(self.against_id)
			if frappe.db.get_value("Work Order", self.against_id, "open_status") == "Close":
				frappe.throw(
					_("Reopen Work Order {0} before cancelling Goods Received Note {1}.").format(
						self.against_id, self.name
					)
				)
			self.flags.essdee_deliverable_consumption = load_submitted_consumption_plan(self)
		super().before_cancel()

	def on_submit(self):
		super().on_submit()
		if self._uses_essdee_deliverable_consumption():
			apply_work_order_stock_update(
				self.against_id,
				self.flags.get("essdee_deliverable_consumption") or [],
			)
		self._enqueue_repost()

	def on_cancel(self):
		super().on_cancel()
		if self._uses_essdee_deliverable_consumption():
			apply_work_order_stock_update(
				self.against_id,
				self.flags.get("essdee_deliverable_consumption") or [],
				cancel=True,
			)
		self._enqueue_repost()

	def _uses_essdee_deliverable_consumption(self):
		return is_calculable_fabric_grn(self)

	def _enqueue_repost(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)


def _lock_work_order(work_order):
	frappe.db.sql(
		"SELECT name FROM `tabWork Order` WHERE name=%s FOR UPDATE",
		(work_order,),
	)

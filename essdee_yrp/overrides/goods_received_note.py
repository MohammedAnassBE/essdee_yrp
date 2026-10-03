"""Essdee's mapped Work Order GRN valuation lifecycle.

Essdee owns the fabric/IPD calculation that maps each consumed input to the
exact received GRN row. Base YRP owns the stock posting, actual FIFO/Moving
Average valuation, persisted production lineage, and cancellation reversal.
"""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_grn import (
	apply_work_order_stock_update,
	calculate_consumption_plan,
	is_calculable_fabric_grn,
	load_submitted_consumption_plan,
	populate_grn_deliverables,
)
from yrp.yrp.doctype.goods_received_note.goods_received_note import (
	GoodsReceivedNote,
	_find_matching_receivable,
	_wo_excess_percentage,
)


class EssdeeGoodsReceivedNote(GoodsReceivedNote):
	"""Extend only regular Essdee fabric Work Order receipts."""

	def onload(self):
		super().onload()
		if self.docstatus != 0 or not self._uses_essdee_deliverable_consumption():
			return

		work_order = frappe.get_doc("Work Order", self.against_id)
		default_knitting = frappe.db.get_single_value(
			"IPD Settings", "default_knitting_process"
		)
		if not default_knitting or work_order.process_name != default_knitting:
			return

		from essdee_yrp.fabric_grn import get_saved_actual_dia_rows

		actual_rows = get_saved_actual_dia_rows(self, work_order)
		if not actual_rows:
			return

		# Base YRP refreshes the planned rows so Pending/Allowed remain current.
		# Rebuild the same payload and append the persisted physical-Dia rows that
		# are intentionally absent from the Work Order plan.
		from yrp.stock.dimensions import apply_dimension_defaults
		from yrp.stock.save_stock_items import group_items_for_ui
		from yrp.yrp.doctype.delivery_challan.delivery_challan import (
			_apply_dimension_values_to_rows,
			_get_production_group_dimensions,
		)
		from yrp.yrp.doctype.goods_received_note.goods_received_note import (
			_pending_receivable_rows,
		)

		delivery_challan = (
			frappe.get_doc("Delivery Challan", self.delivery_challan)
			if self.delivery_challan else None
		)
		rows = _pending_receivable_rows(
			work_order,
			existing_rows=self.get("items") or [],
			delivery_challan=delivery_challan,
		)
		# Once an operator has saved one or more physical Actual-Dia rows for a
		# planned receivable, do not resurrect the unsaved planned Dia as a zero-
		# quantity row on every reopen.  A genuinely saved planned-Dia quantity is
		# retained, and the editor's Add Dia control remains available if the
		# operator later wants to add the planned Dia back explicitly.
		actual_sources = {
			row.get("ref_docname") for row in actual_rows if row.get("ref_docname")
		}
		rows = [
			row for row in rows
			if not (
				row.get("ref_docname") in actual_sources
				and flt(row.get("quantity")) <= 0
			)
		]
		rows.extend(actual_rows)
		_apply_dimension_values_to_rows(
			rows, _get_production_group_dimensions(work_order)
		)
		apply_dimension_defaults(rows)
		self.set_onload(
			"item_details", group_items_for_ui(rows, "Goods Received Note")
		)

	def submit(self):
		# Document._save locks the GRN parent in check_if_latest before running
		# before_submit. Enter through the public lifecycle method and acquire the
		# Lot first so every conversion writer has the real Lot -> GRN order.
		from essdee_yrp.fabric_substitution import (
			lock_lot_for_default_knitting_grn,
		)

		lock_lot_for_default_knitting_grn(self)
		return super().submit()

	def cancel(self):
		from essdee_yrp.fabric_substitution import (
			lock_lot_for_default_knitting_grn,
		)

		lock_lot_for_default_knitting_grn(self)
		return super().cancel()

	def before_submit(self):
		from essdee_yrp.fabric_substitution import (
			lock_lot_for_default_knitting_grn,
		)

		# One global order for conversion writers: Lot, then Work Order/GRN.
		# The rebuild can therefore wait for every submitted source row without
		# ever committing a partial SKIP LOCKED snapshot.
		lock_lot_for_default_knitting_grn(self)
		if self._uses_essdee_deliverable_consumption():
			locked_work_order = _get_locked_work_order(self.against_id)
			self.flags.essdee_locked_work_order = locked_work_order
			plan = calculate_consumption_plan(self, work_order_doc=locked_work_order)
			populate_grn_deliverables(self, plan)
			self.flags.essdee_deliverable_consumption = plan
		super().before_submit()

	def before_cancel(self):
		from essdee_yrp.fabric_substitution import (
			lock_lot_for_default_knitting_grn,
		)

		lock_lot_for_default_knitting_grn(self)
		# Cancellation hooks run before Frappe updates the parent row. Take the
		# source lock explicitly so a concurrent Calculate either commits its
		# allocation first or reloads this receipt after it is cancelled.
		frappe.db.sql(
			"SELECT name FROM `tabGoods Received Note` WHERE name=%s FOR UPDATE",
			(self.name,),
		)
		if self._uses_essdee_deliverable_consumption():
			locked_work_order = _get_locked_work_order(self.against_id)
			self.flags.essdee_locked_work_order = locked_work_order
			if locked_work_order.open_status == "Close":
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
				work_order_doc=self.flags.get("essdee_locked_work_order"),
			)
		# Keep the Lot-level planned -> actual substitution projection in the
		# same database transaction as the authoritative GRN stock posting.
		from essdee_yrp.fabric_tracking import on_grn_submit

		on_grn_submit(self)
		from essdee_yrp.fabric_substitution import (
			rebuild_lot_fabric_conversions_for_grn,
		)

		rebuild_lot_fabric_conversions_for_grn(self)
		self._enqueue_repost()

	def on_cancel(self):
		super().on_cancel()
		if self._uses_essdee_deliverable_consumption():
			apply_work_order_stock_update(
				self.against_id,
				self.flags.get("essdee_deliverable_consumption") or [],
				cancel=True,
				work_order_doc=self.flags.get("essdee_locked_work_order"),
			)
		from essdee_yrp.fabric_tracking import on_grn_cancel

		on_grn_cancel(self)
		from essdee_yrp.fabric_substitution import (
			rebuild_lot_fabric_conversions_for_grn,
		)

		rebuild_lot_fabric_conversions_for_grn(self)
		self._enqueue_repost()

	def _uses_essdee_deliverable_consumption(self):
		return is_calculable_fabric_grn(self)

	def validate_against_work_order_pending(self):
		"""Link against the post-lock WO state without capping a physical receipt."""
		wo = self.flags.get("essdee_locked_work_order")
		if not wo:
			return super().validate_against_work_order_pending()
		for row in self.items:
			target = _find_matching_receivable(wo.receivables, row)
			if not target:
				frappe.throw(_(
					"Row {0}: no matching Work Order Receivable found for {1}."
				).format(row.idx, row.item_variant))
			row.ref_doctype = "Work Order Receivables"
			row.ref_docname = target.name
			row.pending_quantity = target.pending_quantity
			# A standard Essdee fabric GRN is an actual physical measurement. Keep
			# the plan in pending_quantity for variance visibility, but never turn
			# it into a receipt cap. Stock/UOM/warehouse validations still run in
			# the normal controller lifecycle.
			row.max_receivable_quantity = None
		excess_pct = _wo_excess_percentage(self.against_id)
		self.validate_against_correction_pending(excess_pct)

	def update_work_order_receivables(self, cancel=False):
		"""Apply pending changes to the same current rows locked at submit."""
		wo = self.flags.get("essdee_locked_work_order")
		if not wo:
			return super().update_work_order_receivables(cancel=cancel)
		changed = False
		for row in self.items:
			target = _find_matching_receivable(wo.receivables, row)
			if not target:
				continue
			qty = flt(row.quantity)
			pending = (
				flt(target.pending_quantity) + qty
				if cancel else flt(target.pending_quantity) - qty
			)
			target.pending_quantity = flt(pending)
			target.db_set("pending_quantity", target.pending_quantity, update_modified=False)
			changed = True
		if changed:
			_update_locked_work_order_status(wo)
		self.update_correction_receivables(cancel=cancel)

	def _enqueue_repost(self):
		from yrp.stock.stock_ledger import enqueue_voucher_repost

		enqueue_voucher_repost(self)


def _lock_work_order(work_order):
	frappe.db.sql(
		"SELECT name FROM `tabWork Order` WHERE name=%s FOR UPDATE",
		(work_order,),
	)


def _get_locked_work_order(work_order):
	"""Current-read and lock the WO header plus all child execution rows."""
	return frappe.get_doc("Work Order", work_order, for_update=True)


def _update_locked_work_order_status(wo):
	wo.set_status()
	wo.db_set("status", wo.status, update_modified=False)
	wo.db_set("is_delivered", wo.is_delivered, update_modified=False)


def _guard_source_grn_allocations(grn):
	"""Compatibility no-op: draft Work Orders are not stock reservations."""
	return None

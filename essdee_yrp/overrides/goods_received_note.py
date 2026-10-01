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
	_remaining_receivable_allowance,
	_wo_excess_percentage,
)


class EssdeeGoodsReceivedNote(GoodsReceivedNote):
	"""Extend only regular Essdee fabric Work Order receipts."""

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
		# Guard every Work Order receipt (including rework,
		# additional and packing modes) so Calculate either commits its exact
		# allocation first or observes this receipt as cancelled afterwards.
		if self.get("against") == "Work Order":
			_guard_source_grn_allocations(self)
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
		"""Validate against the post-lock WO state, not an RR snapshot."""
		wo = self.flags.get("essdee_locked_work_order")
		if not wo:
			return super().validate_against_work_order_pending()
		totals_by_receivable = {}
		receivable_by_name = {}
		for row in self.items:
			target = _find_matching_receivable(wo.receivables, row)
			if not target:
				frappe.throw(_(
					"Row {0}: no matching Work Order Receivable found for {1}."
				).format(row.idx, row.item_variant))
			totals_by_receivable[target.name] = (
				totals_by_receivable.get(target.name, 0) + flt(row.quantity)
			)
			receivable_by_name[target.name] = target
			row.ref_doctype = "Work Order Receivables"
			row.ref_docname = target.name
			row.pending_quantity = target.pending_quantity
		excess_pct = _wo_excess_percentage(self.against_id)
		for receivable_name, total_qty in totals_by_receivable.items():
			target = receivable_by_name[receivable_name]
			allowance = _remaining_receivable_allowance(
				target.qty, target.pending_quantity, excess_pct
			)
			if total_qty > allowance + 0.0001:
				frappe.throw(_(
					"Received qty {0} exceeds allowance {1} for {2} "
					"(ordered {3}, excess allowance {4}%)."
				).format(
					flt(total_qty), flt(allowance), target.item_variant,
					flt(target.qty), flt(excess_pct),
				))
			for row in self.items:
				if _find_matching_receivable([target], row):
					row.max_receivable_quantity = max(flt(allowance), 0)
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
	"""Do not invalidate a receipt allocated to any non-cancelled later WO."""
	allocations = frappe.db.sql(
		"""
		SELECT DISTINCT item.parent
		FROM `tabWork Order Deliverables` item
		WHERE item.parenttype = 'Work Order'
			AND item.source_grn = %s
		ORDER BY item.parent
		FOR UPDATE
		""",
		(grn.name,),
		as_dict=True,
	)
	parents = [row.parent for row in allocations]
	if not parents:
		return
	# A target held by another request is treated conservatively as live. SKIP
	# LOCKED prevents target-WO -> source-GRN lock inversion with Calculate while
	# retaining a post-source-lock current read for every available parent.
	statuses = {
		row.name: row.docstatus
		for row in frappe.db.sql(
			"""
			SELECT name, docstatus
			FROM `tabWork Order`
			WHERE name IN %(parents)s
			FOR UPDATE SKIP LOCKED
			""",
			{"parents": tuple(parents)},
			as_dict=True,
		)
	}
	work_orders = [
		name for name in parents
		if name not in statuses or statuses[name] < 2
	]
	if not work_orders:
		return
	links = ", ".join(
		frappe.utils.get_link_to_form("Work Order", name) for name in work_orders
	)
	frappe.throw(
		_(
			"Goods Received Note {0} is allocated to later Work Order(s): {1}. "
			"Cancel those Work Orders before cancelling this receipt."
		).format(grn.name, links)
	)

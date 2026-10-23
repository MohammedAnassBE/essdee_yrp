"""One-off repair of Work Order piece tracking for migrated F15 packing GRNs.

F15 credited each packing GRN's box count to every packing colour, so migrated
received figures are inflated. Replay now records the GRN's real pieces. This
replays the affected Work Orders: tracking rows, lot pack quantities and the
Finishing Plan projection only. Stock ledger and valuation are never touched.

Dry run (default, no writes):
	bench --site SITE execute essdee_yrp.migration.repair_packing_tracking.run
Apply:
	bench --site SITE execute essdee_yrp.migration.repair_packing_tracking.run --kwargs "{'apply': 1}"
"""

from collections import defaultdict

import frappe
from frappe.utils import flt
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _get_warehouse_for_supplier
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

from essdee_yrp.finishing.loose_piece import get_loose_piece_stock_variant
from essdee_yrp.work_order_piece_tracking import (
	calculate_work_order_piece_tracking,
	rebuild_work_order_piece_tracking,
)


def run(apply=0, work_orders=None, verbose=1):
	names = frappe.parse_json(work_orders) if work_orders else get_candidate_work_orders()
	changes, errors = [], []
	for name in names:
		try:
			change = get_work_order_change(name)
		except Exception as error:
			errors.append({"work_order": name, "error": repr(error)})
			continue
		if change["rows"]:
			changes.append(change)
	anomalies, stock_summary = get_anomalies(changes)
	if verbose:
		print_report(changes, anomalies, errors, len(names))
		print(f"Stock buckets: {stock_summary}")
	if apply:
		apply_changes(changes, errors)
	return {
		"candidates": len(names),
		"changed": len(changes),
		"anomalies": len(anomalies),
		"stock_buckets": stock_summary,
		"errors": errors,
		"applied": bool(apply),
	}


def get_candidate_work_orders():
	"""Submitted Work Orders with a non-dynamic packing GRN whose consumed rows lack an output link."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT grn.against_id
		FROM `tabYRP Goods Received Note` grn
		WHERE grn.docstatus = 1
		  AND grn.against = 'YRP Work Order'
		  AND grn.includes_packing = 1
		  AND IFNULL(grn.is_return, 0) = 0
		  AND IFNULL(grn.packing_calculation_version, 0) < 2
		  AND EXISTS (
			SELECT 1 FROM `tabSD YRP GRN Deliverable` row
			WHERE row.parent = grn.name AND row.parenttype = 'YRP Goods Received Note'
		  )
		  AND NOT EXISTS (
			SELECT 1 FROM `tabSD YRP GRN Deliverable` row
			WHERE row.parent = grn.name AND row.parenttype = 'YRP Goods Received Note'
			  AND IFNULL(row.goods_received_note_item, '') != ''
		  )
		ORDER BY grn.against_id
		""",
		pluck=True,
	)


def get_work_order_change(name):
	doc = frappe.get_doc("YRP Work Order", name)
	result = calculate_work_order_piece_tracking(name)
	after = {row["name"]: row for row in result["rows"]}
	rows = []
	for row in doc.get("work_order_calculated_items") or []:
		received = after[row.name]["received_qty"]
		if flt(row.received_qty) == flt(received):
			continue
		rows.append(
			{
				"item_variant": row.item_variant,
				"set_combination": row.set_combination,
				"delivered": flt(row.delivered_quantity),
				"received_before": flt(row.received_qty),
				"received_after": flt(received),
			}
		)
	return {
		"work_order": name,
		"doc": doc,
		"received_before": flt(doc.total_no_of_pieces_received),
		"received_after": flt(result["total_received"]),
		"rows": rows,
		"after": after,
	}


def get_anomalies(changes):
	"""Flag negative remaining, and stock buckets whose remaining moves further from stock."""
	anomalies = []
	buckets = defaultdict(lambda: {"before": 0.0, "after": 0.0, "work_orders": set()})
	for change in changes:
		doc = change["doc"]
		for row in doc.get("work_order_calculated_items") or []:
			after = change["after"][row.name]
			remaining = flt(after["delivered_quantity"]) - flt(after["received_qty"])
			if remaining < 0:
				anomalies.append(
					f"{doc.name} {row.item_variant}: remaining {remaining:g} after repair "
					f"(delivered {after['delivered_quantity']}, received {after['received_qty']})"
				)
			key = None if doc.get("open_status") == "Close" else _stock_bucket(doc, row)
			if key:
				buckets[key]["before"] += max(flt(row.delivered_quantity) - flt(row.received_qty), 0)
				buckets[key]["after"] += max(remaining, 0)
				buckets[key]["work_orders"].add(doc.name)
	summary = defaultdict(int)
	for (item, warehouse, dimensions), bucket in buckets.items():
		stock = flt(get_stock_balance(item, warehouse, **dict(dimensions)))
		before_gap, after_gap = abs(bucket["before"] - stock), abs(bucket["after"] - stock)
		summary["buckets"] += 1
		summary["after_matches_stock"] += after_gap <= 0.001
		summary["before_matched_stock"] += before_gap <= 0.001
		summary["closer_to_stock"] += after_gap < before_gap
		if after_gap > before_gap + 0.001:
			summary["further_from_stock"] += 1
			anomalies.append(
				f"{', '.join(sorted(bucket['work_orders']))} {item} @ {warehouse} {dict(dimensions)}: "
				f"remaining {bucket['before']:g} -> {bucket['after']:g}, stock {stock:g}"
			)
	return anomalies, dict(summary)


def _stock_bucket(doc, row):
	deliverable = next(
		(
			item
			for item in doc.get("deliverables") or []
			if item.item_variant == row.item_variant
			and frappe.parse_json(item.set_combination or "{}")
			== frappe.parse_json(row.set_combination or "{}")
		),
		None,
	)
	warehouse = _get_warehouse_for_supplier(doc.supplier)
	if not deliverable or not warehouse:
		return None
	item = get_loose_piece_stock_variant(doc, row.item_variant)
	return item, warehouse, tuple(sorted(_stock_dimension_values(doc, deliverable).items()))


def print_report(changes, anomalies, errors, candidates):
	print(f"Candidates: {candidates}; Work Orders that change: {len(changes)}")
	for change in changes:
		print(
			f"\n{change['work_order']}: received {change['received_before']:g} -> {change['received_after']:g}"
		)
		for row in change["rows"]:
			print(
				f"  {row['item_variant']}: delivered {row['delivered']:g}, "
				f"received {row['received_before']:g} -> {row['received_after']:g}, "
				f"remaining {row['delivered'] - row['received_before']:g} -> "
				f"{row['delivered'] - row['received_after']:g}"
			)
	print(f"\nAnomalies: {len(anomalies)}")
	for anomaly in anomalies:
		print(f"  {anomaly}")
	print(f"\nErrors: {len(errors)}")
	for error in errors:
		print(f"  {error['work_order']}: {error['error']}")


def apply_changes(changes, errors):
	for change in changes:
		try:
			rebuild_work_order_piece_tracking(change["work_order"], check_permission=False)
			frappe.db.commit()  # nosemgrep: one Work Order per transaction
		except Exception as error:
			frappe.db.rollback()
			errors.append({"work_order": change["work_order"], "error": repr(error)})

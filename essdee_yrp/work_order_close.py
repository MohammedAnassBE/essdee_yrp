"""Valuation-aware Essdee Work Order close lifecycle."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime

from yrp.yrp.doctype.yrp_work_order.yrp_work_order import (
	_apply_close_details,
	_get_wo_close_approver_role,
	_is_wo_close_manager,
	_stock_dimension_values,
	_validate_wo_close,
)


QTY_TOLERANCE = 0.000001
SD_CLOSE_REASONS = (
	"NA",
	"Cutting Shortage",
	"Printing Shortage",
	"Sewing Shortage",
	"Sewing Missing",
	"Others",
)


@frappe.whitelist()
def close_work_order(
	work_order,
	sd_close_reason=None,
	close_reason=None,
	close_other_reason=None,
	close_remarks=None,
):
	"""Close with full actual excess usage or fail without clipping stock."""
	from yrp.stock.stock_ledger import enqueue_voucher_repost, make_sl_entries
	from yrp.stock.utils import (
		close_voucher_reservations,
		get_conversion_factor,
		get_stock_balance,
	)
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		_get_warehouse_for_supplier,
	)
	from yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment import (
		create_adjustment,
		register_production_links,
	)

	selected_reason, other_reason = _validate_close_reason(
		sd_close_reason or close_reason, close_other_reason
	)
	frappe.db.sql(
		"SELECT name FROM `tabYRP Work Order` WHERE name=%s FOR UPDATE",
		(work_order,),
	)
	doc = frappe.get_doc('YRP Work Order', work_order)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only submitted Work Orders can be closed."))
	if doc.open_status == "Close":
		return _close_result(doc.name, "Close")

	if not _is_wo_close_manager(throw_if_missing=True):
		if doc.open_status == "Close Request":
			approver_role = _get_wo_close_approver_role()
			frappe.throw(
				_("Only users with role {0} can approve close requests.").format(
					approver_role
				)
			)
		_apply_close_details(
			doc,
			"Close Request",
			None,
			other_reason,
			close_remarks,
		)
		doc.sd_close_reason = selected_reason
		doc.save(ignore_permissions=True)
		frappe.msgprint(_("Close Request has been submitted for approval."), alert=True)
		return {"status": "Close Request", "deducted_qty": 0.0}

	_validate_wo_close(doc)
	warehouse = _get_warehouse_for_supplier(doc.supplier)
	if not warehouse:
		frappe.throw(_("No active Warehouse found for supplier {0}.").format(doc.supplier))

	entries = []
	excess_plans = []
	remaining_by_bucket = {}
	posting_date = nowdate()
	posting_time = nowtime()
	for row in doc.get("deliverables") or []:
		delivered_qty = flt(row.qty) - flt(row.pending_quantity)
		reduce_qty = delivered_qty - flt(row.stock_update)
		if reduce_qty <= 0:
			continue
		conversion = get_conversion_factor(row.item_variant, row.uom)
		factor = flt(conversion.get("conversion_factor")) or 1
		reduce_stock_qty = reduce_qty * factor
		dimensions = _stock_dimension_values(doc, row)
		bucket = (row.item_variant, warehouse, tuple(sorted(dimensions.items())))
		if bucket not in remaining_by_bucket:
			balance, valuation_rate = get_stock_balance(
				row.item_variant,
				warehouse,
				posting_date=posting_date,
				posting_time=posting_time,
				with_valuation_rate=True,
				**dimensions,
			)
			remaining_by_bucket[bucket] = {
				"qty": max(flt(balance), 0),
				"valuation_rate": flt(valuation_rate),
			}

		bucket_balance = remaining_by_bucket[bucket]
		if bucket_balance["qty"] + QTY_TOLERANCE < reduce_stock_qty:
			frappe.throw(
				_(
					"Cannot close Work Order {0}. Row {1} requires {2} {3} of "
					"excess usage, but only {4} is available for the same Stock "
					"Dimensions. Record the return or correct consumption first."
				).format(
					doc.name,
					row.idx,
					round(reduce_stock_qty, 6),
					conversion.get("stock_uom") or row.uom,
					round(bucket_balance["qty"], 6),
				)
			)

		output_allocations = _get_excess_output_allocations(doc, row, dimensions)
		result_key = f"wo-close:{row.name}"
		entries.append(
			{
				"item": row.item_variant,
				"warehouse": warehouse,
				"uom": conversion.get("stock_uom") or row.uom,
				"voucher_type": doc.doctype,
				"voucher_no": doc.name,
				"voucher_detail_no": row.name,
				"posting_date": posting_date,
				"posting_time": posting_time,
				"qty": -reduce_stock_qty,
				"rate": 0,
				"outgoing_rate": flt(
					row.valuation_rate
					or row.rate
					or bucket_balance["valuation_rate"]
				),
				"is_cancelled": 0,
				"_result_key": result_key,
				**dimensions,
			}
		)
		excess_plans.append(
			{
				"result_key": result_key,
				"deliverable": row,
				"quantity": reduce_qty,
				"stock_quantity": reduce_stock_qty,
				"stock_uom": conversion.get("stock_uom") or row.uom,
				"dimensions": dimensions,
				"output_allocations": output_allocations,
			}
		)
		bucket_balance["qty"] -= reduce_stock_qty

	ledger_result = make_sl_entries(entries, return_details=True, force_inline=True)
	for plan in excess_plans:
		detail = ledger_result["entries"].get(plan["result_key"])
		if not detail:
			frappe.throw(
				_("Could not calculate actual excess-usage value for {0}.").format(
					plan["deliverable"].item_variant
				)
			)
		plan["ledger_detail"] = detail
		_record_excess_usage(doc, plan)
		plan["deliverable"].stock_update = flt(
			plan["deliverable"].stock_update
		) + flt(plan["quantity"])

	_apply_close_details(doc, "Close", None, other_reason, close_remarks)
	doc.sd_close_reason = selected_reason
	doc.closed_by = frappe.session.user
	doc.is_delivered = 1
	doc.total_quantity = 0
	doc.save(ignore_permissions=True)

	adjustment_allocations = []
	production_links = []
	for plan in excess_plans:
		detail = plan["ledger_detail"]
		weights = sum(flt(row["allocation_weight"]) for row in plan["output_allocations"])
		if weights <= 0:
			frappe.throw(
				_("Excess usage for {0} has no output allocation weight.").format(
					plan["deliverable"].item_variant
				)
			)
		assigned_value = 0.0
		assigned_qty = 0.0
		for index, output in enumerate(plan["output_allocations"]):
			is_last = index == len(plan["output_allocations"]) - 1
			value_share = (
				flt(detail["value"]) - assigned_value
				if is_last
				else flt(detail["value"])
				* flt(output["allocation_weight"])
				/ weights
			)
			qty_share = (
				flt(plan["stock_quantity"]) - assigned_qty
				if is_last
				else flt(plan["stock_quantity"])
				* flt(output["allocation_weight"])
				/ weights
			)
			assigned_value += value_share
			assigned_qty += qty_share
			target_sle = output["output_receipt_sle"]
			target = _get_owned_output_sle(output)
			adjustment_allocations.append(
				{
					"source_row": plan["audit_row"].name,
					"source_sle": detail["sle"],
					"target_sle": target_sle,
					"item": target.item,
					"quantity": qty_share,
					"old_rate": flt(target.rate),
					"new_rate": flt(target.rate) + value_share / flt(target.qty),
					"difference": value_share,
					"allocation_weight": output["allocation_weight"],
					"stock_dimensions": frappe.as_json(plan["dimensions"]),
				}
			)
			production_links.append(
				{
					"consumption_sle": detail["sle"],
					"output_receipt_sle": target_sle,
					"source_row": plan["audit_row"].name,
					"input_quantity": qty_share,
					"allocation_weight": output["allocation_weight"],
					"stock_dimensions": frappe.as_json(plan["dimensions"]),
				}
			)

	register_production_links(doc.doctype, doc.name, production_links)
	create_adjustment(
		adjustment_type="Work Order Excess Usage",
		source_doctype=doc.doctype,
		source_name=doc.name,
		effective_date=posting_date,
		allocations=adjustment_allocations,
		idempotency_key=f"{doc.doctype}:{doc.name}:close:1",
	)
	close_voucher_reservations('YRP Work Order', doc.name)
	enqueue_voucher_repost(
		frappe._dict(
			doctype=doc.doctype,
			name=doc.name,
			posting_date=posting_date,
			posting_time=posting_time,
		)
	)
	return {
		"status": "Close",
		"deducted_qty": round(
			sum(flt(plan["stock_quantity"]) for plan in excess_plans), 3
		),
	}


def _validate_close_reason(selected_reason, close_other_reason):
	selected_reason = (selected_reason or "").strip()
	if selected_reason not in SD_CLOSE_REASONS:
		frappe.throw(_("Select a valid SD Close Reason."))
	other_reason = (close_other_reason or "").strip()
	if selected_reason == "Others" and not other_reason:
		frappe.throw(_("Enter the other close reason."))
	if selected_reason != "Others":
		other_reason = ""
	return selected_reason, other_reason


def _get_excess_output_allocations(work_order, deliverable, dimensions):
	"""Resolve exact submitted output receipts that used this input."""
	rows = frappe.db.sql(
		"""
		SELECT d.name, d.parent AS output_voucher,
		       d.goods_received_note_item AS output_detail,
		       d.received_item_variant AS output_item,
		       d.output_receipt_sle, d.stock_qty, d.stock_dimensions
		FROM `tabSD YRP YRP GRN Deliverable` d
		INNER JOIN `tabYRP Goods Received Note` g ON g.name = d.parent
		WHERE d.parenttype = 'YRP Goods Received Note'
		  AND d.parentfield = 'grn_deliverables'
		  AND g.docstatus = 1
		  AND g.against = 'YRP Work Order'
		  AND g.against_id = %s
		  AND d.work_order_deliverable = %s
		  AND COALESCE(d.output_receipt_sle, '') != ''
		ORDER BY g.posting_date, g.posting_time, g.creation, d.idx
		""",
		(work_order.name, deliverable.name),
		as_dict=True,
	)
	grouped = {}
	for row in rows:
		row_dimensions = frappe.parse_json(row.stock_dimensions or "{}")
		if any(
			(row_dimensions.get(key) or None) != (value or None)
			for key, value in dimensions.items()
		):
			continue
		key = (
			row.output_receipt_sle,
			row.output_voucher,
			row.output_detail,
			row.output_item,
		)
		grouped[key] = flt(grouped.get(key)) + flt(row.stock_qty)
	if not grouped:
		frappe.throw(
			_(
				"Cannot allocate excess usage for Work Order row {0}. No submitted "
				"GRN output has exact mapped lineage and matching Stock Dimensions. "
				"Historical ambiguous lineage must be resolved before closing."
			).format(deliverable.idx or deliverable.name)
		)
	return [
		{
			"output_receipt_sle": key[0],
			"output_voucher": key[1],
			"output_detail": key[2],
			"output_item": key[3],
			"allocation_weight": weight,
		}
		for key, weight in grouped.items()
		if weight > 0
	]


def _get_owned_output_sle(output):
	"""Load only the active GRN receipt proved by mapped output lineage."""
	target = frappe.db.get_value(
		'YRP Stock Ledger Entry',
		{
			"name": output["output_receipt_sle"],
			"voucher_type": 'YRP Goods Received Note',
			"voucher_no": output["output_voucher"],
			"voucher_detail_no": output["output_detail"],
			"item": output["output_item"],
			"qty": [">", 0],
			"is_cancelled": 0,
		},
		["item", "qty", "rate"],
		as_dict=True,
	)
	if not target:
		frappe.throw(
			_("Output receipt SLE {0} is not an active owned GRN receipt.").format(
				output["output_receipt_sle"]
			)
		)
	return target


def _record_excess_usage(work_order, plan):
	"""Persist the exact consumed quantity, SLE, dimensions, and actual value."""
	deliverable = plan["deliverable"]
	detail = plan["ledger_detail"]
	row = work_order.append(
		"work_order_excess_usage_items",
		{
			"item_variant": deliverable.item_variant,
			"excess_quantity": plan["quantity"],
			"rate": detail["rate"],
			"actual_value": detail["value"],
			"uom": deliverable.uom,
			"stock_quantity": plan["stock_quantity"],
			"stock_uom": plan["stock_uom"],
			"work_order_deliverable": deliverable.name,
			"source_sle": detail["sle"],
			"stock_dimensions": frappe.as_json(plan["dimensions"]),
		},
	)
	plan["audit_row"] = row
	return row


def _close_result(work_order, status):
	deducted = abs(
		flt(
			frappe.db.sql(
				"""
				SELECT COALESCE(SUM(qty), 0)
				FROM `tabYRP Stock Ledger Entry`
				WHERE voucher_type = 'YRP Work Order'
				  AND voucher_no = %s
				  AND is_cancelled = 0
				""",
				(work_order,),
			)[0][0]
		)
	)
	return {"status": status, "deducted_qty": round(deducted, 3)}

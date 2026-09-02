"""Apply/reverse Essdee finishing side effects of a generic YRP Stock Entry."""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from essdee_yrp.finishing.packing import rebuild_finishing_packing_quantities
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.state import (
	get_finishing_plan_dict,
	get_finishing_plan_list,
)
from essdee_yrp.finishing.status import (
	apply_auto_fp_status,
	cancel_finishing_dispatch_log,
	record_finishing_dispatch_log,
)
from yrp.utils import update_if_string_instance


def apply_stock_entry(stock_entry, *, cancelled=False):
	"""Update Essdee finishing trace state after YRP posts/reverses stock."""
	_update_incomplete_transfer_tracking(stock_entry, cancelled=cancelled)
	if stock_entry.against == 'SD YRP Finishing Plan Dispatch':
		_update_dispatch_document(stock_entry, cancelled=cancelled)
	elif stock_entry.against == 'SD YRP Finishing Plan':
		_update_finishing_plan(stock_entry, cancelled=cancelled)


def _update_dispatch_document(stock_entry, *, cancelled):
	dispatch_doc = frappe.get_doc('SD YRP Finishing Plan Dispatch', stock_entry.against_id)
	batch_dispatches = _get_batch_dispatches(stock_entry)
	dynamic_plans, dispatch_boxes, dispatch_pieces = _update_packing_batches(
		batch_dispatches, cancelled=cancelled
	)
	finishing_plan_names = set(dynamic_plans)

	for row in dispatch_doc.get("finishing_plan_dispatch_items") or []:
		if row.packing_source == "batch":
			if row.against_id:
				finishing_plan_names.add(row.against_id)
			continue

		detail = frappe.db.get_value(
			'SD YRP Finishing Plan GRN Detail',
			row.against_id_detail,
			["name", "parent", "dispatched"],
			as_dict=True,
		)
		if not detail:
			detail = frappe.db.get_value(
				'SD YRP Finishing Plan GRN Detail',
				{"parent": row.against_id, "item_variant": row.item_variant},
				["name", "parent", "dispatched"],
				as_dict=True,
			)
		if not detail:
			frappe.throw(
				_("Cannot update dispatched quantity for {0} in Finishing Plan {1}").format(
					row.item_variant, row.against_id
				)
			)

		updated = flt(detail.dispatched) + (-flt(row.quantity) if cancelled else flt(row.quantity))
		if updated < -1e-6:
			frappe.throw(
				_("Dispatched quantity cannot be negative for {0}").format(row.item_variant)
			)
		frappe.db.set_value(
			'SD YRP Finishing Plan GRN Detail', detail.name, "dispatched", max(updated, 0)
		)
		if detail.parent:
			finishing_plan_names.add(detail.parent)
			if not cancelled and detail.parent not in dynamic_plans:
				dispatch_boxes[detail.parent] = (
					dispatch_boxes.get(detail.parent, 0) + flt(row.quantity)
				)

	dispatch_doc.stock_entry = None if cancelled else stock_entry.name
	dispatch_doc.save(ignore_permissions=True)

	for finishing_plan_name in finishing_plan_names:
		finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_plan_name)
		if finishing_plan_name in dynamic_plans:
			rebuild_finishing_packing_quantities(finishing_doc)
		if cancelled:
			cancel_finishing_dispatch_log(finishing_doc, stock_entry.name)
		else:
			record_finishing_dispatch_log(
				finishing_doc,
				stock_entry,
				dispatch_boxes.get(finishing_plan_name, 0),
				source_doctype='SD YRP Finishing Plan Dispatch',
				source_name=dispatch_doc.name,
				dispatch_pieces=(
					dispatch_pieces.get(finishing_plan_name)
					if finishing_plan_name in dynamic_plans
					else None
				),
			)
		apply_auto_fp_status(finishing_doc)
		finishing_doc.save(ignore_permissions=True)


def _update_finishing_plan(stock_entry, *, cancelled):
	finishing_doc = frappe.get_doc('SD YRP Finishing Plan', stock_entry.against_id)
	if stock_entry.purpose == "Material Issue":
		_update_direct_dispatch(finishing_doc, stock_entry, cancelled=cancelled)
	else:
		_update_ironing_excess(finishing_doc, stock_entry, cancelled=cancelled)


def _update_direct_dispatch(finishing_doc, stock_entry, *, cancelled):
	batch_dispatches = _get_batch_dispatches(stock_entry)
	dynamic_dispatch = bool(batch_dispatches)
	dispatch_boxes = 0
	dispatch_pieces = 0
	quantities = {
		row.item_variant: {
			"quantity": flt(row.quantity),
			"dispatched": flt(row.dispatched),
		}
		for row in finishing_doc.get("finishing_plan_grn_details") or []
	}

	if dynamic_dispatch:
		_plans, boxes_by_plan, pieces_by_plan = _update_packing_batches(
			batch_dispatches,
			cancelled=cancelled,
			expected_finishing_plan=finishing_doc.name,
		)
		dispatch_boxes = boxes_by_plan.get(finishing_doc.name, 0)
		dispatch_pieces = pieces_by_plan.get(finishing_doc.name, 0)
		rebuild_finishing_packing_quantities(finishing_doc)
	else:
		for row in stock_entry.get("items") or []:
			if row.item not in quantities:
				quantities[row.item] = {"quantity": 0, "dispatched": 0}
			delta = -flt(row.qty) if cancelled else flt(row.qty)
			quantities[row.item]["dispatched"] += delta
			if quantities[row.item]["dispatched"] < -1e-6:
				frappe.throw(
					_("Dispatched quantity cannot be negative for {0}").format(row.item)
				)
			if not cancelled:
				dispatch_boxes += flt(row.qty)
		finishing_doc.set(
			"finishing_plan_grn_details",
			[
				{
					"item_variant": item_variant,
					"quantity": values["quantity"],
					"dispatched": max(values["dispatched"], 0),
				}
				for item_variant, values in quantities.items()
			],
		)

	stock_entry_list = update_if_string_instance(finishing_doc.stock_entry_list) or {}
	if cancelled:
		stock_entry_list.pop(stock_entry.name, None)
		cancel_finishing_dispatch_log(finishing_doc, stock_entry.name)
	else:
		stock_entry_list[stock_entry.name] = now_datetime().strftime("%d-%m-%Y %H:%M:%S")
		record_finishing_dispatch_log(
			finishing_doc,
			stock_entry,
			dispatch_boxes,
			source_doctype='SD YRP Finishing Plan',
			source_name=finishing_doc.name,
			dispatch_pieces=dispatch_pieces if dynamic_dispatch else None,
		)
	finishing_doc.stock_entry_list = frappe.json.dumps(stock_entry_list)
	apply_auto_fp_status(finishing_doc)
	finishing_doc.save(ignore_permissions=True)


def _update_ironing_excess(finishing_doc, stock_entry, *, cancelled):
	finishing_items = get_finishing_plan_dict(finishing_doc)
	for row in stock_entry.get("items") or []:
		combination = json_object(row.set_combination)
		key = (row.item, tuple(sorted(combination.items())))
		if key not in finishing_items:
			frappe.throw(
				_("No Finishing Plan row matches item {0} and its set combination").format(
					row.item
				)
			)
		finishing_items[key]["ironing_excess"] += (
			-flt(row.qty) if cancelled else flt(row.qty)
		)

	finishing_doc.set(
		"finishing_plan_details", get_finishing_plan_list(finishing_items)
	)
	ironing_excess_list = update_if_string_instance(finishing_doc.ironing_excess_list) or {}
	if cancelled:
		ironing_excess_list.pop(stock_entry.name, None)
	else:
		ironing_excess_list[stock_entry.name] = now_datetime().strftime(
			"%d-%m-%Y %H:%M:%S"
		)
	finishing_doc.ironing_excess_list = frappe.json.dumps(ironing_excess_list)
	finishing_doc.save(ignore_permissions=True)


def _get_batch_dispatches(stock_entry):
	payload = update_if_string_instance(
		stock_entry.get("packing_batch_dispatch_json")
	) or []
	if payload and not isinstance(payload, list):
		frappe.throw(_("Packing batch dispatch data must be a JSON list"))
	return payload


def _update_packing_batches(
	batch_dispatches,
	*,
	cancelled,
	expected_finishing_plan=None,
):
	plans = set()
	boxes_by_plan = {}
	pieces_by_plan = {}
	for batch in batch_dispatches:
		if not isinstance(batch, dict):
			frappe.throw(_("Each packing batch dispatch row must be an object"))
		batch_row = batch.get("batch_row")
		finishing_plan = batch.get("finishing_plan") or expected_finishing_plan
		boxes = flt(batch.get("box_quantity"))
		if not batch_row or not finishing_plan or boxes <= 0:
			frappe.throw(_("Packing batch, Finishing Plan, and a positive box quantity are required"))
		if expected_finishing_plan and finishing_plan != expected_finishing_plan:
			frappe.throw(
				_("Packing batch belongs to Finishing Plan {0}, expected {1}").format(
					finishing_plan, expected_finishing_plan
				)
			)

		batch_values = frappe.db.get_value(
			'SD YRP GRN Packing Batch',
			batch_row,
			["parent", "box_quantity", "dispatched_boxes"],
			as_dict=True,
		)
		if not batch_values:
			frappe.throw(_("Packing batch {0} does not exist").format(batch_row))
		if batch.get("grn") and batch.get("grn") != batch_values.parent:
			frappe.throw(
				_("Packing batch {0} does not belong to GRN {1}").format(
					batch_row, batch.get("grn")
				)
			)

		current = flt(batch_values.dispatched_boxes)
		updated = current - boxes if cancelled else current + boxes
		if updated < -1e-6 or updated > flt(batch_values.box_quantity) + 1e-6:
			frappe.throw(
				_("Packing batch {0} dispatch would be outside 0–{1} boxes").format(
					batch_row, batch_values.box_quantity
				)
			)
		frappe.db.set_value(
			'SD YRP GRN Packing Batch', batch_row, "dispatched_boxes", max(updated, 0)
		)

		size_pieces = update_if_string_instance(batch.get("size_pieces")) or {}
		plans.add(finishing_plan)
		boxes_by_plan[finishing_plan] = boxes_by_plan.get(finishing_plan, 0) + boxes
		pieces_by_plan[finishing_plan] = pieces_by_plan.get(finishing_plan, 0) + sum(
			flt(quantity) for quantity in size_pieces.values()
		)
	return plans, boxes_by_plan, pieces_by_plan


def _update_incomplete_transfer_tracking(stock_entry, *, cancelled):
	if stock_entry.purpose == "GRN Completion" and stock_entry.against_id:
		_update_grn_transfer_tracking(stock_entry.against_id, cancelled=cancelled)
	elif stock_entry.purpose == "DC Completion" and stock_entry.against_id:
		_update_dc_transfer_tracking(stock_entry.against_id, cancelled=cancelled)


def _update_grn_transfer_tracking(grn_name, *, cancelled):
	finishing_process = frappe.db.get_single_value(
		'SD YRP MRP Settings', "finishing_inward_process"
	)
	if not finishing_process:
		return
	process_name, lot = frappe.db.get_value(
		'YRP Goods Received Note', grn_name, ["process_name", "lot"]
	) or (None, None)
	if not process_name or not lot:
		return

	processes = [process_name]
	if frappe.db.get_value('YRP Process', process_name, "is_group"):
		processes = frappe.get_all(
			'YRP Process Details',
			filters={"parent": process_name},
			pluck="process_name",
		)
	if finishing_process not in processes:
		return

	finishing_plan = frappe.db.get_value('SD YRP Finishing Plan', {"lot": lot}, "name")
	if not finishing_plan:
		return
	finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_plan)
	entries = update_if_string_instance(finishing_doc.incomplete_transfer_grn_list) or {}
	if cancelled:
		entries[grn_name] = True
	else:
		entries.pop(grn_name, None)
	finishing_doc.incomplete_transfer_grn_list = frappe.json.dumps(entries)
	finishing_doc.save(ignore_permissions=True)


def _update_dc_transfer_tracking(delivery_challan, *, cancelled):
	lot = frappe.db.get_value('YRP Delivery Challan', delivery_challan, "lot")
	finishing_plan = frappe.db.get_value('SD YRP Finishing Plan', {"lot": lot}, "name")
	if not finishing_plan:
		return
	finishing_doc = frappe.get_doc('SD YRP Finishing Plan', finishing_plan)
	entries = update_if_string_instance(finishing_doc.incomplete_transfer_dc_list) or {}
	if cancelled:
		entries[delivery_challan] = True
	else:
		entries.pop(delivery_challan, None)
	finishing_doc.incomplete_transfer_dc_list = frappe.json.dumps(entries)
	finishing_doc.save(ignore_permissions=True)

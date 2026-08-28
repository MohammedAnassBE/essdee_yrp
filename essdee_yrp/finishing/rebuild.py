"""Idempotent Finishing Plan rebuild and supporting Desk read actions."""

import frappe
from frappe.utils import flt

from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.status import apply_auto_fp_status
from yrp.utils import get_variant_attr_details, update_if_string_instance


def get_process_work_orders(process, lot):
	"""Return submitted non-rework WOs for a process or a process group."""
	if not process or not lot:
		return []
	process_names = frappe.get_all(
		"Process Details",
		filters={"process_name": process},
		pluck="parent",
	)
	process_names.append(process)
	return frappe.get_all(
		"Work Order",
		filters={
			"lot": lot,
			"docstatus": 1,
			"process_name": ["in", list(dict.fromkeys(process_names))],
			"is_rework": 0,
		},
		pluck="name",
	)


@frappe.whitelist()
def get_incomplete_transfer_docs(lot, doc_name):
	finishing_process = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	if not finishing_process:
		frappe.throw("Set Finishing Inward Process")
	grns = _incomplete_transfer_grns(lot, finishing_process)
	delivery_challans = frappe.get_all(
		"Delivery Challan",
		filters={
			"docstatus": 1,
			"includes_packing": 1,
			"lot": lot,
			"is_internal_unit": 1,
			"transfer_complete": 0,
		},
		pluck="name",
	)
	doc = frappe.get_doc("Finishing Plan", doc_name)
	doc.check_permission("write")
	doc.incomplete_transfer_grn_list = frappe.as_json(dict.fromkeys(grns, True))
	doc.incomplete_transfer_dc_list = frappe.as_json(dict.fromkeys(delivery_challans, True))
	doc.save()
	return {"goods_received_notes": grns, "delivery_challans": delivery_challans}


def _incomplete_transfer_grns(lot, finishing_process=None):
	"""Replay submitted internal-unit GRNs instead of trusting a stale JSON cache."""
	finishing_process = finishing_process or frappe.db.get_single_value(
		"MRP Settings", "finishing_inward_process"
	)
	if not finishing_process:
		return []
	work_orders = get_process_work_orders(finishing_process, lot)
	if not work_orders:
		return []
	return frappe.get_all(
		"Goods Received Note",
		filters={
			"docstatus": 1,
			"against": "Work Order",
			"against_id": ["in", work_orders],
			"lot": lot,
			"is_internal_unit": 1,
			"transfer_complete": 0,
		},
		pluck="name",
	)


def rebuild_finishing_plan(doc_name, *, check_permission=False):
	"""Rebuild all derived Finishing quantities from submitted source documents."""
	# Load the parent and its child rows with the same locking read. Loading first
	# and locking afterward leaves a stale repeatable-read snapshot when two
	# completed Work Order calculations target the same plan concurrently.
	doc = frappe.get_doc("Finishing Plan", doc_name, for_update=True)
	if check_permission:
		doc.check_permission("write")
	work_order = frappe.get_doc("Work Order", doc.work_order)
	default_type, rejected_type = _received_type_defaults()
	items = {}
	for row in work_order.get("work_order_calculated_items") or []:
		key, combination = _row_key(row)
		items.setdefault(key, _empty_finishing_row(row.item_variant, combination))

	finishing_process = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	if not finishing_process:
		frappe.throw("Set Finishing Inward Process")
	for work_order_name in get_process_work_orders(finishing_process, doc.lot):
		_process_work_order_quantities(
			frappe.get_doc("Work Order", work_order_name),
			items,
			default_type,
			rejected_type,
		)

	cutting_process = get_configured_cutting_process(
		production_detail=doc.production_detail,
		lot=doc.lot,
	)
	for work_order_name in get_process_work_orders(cutting_process, doc.lot):
		for row in frappe.get_doc("Work Order", work_order_name).get("work_order_calculated_items") or []:
			if flt(row.received_qty) <= 0:
				continue
			key, _combination = _row_key(row)
			if key in items:
				items[key]["cutting_qty"] += flt(row.received_qty)

	_sync_delivery_challans(doc)
	_sync_incomplete_grns(doc, finishing_process)
	rework = _collect_rework(doc.lot, items, default_type, rejected_type)
	_apply_delivery_challans(doc, items)
	_apply_lot_transfers(doc, items)
	_apply_return_grns(doc, items, rework, default_type, rejected_type)
	_apply_ironing_excess(doc, items)

	detail_rows = []
	rework_rows = []
	for key, values in items.items():
		values["return_qty"] -= values["return_dc_qty"]
		values["pack_return_qty"] -= values["pack_dc_qty"]
		rework_values = rework.get(key)
		values["reworked"] = rework_values["reworked_quantity"] if rework_values else 0
		detail_rows.append(_to_finishing_detail(values))
		if values["rework_qty"] > 0:
			rework_rows.append(
				{
					"item_variant": values["item_variant"],
					"set_combination": values["set_combination"],
					"quantity": values["rework_qty"],
					"reworked_quantity": (
						rework_values["reworked_quantity"] if rework_values else 0
					),
					"rejected_qty": rework_values["rejected_qty"] if rework_values else 0,
				}
			)
	doc.set("finishing_plan_details", detail_rows)
	doc.set("finishing_plan_reworked_details", rework_rows)
	apply_auto_fp_status(doc)
	doc.save(ignore_permissions=not check_permission)
	return doc.name


def _sync_incomplete_grns(doc, finishing_process=None):
	doc.incomplete_transfer_grn_list = frappe.as_json(
		dict.fromkeys(
			_incomplete_transfer_grns(doc.lot, finishing_process), True
		)
	)


def _sync_delivery_challans(doc):
	"""Rebuild the FP's DC references from submitted stock documents."""
	rows = frappe.get_all(
		"Delivery Challan",
		filters={
			"lot": doc.lot,
			"docstatus": 1,
			"includes_packing": 1,
		},
		fields=[
			"name",
			"creation",
			"posting_date",
			"is_internal_unit",
			"transfer_complete",
		],
		order_by="creation asc",
	)
	doc.dc_list = frappe.as_json(
		{
			row.name: row.creation.strftime("%d-%m-%Y %H:%M:%S")
			for row in rows
		}
	)
	posting_dates = [row.posting_date for row in rows if row.posting_date]
	doc.finishing_start_date = min(posting_dates) if posting_dates else None
	doc.incomplete_transfer_dc_list = frappe.as_json(
		{
			row.name: True
			for row in rows
			if row.is_internal_unit and not row.transfer_complete
		}
	)


@frappe.whitelist()
def fetch_quantity(doc_name):
	return rebuild_finishing_plan(doc_name, check_permission=True)


def sync_finishing_plans_from_work_order(doc):
	"""Refresh affected plans from one fully persisted source Work Order projection.

	The Work Order calculated-item rows are the source of truth. Rebuilding from
	them keeps DC, GRN, return, cancellation, and retry paths idempotent instead
	of trying to reverse individual Finishing Plan counters. Call this only after
	the piece projection has finished; a job-enqueue or intermediate document-save
	event is not an authoritative completion boundary.
	"""
	if doc.docstatus not in (1, 2) or doc.get("is_rework") or not doc.get("lot"):
		return []

	finishing_process = frappe.db.get_single_value(
		"MRP Settings", "finishing_inward_process"
	)
	plans = frappe.get_all(
		"Finishing Plan",
		filters={"lot": doc.lot},
		fields=["name", "production_detail"],
		order_by="creation asc",
	)
	updated = []
	for plan in plans:
		cutting_process = get_configured_cutting_process(
			production_detail=plan.production_detail,
			lot=doc.lot,
		)
		if not (
			_process_matches_configured(doc.process_name, finishing_process)
			or _process_matches_configured(doc.process_name, cutting_process)
		):
			continue
		rebuild_finishing_plan(plan.name, check_permission=False)
		updated.append(plan.name)
	return updated


def on_work_order_lifecycle_change(doc, method=None):
	"""Handle submit/cancel, whose lifecycle event is itself the final boundary."""
	del method
	return sync_finishing_plans_from_work_order(doc)


def _process_matches_configured(process_name, configured_process):
	if not process_name or not configured_process:
		return False
	if process_name == configured_process:
		return True
	if not frappe.db.get_value("Process", process_name, "is_group"):
		return False
	return bool(
		frappe.db.exists(
			"Process Details",
			{"parent": process_name, "process_name": configured_process},
		)
	)


def _process_work_order_quantities(work_order, items, default_type, rejected_type):
	for row in work_order.get("work_order_calculated_items") or []:
		if flt(row.quantity) <= 0:
			continue
		key, _combination = _row_key(row)
		if key not in items:
			continue
		values = items[key]
		values["delivered_quantity"] += flt(row.received_qty)
		values["inward_quantity"] += flt(row.delivered_quantity)
		for received_type, quantity in (
			update_if_string_instance(row.received_type_json) or {}
		).items():
			quantity = flt(quantity)
			values["received_types"][received_type] = (
				values["received_types"].get(received_type, 0) + quantity
			)
			if received_type == default_type:
				values["accepted_qty"] += quantity
			elif received_type == rejected_type:
				values["rejected_qty"] += quantity
			else:
				values["rework_qty"] += quantity


def _collect_rework(lot, items, default_type, rejected_type):
	rework = {}
	for name in frappe.get_all("GRN Rework Item", filters={"lot": lot}, pluck="name"):
		doc = frappe.get_doc("GRN Rework Item", name)
		from_finishing = frappe.db.get_value(
			"Goods Received Note", doc.grn_number, "from_finishing"
		)
		for row in doc.get("grn_rework_item_details") or []:
			key, _combination = _row_key(row)
			values = rework.setdefault(key, {"quantity": 0, "reworked_quantity": 0, "rejected_qty": 0})
			values["quantity"] += flt(row.quantity)
			# Rejection is editable/provisional until Complete Rework posts the
			# Received Type conversion.  Do not let an unrelated idempotent plan
			# rebuild report that unposted draft quantity as Rejected stock.
			if row.get("completed"):
				values["rejected_qty"] += flt(row.get("rejection"))
			if from_finishing and key in items:
				items[key]["rework_qty"] += flt(row.quantity)
		for row in doc.get("grn_reworked_item_details") or []:
			key, _combination = _row_key(row)
			values = rework.setdefault(key, {"quantity": 0, "reworked_quantity": 0, "rejected_qty": 0})
			values["reworked_quantity"] += flt(row.quantity)
	_apply_rework_work_order_receipts(lot, items, rework, default_type, rejected_type)
	return rework


def _apply_rework_work_order_receipts(lot, items, rework, default_type, rejected_type):
	"""Project submitted generic rework results without duplicating inward."""
	rework_work_orders = frappe.get_all(
		"Work Order",
		filters={"lot": lot, "docstatus": 1, "is_rework": 1},
		pluck="name",
	)
	if not rework_work_orders:
		return
	rework_grns = frappe.get_all(
		"Goods Received Note",
		filters={
			"against": "Work Order",
			"against_id": ["in", rework_work_orders],
			"docstatus": 1,
			"is_return": 0,
		},
		pluck="name",
	)
	if not rework_grns:
		return
	receipt_rows = frappe.get_all(
		"Goods Received Note Item",
		filters={
			"parent": ["in", rework_grns],
			"parenttype": "Goods Received Note",
		},
		fields=[
			"item_variant",
			"quantity",
			"received_type",
			"set_combination",
		],
		limit_page_length=0,
	)
	_apply_rework_receipt_rows(
		receipt_rows, items, rework, default_type, rejected_type
	)


def _apply_rework_receipt_rows(rows, items, rework, default_type, rejected_type):
	for row in rows:
		key, _combination = _row_key(row)
		if key not in items:
			continue
		values = rework.setdefault(
			key, {"quantity": 0, "reworked_quantity": 0, "rejected_qty": 0}
		)
		received_type = row.get("received_type") or default_type
		if received_type == default_type:
			values["reworked_quantity"] += flt(row.quantity)
		elif received_type == rejected_type:
			values["rejected_qty"] += flt(row.quantity)


def _apply_delivery_challans(doc, items):
	for name in (update_if_string_instance(doc.dc_list) or {}):
		if frappe.db.get_value("Delivery Challan", name, "docstatus") != 1:
			continue
		delivery_challan = frappe.get_doc("Delivery Challan", name)
		for row in delivery_challan.get("items") or []:
			key, _combination = _row_key(row)
			if key not in items:
				continue
			quantity = flt(row.stock_qty) or flt(row.delivered_quantity)
			items[key]["dc_qty"] += quantity
			if delivery_challan.get("loose_piece_dc"):
				items[key]["return_dc_qty"] += quantity
			if delivery_challan.get("pack_piece_dc"):
				items[key]["pack_dc_qty"] += quantity


def _apply_lot_transfers(doc, items):
	for name in (update_if_string_instance(doc.lot_transfer_list) or {}):
		if frappe.db.get_value("Lot Transfer", name, "docstatus") != 1:
			continue
		for row in frappe.get_doc("Lot Transfer", name).get("items") or []:
			key = _key(row.item, row.set_combination)
			if key in items:
				items[key]["lot_transferred"] += flt(row.qty)


def _apply_return_grns(doc, items, rework, default_type, rejected_type):
	grns = set(update_if_string_instance(doc.return_grn_list) or {})
	grns.update(update_if_string_instance(doc.pack_return_list) or {})
	for name in grns:
		if frappe.db.get_value("Goods Received Note", name, "docstatus") != 1:
			continue
		grn = frappe.get_doc("Goods Received Note", name)
		for row in grn.get("items") or []:
			key, _combination = _row_key(row)
			if key not in items:
				continue
			quantity = flt(row.quantity)
			received_type = row.get("received_type") or default_type
			if received_type != default_type:
				values = rework.setdefault(key, {"quantity": 0, "reworked_quantity": 0, "rejected_qty": 0})
				values["quantity"] += quantity
				if received_type == rejected_type:
					values["rejected_qty"] += quantity
				items[key]["accepted_qty"] -= quantity
			else:
				fieldname = "pack_return_qty" if grn.get("is_pack") else "return_qty"
				items[key][fieldname] += quantity
			items[key]["dc_qty"] -= quantity


def _apply_ironing_excess(doc, items):
	for name in (update_if_string_instance(doc.ironing_excess_list) or {}):
		if frappe.db.get_value("Stock Entry", name, "docstatus") != 1:
			continue
		for row in frappe.get_doc("Stock Entry", name).get("items") or []:
			key = _key(row.item, row.set_combination)
			if key in items:
				items[key]["ironing_excess"] += flt(row.qty)


def _empty_finishing_row(item_variant, combination):
	return {
		"item_variant": item_variant,
		"set_combination": frappe.as_json(combination),
		"received_types": {},
		"inward_quantity": 0,
		"delivered_quantity": 0,
		"cutting_qty": 0,
		"accepted_qty": 0,
		"rework_qty": 0,
		"lot_transferred": 0,
		"ironing_excess": 0,
		"reworked": 0,
		"dc_qty": 0,
		"return_qty": 0,
		"pack_return_qty": 0,
		"return_dc_qty": 0,
		"pack_dc_qty": 0,
		"transferred_qty": 0,
		"rejected_qty": 0,
	}


def _to_finishing_detail(values):
	return {
		"item_variant": values["item_variant"],
		"set_combination": values["set_combination"],
		"received_type_json": frappe.as_json(values["received_types"]),
		**{
			fieldname: values[fieldname]
			for fieldname in (
				"inward_quantity",
				"delivered_quantity",
				"cutting_qty",
				"accepted_qty",
				"lot_transferred",
				"ironing_excess",
				"reworked",
				"dc_qty",
				"return_qty",
				"pack_return_qty",
				"return_dc_qty",
				"pack_dc_qty",
				"transferred_qty",
				"rejected_qty",
			)
		},
	}


def _row_key(row):
	combination = json_object(row.set_combination)
	return (row.item_variant, tuple(sorted(combination.items()))), combination


def _key(item_variant, set_combination):
	combination = json_object(set_combination)
	return item_variant, tuple(sorted(combination.items()))


def _received_type_defaults():
	settings = frappe.get_cached_doc("YRP Stock Settings")
	return settings.default_received_type, settings.default_rejected_received_type


def get_configured_cutting_process(*, production_detail=None, lot=None):
	if not production_detail and lot:
		production_detail = frappe.db.get_value("Lot", lot, "production_detail")
	if production_detail:
		process = frappe.get_cached_value(
			"Item Production Detail", production_detail, "cutting_process"
		)
		if process:
			return process
	if frappe.get_meta("MRP Settings").has_field("cutting_process"):
		return frappe.db.get_single_value("MRP Settings", "cutting_process") or "Cutting"
	return "Cutting"


def _configured_cutting_process(production_detail=None, lot=None):
	"""Compatibility alias for callers migrated before IPD-aware configuration."""
	return get_configured_cutting_process(
		production_detail=production_detail,
		lot=lot,
	)

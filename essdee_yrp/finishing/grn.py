"""Essdee Finishing side effects for the generic YRP Goods Received Note."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime

from essdee_yrp.finishing.packing import rebuild_finishing_packing_quantities
from essdee_yrp.finishing.parsing import json_object
from essdee_yrp.finishing.state import (
	get_finishing_plan_dict,
	get_finishing_plan_list,
	get_finishing_rework_dict,
	get_finishing_rework_list,
)
from essdee_yrp.finishing.status import apply_auto_fp_status
from yrp.utils import update_if_string_instance


def before_cancel(grn, method=None):
	"""Do not cancel a packing GRN while any of its boxes are dispatched."""
	if not grn.get("includes_packing"):
		return
	dispatched_batch = next(
		(
			row
			for row in grn.get("packing_batches") or []
			if flt(row.get("dispatched_boxes")) > 0
		),
		None,
	)
	if dispatched_batch:
		frappe.throw(
			_("Cancel the related Finishing Plan dispatch entries before cancelling this GRN")
		)


def on_submit(grn, method=None):
	apply_goods_received_note(grn, cancelled=False)


def on_cancel(grn, method=None):
	apply_goods_received_note(grn, cancelled=True)


def apply_goods_received_note(grn, *, cancelled):
	"""Apply or reverse only the Finishing-owned state derived from a GRN."""
	if grn.against != "Work Order" or not grn.get("lot"):
		return
	if not (grn.get("includes_packing") or _is_finishing_inward_process(grn.process_name)):
		return

	finishing_plan_name = frappe.db.get_value(
		"Finishing Plan",
		{"lot": grn.lot},
		"name",
	)
	if not finishing_plan_name:
		return
	if grn.get("is_rework"):
		# Rework receipts resolve an existing non-default inward quantity; they
		# are not another finishing inward. Rebuild from submitted source state
		# so submit/cancel and retries remain symmetric and idempotent.
		from essdee_yrp.finishing.rebuild import rebuild_finishing_plan

		rebuild_finishing_plan(finishing_plan_name, check_permission=False)
		return

	finishing_doc = frappe.get_doc("Finishing Plan", finishing_plan_name)
	if grn.get("includes_packing") and not grn.get("is_return"):
		_update_packing_receipt(finishing_doc, grn, cancelled=cancelled)
	elif grn.get("is_return"):
		_update_return_receipt(finishing_doc, grn, cancelled=cancelled)
	else:
		_update_finishing_inward(finishing_doc, grn, cancelled=cancelled)

	apply_auto_fp_status(finishing_doc)
	finishing_doc.save(ignore_permissions=True)


def _update_packing_receipt(finishing_doc, grn, *, cancelled):
	rebuild_finishing_packing_quantities(finishing_doc)
	if grn.get("from_finishing"):
		grn_list = update_if_string_instance(finishing_doc.grn_list) or {}
		if cancelled:
			grn_list.pop(grn.name, None)
		else:
			grn_list[grn.name] = now_datetime().strftime("%d-%m-%Y %H:%M:%S")
		finishing_doc.grn_list = frappe.as_json(grn_list)
		_recalculate_finishing_end_date(finishing_doc, grn, grn_list, cancelled)


def _recalculate_finishing_end_date(finishing_doc, grn, grn_list, cancelled):
	if cancelled:
		remaining_dates = [
			frappe.db.get_value("Goods Received Note", name, "posting_date")
			for name in grn_list
		]
		remaining_dates = [date for date in remaining_dates if date]
		finishing_doc.finishing_end_date = max(remaining_dates) if remaining_dates else None
		return

	posting_date = grn.get("posting_date") or grn.get("actual_date")
	if posting_date and (
		not finishing_doc.finishing_end_date
		or getdate(posting_date) > getdate(finishing_doc.finishing_end_date)
	):
		finishing_doc.finishing_end_date = posting_date


def _update_return_receipt(finishing_doc, grn, *, cancelled):
	default_type, rejected_type = _received_type_defaults()
	finishing_items = get_finishing_plan_dict(finishing_doc)
	rework_items = get_finishing_rework_dict(finishing_doc)
	operation = -1 if cancelled else 1

	for row in grn.get("items") or []:
		key = _item_key(row)
		if key not in finishing_items:
			continue
		quantity = flt(row.quantity)
		received_type = row.get("received_type") or default_type
		values = finishing_items[key]
		if received_type == default_type:
			fieldname = "pack_return_qty" if grn.get("is_pack") else "return_qty"
			values[fieldname] += operation * quantity
		else:
			rework = rework_items.setdefault(
				key,
				{
					"quantity": 0,
					"reworked_quantity": 0,
					"rejected_qty": 0,
					"set_combination": row.set_combination,
				},
			)
			rework["quantity"] += operation * quantity
			if received_type == rejected_type:
				rework["rejected_qty"] += operation * quantity
			values["accepted_qty"] -= operation * quantity
		values["dc_qty"] -= operation * quantity

	_update_finishing_list_field(finishing_doc, grn, cancelled=cancelled)
	finishing_doc.set("finishing_plan_details", get_finishing_plan_list(finishing_items))
	finishing_doc.set(
		"finishing_plan_reworked_details",
		get_finishing_rework_list(rework_items),
	)


def _update_finishing_list_field(finishing_doc, grn, *, cancelled):
	fieldname = "pack_return_list" if grn.get("is_pack") else "return_grn_list"
	if not grn.get("is_pack") and not grn.get("from_finishing"):
		return
	entries = update_if_string_instance(finishing_doc.get(fieldname)) or {}
	if cancelled:
		entries.pop(grn.name, None)
	else:
		entries[grn.name] = now_datetime().strftime("%d-%m-%Y %H:%M:%S")
	finishing_doc.set(fieldname, frappe.as_json(entries))


def _update_finishing_inward(finishing_doc, grn, *, cancelled):
	default_type, rejected_type = _received_type_defaults()
	finishing_items = get_finishing_plan_dict(finishing_doc)
	rework_items = get_finishing_rework_dict(finishing_doc)
	operation = -1 if cancelled else 1

	for row in grn.get("items") or []:
		key = _item_key(row)
		if key not in finishing_items:
			continue
		quantity = operation * flt(row.quantity)
		received_type = row.get("received_type") or default_type
		values = finishing_items[key]
		values["delivered_quantity"] += quantity
		values["received_types"].setdefault(received_type, 0)
		values["received_types"][received_type] += quantity
		if received_type == default_type:
			values["accepted_qty"] += quantity
		else:
			rework = rework_items.setdefault(
				key,
				{
					"quantity": 0,
					"reworked_quantity": 0,
					"rejected_qty": 0,
					"set_combination": row.set_combination,
				},
			)
			rework["quantity"] += quantity
			if received_type == rejected_type:
				rework["rejected_qty"] += quantity

	finishing_doc.set("finishing_plan_details", get_finishing_plan_list(finishing_items))
	finishing_doc.set(
		"finishing_plan_reworked_details",
		get_finishing_rework_list(rework_items),
	)


def _received_type_defaults():
	settings = frappe.get_cached_doc("YRP Stock Settings")
	return settings.default_received_type, settings.default_rejected_received_type


def _item_key(row):
	set_combination = json_object(row.set_combination)
	return row.item_variant, tuple(sorted(set_combination.items()))


def _is_finishing_inward_process(process_name):
	finishing_process = frappe.db.get_single_value("MRP Settings", "finishing_inward_process")
	if not process_name or not finishing_process:
		return False
	if process_name == finishing_process:
		return True
	if not frappe.db.get_value("Process", process_name, "is_group"):
		return False
	return bool(
		frappe.db.exists(
			"Process Details",
			{"parent": process_name, "process_name": finishing_process},
		)
	)

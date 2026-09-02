"""Synchronize Finishing Plan quantities after packing DC lifecycle events."""

import frappe


def on_submit(delivery_challan, method=None):
	del method
	_sync_finishing_plan(delivery_challan)


def on_cancel(delivery_challan, method=None):
	del method
	_sync_finishing_plan(delivery_challan)


def _sync_finishing_plan(delivery_challan):
	if not delivery_challan.get("includes_packing") or not delivery_challan.get("lot"):
		return
	finishing_plan = frappe.db.get_value(
		'SD YRP Finishing Plan', {"lot": delivery_challan.lot}, "name"
	)
	if not finishing_plan:
		return
	from essdee_yrp.finishing.rebuild import rebuild_finishing_plan

	rebuild_finishing_plan(finishing_plan, check_permission=False)

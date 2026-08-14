"""Essdee Lot entries for YRP's safe UI registry extension points."""

from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import flt

from yrp.yrp.api.ui_metrics import (
	OPEN_WO_FILTERS,
	_received_from_rows,
	_wo_child_rows,
)

OPEN_LOT_FILTERS = [["status", "=", "Open"]]


def _count(doctype, filters):
	rows = frappe.get_list(
		doctype,
		filters=deepcopy(filters),
		fields=[{"COUNT": "name", "as": "value"}],
	)
	return int(rows[0]["value"]) if rows else 0


def _active_lot_names():
	if not frappe.get_meta("Work Order").has_field("lot"):
		return []
	return frappe.get_list(
		"Work Order",
		filters=deepcopy(OPEN_WO_FILTERS) + [["lot", "is", "set"]],
		pluck="lot",
		distinct=True,
		limit=0,
	)


def get_metrics():
	return {
		"open_lots": {
			"label": "Open Lots",
			"doctypes": ["Lot"],
			"compute": lambda: _count("Lot", OPEN_LOT_FILTERS),
			"goto": lambda: {"doctype": "Lot", "filters": deepcopy(OPEN_LOT_FILTERS)},
			"home_queue": True,
		},
		"active_lots": {
			"label": "Active Lots",
			"doctypes": ["Work Order", "Lot"],
			"compute": lambda: len(_active_lot_names()),
			"goto": lambda: {
				"doctype": "Lot",
				"filters": [["name", "in", _active_lot_names()]],
			},
		},
	}


def _calc_lot_balance(params):
	unknown = set(params) - {"lot"}
	if unknown:
		frappe.throw(
			_("Unknown parameter(s) for lot_balance: {0}").format(", ".join(sorted(unknown))),
			title=_("Invalid Calculation Params"),
		)
	lot = params.get("lot")
	if not lot or not isinstance(lot, str):
		frappe.throw(
			_("lot_balance requires a 'lot' parameter (a Lot name)"),
			title=_("Invalid Calculation Params"),
		)
	for doctype in ("Lot", "Work Order"):
		frappe.has_permission(doctype, "read", throw=True)
	if not frappe.db.exists("Lot", lot):
		frappe.throw(_("Lot {0} not found").format(frappe.bold(lot)), frappe.DoesNotExistError)
	frappe.has_permission("Lot", "read", doc=lot, throw=True)
	if not frappe.get_meta("Work Order").has_field("lot"):
		frappe.throw(_("Work Order has no 'lot' dimension field on this site"))

	wo_rows = frappe.get_list(
		"Work Order",
		filters=[["lot", "=", lot], ["docstatus", "=", 1]],
		fields=["name", "planned_quantity"],
		limit=0,
	)
	wo_names = [row.name for row in wo_rows]
	ordered = sum(flt(row.planned_quantity) for row in wo_rows)
	produced = delivered = 0.0
	if wo_names:
		produced = _received_from_rows(
			_wo_child_rows("Work Order Receivables", {"parent": ["in", wo_names]})
		)
		delivered = _received_from_rows(
			_wo_child_rows("Work Order Deliverables", {"parent": ["in", wo_names]})
		)
	balance = max(ordered - produced, 0)
	return {
		"name": "lot_balance",
		"label": _("Lot balance"),
		"params": {"lot": lot},
		"value": balance,
		"lines": [
			[_("Work orders"), len(wo_names)],
			[_("Ordered"), ordered],
			[_("Produced (received back)"), produced],
			[_("Materials delivered to supplier"), delivered],
			[_("Balance to receive"), balance],
		],
	}


def get_calculations():
	return {
		"lot_balance": {
			"label": "Lot balance",
			"run": _calc_lot_balance,
			"params": {
				"lot": {
					"type": "string",
					"required": True,
					"effect": "Name of the Lot to balance (row-level read permission enforced).",
				}
			},
		},
	}

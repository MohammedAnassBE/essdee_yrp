"""Permission-aware web editor and optimizer lifecycle for LaySheet Planner."""

from __future__ import annotations

import json
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet_planner import (
	sd_yrp_cutting_laysheet_planner as native,
)


DOCTYPE = "SD YRP Cutting Laysheet Planner"
ACTIVE_STATUSES = {"Queued", "Running"}
TERMINAL_STATUSES = {"Completed", "Failed"}
EDITABLE_FIELDS = {
	"lot",
	"item",
	"description",
	"max_plies",
	"max_pieces",
	"tolerance_pct",
	"max_lays",
	"tubular",
	"order_details",
}
EDITABLE_ROW_FIELDS = {"name", "_row_key", "size", "qty"}
SUMMARY_FIELDS = {
	"total_lays",
	"unique_markers",
	"avg_pieces_per_ply",
	"total_order",
	"total_cut",
	"overcut",
	"overcut_pct",
	"undercut",
	"undercut_pct",
}


def _parse_json(value, fallback):
	if value in (None, ""):
		return deepcopy(fallback)
	if isinstance(value, (dict, list)):
		return deepcopy(value)
	return frappe.parse_json(value)


def _doc_value(doc, fieldname, default=None):
	value = getattr(doc, fieldname, None)
	if value is not None and not callable(value):
		return value
	return doc.get(fieldname, default) if hasattr(doc, "get") else default


def _allowed(ptype, doc=None):
	kwargs = {"ptype": ptype}
	if doc is not None:
		kwargs["doc"] = doc
	return bool(frappe.has_permission(DOCTYPE, **kwargs))


def _require_permission(ptype, doc=None):
	if not _allowed(ptype, doc):
		frappe.throw(
			_("You do not have {0} permission for Cutting LaySheet Planner.").format(ptype),
			frappe.PermissionError,
		)


def _assert_not_stale(doc, expected_modified=None):
	if expected_modified and str(_doc_value(doc, "modified")) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _optimizer_values(values):
	return {
		"order": {row["size"]: row["qty"] for row in values["order_details"]},
		"max_plies": values["max_plies"],
		"max_pieces": values["max_pieces"],
		"tolerance_pct": values["tolerance_pct"],
		"max_lays": values["max_lays"],
		"tubular": bool(values["tubular"]),
	}


def _normalise_values(values, existing_doc=None):
	values = _parse_json(values, {})
	if not isinstance(values, dict):
		frappe.throw(_("LaySheet Planner values must be an object."))
	unknown = set(values) - EDITABLE_FIELDS
	if unknown:
		frappe.throw(
			_("These LaySheet Planner fields cannot be changed here: {0}.").format(
				", ".join(sorted(unknown))
			)
		)
	rows = _parse_json(values.get("order_details"), [])
	if not isinstance(rows, list):
		frappe.throw(_("Order Details must be a list."))
	existing_names = {
		_doc_value(row, "name")
		for row in (_doc_value(existing_doc, "order_details", []) or [])
		if _doc_value(row, "name")
	}
	seen_names = set()
	seen_sizes = set()
	clean_rows = []
	for index, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			frappe.throw(_("Order row {0} must be an object.").format(index))
		unknown_row = set(row) - EDITABLE_ROW_FIELDS
		if unknown_row:
			frappe.throw(_("Order row {0} contains fields that cannot be changed here.").format(index))
		name = row.get("name") or None
		if name:
			if name not in existing_names:
				frappe.throw(_("Order row {0} does not belong to this Planner.").format(name))
			if name in seen_names:
				frappe.throw(_("Order row {0} is repeated.").format(name))
			seen_names.add(name)
		size = str(row.get("size") or "").strip()
		if not size:
			frappe.throw(_("Size is required in order row {0}.").format(index))
		if size in seen_sizes:
			frappe.throw(_("Duplicate size '{0}' is not allowed.").format(size))
		seen_sizes.add(size)
		qty = row.get("qty")
		if isinstance(qty, bool) or not isinstance(qty, (int, float)) or int(qty) != qty:
			frappe.throw(_("Quantity for size {0} must be a whole number.").format(size))
		clean = {"size": size, "qty": int(qty)}
		if name:
			clean["name"] = name
		clean_rows.append(clean)

	clean_values = {
		"lot": values.get("lot"),
		"item": values.get("item"),
		"description": str(values.get("description") or "").strip(),
		"max_plies": values.get("max_plies"),
		"max_pieces": values.get("max_pieces"),
		"tolerance_pct": 3 if values.get("tolerance_pct") is None else values.get("tolerance_pct"),
		"max_lays": 8 if values.get("max_lays") is None else values.get("max_lays"),
		"tubular": cint(values.get("tubular")),
		"order_details": clean_rows,
	}
	if not clean_values["description"]:
		frappe.throw(_("Description is required."))
	native._validate_optimizer_inputs(_optimizer_values(clean_values))
	return clean_values


def _safe_error(value):
	message = str(value or "").strip()
	if not message:
		return ""
	lower = message.lower()
	if "traceback" in lower or " file \"" in lower or " file /" in lower or ".py\"" in lower:
		return _("Lay optimization failed. Review the inputs and try again.")
	return message.splitlines()[0][:280]


def _safe_result(result, sizes):
	if not isinstance(result, dict) or not result.get("strategy"):
		return None
	per_size = result.get("per_size") or {}
	lays = result.get("lays") or []
	if set(per_size) != set(sizes):
		return None
	clean_lays = []
	for lay in lays:
		if not isinstance(lay, dict):
			return None
		ratio = lay.get("ratio") or {}
		cut_per_size = lay.get("cut_per_size") or {}
		if set(ratio) != set(sizes) or set(cut_per_size) != set(sizes):
			return None
		clean_lays.append(
			{
				"lay_no": lay.get("lay_no"),
				"plies": lay.get("plies"),
				"ratio": {size: ratio.get(size) for size in sizes},
				"pieces_per_ply": lay.get("pieces_per_ply"),
				"total_pieces": lay.get("total_pieces"),
				"cut_per_size": {size: cut_per_size.get(size) for size in sizes},
			}
		)
	return {
		"strategy": result.get("strategy"),
		"strategy_description": str(result.get("strategy_description") or "")[:240],
		"status": result.get("status") or ("success" if result.get("success") else "failed"),
		"summary": {field: (result.get("summary") or {}).get(field) for field in SUMMARY_FIELDS},
		"per_size": {
			size: {
				"order": per_size[size].get("order"),
				"cut": per_size[size].get("cut"),
				"diff": per_size[size].get("diff"),
				"pct": per_size[size].get("pct"),
			}
			for size in sizes
		},
		"lays": clean_lays,
	}


def _normalise_results(payload, sizes):
	payload = payload if isinstance(payload, dict) else {}
	successful = []
	for result in payload.get("results") or []:
		clean = _safe_result(result, sizes)
		if clean:
			successful.append(clean)
	failed = []
	for outcome in payload.get("failed") or []:
		if not isinstance(outcome, dict) or not outcome.get("strategy"):
			continue
		failed.append(
			{
				"strategy": outcome.get("strategy"),
				"status": outcome.get("status") or "failed",
				"error": _safe_error(outcome.get("error")),
				"deduplicated": bool(outcome.get("deduplicated")),
				"same_as": outcome.get("same_as"),
				"dominated": bool(outcome.get("dominated")),
				"dominated_by": outcome.get("dominated_by"),
				"selectable": bool(outcome.get("success")),
			}
		)
	return {
		"successful": successful,
		"failed": failed,
		"optimizer_version": str(payload.get("optimizer_version") or ""),
	}


def _permissions(doc=None):
	return {
		"can_read": _allowed("read", doc),
		"can_create": _allowed("create"),
		"can_write": bool(doc is not None and _allowed("write", doc)),
		"can_print": bool(doc is not None and _allowed("print", doc)),
	}


def _record(doc):
	return {
		"name": _doc_value(doc, "name"),
		"modified": _doc_value(doc, "modified"),
		"docstatus": cint(_doc_value(doc, "docstatus", 0)),
		"lot": _doc_value(doc, "lot"),
		"item": _doc_value(doc, "item"),
		"description": _doc_value(doc, "description"),
		"max_plies": _doc_value(doc, "max_plies"),
		"max_pieces": _doc_value(doc, "max_pieces"),
		"tolerance_pct": 3 if _doc_value(doc, "tolerance_pct") is None else _doc_value(doc, "tolerance_pct"),
		"max_lays": 8 if _doc_value(doc, "max_lays") is None else _doc_value(doc, "max_lays"),
		"tubular": cint(_doc_value(doc, "tubular", 0)),
		"optimization_status": _doc_value(doc, "optimization_status") or "Not Started",
		"optimization_started_on": _doc_value(doc, "optimization_started_on"),
		"optimization_completed_on": _doc_value(doc, "optimization_completed_on"),
		"optimization_error": _safe_error(_doc_value(doc, "optimization_error")),
		"selected_strategy": _doc_value(doc, "selected_strategy"),
		"summary": {
			"total_lays": cint(_doc_value(doc, "total_lays", 0)),
			"total_order": cint(_doc_value(doc, "total_order", 0)),
			"total_cut": cint(_doc_value(doc, "total_cut", 0)),
			"overcut": cint(_doc_value(doc, "overcut", 0)),
			"overcut_pct": flt(_doc_value(doc, "overcut_pct", 0)),
			"undercut": cint(_doc_value(doc, "undercut", 0)),
			"undercut_pct": flt(_doc_value(doc, "undercut_pct", 0)),
		},
		"order_details": [
			{
				"_row_key": _doc_value(row, "name") or f"row-{index}",
				"name": _doc_value(row, "name"),
				"size": _doc_value(row, "size"),
				"qty": cint(_doc_value(row, "qty", 0)),
			}
			for index, row in enumerate(_doc_value(doc, "order_details", []) or [])
		],
	}


def _has_valid_inputs(doc):
	try:
		native._validate_optimizer_inputs(native._get_optimizer_inputs(doc))
		return True
	except Exception:
		return False


def _action_flags(doc, permissions, has_results=False):
	status = _doc_value(doc, "optimization_status") or "Not Started"
	active = status in ACTIVE_STATUSES
	can_edit_inputs = permissions["can_create"] if not _doc_value(doc, "name") else permissions["can_write"]
	can_optimize = bool(_doc_value(doc, "name") and permissions["can_write"] and not active and _has_valid_inputs(doc))
	return {
		"can_edit_inputs": bool(can_edit_inputs and not active),
		"can_optimize": can_optimize,
		"can_retry": bool(status == "Failed" and can_optimize),
		"can_select_result": bool(status == "Completed" and permissions["can_write"] and has_results),
		"should_poll": active,
	}


@frappe.whitelist()
def get_editor(name=None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		_require_permission("read", doc)
		native.recover_stuck_optimization(doc)
	else:
		_require_permission("create")
		doc = frappe.new_doc(DOCTYPE)
		if _doc_value(doc, "max_plies") is None:
			doc.max_plies = 10000
		if _doc_value(doc, "tolerance_pct") is None:
			doc.tolerance_pct = 3
		if _doc_value(doc, "max_lays") is None:
			doc.max_lays = 8
	permissions = _permissions(doc if name else None)
	record = _record(doc)
	stored = _parse_json(_doc_value(doc, "result_json"), {})
	sizes = [row["size"] for row in record["order_details"]]
	results = _normalise_results(stored, sizes)
	return {
		"record": record,
		"results": results,
		"permissions": permissions,
		"actions": _action_flags(doc, permissions, bool(results["successful"])),
	}


@frappe.whitelist()
def save(values, name=None, expected_modified=None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		_require_permission("write", doc)
		_assert_not_stale(doc, expected_modified)
		if (_doc_value(doc, "optimization_status") or "Not Started") in ACTIVE_STATUSES:
			frappe.throw(_("Inputs cannot be changed while lay optimization is queued or running."))
	else:
		_require_permission("create")
		doc = frappe.new_doc(DOCTYPE)
	clean = _normalise_values(values, doc if name else None)
	doc.update(clean)
	if name:
		doc.save()
	else:
		doc.insert()
	return get_editor(doc.name)


@frappe.whitelist()
def start_optimization(name, expected_modified=None):
	doc = frappe.get_doc(DOCTYPE, name)
	_require_permission("write", doc)
	_assert_not_stale(doc, expected_modified)
	if (_doc_value(doc, "optimization_status") or "Not Started") in ACTIVE_STATUSES:
		frappe.throw(_("Optimization is already {0}.").format(doc.optimization_status.lower()))
	native.optimize(name)
	return get_status(name)


@frappe.whitelist()
def get_status(name):
	doc = frappe.get_doc(DOCTYPE, name)
	_require_permission("read", doc)
	native.recover_stuck_optimization(doc)
	status = _doc_value(doc, "optimization_status") or "Not Started"
	permissions = _permissions(doc)
	return {
		"name": doc.name,
		"status": status,
		"error_message": _safe_error(_doc_value(doc, "optimization_error")),
		"started_on": _doc_value(doc, "optimization_started_on"),
		"completed_on": _doc_value(doc, "optimization_completed_on"),
		"modified": _doc_value(doc, "modified"),
		"terminal": status in TERMINAL_STATUSES,
		"actions": _action_flags(doc, permissions, bool(_doc_value(doc, "result_json"))),
	}


@frappe.whitelist()
def select_result(name, strategy, expected_modified=None):
	doc = frappe.get_doc(DOCTYPE, name)
	_require_permission("write", doc)
	_assert_not_stale(doc, expected_modified)
	if (_doc_value(doc, "optimization_status") or "Not Started") != "Completed":
		frappe.throw(_("Only completed optimization results can be selected."))
	payload = _parse_json(_doc_value(doc, "result_json"), {})
	current_values = native._get_optimizer_inputs(doc)
	if native._input_fingerprint(payload.get("input") or {}) != native._input_fingerprint(current_values):
		frappe.throw(_("Planner inputs changed after this result was generated. Run Optimize again."))
	successful = {result.get("strategy") for result in payload.get("results") or [] if result.get("success")}
	selectable_outcomes = {
		outcome.get("strategy")
		for outcome in payload.get("failed") or []
		if outcome.get("success") and (outcome.get("deduplicated") or outcome.get("dominated"))
	}
	if strategy not in successful | selectable_outcomes:
		frappe.throw(_("Strategy '{0}' is not available for selection.").format(strategy))
	native.select_strategy(name, strategy)
	return get_editor(name)

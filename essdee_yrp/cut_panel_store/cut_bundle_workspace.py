"""Cut Bundle Edit services for the Cut Panel Store browser workspace."""

from __future__ import annotations

import json
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate, nowtime
from yrp.attribute_links import value as attribute_value

from essdee_yrp.cut_panel_store.common import assert_expected_modified, parse_json_object
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_edit.sd_yrp_cut_bundle_edit import (
	get_major_colours,
	get_major_set_colours,
	print_labels,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement import (
	_get_cut_bundle_unmoved_data as get_cut_bundle_unmoved_data,
)

CUT_BUNDLE_DOCTYPE = "SD YRP Cut Bundle Edit"


def _json_value(value, default):
	if value in (None, ""):
		return deepcopy(default)
	parsed = frappe.parse_json(value) if isinstance(value, str) else value
	return deepcopy(parsed if isinstance(parsed, type(default)) else default)


def _document_permission(doc, ptype: str) -> bool:
	"""Quiet capability probe: a denied check must not surface Frappe's permission message."""
	return bool(frappe.has_permission(doc.doctype, ptype=ptype, doc=doc))


def _context(doc=None, source=None) -> frappe._dict:
	source = parse_json_object(source, label=_("Source"))
	lot = doc.lot if doc else source.get("lot")
	warehouse = doc.warehouse if doc else source.get("warehouse")
	item = doc.item if doc else None
	if lot:
		lot_doc = frappe.get_doc("SD YRP Lot", lot)
		lot_doc.check_permission("read")
		item = lot_doc.item
	return frappe._dict(lot=lot, warehouse=warehouse, item=item)


def _require_source(context) -> None:
	if not context.lot:
		frappe.throw(_("Select a Lot before fetching bundles."))
	if not context.warehouse:
		frappe.throw(_("Select a Warehouse before fetching bundles."))
	if not context.item:
		frappe.throw(_("Lot {0} has no Item.").format(context.lot))


def _permissions(doc=None) -> dict:
	return {
		"can_create": bool(frappe.has_permission(CUT_BUNDLE_DOCTYPE, ptype="create")),
		"can_write": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "write")),
		"can_submit": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "submit")),
		"can_cancel": bool(doc and cint(doc.docstatus) == 1 and _document_permission(doc, "cancel")),
		"can_amend": bool(doc and cint(doc.docstatus) == 2 and _document_permission(doc, "amend")),
		"can_print": bool(doc and cint(doc.docstatus) == 1 and not doc.printed_time and _document_permission(doc, "print")),
	}


def _record_payload(doc) -> dict:
	inputs = _json_value(doc.input_json, [])
	outputs = _json_value(doc.output_json, [])
	bundles = _json_value(doc.cut_panel_movement_json, {})
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"status": {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(cint(doc.docstatus), _("Unknown")),
		"lot": doc.lot,
		"warehouse": doc.warehouse,
		"item": doc.item,
		"colour": doc.colour,
		"posting_date": doc.posting_date,
		"posting_time": doc.posting_time,
		"printed_time": doc.printed_time,
		"modified": doc.modified,
		"inputs": inputs,
		"outputs": outputs,
		"movement_data": {
			"bundles": bundles,
			"inputs": inputs,
			"outputs": outputs,
			"selected_colour": doc.colour,
		},
		"permissions": _permissions(doc),
	}


def _editor_payload(context, doc=None) -> dict:
	return {
		"context": context,
		"record": _record_payload(doc) if doc else None,
		"defaults": {
			"lot": context.lot,
			"warehouse": context.warehouse,
			"item": context.item,
			"posting_date": doc.posting_date if doc else nowdate(),
			"posting_time": doc.posting_time if doc else nowtime(),
			"selected_colour": doc.colour if doc else None,
		},
		"permissions": _permissions(doc),
	}


@frappe.whitelist()
def get_cut_bundle_editor(name: str | None = None, source=None) -> dict:
	if name:
		doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
		doc.check_permission("read")
		return _editor_payload(_context(doc=doc), doc)
	frappe.has_permission(CUT_BUNDLE_DOCTYPE, ptype="create", throw=True)
	return _editor_payload(_context(source=source))


def _empty_available() -> dict:
	return {"panels": [], "data": {}, "collapsed_details": [], "accessory_data": [], "is_set_item": 0}


def _source_snapshot(context, values=None) -> dict:
	values = parse_json_object(values)
	_require_source(context)
	if not frappe.db.exists("Supplier", context.warehouse):
		frappe.throw(_("Supplier {0} does not exist.").format(context.warehouse))
	posting_date = values.get("posting_date") or nowdate()
	posting_time = values.get("posting_time") or nowtime()
	choices = get_major_colours(posting_date, posting_time, context.warehouse, context.lot) or {}
	selected_colour = values.get("selected_colour") or values.get("colour")
	available = _empty_available()
	if selected_colour:
		if selected_colour not in (choices.get("colours") or []):
			frappe.throw(_("Selected Colour is no longer available. Fetch bundles again."))
		available = get_cut_bundle_unmoved_data(
			context.warehouse,
			context.lot,
			posting_date,
			posting_time,
			0,
			get_collapsed=True,
			bundle_colour=selected_colour,
		) or _empty_available()
	return {"context": context, "choices": choices, "available": available}


@frappe.whitelist()
def preview_cut_bundle_source(lot=None, warehouse=None, values=None, name=None) -> dict:
	if name:
		doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
		doc.check_permission("write")
		context = _context(doc=doc)
	else:
		frappe.has_permission(CUT_BUNDLE_DOCTYPE, ptype="create", throw=True)
		context = _context(source={"lot": lot, "warehouse": warehouse})
	return _source_snapshot(context, values)


def _plain(value):
	return attribute_value(value)


def _normalised_panel(value) -> str:
	return ",".join(_split_panels(value))


def _combination_identity(value) -> str:
	if isinstance(value, str):
		value = frappe.parse_json(value) or {}
	return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)


def _row_identity(row, panel=None, *, include_combination=True, include_collapsed=True) -> tuple:
	return (
		cint(row.get("lay_no")),
		cint(row.get("bundle_no")),
		str(_plain(row.get("size")) or ""),
		str(_plain(row.get("colour")) or ""),
		_normalised_panel(panel if panel is not None else row.get("panel")),
		str(row.get("shade") or ""),
		*([bool(cint(row.get("is_collapsed")))] if include_collapsed else []),
		*([_combination_identity(row.get("set_combination"))] if include_combination else []),
	)


def _split_panels(value) -> list[str]:
	return [part.strip() for part in str(_plain(value) or "").split(",") if part.strip()]


def _available_input_rows(available) -> dict[tuple, dict]:
	rows = {}
	physical_identities = {}
	panels = available.get("panels") or []
	for colour, detail in (available.get("data") or {}).items():
		group_panels = panels if isinstance(panels, list) else panels.get(detail.get("part"), [])
		for source in detail.get("data") or []:
			for panel in group_panels:
				qty = flt(source.get(panel))
				if qty <= 0:
					continue
				row = {
					"lay_no": cint(source.get("lay_no")),
					"bundle_no": cint(source.get("bundle_no")),
					"qty": qty,
					"panel": panel,
					"set_combination": deepcopy(source.get("set_combination") or {}),
					"shade": source.get("shade") or "",
					"size": _plain(source.get("size")),
					"colour": _plain(source.get(f"{panel}_colour")) or _plain(colour),
					"is_collapsed": False,
				}
				physical = _row_identity(row, include_combination=False)
				if physical in physical_identities and physical_identities[physical] != _combination_identity(row.get("set_combination")):
					frappe.throw(_("Bundle stock has an ambiguous set combination. Correct the ledger before editing this bundle."))
				physical_identities[physical] = _combination_identity(row.get("set_combination"))
				rows[_row_identity(row)] = row
	for source in available.get("collapsed_details") or []:
		qty = flt(source.get("quantity"))
		if qty <= 0:
			continue
		row = {
			"lay_no": cint(source.get("lay_no")),
			"bundle_no": cint(source.get("bundle_no")),
			"qty": qty,
			"panel": _plain(source.get("panel")),
			"set_combination": deepcopy(source.get("set_combination") or {}),
			"shade": source.get("shade") or "",
			"size": _plain(source.get("size")),
			"colour": _plain(source.get("colour")),
			"is_collapsed": True,
		}
		physical = _row_identity(row, include_combination=False)
		if physical in physical_identities and physical_identities[physical] != _combination_identity(row.get("set_combination")):
			frappe.throw(_("Bundle stock has an ambiguous set combination. Correct the ledger before editing this bundle."))
		physical_identities[physical] = _combination_identity(row.get("set_combination"))
		rows[_row_identity(row)] = row
	return rows


def _choice_panels(choices) -> set[str]:
	panels = choices.get("panels") or []
	if isinstance(panels, dict):
		return {str(_plain(panel)) for group in panels.values() for panel in (group or [])}
	return {str(_plain(panel)) for panel in panels}


def _canonical_inputs(available, input_rows) -> list[dict]:
	known = _available_input_rows(available)
	canonical = []
	seen = set()
	for client in input_rows or []:
		panels = _split_panels(client.get("panel"))
		if not panels:
			frappe.throw(_("Every input bundle needs at least one Panel."))
		key = _row_identity({**client, "panel": ",".join(panels)})
		server = known.get(key)
		if not server or flt(client.get("qty")) != flt(server.get("qty")):
			frappe.throw(_("Bundle stock changed while this edit was open. Fetch bundles again."))
		if key in seen:
			frappe.throw(_("The same input bundle cannot be selected twice."))
		seen.add(key)
		first = deepcopy(server)
		first["panel"] = _normalised_panel(server.get("panel"))
		first["set_combination"] = deepcopy(server.get("set_combination") or {})
		canonical.append(first)
	if not canonical:
		frappe.throw(_("Select at least one input bundle."))
	return canonical


def _canonical_outputs(output_rows, choices, lot) -> list[dict]:
	allowed_colours = {str(_plain(value)) for value in choices.get("colours") or []}
	allowed_sizes = {str(_plain(value)) for value in choices.get("sizes") or []}
	allowed_panels = _choice_panels(choices)
	canonical = []
	seen = set()
	for client in output_rows or []:
		panels = _split_panels(client.get("panel"))
		colour = str(_plain(client.get("colour")) or "")
		size = str(_plain(client.get("size")) or "")
		qty = flt(client.get("qty"))
		if not panels or any(panel not in allowed_panels for panel in panels):
			frappe.throw(_("An output bundle contains an invalid Panel."))
		if colour not in allowed_colours or size not in allowed_sizes:
			frappe.throw(_("An output bundle contains an invalid Colour or Size."))
		if qty <= 0 or qty != cint(qty) or cint(client.get("lay_no")) <= 0 or cint(client.get("bundle_no")) <= 0:
			frappe.throw(_("Output bundle Lay, Bundle and Quantity values must be greater than zero."))
		if not str(client.get("shade") or "").strip():
			frappe.throw(_("Every output bundle needs a Shade."))
		canonical_panel = ",".join(panels)
		identity = _row_identity({**client, "panel": canonical_panel, "is_collapsed": False}, include_combination=False, include_collapsed=False)
		if identity in seen:
			frappe.throw(_("Output bundle identities must be unique."))
		seen.add(identity)
		set_combination = get_major_set_colours(colour, panels[0], lot) or {}
		client_combination = client.get("set_combination") or {}
		if isinstance(client_combination, str):
			client_combination = frappe.parse_json(client_combination) or {}
		for key in ("major_colour", "set_colour"):
			if key in set_combination and set_combination[key] is None:
				selected = str(_plain(client_combination.get(key)) or "")
				if selected not in allowed_colours:
					frappe.throw(_("Select a valid {0} for the output bundle.").format(_(key.replace("_", " ").title())))
				set_combination[key] = selected
		canonical.append({
			"lay_no": cint(client.get("lay_no")),
			"bundle_no": cint(client.get("bundle_no")),
			"qty": qty,
			"panel": canonical_panel,
			"set_combination": set_combination,
			"shade": str(client.get("shade") or ""),
			"size": size,
			"colour": colour,
		})
	if not canonical:
		frappe.throw(_("Create at least one output bundle."))
	return canonical


def _quantity_map(rows) -> dict[tuple, float]:
	result = {}
	for row in rows:
		for panel in _split_panels(row.get("panel")):
			key = (str(_plain(row.get("size")) or ""), str(_plain(row.get("colour")) or ""), panel)
			result[key] = result.get(key, 0) + flt(row.get("qty"))
	return result


def _movement_with_inputs(available, input_rows) -> dict:
	movement = deepcopy(available)
	selected = {_row_identity(row) for row in input_rows}
	panels = movement.get("panels") or []
	for colour, detail in (movement.get("data") or {}).items():
		group_panels = panels if isinstance(panels, list) else panels.get(detail.get("part"), [])
		for row in detail.get("data") or []:
			all_selected = True
			for panel in group_panels:
				probe = {**row, "colour": _plain(row.get(f"{panel}_colour")) or _plain(colour), "panel": panel, "is_collapsed": False}
				chosen = _row_identity(probe) in selected
				row[f"{panel}_moved"] = chosen
				all_selected = all_selected and (chosen or flt(row.get(panel)) <= 0)
			row["bundle_moved"] = all_selected
	for row in movement.get("collapsed_details") or []:
		probe = {**row, "qty": row.get("quantity"), "is_collapsed": True}
		chosen = _row_identity(probe) in selected
		row["moved"] = chosen
		row["move_qty"] = flt(row.get("quantity")) if chosen else 0
	return movement


def _authoritative_bundle_values(available, input_rows, output_rows, choices, lot) -> dict:
	inputs = _canonical_inputs(available, input_rows)
	outputs = _canonical_outputs(output_rows, choices, lot)
	if _quantity_map(inputs) != _quantity_map(outputs):
		frappe.throw(_("Input and output bundle quantities must match for every Size, Colour and Panel."))
	known = {_row_identity(row, include_combination=False, include_collapsed=False) for row in _available_input_rows(available).values()}
	selected = {_row_identity(row, include_combination=False, include_collapsed=False) for row in inputs}
	for row in outputs:
		if _row_identity(row, include_combination=False, include_collapsed=False) in known - selected:
			frappe.throw(_("An output bundle conflicts with an existing unselected bundle. Choose a different Lay or Bundle number."))
	return {"inputs": inputs, "outputs": outputs, "bundles": _movement_with_inputs(available, inputs)}


def _apply_values(doc, context, values, authoritative, *, is_new) -> None:
	if is_new:
		doc.lot = context.lot
		doc.item = context.item
		doc.warehouse = context.warehouse
		doc.posting_date = values.get("posting_date") or nowdate()
		doc.posting_time = values.get("posting_time") or nowtime()
	doc.colour = values.get("selected_colour") or values.get("colour")
	doc.movement_data = {
		"bundles": authoritative["bundles"],
		"inputs": authoritative["inputs"],
		"outputs": authoritative["outputs"],
		"selected_colour": doc.colour,
	}


def _lock_source_rows(context) -> None:
	frappe.db.sql(
		"""
		SELECT name FROM `tabSD YRP Cut Bundle Movement Ledger`
		WHERE lot = %(lot)s AND supplier = %(warehouse)s
			AND is_cancelled = 0 AND transformed = 0
		FOR UPDATE
		""",
		{"lot": context.lot, "warehouse": context.warehouse},
	)


@frappe.whitelist()
def save_cut_bundle(values, name: str | None = None, submit=False, expected_modified=None) -> dict:
	values = parse_json_object(values)
	is_new = not name
	if is_new:
		frappe.has_permission(CUT_BUNDLE_DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(CUT_BUNDLE_DOCTYPE)
		context = _context(source=values)
	else:
		doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
		doc.check_permission("write")
		assert_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Cut Bundle Edit can be changed."))
		context = _context(doc=doc)
	_require_source(context)
	if cint(submit):
		_lock_source_rows(context)
	snapshot = _source_snapshot(context, values)
	authoritative = _authoritative_bundle_values(
		snapshot["available"], values.get("inputs") or [], values.get("outputs") or [], snapshot["choices"], context.lot
	)
	_apply_values(doc, context, values, authoritative, is_new=is_new)
	doc.save()
	if cint(submit):
		doc.check_permission("submit")
		doc.submit()
	return _record_payload(doc)


def _revalidate_saved_draft(doc) -> None:
	values = {
		"posting_date": doc.posting_date,
		"posting_time": doc.posting_time,
		"selected_colour": doc.colour,
		"inputs": _json_value(doc.input_json, []),
		"outputs": _json_value(doc.output_json, []),
	}
	context = _context(doc=doc)
	_lock_source_rows(context)
	snapshot = _source_snapshot(context, values)
	authoritative = _authoritative_bundle_values(
		snapshot["available"], values["inputs"], values["outputs"], snapshot["choices"], context.lot
	)
	_apply_values(doc, context, values, authoritative, is_new=False)
	doc.save()


@frappe.whitelist()
def execute_cut_bundle_command(name, command, expected_modified=None) -> dict:
	doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
	assert_expected_modified(doc, expected_modified)
	if command == "submit":
		doc.check_permission("submit")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Cut Bundle Edit can be submitted."))
		_revalidate_saved_draft(doc)
		doc.submit()
	elif command == "cancel":
		doc.check_permission("cancel")
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only a Submitted Cut Bundle Edit can be cancelled."))
		doc.cancel()
	elif command == "amend":
		doc.check_permission("amend")
		if cint(doc.docstatus) != 2:
			frappe.throw(_("Only a Cancelled Cut Bundle Edit can be amended."))
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.printed_time = None
		amended.insert()
		doc = amended
	else:
		frappe.throw(_("Unsupported Cut Bundle Edit command."))
	return _record_payload(doc)


@frappe.whitelist()
def get_cut_bundle_print_data(name, printer) -> dict:
	if not printer:
		frappe.throw(_("Select a printer."))
	doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
	doc.check_permission("print")
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Submit this Cut Bundle Edit before printing labels."))
	if doc.printed_time:
		frappe.throw(_("Labels were already printed for this Cut Bundle Edit."))
	token = frappe.generate_hash(length=32)
	frappe.cache.set_value(
		f"cut-bundle-print:{token}",
		{"name": doc.name, "user": frappe.session.user, "modified": str(doc.modified)},
		expires_in_sec=300,
	)
	return {
		"name": doc.name,
		"printer": printer,
		"zpl": print_labels(CUT_BUNDLE_DOCTYPE, doc.name),
		"expected_modified": doc.modified,
		"confirmation_token": token,
	}


@frappe.whitelist()
def confirm_cut_bundle_print(name, expected_modified=None, confirmation_token=None) -> dict:
	if not expected_modified or not confirmation_token:
		frappe.throw(_("The print confirmation expired. Prepare the labels again."))
	doc = frappe.get_doc(CUT_BUNDLE_DOCTYPE, name)
	doc.check_permission("print")
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	cache_key = f"cut-bundle-print:{confirmation_token}"
	confirmation = frappe.cache.get_value(cache_key) or {}
	if (
		confirmation.get("name") != doc.name
		or confirmation.get("user") != frappe.session.user
		or confirmation.get("modified") != str(doc.modified)
	):
		frappe.throw(_("The print confirmation expired. Prepare the labels again."))
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Submit this Cut Bundle Edit before confirming label printing."))
	if not doc.printed_time:
		frappe.cache.delete_value(cache_key)
		doc.db_set("printed_time", now_datetime(), update_modified=True)
		doc.reload()
	return _record_payload(doc)

"""Box Sticker Print services for the Cut Panel Store browser workspace."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as attribute_value

from essdee_yrp.cut_panel_store.common import assert_expected_modified, parse_json_object
from essdee_yrp.essdee_yrp.doctype.sd_yrp_box_sticker_print.sd_yrp_box_sticker_print import (
	_lock_linked_production_order,
	_raw_code,
	get_fg_details,
	get_printer,
	get_raw_code,
	get_template,
)


BOX_STICKER_DOCTYPE = "SD YRP Box Sticker Print"
BOX_STICKER_DETAIL_DOCTYPE = "SD YRP Box Sticker Print Detail"
PRINT_FORMAT_DOCTYPE = "YRP ZPL Raw Print Format"
RESERVATION_DOCTYPE = "SD YRP Box Sticker Print Reservation"
SUPPORTED_PRINTER_TYPES = {"200dpi", "300dpi"}
PRINTER_DPI = {"200dpi": 203, "300dpi": 300}
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$")


def _value(row, fieldname, default=None):
	if isinstance(row, dict):
		return row.get(fieldname, default)
	return getattr(row, fieldname, default)


def _plain(value):
	return attribute_value(value)


def _size_key(value) -> str:
	return str(_plain(value) or "").strip()


def _integer(value, label, *, minimum=0) -> int:
	try:
		number = Decimal(str(value if value not in (None, "") else 0))
	except (InvalidOperation, ValueError):
		frappe.throw(_("{0} must be a whole number.").format(label))
	if not number.is_finite() or number != number.to_integral_value() or number < minimum:
		frappe.throw(_("{0} must be a whole number of at least {1}.").format(label, minimum))
	return int(number)


def _require_expected_modified(doc, expected_modified) -> None:
	if not expected_modified:
		frappe.throw(
			_("This document must be reloaded before it can be changed."),
			frappe.TimestampMismatchError,
		)
	assert_expected_modified(doc, expected_modified)


def _allowed_quantity(row):
	if cint(_value(row, "allow_excess_quantity")):
		return None
	quantity = _integer(_value(row, "quantity"), _("Quantity"))
	percentage = _integer(_value(row, "allow_excess_percentage"), _("Allow Excess Percentage"))
	return quantity + math.ceil(quantity * percentage / 100)


def _row_payload(row) -> dict:
	allowed = _allowed_quantity(row)
	printed = _integer(_value(row, "printed_quantity"), _("Printed Quantity"))
	return {
		"name": _value(row, "name"),
		"size": _size_key(_value(row, "size")),
		"mrp": flt(_value(row, "mrp")),
		"quantity": _integer(_value(row, "quantity"), _("Quantity")),
		"printed_quantity": printed,
		"allow_excess_quantity": cint(_value(row, "allow_excess_quantity")),
		"allow_excess_percentage": _integer(
			_value(row, "allow_excess_percentage"), _("Allow Excess Percentage")
		),
		"allowed_quantity": allowed,
		"remaining_quantity": None if allowed is None else max(allowed - printed, 0),
	}


def _document_permission(doc, ptype: str) -> bool:
	"""Quiet capability probe: a denied check must not surface Frappe's permission message."""
	return bool(frappe.has_permission(doc.doctype, ptype=ptype, doc=doc))


def _permissions(doc=None) -> dict:
	return {
		"can_create": bool(frappe.has_permission(BOX_STICKER_DOCTYPE, ptype="create")),
		"can_write": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "write")),
		"can_submit": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "submit")),
		"can_cancel": bool(doc and cint(doc.docstatus) == 1 and _document_permission(doc, "cancel")),
		"can_print": bool(doc and cint(doc.docstatus) == 1 and _document_permission(doc, "read")),
	}


def _record_payload(doc) -> dict:
	permissions = _permissions(doc)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"status": {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(
			cint(doc.docstatus), _("Unknown")
		),
		"lot": doc.lot,
		"fg_item": doc.fg_item,
		"size": doc.size,
		"use_item_name": cint(doc.use_item_name),
		"display_name": doc.display_name,
		"print_format": doc.print_format,
		"piece_per_box": cint(doc.piece_per_box),
		"against": doc.against,
		"against_id": doc.against_id,
		"modified": doc.modified,
		"rows": [_row_payload(row) for row in doc.box_sticker_print_details],
		"permissions": permissions,
	}


def _load_source_documents(lot, fg_item):
	if not lot:
		frappe.throw(_("Select a Lot before fetching Box Sticker rows."))
	if not fg_item:
		frappe.throw(_("Select an FG Item before fetching Box Sticker rows."))
	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("read")
	fg_doc = frappe.get_doc("SD YRP FG Item Master", fg_item)
	fg_doc.check_permission("read")
	return lot_doc, fg_doc


def _client_rows(values) -> tuple[list, bool]:
	values = values or {}
	if "rows" in values:
		return values.get("rows") or [], True
	if "box_sticker_print_details" in values:
		return values.get("box_sticker_print_details") or [], True
	return [], False


def _canonical_source_rows(
	lot,
	fg_item,
	values=None,
	existing_rows=None,
	*,
	source_documents=None,
) -> list[dict]:
	if source_documents is None:
		_load_source_documents(lot, fg_item)
	authoritative = get_fg_details(fg_item, lot) or []
	server_by_size = {}
	server_order = []
	for row in authoritative:
		size = _size_key(_value(row, "size"))
		if not size or size in server_by_size:
			frappe.throw(_("FG Item size rows are incomplete or duplicated. Correct the FG Item before continuing."))
		server_order.append(size)
		server_by_size[size] = row
	if not server_order:
		frappe.throw(_("FG Item {0} has no Box Sticker sizes.").format(fg_item))

	client_rows, supplied = _client_rows(values)
	if not isinstance(client_rows, list):
		frappe.throw(_("Box Sticker rows must be a list."))
	client_by_size = {}
	for row in client_rows:
		if not isinstance(row, dict):
			frappe.throw(_("Every Box Sticker row must be an object."))
		size = _size_key(row.get("size"))
		if not size or size in client_by_size or size not in server_by_size:
			frappe.throw(_("Box Sticker sizes changed or contain an unknown row. Refresh the FG Item rows."))
		client_by_size[size] = row
	if supplied and set(client_by_size) != set(server_by_size):
		frappe.throw(_("Box Sticker sizes changed. Refresh the FG Item rows before saving."))

	existing_by_size = {}
	for row in existing_rows or []:
		size = _size_key(_value(row, "size"))
		if not size or size in existing_by_size:
			frappe.throw(_("Saved Box Sticker rows contain duplicate sizes."))
		existing_by_size[size] = row

	result = []
	for size in server_order:
		server = server_by_size[size]
		client = client_by_size.get(size, {})
		existing = existing_by_size.get(size)
		client_name = client.get("name") or client.get("doc_name")
		existing_name = _value(existing, "name") if existing else None
		if existing:
			if supplied and client_name != existing_name:
				frappe.throw(_("Box Sticker detail identity changed. Reload the document before saving."))
		elif client_name:
			frappe.throw(_("A Box Sticker detail name was not issued by this document."))
		quantity = _integer(
			client.get("quantity", _value(existing, "quantity", 0)),
			_("Quantity for size {0}").format(size),
		)
		percentage = _integer(
			client.get(
				"allow_excess_percentage",
				_value(existing, "allow_excess_percentage", 5),
			),
			_("Allow Excess Percentage for size {0}").format(size),
		)
		if percentage > 100:
			frappe.throw(_("Allow Excess Percentage cannot exceed 100."))
		row = {
			"size": size,
			"mrp": flt(_value(existing, "mrp") if existing else _value(server, "mrp")),
			"quantity": quantity,
			"printed_quantity": _integer(
				_value(existing, "printed_quantity", 0), _("Printed Quantity for size {0}").format(size)
			),
			"allow_excess_quantity": cint(
				_value(existing, "allow_excess_quantity")
				if existing
				else _value(server, "allow_excess_quantity", 0)
			),
			"allow_excess_percentage": percentage,
		}
		if existing_name:
			row["name"] = existing_name
		result.append(row)
	return result


def _context(lot=None, fg_item=None, display_name=None) -> dict:
	return {
		"lot": lot,
		"fg_item": fg_item,
		"display_name": display_name or fg_item,
	}


def _source_payload(lot, fg_item, values=None, existing_rows=None) -> dict:
	source_documents = _load_source_documents(lot, fg_item)
	fg_doc = source_documents[1]
	rows = _canonical_source_rows(
		lot,
		fg_item,
		values,
		existing_rows,
		source_documents=source_documents,
	)
	return {
		"context": _context(lot, fg_item, _value(fg_doc, "display_name") or fg_item),
		"rows": [_row_payload(row) for row in rows],
		"defaults": {"lot": lot, "fg_item": fg_item},
	}


@frappe.whitelist()
def get_box_sticker_editor(name: str | None = None, source=None) -> dict:
	if name:
		doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
		doc.check_permission("read")
		record = _record_payload(doc)
		return {
			"context": _context(doc.lot, doc.fg_item, doc.display_name),
			"record": record,
			"defaults": {
				"lot": doc.lot,
				"fg_item": doc.fg_item,
				"size": doc.size,
				"use_item_name": cint(doc.use_item_name),
				"print_format": doc.print_format,
				"rows": deepcopy(record["rows"]),
			},
			"permissions": record["permissions"],
		}

	frappe.has_permission(BOX_STICKER_DOCTYPE, ptype="create", throw=True)
	source = parse_json_object(source, label=_("Source"))
	lot = source.get("lot")
	fg_item = source.get("fg_item")
	rows = []
	context = _context(lot, fg_item)
	if lot and fg_item:
		source_payload = _source_payload(lot, fg_item)
		rows = source_payload["rows"]
		context = source_payload["context"]
	return {
		"context": context,
		"record": None,
		"defaults": {
			"lot": lot,
			"fg_item": fg_item,
			"size": source.get("size"),
			"use_item_name": cint(source.get("use_item_name")),
			"print_format": source.get("print_format"),
			"rows": rows,
		},
		"permissions": _permissions(),
	}


@frappe.whitelist()
def preview_box_sticker_source(lot=None, fg_item=None, values=None, name=None) -> dict:
	values = parse_json_object(values)
	if name:
		doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Box Sticker Print can refresh source rows."))
		target_lot = lot or values.get("lot") or doc.lot
		target_fg_item = fg_item or values.get("fg_item") or doc.fg_item
		same_source = target_lot == doc.lot and target_fg_item == doc.fg_item
		existing_rows = doc.box_sticker_print_details if same_source else None
	else:
		frappe.has_permission(BOX_STICKER_DOCTYPE, ptype="create", throw=True)
		target_lot = lot or values.get("lot")
		target_fg_item = fg_item or values.get("fg_item")
		existing_rows = None
	return _source_payload(target_lot, target_fg_item, values, existing_rows)


def _validate_print_format(print_format):
	if not print_format:
		frappe.throw(_("Select a Print Format."))
	doc = frappe.get_doc(PRINT_FORMAT_DOCTYPE, print_format)
	doc.check_permission("read")
	return doc


def _apply_values(doc, values, rows) -> None:
	doc.lot = values.get("lot")
	doc.fg_item = values.get("fg_item")
	doc.size = values.get("size") or None
	doc.use_item_name = cint(values.get("use_item_name"))
	doc.print_format = values.get("print_format")
	doc.set("box_sticker_print_details", rows)


@frappe.whitelist()
def save_box_sticker(values, name: str | None = None, submit=False, expected_modified=None) -> dict:
	values = parse_json_object(values)
	is_new = not name
	if is_new:
		frappe.has_permission(BOX_STICKER_DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(BOX_STICKER_DOCTYPE)
	else:
		doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
		doc.check_permission("write")
		_require_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Box Sticker Print can be changed."))

	lot = values.get("lot") or (None if is_new else doc.lot)
	fg_item = values.get("fg_item") or (None if is_new else doc.fg_item)
	print_format = values.get("print_format") or (None if is_new else doc.print_format)
	values = {
		**values,
		"lot": lot,
		"fg_item": fg_item,
		"print_format": print_format,
		"size": values.get("size", None if is_new else doc.size),
		"use_item_name": values.get("use_item_name", 0 if is_new else doc.use_item_name),
	}
	same_source = not is_new and lot == doc.lot and fg_item == doc.fg_item
	rows = _canonical_source_rows(
		lot,
		fg_item,
		values,
		doc.box_sticker_print_details if same_source else None,
	)
	if not sum(row["quantity"] for row in rows) and not any(
		row["allow_excess_quantity"] for row in rows
	):
		frappe.throw(_("Enter the quantity."))
	_validate_print_format(print_format)
	if cint(submit):
		doc.check_permission("submit")
	_apply_values(doc, values, rows)
	doc.save()
	if cint(submit):
		doc.submit()
	return _record_payload(doc)


def _revalidate_saved_draft(doc) -> None:
	values = {
		"lot": doc.lot,
		"fg_item": doc.fg_item,
		"size": doc.size,
		"use_item_name": doc.use_item_name,
		"print_format": doc.print_format,
		"rows": [
			{
				"name": row.name,
				"size": _size_key(row.size),
				"quantity": row.quantity,
				"allow_excess_percentage": row.allow_excess_percentage,
			}
			for row in doc.box_sticker_print_details
		],
	}
	rows = _canonical_source_rows(doc.lot, doc.fg_item, values, doc.box_sticker_print_details)
	_validate_print_format(doc.print_format)
	_apply_values(doc, values, rows)
	doc.save()


@frappe.whitelist()
def execute_box_sticker_command(name, command, expected_modified=None) -> dict:
	if command not in {"submit", "cancel"}:
		frappe.throw(_("Unsupported Box Sticker Print command."))
	frappe.has_permission(BOX_STICKER_DOCTYPE, ptype=command, throw=True)
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
	doc.check_permission(command)
	_require_expected_modified(doc, expected_modified)
	if command == "submit":
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Box Sticker Print can be submitted."))
		_revalidate_saved_draft(doc)
		doc.submit()
	else:
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only a Submitted Box Sticker Print can be cancelled."))
		doc.cancel()
	return _record_payload(doc)


@frappe.whitelist()
def get_box_sticker_preview(name) -> dict:
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
	doc.check_permission("read")
	if not doc.box_sticker_print_details:
		frappe.throw(_("Add at least one Box Sticker Print row."))
	print_format = _validate_print_format(doc.print_format)
	_integer(print_format.labels_per_row, _("Labels Per Row"), minimum=1)
	preview = get_raw_code(name)
	code = preview.get("code") or ""
	return {
		"code": code,
		"zpl": code,
		"raw": code,
		"height": preview.get("height"),
		"width": preview.get("width"),
	}


@frappe.whitelist()
def get_configured_box_sticker_printers(printers) -> list[str]:
	frappe.has_permission(BOX_STICKER_DOCTYPE, ptype="read", throw=True)
	if isinstance(printers, str):
		printers = frappe.parse_json(printers)
	if not isinstance(printers, list) or any(not isinstance(printer, str) for printer in printers):
		frappe.throw(_("Printers must be a list of printer names."))
	return get_printer(printers)


def _get_print_format_doc(print_format, printer_type):
	if printer_type not in SUPPORTED_PRINTER_TYPES:
		frappe.throw(_("Select a supported printer resolution."))
	doc = _validate_print_format(print_format)
	label_count = _integer(doc.labels_per_row, _("Labels Per Row"), minimum=1)
	return doc, _raw_code(doc, printer_type), label_count


def _lock_box_sticker(
	name,
	expected_modified=None,
	*,
	require_expected=True,
	require_submitted=True,
	permission_type="read",
):
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
	doc.check_permission(permission_type)
	if require_expected:
		_require_expected_modified(doc, expected_modified)
	elif expected_modified:
		assert_expected_modified(doc, expected_modified)
	_lock_linked_production_order(doc.lot)
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Box Sticker Print` WHERE name = %s FOR UPDATE",
		(name,),
	)
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
	doc.check_permission(permission_type)
	if require_expected:
		_require_expected_modified(doc, expected_modified)
	elif expected_modified:
		assert_expected_modified(doc, expected_modified)
	if require_submitted and cint(doc.docstatus) != 1:
		frappe.throw(_("Submit the Box Sticker Print before printing."))
	return doc


def _locked_detail_rows(parent, names):
	if not names:
		return []
	placeholders = ", ".join(["%s"] * len(names))
	rows = frappe.db.sql(
		f"""
		SELECT name, parent, size, mrp, printed_quantity, quantity,
			allow_excess_quantity, allow_excess_percentage
		FROM `tabSD YRP Box Sticker Print Detail`
		WHERE parent = %s AND name IN ({placeholders})
		ORDER BY name
		FOR UPDATE
		""",
		(parent, *names),
		as_dict=True,
	)
	return attribute_db.business_values(rows)


def _requested_rows(rows) -> list[dict]:
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Enter at least one positive print quantity."))
	result = []
	seen = set()
	for row in rows:
		if not isinstance(row, dict):
			frappe.throw(_("Every print row must be an object."))
		name = str(row.get("doc_name") or row.get("name") or "").strip()
		quantity = _integer(row.get("quantity"), _("Print Quantity"), minimum=1)
		if not name:
			frappe.throw(_("Every print row needs a detail name."))
		if name in seen:
			frappe.throw(_("The same Box Sticker detail cannot be printed twice in one request."))
		seen.add(name)
		result.append({"name": name, "quantity": quantity})
	return result


def _reservation_token(reservation) -> str:
	if isinstance(reservation, str):
		if reservation.lstrip().startswith("{"):
			reservation = frappe.parse_json(reservation)
		else:
			return reservation.strip()
	if isinstance(reservation, dict):
		return str(reservation.get("reservation") or reservation.get("reservation_id") or "").strip()
	return ""


def _normalise_request_id(request_id) -> str:
	request_id = str(request_id or "").strip()
	if not REQUEST_ID_PATTERN.fullmatch(request_id):
		frappe.throw(_("Request ID must be 8 to 64 letters, numbers, dots, colons, underscores or dashes."))
	return request_id


def _reservation_fingerprint(name, requested, printer_type, expected_modified) -> str:
	payload = {
		"name": name,
		"rows": sorted(requested, key=lambda row: row["name"]),
		"printer_type": printer_type,
		"expected_modified": str(expected_modified),
	}
	encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
	return hashlib.sha256(encoded).hexdigest()


def _lock_reservation(request_id, *, for_update=True):
	lock_clause = "FOR UPDATE" if for_update else ""
	rows = frappe.db.sql(
		f"""
		SELECT name, request_id, box_sticker_print, requested_by, state,
			fingerprint, printer_type, expected_modified, payload_json, zpl
		FROM `tabSD YRP Box Sticker Print Reservation`
		WHERE name = %s
		{lock_clause}
		""",
		(request_id,),
		as_dict=True,
	)
	if not rows:
		return None
	return rows[0]


def _claim_reservation(
	*,
	request_id,
	box_sticker,
	user,
	fingerprint,
	printer_type,
	expected_modified,
):
	now = now_datetime()
	frappe.db.sql(
		"""
		INSERT IGNORE INTO `tabSD YRP Box Sticker Print Reservation`
			(name, creation, modified, modified_by, owner, docstatus, idx,
			 request_id, box_sticker_print, requested_by, state, fingerprint,
			 printer_type, expected_modified, payload_json, zpl)
		VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, 'Preparing', %s, %s, %s, '[]', '')
		""",
		(
			request_id,
			now,
			now,
			user,
			user,
			request_id,
			box_sticker,
			user,
			fingerprint,
			printer_type,
			str(expected_modified),
		),
	)
	row_count = frappe.db.sql("SELECT ROW_COUNT()") or [(0,)]
	inserted = bool(cint(row_count[0][0]))
	reservation = _lock_reservation(request_id)
	if not reservation:
		frappe.throw(_("The print reservation could not be claimed."))
	if reservation.requested_by != user:
		frappe.throw(_("The print reservation is not available."), frappe.PermissionError)
	if (
		reservation.box_sticker_print != box_sticker
		or reservation.fingerprint != fingerprint
		or reservation.printer_type != printer_type
	):
		frappe.throw(_("This request ID was already used for different print data."))
	if not inserted and reservation.state == "Preparing":
		frappe.throw(_("This print request is still being prepared. Retry shortly."))
	return reservation, inserted


def _update_reservation(request_id, **values) -> None:
	frappe.db.set_value(
		RESERVATION_DOCTYPE,
		request_id,
		values,
		update_modified=True,
	)


def _owned_reservation(request_id, *, for_update=True):
	reservation = _lock_reservation(request_id, for_update=for_update)
	if not reservation or reservation.requested_by != frappe.session.user:
		frappe.throw(_("The print reservation is not available."), frappe.PermissionError)
	return reservation


def _reservation_rows(reservation) -> list[dict]:
	try:
		rows = json.loads(reservation.payload_json or "[]")
	except (TypeError, ValueError):
		rows = None
	if not isinstance(rows, list):
		frappe.throw(_("The stored print reservation is invalid. Contact an administrator."))
	return rows


def _validated_reserved_row(row) -> tuple[str, int, int, int]:
	if not isinstance(row, dict):
		frappe.throw(_("The stored print reservation is invalid. Contact an administrator."))
	name = str(row.get("name") or "").strip()
	delta = _integer(row.get("delta"), _("Reserved Quantity"), minimum=1)
	before = _integer(row.get("before"), _("Reserved Starting Total"))
	after = _integer(row.get("after"), _("Reserved Ending Total"), minimum=1)
	if not name or after != before + delta:
		frappe.throw(_("The stored print reservation is invalid. Contact an administrator."))
	return name, delta, before, after


def _reserved_printed_floors(parent, names) -> dict[str, int]:
	"""Return the minimum valid printed total for each requested detail.

	The Box Sticker parent lock serializes reserve/rollback operations before this
	locking read. Confirm can only move Active to Confirmed, and both states keep
	their delta in effect.
	"""
	wanted = {str(name) for name in names if name}
	if not wanted:
		return {}
	reservations = frappe.db.sql(
		"""
		SELECT name, state, payload_json
		FROM `tabSD YRP Box Sticker Print Reservation`
		WHERE box_sticker_print = %s
		ORDER BY name
		FOR UPDATE
		""",
		(parent,),
		as_dict=True,
	)
	baselines = {}
	in_effect = {}
	for reservation in reservations:
		seen = set()
		for row in _reservation_rows(reservation):
			name, delta, before, _after = _validated_reserved_row(row)
			if name in seen:
				frappe.throw(_("The stored print reservation is invalid. Contact an administrator."))
			seen.add(name)
			if name not in wanted:
				continue
			baselines[name] = min(baselines.get(name, before), before)
			if reservation.state in {"Active", "Confirmed"}:
				in_effect[name] = in_effect.get(name, 0) + delta
	return {
		name: baselines[name] + in_effect.get(name, 0)
		for name in wanted
		if name in baselines
	}


def _reservation_response(reservation, doc, *, already_reserved) -> dict:
	state = str(reservation.state or "").lower().replace(" ", "_")
	return {
		"reservation": reservation.request_id,
		"reservation_id": reservation.request_id,
		"reservation_state": state,
		"already_reserved": already_reserved,
		"zpl": reservation.zpl or "",
		"raw": reservation.zpl or "",
		"expected_modified": doc.modified,
		"record": _record_payload(doc),
		"print_format": doc.print_format,
	}


def _authorise_box_sticker_print(name, expected_modified):
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, name)
	doc.check_permission("read")
	_require_expected_modified(doc, expected_modified)
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Submit the Box Sticker Print before printing."))
	return doc


@frappe.whitelist()
def reserve_box_sticker_print(
	name,
	rows,
	printer_type,
	request_id=None,
	expected_modified=None,
) -> dict:
	doc = _authorise_box_sticker_print(name, expected_modified)
	requested = _requested_rows(rows)
	request_id = _normalise_request_id(request_id)
	fingerprint = _reservation_fingerprint(name, requested, printer_type, expected_modified)
	doc = _lock_box_sticker(name, expected_modified)
	reservation, inserted = _claim_reservation(
		request_id=request_id,
		box_sticker=name,
		user=frappe.session.user,
		fingerprint=fingerprint,
		printer_type=printer_type,
		expected_modified=expected_modified,
	)
	if not inserted:
		if reservation.state == "Rolled Back":
			frappe.throw(_("This print request was already rolled back. Start a new print request."))
		if reservation.state == "Confirmed":
			frappe.throw(_("This print request was already confirmed. Start a new print request."))
		if reservation.state != "Active":
			frappe.throw(_("This print request is not available for replay."))
		return _reservation_response(reservation, doc, already_reserved=True)

	print_format, raw_code, label_count = _get_print_format_doc(doc.print_format, printer_type)
	locked_rows = _locked_detail_rows(doc.name, sorted(row["name"] for row in requested))
	locked_by_name = {row.name: row for row in locked_rows}
	if len(locked_by_name) != len(requested):
		frappe.throw(_("A Box Sticker detail is stale or does not belong to this document. Reload it."))

	prepared = []
	zpl = ""
	for requested_row in requested:
		row = locked_by_name.get(requested_row["name"])
		if not row or row.parent != doc.name:
			frappe.throw(_("A Box Sticker detail is stale or does not belong to this document. Reload it."))
		quantity = requested_row["quantity"]
		delta = math.ceil(quantity / label_count) * label_count
		printed = _integer(row.printed_quantity, _("Printed Quantity"))
		allowed = _allowed_quantity(row)
		if allowed is not None and printed + quantity > allowed:
			frappe.throw(
				_("Size {0} can print at most {1} more label(s).").format(
					_size_key(row.size), max(allowed - printed, 0)
				)
			)
		item = {
			"doc_name": row.name,
			"quantity": quantity,
			"size": _size_key(doc.size) or _size_key(row.size),
			"mrp": flt(row.mrp),
		}
		zpl += get_template(
			doc,
			item,
			raw_code,
			label_count,
			doc.fg_item,
			dpi=PRINTER_DPI[printer_type],
		)
		prepared.append(
			{
				"name": row.name,
				"delta": delta,
				"before": printed,
				"after": printed + delta,
			}
		)

	for row in prepared:
		attribute_db.set_value(
			BOX_STICKER_DETAIL_DOCTYPE,
			row["name"],
			"printed_quantity",
			row["after"],
		)
	_update_reservation(
		request_id,
		state="Active",
		payload_json=json.dumps(prepared, separators=(",", ":")),
		zpl=zpl,
	)
	doc.reload()
	reservation = _lock_reservation(request_id)
	return _reservation_response(reservation, doc, already_reserved=False)


@frappe.whitelist()
def confirm_box_sticker_print(reservation) -> dict:
	request_id = _reservation_token(reservation)
	if not request_id:
		frappe.throw(_("A print reservation is required."))
	request_id = _normalise_request_id(request_id)
	reserved = _owned_reservation(request_id)
	if reserved.state == "Rolled Back":
		frappe.throw(_("This print reservation was already rolled back."))
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, reserved.box_sticker_print)
	# The labels have already left the browser before confirmation begins.  An
	# operator must therefore be able to acknowledge their owned reservation
	# even if another request cancelled the parent in the meantime.
	doc.check_permission("read")
	already_confirmed = reserved.state == "Confirmed"
	if not already_confirmed and reserved.state == "Active":
		_update_reservation(request_id, state="Confirmed")
	elif not already_confirmed:
		frappe.throw(_("The print reservation is not available."))
	return {
		"confirmed": True,
		"already_confirmed": already_confirmed,
		"reservation": request_id,
		"reservation_id": request_id,
		"record": _record_payload(doc),
	}


@frappe.whitelist()
def get_box_sticker_print_recovery(request_id) -> dict:
	"""Return only the current user's durable state for an interrupted print.

	Missing and foreign request IDs deliberately have the same response so the
	lookup cannot be used as a reservation-existence oracle.
	"""

	request_id = _normalise_request_id(request_id)
	reserved = _lock_reservation(request_id, for_update=False)
	if not reserved or reserved.requested_by != frappe.session.user:
		return {"state": "Missing", "reservation": request_id}
	doc = frappe.get_doc(BOX_STICKER_DOCTYPE, reserved.box_sticker_print)
	doc.check_permission("read")
	state = str(reserved.state or "")
	payload = {
		"state": state,
		"reservation": request_id,
		"reservation_id": request_id,
		"record": _record_payload(doc),
	}
	if state == "Active":
		can_resume = cint(doc.docstatus) == 1 and _document_permission(doc, "read")
		payload.update({"can_resume": can_resume, "release_required": not can_resume})
		if can_resume:
			payload.update(
				{
					"zpl": reserved.zpl or "",
					"raw": reserved.zpl or "",
					"printer_type": reserved.printer_type,
				}
			)
	return payload


@frappe.whitelist()
def rollback_box_sticker_print(reservation) -> dict:
	request_id = _reservation_token(reservation)
	if not request_id:
		frappe.throw(_("A print reservation is required."))
	request_id = _normalise_request_id(request_id)
	reference = _owned_reservation(request_id, for_update=False)
	doc = _lock_box_sticker(
		reference.box_sticker_print,
		require_expected=False,
		require_submitted=False,
		permission_type="read",
	)
	reserved = _owned_reservation(request_id)
	if reserved.box_sticker_print != reference.box_sticker_print:
		frappe.throw(_("The print reservation is not available."), frappe.PermissionError)
	if reserved.state == "Confirmed":
		frappe.throw(_("A confirmed print reservation cannot be rolled back."))
	if reserved.state == "Rolled Back":
		return {
			"rolled_back": True,
			"already_rolled_back": True,
			"reservation": request_id,
			"reservation_id": request_id,
			"record": _record_payload(doc),
		}
	if reserved.state != "Active":
		frappe.throw(_("The print reservation is not available."))

	rows = _reservation_rows(reserved)
	names = sorted(str(row.get("name") or "") for row in rows)
	printed_floors = _reserved_printed_floors(doc.name, names)
	locked_rows = _locked_detail_rows(doc.name, names)
	locked_by_name = {row.name: row for row in locked_rows}
	if len(locked_by_name) != len(rows):
		frappe.throw(_("The reserved Box Sticker rows changed. Contact an administrator."))
	updates = []
	for reserved_row in rows:
		name, delta, _before, _after = _validated_reserved_row(reserved_row)
		row = locked_by_name.get(name)
		printed = _integer(row.printed_quantity, _("Printed Quantity")) if row else 0
		if (
			not row
			or row.parent != doc.name
			or name not in printed_floors
			or printed < printed_floors[name]
		):
			frappe.throw(_("The reserved Box Sticker totals changed. Contact an administrator."))
		updates.append((row.name, printed - delta))
	for row_name, printed_quantity in updates:
		attribute_db.set_value(
			BOX_STICKER_DETAIL_DOCTYPE,
			row_name,
			"printed_quantity",
			printed_quantity,
		)
	_update_reservation(request_id, state="Rolled Back")
	doc.reload()
	return {
		"rolled_back": True,
		"already_rolled_back": False,
		"reservation": request_id,
		"reservation_id": request_id,
		"record": _record_payload(doc),
	}

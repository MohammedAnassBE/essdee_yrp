"""Excel Sticker Print services for the Cut Panel Store browser workspace."""

from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import unquote, urlparse
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import frappe
from frappe import _
from frappe.utils import cint
from lxml.etree import XMLSyntaxError
from openpyxl.utils.exceptions import InvalidFileException
from yrp.yrp.doctype.yrp_excel_sticker_print.yrp_excel_sticker_print import (
	get_template as render_excel_sticker_template,
)

from essdee_yrp.cut_panel_store.common import parse_json_object


EXCEL_STICKER_DOCTYPE = "YRP Excel Sticker Print"
PRINT_FORMAT_DOCTYPE = "YRP ZPL Raw Print Format"
SUPPORTED_PRINTER_TYPES = {"200dpi": 203, "300dpi": 300}
SAMPLE_ROW_LIMIT = 10
SAMPLE_COLUMN_LIMIT = 20
SAMPLE_HEADER_LIMIT = 80
SAMPLE_CELL_LIMIT = 160
TEMPORARY_NAME_PREFIX = "new-yrp-excel-sticker-print-"


def _document_permission(doc, ptype: str) -> bool:
	"""Quiet capability probe: a denied check must not surface Frappe's permission message."""
	return bool(frappe.has_permission(doc.doctype, ptype=ptype, doc=doc))


def _permissions(doc=None) -> dict:
	return {
		"can_create": bool(frappe.has_permission(EXCEL_STICKER_DOCTYPE, ptype="create")),
		"can_write": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "write")),
		"can_submit": bool(doc and cint(doc.docstatus) == 0 and _document_permission(doc, "submit")),
		"can_print": bool(doc and cint(doc.docstatus) == 1 and _document_permission(doc, "print")),
	}


def _require_expected_modified(doc, expected_modified) -> None:
	if not expected_modified or str(doc.modified) != str(expected_modified):
		frappe.throw(
			_("This document changed after you opened it. Reload it and try again."),
			frappe.TimestampMismatchError,
		)


def _temporary_name(value) -> str:
	name = str(value or "").strip()
	if not name.startswith(TEMPORARY_NAME_PREFIX) or len(name) <= len(TEMPORARY_NAME_PREFIX):
		frappe.throw(_("The Excel upload target is invalid. Open a new editor and upload the file again."))
	return name


def _xlsx_path(value) -> bool:
	path = unquote(urlparse(str(value or "")).path)
	return path.lower().endswith(".xlsx")


def _attachment(doc, file_url, *, temporary_name=None):
	if not file_url:
		frappe.throw(_("Please upload an Excel file."))
	if not str(file_url).startswith("/private/files/") or not _xlsx_path(file_url):
		frappe.throw(_("Upload a valid .xlsx file."))
	target_name = _temporary_name(temporary_name) if temporary_name else doc.name
	try:
		file_doc = frappe.get_doc(
			"File",
			{
				"file_url": file_url,
				"attached_to_doctype": EXCEL_STICKER_DOCTYPE,
				"attached_to_name": target_name,
				"attached_to_field": "excel_file",
			},
		)
	except frappe.DoesNotExistError:
		frappe.throw(_("The Excel file is not an available attachment. Upload it again."))
	file_doc.check_permission("read")

	if (
		not cint(file_doc.is_private)
		or not str(file_doc.file_url).startswith("/private/files/")
		or not _xlsx_path(file_doc.file_name)
		or not _xlsx_path(file_doc.file_url)
	):
		frappe.throw(_("Upload a valid .xlsx file."))
	if file_doc.attached_to_doctype != EXCEL_STICKER_DOCTYPE:
		frappe.throw(_("The Excel file is not attached to this Excel Sticker Print."))
	if file_doc.attached_to_field != "excel_file":
		frappe.throw(_("The Excel file must be attached through the Excel File field."))

	if temporary_name:
		if file_doc.attached_to_name != target_name or file_doc.owner != frappe.session.user:
			frappe.throw(_("The Excel file does not belong to this new draft."))
	elif file_doc.attached_to_name != target_name:
		frappe.throw(_("The Excel file is attached to a different document."))
	return file_doc


def _print_format(name):
	if not name:
		frappe.throw(_("Select a Print Format."))
	doc = frappe.get_doc(PRINT_FORMAT_DOCTYPE, name)
	doc.check_permission("read")
	return doc


def _serialized_rows(doc) -> list[dict]:
	if not doc.serialized_data:
		return []
	try:
		rows = json.loads(doc.serialized_data)
	except (TypeError, ValueError, json.JSONDecodeError):
		frappe.throw(_("The parsed Excel data is invalid. Submit the draft again."))
	if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
		frappe.throw(_("The parsed Excel data is invalid. Submit the draft again."))
	return rows


def _short_text(value, limit) -> str:
	text = str(value or "")
	return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_cell(value):
	if value is None or isinstance(value, (bool, int)):
		return value
	if isinstance(value, float):
		return value if math.isfinite(value) else None
	return _short_text(value, SAMPLE_CELL_LIMIT)


def _unique_column_alias(column, used) -> str:
	alias = _short_text(column, SAMPLE_HEADER_LIMIT)
	if alias not in used:
		used.add(alias)
		return alias
	index = 2
	while True:
		suffix = f"… ({index})"
		alias = f"{column[: SAMPLE_HEADER_LIMIT - len(suffix)]}{suffix}"
		if alias not in used:
			used.add(alias)
			return alias
		index += 1


def _cell_is_clipped(value) -> bool:
	return not (
		value is None
		or isinstance(value, (bool, int))
		or (isinstance(value, float) and math.isfinite(value))
	) and len(str(value)) > SAMPLE_CELL_LIMIT


def _sample(rows) -> dict:
	columns = []
	seen = set()
	for row in rows[:SAMPLE_ROW_LIMIT]:
		for key in row:
			key = str(key)
			if key not in seen:
				seen.add(key)
				columns.append(key)
				if len(columns) == SAMPLE_COLUMN_LIMIT:
					break
		if len(columns) == SAMPLE_COLUMN_LIMIT:
			break
	used_aliases = set()
	safe_columns = [_unique_column_alias(column, used_aliases) for column in columns]
	safe_rows = [
		{
			safe_column: _safe_cell(row.get(column))
			for column, safe_column in zip(columns, safe_columns, strict=True)
		}
		for row in rows[:SAMPLE_ROW_LIMIT]
	]
	return {
		"columns": safe_columns,
		"rows": safe_rows,
		"truncated": (
			len(rows) > SAMPLE_ROW_LIMIT
			or any(len(row) > SAMPLE_COLUMN_LIMIT for row in rows[:SAMPLE_ROW_LIMIT])
			or any(len(column) > SAMPLE_HEADER_LIMIT for column in columns)
			or any(
				_cell_is_clipped(row.get(column))
				for row in rows[:SAMPLE_ROW_LIMIT]
				for column in columns
			)
		),
	}


def _record_payload(doc) -> dict:
	_attachment(doc, doc.excel_file)
	rows = _serialized_rows(doc)
	sample = _sample(rows)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"status": {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(
			cint(doc.docstatus), _("Unknown")
		),
		"excel_file": doc.excel_file,
		"print_format": doc.print_format,
		"modified": doc.modified,
		"row_count": len(rows),
		"columns": sample["columns"],
		"sample_rows": sample["rows"],
		"sample": sample,
		"permissions": _permissions(doc),
	}


@frappe.whitelist()
def get_excel_sticker_editor(name: str | None = None) -> dict:
	if name:
		doc = frappe.get_doc(EXCEL_STICKER_DOCTYPE, name)
		doc.check_permission("read")
		record = _record_payload(doc)
		return {
			"record": record,
			"defaults": {
				"excel_file": doc.excel_file,
				"print_format": doc.print_format,
			},
			"permissions": record["permissions"],
		}

	frappe.has_permission(EXCEL_STICKER_DOCTYPE, ptype="create", throw=True)
	temporary_name = f"{TEMPORARY_NAME_PREFIX}{frappe.generate_hash(length=10)}"
	return {
		"record": None,
		"defaults": {"excel_file": None, "print_format": None, "temporary_name": temporary_name},
		"upload": {
			"doctype": EXCEL_STICKER_DOCTYPE,
			"docname": temporary_name,
			"fieldname": "excel_file",
			"is_private": 1,
		},
		"permissions": _permissions(),
	}


@frappe.whitelist()
def save_excel_sticker(values, name: str | None = None, submit=False, expected_modified=None) -> dict:
	values = parse_json_object(values)
	is_new = not name
	if is_new:
		frappe.has_permission(EXCEL_STICKER_DOCTYPE, ptype="create", throw=True)
	else:
		doc = frappe.get_doc(EXCEL_STICKER_DOCTYPE, name)
		doc.check_permission("write")
		_require_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Excel Sticker Print can be changed."))

	if cint(submit):
		frappe.throw(_("Save the Draft first, then submit it separately."))
	if is_new:
		doc = frappe.new_doc(EXCEL_STICKER_DOCTYPE)

	excel_file = values.get("excel_file", None if is_new else doc.excel_file)
	print_format_name = values.get("print_format", None if is_new else doc.print_format)
	temporary_name = values.get("temporary_name") if is_new else None
	_attachment(doc, excel_file, temporary_name=temporary_name)
	_print_format(print_format_name)

	doc.excel_file = excel_file
	doc.print_format = print_format_name
	if is_new:
		doc.__temporary_name = _temporary_name(temporary_name)
	doc.save()
	return _record_payload(doc)


def _safe_submit(doc) -> None:
	try:
		doc.submit()
	except frappe.ValidationError:
		raise
	except AttributeError as exc:
		if str(exc) != "'NoneType' object has no attribute 'iter_rows'":
			raise
		frappe.throw(_("The Excel workbook could not be read. Upload a valid .xlsx file."))
	except (
		BadZipFile,
		InvalidFileException,
		XMLSyntaxError,
		OSError,
		EOFError,
		KeyError,
		TypeError,
		ValueError,
		ParseError,
	):
		frappe.throw(_("The Excel workbook could not be read. Upload a valid .xlsx file."))


@frappe.whitelist()
def execute_excel_sticker_command(name, command, expected_modified=None) -> dict:
	if command != "submit":
		frappe.throw(_("Unsupported Excel Sticker Print command."))
	frappe.has_permission(EXCEL_STICKER_DOCTYPE, ptype=command, throw=True)
	doc = frappe.get_doc(EXCEL_STICKER_DOCTYPE, name)
	doc.check_permission(command)
	_require_expected_modified(doc, expected_modified)

	if cint(doc.docstatus) != 0:
		frappe.throw(_("Only a Draft Excel Sticker Print can be submitted."))
	_attachment(doc, doc.excel_file)
	_print_format(doc.print_format)
	_safe_submit(doc)
	return _record_payload(doc)


def _raw_code(print_format, printer_type) -> str:
	if printer_type not in SUPPORTED_PRINTER_TYPES:
		frappe.throw(_("Select either 200dpi or 300dpi."))
	for detail in print_format.zpl_raw_print_format_details or []:
		if detail.printer_type == printer_type and detail.raw_code:
			return detail.raw_code
	frappe.throw(_("The Print Format has no {0} template.").format(printer_type))


def _labels_per_row(value) -> int:
	try:
		number = Decimal(str(value))
	except (InvalidOperation, ValueError):
		frappe.throw(_("Labels Per Row must be a positive whole number."))
	if not number.is_finite() or number <= 0 or number != number.to_integral_value():
		frappe.throw(_("Labels Per Row must be a positive whole number."))
	return int(number)


def _positive_quantity(value, row_number) -> Decimal | None:
	if value in (None, "", 0, 0.0):
		return None
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		frappe.throw(_("Print Quantity in Excel row {0} must be a positive number.").format(row_number))
	number = Decimal(str(value))
	if not number.is_finite() or number <= 0:
		frappe.throw(_("Print Quantity in Excel row {0} must be a positive number.").format(row_number))
	return number


def _render_context(row, *, dpi, print_quantity) -> dict:
	context = {key: value for key, value in row.items() if key not in {"dpi", "print_quantity"}}
	context.update({"print_quantity": print_quantity, "dpi": dpi})
	return context


@frappe.whitelist()
def get_excel_sticker_preview(name) -> dict:
	doc = frappe.get_doc(EXCEL_STICKER_DOCTYPE, name)
	doc.check_permission("read")
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Submit the Excel Sticker Print before previewing it."))
	_attachment(doc, doc.excel_file)
	rows = _serialized_rows(doc)
	if not rows:
		frappe.throw(_("No rows were found in the submitted Excel file."))
	print_format = _print_format(doc.print_format)
	raw_code = _raw_code(print_format, "300dpi")
	code = render_excel_sticker_template(
		_render_context(rows[0], dpi=SUPPORTED_PRINTER_TYPES["300dpi"], print_quantity=1),
		raw_code,
		dpi_value=SUPPORTED_PRINTER_TYPES["300dpi"],
	)
	return {
		"code": code,
		"zpl": code,
		"raw": code,
		"height": print_format.height,
		"width": print_format.width,
	}


@frappe.whitelist()
def get_excel_sticker_print_data(name, printer_type) -> str:
	doc = frappe.get_doc(EXCEL_STICKER_DOCTYPE, name)
	doc.check_permission("print")
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Submit the Excel Sticker Print before printing."))
	_attachment(doc, doc.excel_file)
	rows = _serialized_rows(doc)
	if not rows:
		frappe.throw(_("No rows were found in the submitted Excel file."))
	print_format = _print_format(doc.print_format)
	raw_code = _raw_code(print_format, printer_type)
	labels_per_row = _labels_per_row(print_format.labels_per_row or 1)
	dpi = SUPPORTED_PRINTER_TYPES[printer_type]

	output = []
	for row_number, row in enumerate(rows, start=2):
		quantity = _positive_quantity(row.get("print_quantity"), row_number)
		if quantity is None:
			continue
		copies = int((quantity / labels_per_row).to_integral_value(rounding=ROUND_CEILING))
		output.append(
			render_excel_sticker_template(
				_render_context(row, dpi=dpi, print_quantity=copies),
				raw_code,
				dpi_value=dpi,
			)
		)
	if not output:
		frappe.throw(_("The Excel file has no rows with a positive Print Quantity."))
	return "".join(output)

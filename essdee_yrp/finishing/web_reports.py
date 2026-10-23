"""Whitelisted /web endpoints for the Finishing reports and rework read models."""

from __future__ import annotations

from io import BytesIO

import frappe
import openpyxl
from frappe import _
from frappe.utils import cint, getdate
from yrp.attribute_read_context import attribute_read_scope

from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import sd_yrp_grn_rework_item as rework_items
from essdee_yrp.finishing import report_sources, reports

DISPATCH_REPORT_PERMISSIONS = (
	("SD YRP Finishing Plan", "read"),
	("YRP Goods Received Note", "read"),
)


def can_view_dispatch_report() -> bool:
	"""Keep every workspace and the report endpoint on one permission rule."""

	return all(
		frappe.has_permission(doctype, ptype=ptype)
		for doctype, ptype in DISPATCH_REPORT_PERMISSIONS
	)


@frappe.whitelist()
def get_packing_dpr(date=None, from_date=None, to_date=None, summary=0, lots=None, items=None):
	return reports.get_finishing_packed_details(
		date=date if not cint(summary) else None,
		lot_list=lots if cint(summary) else None,
		item_list=items if cint(summary) else None,
		from_date=from_date if cint(summary) else None,
		to_date=to_date if cint(summary) else None,
		summary=cint(summary),
	)


@frappe.whitelist()
def get_dispatch_report(from_date, to_date, lots=None, items=None):
	if not can_view_dispatch_report():
		frappe.throw(_("Not permitted to view the Finishing Plan Dispatch Report."), frappe.PermissionError)
	return reports.get_finishing_dispatch_report(from_date, to_date, lots, items)


@frappe.whitelist()
def get_ironing_dpr(date=None, from_date=None, to_date=None, summary=0, lots=None, items=None):
	summary = cint(summary)
	return report_sources.get_ironing_dpr(
		date=None if summary else date,
		lot=lots if summary else None,
		item=items if summary else None,
		from_date=from_date if summary else None,
		to_date=to_date if summary else None,
		summary=summary,
	)


@frappe.whitelist()
def get_rejection_details(start_date, end_date, lot=None, item=None, colour=None):
	return report_sources.get_rejection_items(start_date, end_date, lot or None, item or None, colour or None)


@frappe.whitelist()
def get_rework_completion(lot, process):
	return report_sources.get_rework_completion(lot, process)


@frappe.whitelist()
def get_rework_details(lot=None, item=None, colour=None, received_type=None, show_reworked=0):
	with attribute_read_scope():
		return rework_items.get_rework_items(
			lot=lot or None,
			item=item or None,
			colour=colour or None,
			received_type=received_type or None,
			show_reworked=cint(show_reworked),
		)


@frappe.whitelist()
def get_rework_groups(lot=None, item=None, colour=None, show_reworked=0):
	with attribute_read_scope():
		return report_sources.get_rework_group_items(
			lot or None, item or None, colour or None, cint(show_reworked)
		)


def report_date(value):
	return getdate(str(value)[:10]).strftime("%d-%m-%Y") if value else ""


def first_colour(details):
	return "-".join(next(iter(details or {}), "").split("-")[1:])


def send_workbook(filename, header, rows):
	workbook = openpyxl.Workbook(write_only=True)
	sheet = workbook.create_sheet("Sheet1", 0)
	sheet.append(header)
	for row in rows:
		sheet.append(row)
	output = BytesIO()
	workbook.save(output)
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = output.getvalue()
	frappe.local.response.type = "binary"


@frappe.whitelist()
def download_rejection_details(start_date, end_date, lot=None, item=None, colour=None):
	"""Rebuild the Rejection Details report from its filters and send it as Excel."""
	data = report_sources.get_rejection_items(start_date, end_date, lot or None, item or None, colour or None)
	types = data.get("types") or []
	rows = [
		[
			series,
			report_date(detail.get("date")),
			detail.get("grn_number"),
			detail.get("lot"),
			detail.get("item"),
			first_colour(detail.get("rejection_detail")),
			*[detail.get("types", {}).get(received_type, 0) for received_type in types],
			detail.get("total"),
		]
		for series, detail in (data.get("report_detail") or {}).items()
	]
	send_workbook(
		"rejection_details.xlsx",
		["Series No", "Date", "GRN Number", "Lot", "Item", "Colour", *types, "Total"],
		rows,
	)


@frappe.whitelist()
def download_rework_details(lot=None, item=None, colour=None, received_type=None, show_reworked=0):
	"""Rebuild the Rework Details list from its filters and send it as Excel (Frappe 15 columns)."""
	data = get_rework_details(lot, item, colour, received_type, show_reworked)
	types = data.get("types") or []
	rows = [
		[
			series,
			report_date(detail.get("date")),
			detail.get("grn_number"),
			detail.get("lot"),
			detail.get("item"),
			first_colour(detail.get("rework_detail")),
			*[
				(detail.get("types", {}).get(received_type) or 0)
				- (detail.get("rejection_detail", {}).get(received_type) or 0)
				for received_type in types
			],
		]
		for series, detail in (data.get("report_detail") or {}).items()
	]
	send_workbook(
		"rework_details.xlsx", ["Series No", "Date", "GRN Number", "Lot", "Item", "Colour", *types], rows
	)

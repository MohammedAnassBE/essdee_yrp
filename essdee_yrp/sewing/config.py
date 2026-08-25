"""Code defaults and validation for the Essdee Sewing Details configuration."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt


DEFAULT_INPUT_TYPES = (
	("Order Qty", 0),
	("Input Qty", 75),
	("Line Output", 20),
	("Checking Output", 3),
	("AQL Output", 3),
)

DEFAULT_INPUT_ORDERS = (
	("Input Qty", "Order Qty"),
	("Line Output", "Input Qty"),
	("Checking Output", "Line Output"),
	("AQL Output", "Checking Output"),
)

DEFAULT_STATUS_SUMMARY = (
	("Input Qty", "Accepted"),
	("Line Output", "Accepted"),
	("Checking Output", "Accepted"),
	("Checking Output", "Adas"),
	("Checking Output", "Oil Mark"),
	("Checking Output", "Other Mistake"),
	("AQL Output", "Accepted"),
)

DEFAULT_SCALAR_SETTINGS = {
	"previous_day_entries": 2,
	"sewing_input_qty_type": "Input Qty",
	"sewing_line_output_type": "Line Output",
	"sewing_plan_inspection_type": "AQL Output",
	"type_wise_diff_summary": "Checking Output",
}


def validate_sewing_input_orders(rows) -> list[frappe._dict]:
	"""Validate and normalize the configured dependency order.

	The child-table order is significant. A dependency must be ``Order Qty`` or
	an Input Type declared in an earlier row, which prevents cycles and makes the
	sequence deterministic for both the browser and the submission endpoint.
	"""

	rows = list(rows or [])
	if not rows:
		frappe.throw(
			_("Configure at least one Sewing Plan Input Order in MRP Settings."),
			title=_("Sewing Entry Configuration Required"),
		)

	configured = []
	seen = {"Order Qty"}
	for index, row in enumerate(rows, start=1):
		input_type = cstr(row.get("input_type")).strip()
		difference_from = cstr(row.get("difference_from")).strip()
		if not input_type or not difference_from:
			frappe.throw(
				_("Sewing Plan Input Order row {0} is incomplete.").format(index)
			)
		if input_type == "Order Qty":
			frappe.throw(_("Order Qty is a source quantity and cannot be an Input Type."))
		if input_type in seen:
			frappe.throw(
				_("Sewing Input Type {0} is configured more than once.").format(
					frappe.bold(input_type)
				)
			)
		if difference_from not in seen:
			frappe.throw(
				_(
					"{0} must appear before {1} in Sewing Plan Input Orders."
				).format(frappe.bold(difference_from), frappe.bold(input_type))
			)
		if not frappe.db.exists("Sewing Plan Input Type", input_type):
			frappe.throw(
				_("Sewing Plan Input Type {0} does not exist.").format(
					frappe.bold(input_type)
				)
			)
		if difference_from != "Order Qty" and not frappe.db.exists(
			"Sewing Plan Input Type", difference_from
		):
			frappe.throw(
				_("Sewing Plan Input Type {0} does not exist.").format(
					frappe.bold(difference_from)
				)
			)

		configured.append(
			frappe._dict(
				input_type=input_type,
				difference_from=difference_from,
				input_key=_input_key(input_type),
				difference_key=_input_key(difference_from),
				allowance=flt(
					frappe.db.get_value(
						"Sewing Plan Input Type", input_type, "allowance"
					)
				),
			)
		)
		seen.add(input_type)
	return configured


def get_sewing_input_configuration() -> list[frappe._dict]:
	settings = frappe.get_cached_doc("MRP Settings")
	return validate_sewing_input_orders(settings.sewing_plan_input_orders)


def ensure_sewing_plan_settings() -> bool:
	"""Seed the F15 Essdee defaults only when a site has no Sewing setup.

	Live configuration always wins: existing child rows and scalar values are
	preserved. This makes fresh installs safe while allowing a migrated site to
	receive its reviewed values from the source MRP Settings document.
	"""

	if not frappe.db.exists("DocType", "MRP Settings"):
		return False
	meta = frappe.get_meta("MRP Settings")
	if not meta.has_field("sewing_plan_input_orders"):
		return False

	changed = False
	for input_type, allowance in DEFAULT_INPUT_TYPES:
		if frappe.db.exists("Sewing Plan Input Type", input_type):
			continue
		frappe.get_doc(
			{
				"doctype": "Sewing Plan Input Type",
				"input_type": input_type,
				"allowance": allowance,
			}
		).insert(ignore_permissions=True)
		changed = True

	settings = frappe.get_doc("MRP Settings")
	if not settings.sewing_plan_input_orders:
		for input_type, difference_from in DEFAULT_INPUT_ORDERS:
			settings.append(
				"sewing_plan_input_orders",
				{"input_type": input_type, "difference_from": difference_from},
			)
		changed = True

	if meta.has_field("sewing_plan_status_summary") and not settings.sewing_plan_status_summary:
		for input_type, received_type in DEFAULT_STATUS_SUMMARY:
			if frappe.db.exists("Received Type", received_type):
				settings.append(
					"sewing_plan_status_summary",
					{"input_type": input_type, "received_type": received_type},
				)
				changed = True

	for fieldname, value in DEFAULT_SCALAR_SETTINGS.items():
		if meta.has_field(fieldname) and not cstr(settings.get(fieldname)).strip():
			settings.set(fieldname, value)
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("MRP Settings", "MRP Settings")
	return changed


def _input_key(value: str) -> str:
	return cstr(value).strip().lower().replace(" ", "_")

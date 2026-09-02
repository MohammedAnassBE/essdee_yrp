"""Validation for the source-owned Essdee Sewing Details configuration."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt


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
		if not frappe.db.exists('SD YRP Sewing Plan Input Type', input_type):
			frappe.throw(
				_("Sewing Plan Input Type {0} does not exist.").format(
					frappe.bold(input_type)
				)
			)
		if difference_from != "Order Qty" and not frappe.db.exists(
			'SD YRP Sewing Plan Input Type', difference_from
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
						'SD YRP Sewing Plan Input Type', input_type, "allowance"
					)
				),
			)
		)
		seen.add(input_type)
	return configured


def get_sewing_input_configuration() -> list[frappe._dict]:
	settings = frappe.get_cached_doc('SD YRP MRP Settings')
	return validate_sewing_input_orders(settings.sewing_plan_input_orders)


def _input_key(value: str) -> str:
	return cstr(value).strip().lower().replace(" ", "_")

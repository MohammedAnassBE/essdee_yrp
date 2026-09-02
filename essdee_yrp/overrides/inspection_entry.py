"""Essdee Inspection Entry source-bin corrections.

An internal-unit GRN posts into the configured Transit Warehouse until its
GRN Completion Stock Entry is submitted.  Base Inspection Entry defaults use
the GRN's final ``to_warehouse`` unconditionally, which makes a pre-completion
inspection point at an empty bin.  Keep the generic controller untouched and
correct only the Essdee source payload.
"""

import frappe
from frappe import _
from frappe.utils import flt

from yrp.yrp.doctype.yrp_inspection_entry.yrp_inspection_entry import (
	_attach_display_meta,
	get_initial_payload as get_base_initial_payload,
)


@frappe.whitelist()
def get_initial_payload(against, against_id):
	sources = get_base_initial_payload(against, against_id)
	if against != 'YRP Goods Received Note':
		return sources

	grn = frappe.get_doc('YRP Goods Received Note', against_id)
	if not grn.get("is_internal_unit") or grn.get("transfer_complete"):
		return sources

	moved = [flt(row.get("ste_received_quantity")) for row in grn.get("items") or []]
	if any(quantity > 0.0001 for quantity in moved):
		frappe.throw(
			_(
				"Goods Received Note {0} is partially transferred. Complete the transfer "
				"before creating its Inspection Entry."
			).format(grn.name)
		)

	transit_warehouse = frappe.db.get_single_value(
		'YRP YRP Stock Settings', "transit_warehouse"
	)
	if not transit_warehouse:
		frappe.throw(
			_("Transit Warehouse must be set in YRP Stock Settings for this Inspection Entry.")
		)

	for source in sources:
		source["warehouse"] = transit_warehouse
	_attach_display_meta(sources)
	return sources

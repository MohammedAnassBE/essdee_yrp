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
	_approver_role,
)
from yrp.yrp.doctype.yrp_inspection_entry.yrp_inspection_entry import (
	get_initial_payload as get_base_initial_payload,
)


@frappe.whitelist()
def get_initial_payload(against, against_id):
	sources = get_base_initial_payload(against, against_id)
	if against != "YRP Goods Received Note":
		return sources

	grn = frappe.get_doc("YRP Goods Received Note", against_id)
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

	transit_warehouse = frappe.db.get_single_value("YRP Stock Settings", "transit_warehouse")
	if not transit_warehouse:
		frappe.throw(_("Transit Warehouse must be set in YRP Stock Settings for this Inspection Entry."))

	for source in sources:
		source["warehouse"] = transit_warehouse
	_attach_display_meta(sources)
	return sources


@frappe.whitelist()
def convert_stock(name):
	"""Convert stock once, then rebuild affected exact-source Lot projections."""
	role = _approver_role()
	if not role:
		frappe.throw(
			_(
				"YRP Settings → Inspection Entry Approver Role is not configured. "
				"Stock conversion is disabled until an approver role is set."
			)
		)
	if role not in (frappe.get_roles(frappe.session.user) or []):
		frappe.throw(
			_("You need the {0} role to convert Inspection Entry stock.").format(role),
			frappe.PermissionError,
		)

	# Discover immutable submitted references first, then enter the same global
	# Lot -> source GRN -> transaction order used by the cloth lifecycle.
	doc = frappe.get_doc("YRP Inspection Entry", name)
	if doc.docstatus != 1:
		frappe.throw(
			_("Inspection Entry {0} must be submitted before converting stock.").format(name)
		)
	conversion_lots = []
	if doc.get("against") == "YRP Goods Received Note":
		from essdee_yrp.fabric_substitution import (
			lock_lots_for_default_knitting_grns,
		)

		source_grns = _source_grn_names(doc)
		conversion_lots = lock_lots_for_default_knitting_grns(source_grns)
		_lock_source_grns(source_grns)

	# This must be a current locking reload. A plain consistent read after waiting
	# on Lot/GRN locks could let two requests both observe an unconverted document.
	doc = frappe.get_doc("YRP Inspection Entry", name, for_update=True)
	if doc.docstatus != 1:
		frappe.throw(
			_("Inspection Entry {0} must be submitted before converting stock.").format(name)
		)
	current_status = doc.status or ""
	if doc.get("is_converted") or current_status == "Converted":
		frappe.throw(_("Inspection Entry {0} has already converted stock.").format(name))
	if current_status == "Cancelled":
		frappe.throw(_("Inspection Entry {0} is cancelled and cannot convert stock.").format(name))

	from yrp.stock.stock_ledger import enqueue_voucher_repost, make_sl_entries

	entries = doc._build_sl_entries(cancel=False)
	if entries:
		make_sl_entries(entries)
	enqueue_voucher_repost(doc)
	doc.db_set("status", "Converted")
	doc.db_set("is_converted", 1)

	if conversion_lots:
		from essdee_yrp.fabric_substitution import _rebuild_lot_fabric_conversions

		for lot in conversion_lots:
			_rebuild_lot_fabric_conversions(lot, already_locked=True)
	return {"status": "Converted", "is_converted": 1}


def _source_grn_names(doc):
	source_items = sorted(
		{
			row.get("ref_docname")
			for row in doc.get("items") or []
			if row.get("ref_doctype") == "YRP Goods Received Note Item"
			and row.get("ref_docname")
		}
	)
	if not source_items:
		return []
	parents = frappe.get_all(
		"YRP Goods Received Note Item",
		filters={"name": ["in", source_items]},
		fields=["name", "parent"],
	)
	return sorted({row.parent for row in parents if row.parent})


def _lock_source_grns(grn_names):
	grn_names = sorted(set(grn_names or []))
	if grn_names:
		frappe.db.sql(
			"SELECT name FROM `tabYRP Goods Received Note` "
			"WHERE name IN %(names)s ORDER BY name FOR UPDATE",
			{"names": tuple(grn_names)},
		)

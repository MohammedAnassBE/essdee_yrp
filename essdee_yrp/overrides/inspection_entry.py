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
	source_grns = []
	source_items = []
	source_against_id = None
	if doc.get("against") == "YRP Goods Received Note":
		from essdee_yrp.fabric_substitution import (
			get_default_knitting_lots_for_grn_items,
			lock_lots_for_default_knitting_grn_items,
		)

		source_against_id = doc.get("against_id")
		source_items = _source_grn_item_names(doc)
		source_grns = _source_grn_names(doc, source_items)
		conversion_lots = lock_lots_for_default_knitting_grn_items(source_items)
		_lock_source_grns(source_grns)
		locked_source_rows = _lock_source_grn_items(source_items)
		# Re-read exact child ownership and keyed eligibility after its parent and
		# child locks. A stale/forged reference must never select a Lot rebuild.
		_source_grn_names(doc, source_items, source_rows=locked_source_rows)
		current_lots = get_default_knitting_lots_for_grn_items(
			source_items,
			for_update=True,
		)
		if current_lots != conversion_lots:
			frappe.throw(
				_("The cloth source lineage changed while Inspection Entry {0} was converting.").format(
					name
				)
			)

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
	if source_against_id:
		_validate_locked_inspection_source(doc, source_against_id, source_items)

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


def _source_grn_item_names(doc):
	return sorted(
		{
			row.get("ref_docname")
			for row in doc.get("items") or []
			if row.get("ref_doctype") == "YRP Goods Received Note Item"
			and row.get("ref_docname")
		}
	)


def _source_grn_names(doc, source_items, *, source_rows=None):
	if not source_items:
		return []
	parents = source_rows
	if parents is None:
		parents = frappe.get_all(
			"YRP Goods Received Note Item",
			filters={"name": ["in", source_items]},
			fields=["name", "parent", "parenttype"],
		)
	by_name = {row.name: row for row in parents}
	missing = [source_item for source_item in source_items if source_item not in by_name]
	if missing:
		frappe.throw(
			_("Goods Received Note source rows no longer exist: {0}.").format(
				", ".join(missing)
			)
		)
	expected_grn = doc.get("against_id")
	for source_item in source_items:
		row = by_name[source_item]
		if row.parenttype != "YRP Goods Received Note" or row.parent != expected_grn:
			frappe.throw(
				_(
					"Goods Received Note source row {0} does not belong to Goods Received Note {1}."
				).format(source_item, expected_grn)
			)
	return [expected_grn]


def _validate_locked_inspection_source(doc, expected_grn, expected_items):
	current_items = _source_grn_item_names(doc)
	if (
		doc.get("against") != "YRP Goods Received Note"
		or doc.get("against_id") != expected_grn
		or current_items != expected_items
	):
		frappe.throw(
			_("Inspection Entry {0} source lineage changed while stock was converting.").format(
				doc.name
			)
		)


def _lock_source_grns(grn_names):
	grn_names = sorted(set(grn_names or []))
	if grn_names:
		frappe.db.sql(
			"SELECT name FROM `tabYRP Goods Received Note` "
			"WHERE name IN %(names)s ORDER BY name FOR UPDATE",
			{"names": tuple(grn_names)},
		)


def _lock_source_grn_items(grn_item_names):
	grn_item_names = sorted(set(grn_item_names or []))
	if grn_item_names:
		return frappe.db.sql(
			"SELECT name, parent, parenttype FROM `tabYRP Goods Received Note Item` "
			"WHERE name IN %(names)s ORDER BY name FOR UPDATE",
			{"names": tuple(grn_item_names)},
			as_dict=True,
		)
	return []

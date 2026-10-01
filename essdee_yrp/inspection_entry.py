"""Protect exact fabric-source allocations during Inspection conversion."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_source import (
	ELIGIBLE_RECEIVED_TYPE,
	QTY_TOLERANCE,
	_accepted_inspection_adjustments,
	_conversion_factor,
)
from yrp.yrp.doctype.inspection_entry.inspection_entry import (
	_approver_role,
)


@frappe.whitelist()
def convert_stock(name):
	"""Run YRP conversion only when Accepted stock remains above reservations."""
	role = _approver_role()
	if not role:
		frappe.throw(_(
			"YRP Settings → Inspection Entry Approver Role is not configured. "
			"Stock conversion is disabled until an approver role is set."
		))
	if role not in (frappe.get_roles(frappe.session.user) or []):
		frappe.throw(
			_("You need the {0} role to convert Inspection Entry stock.").format(role),
			frappe.PermissionError,
		)

	# The first read discovers immutable submitted source references. Lock those
	# parents before the IE to match Calculate's source-GRN-first order, then
	# reload the complete IE with a *current* locking read. Calling the base
	# endpoint here would reload via a plain consistent read and could let two
	# concurrent Convert requests both post stock.
	doc = frappe.get_doc("Inspection Entry", name)
	conversion_lots = []
	if doc.get("against") == "Goods Received Note":
		from essdee_yrp.fabric_substitution import (
			lock_lots_for_default_knitting_grns,
		)

		# Conversion writers use the same global order as GRN lifecycle hooks:
		# affected Lots first, then exact source GRN parents.
		conversion_lots = lock_lots_for_default_knitting_grns(
			_source_grn_names(doc)
		)
		_lock_source_grns(doc)
	doc = frappe.get_doc("Inspection Entry", name, for_update=True)
	if doc.docstatus != 1:
		frappe.throw(
			_("Inspection Entry {0} must be submitted before converting stock.").format(name)
		)
	current_status = doc.status or ""
	if doc.get("is_converted") or current_status == "Converted":
		frappe.throw(_("Inspection Entry {0} has already converted stock.").format(name))
	if current_status == "Cancelled":
		frappe.throw(_("Inspection Entry {0} is cancelled and cannot convert stock.").format(name))
	_guard_exact_fabric_allocations(doc)

	from yrp.stock.stock_ledger import enqueue_voucher_repost, make_sl_entries

	entries = doc._build_sl_entries(cancel=False)
	if entries:
		make_sl_entries(entries)
	enqueue_voucher_repost(doc)
	doc.db_set("status", "Converted")
	doc.db_set("is_converted", 1)
	if conversion_lots:
		from essdee_yrp.fabric_substitution import (
			_rebuild_lot_fabric_conversions,
		)

		for lot in conversion_lots:
			_rebuild_lot_fabric_conversions(lot, already_locked=True)
	return {"status": "Converted", "is_converted": 1}


def _guard_exact_fabric_allocations(doc):
	if doc.get("against") != "Goods Received Note":
		return
	delta_by_source = _accepted_delta_by_source(doc)
	if not delta_by_source or all(delta >= -QTY_TOLERANCE for delta in delta_by_source.values()):
		return

	source_names = sorted(delta_by_source)
	_lock_source_grns(doc)

	source_rows = frappe.db.sql(
		"""
		SELECT name AS source_grn_item, item_variant, quantity, stock_qty, uom,
			received_type
		FROM `tabGoods Received Note Item`
		WHERE name IN %(names)s
		ORDER BY name
		FOR UPDATE
		""",
		{"names": tuple(source_names)},
		as_dict=True,
	)
	by_name = {row.source_grn_item: row for row in source_rows}
	adjustments = _accepted_inspection_adjustments(source_rows)
	reservations = _exact_accepted_reservations(source_names)

	for source_name, delta in delta_by_source.items():
		if delta >= -QTY_TOLERANCE:
			continue
		source = by_name.get(source_name)
		if not source:
			frappe.throw(_("Inspection source row {0} no longer exists.").format(source_name))
		initial = 0.0
		if source.received_type == ELIGIBLE_RECEIVED_TYPE:
			initial = flt(source.stock_qty) or (
				flt(source.quantity) * _conversion_factor(source.item_variant, source.uom)
			)
		remaining = max(
			initial + flt(adjustments.get(source_name)) + flt(delta),
			0,
		)
		reserved = flt(reservations.get(source_name))
		if remaining + QTY_TOLERANCE < reserved:
			frappe.throw(_(
				"Cannot reclassify Accepted stock from GRN row {0}. Later fabric Work "
				"Orders reserve {1} Kg, but this conversion would leave only {2} Kg."
			).format(source_name, flt(reserved, 3), flt(remaining, 3)))


def _source_grn_names(doc):
	source_names = sorted({
		row.get("ref_docname") for row in doc.get("items") or []
		if row.get("ref_doctype") == "Goods Received Note Item"
		and row.get("ref_docname")
	})
	if not source_names:
		return []
	parents = frappe.get_all(
		"Goods Received Note Item",
		filters={"name": ["in", source_names]},
		fields=["name", "parent"],
	)
	return sorted({row.parent for row in parents if row.parent})


def _lock_source_grns(doc):
	parent_names = _source_grn_names(doc)
	if parent_names:
		frappe.db.sql(
			"SELECT name FROM `tabGoods Received Note` "
			"WHERE name IN %(names)s ORDER BY name FOR UPDATE",
			{"names": tuple(parent_names)},
		)


def _accepted_delta_by_source(doc):
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	deltas = defaultdict(float)
	for row in doc.get("items") or []:
		if row.get("ref_doctype") != "Goods Received Note Item" or not row.get("ref_docname"):
			continue
		source_type = row.get("received_type") or default_received_type
		target_type = row.get("target_received_type")
		qty = flt(row.get("qty"))
		if source_type == ELIGIBLE_RECEIVED_TYPE and target_type != ELIGIBLE_RECEIVED_TYPE:
			deltas[row.ref_docname] -= qty
		elif source_type != ELIGIBLE_RECEIVED_TYPE and target_type == ELIGIBLE_RECEIVED_TYPE:
			deltas[row.ref_docname] += qty
	return dict(deltas)


def _exact_accepted_reservations(source_names):
	rows = frappe.db.sql(
		"""
		SELECT item.source_grn_item, item.item_variant, item.qty,
			item.pending_quantity, item.stock_update, item.uom,
			item.received_type, item.parent
		FROM `tabWork Order Deliverables` item
		WHERE item.parenttype = 'Work Order'
			AND item.source_grn_item IN %(source_names)s
		ORDER BY item.parent, item.idx
		FOR UPDATE
		""",
		{"source_names": tuple(source_names)},
		as_dict=True,
	)
	parent_names = sorted({row.parent for row in rows})
	parent_status = {
		row.name: row
		for row in frappe.db.sql(
			"""
			SELECT name, docstatus, open_status
			FROM `tabWork Order`
			WHERE name IN %(names)s
			FOR UPDATE SKIP LOCKED
			""",
			{"names": tuple(parent_names)},
			as_dict=True,
		)
	} if parent_names else {}
	reserved = defaultdict(float)
	for row in rows:
		status = parent_status.get(row.parent)
		if status and status.docstatus == 2:
			continue
		planned = max(flt(row.qty), 0)
		executed = max(
			planned - flt(row.pending_quantity),
			flt(row.stock_update),
			0,
		)
		# A locked/skipped parent is treated conservatively as active. Normally
		# this current read mirrors source availability and releases only a
		# closed order's unexecuted plan without creating a target/source deadlock.
		qty = executed if status and status.open_status == "Close" else max(planned, executed)
		reserved[row.source_grn_item] += qty * _conversion_factor(
			row.item_variant, row.uom
		)
	return dict(reserved)

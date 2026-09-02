"""Essdee Purchase Order linked-Lot policy and APIs."""

import frappe
from frappe import _
from frappe.utils import escape_html


def _has_link_fields(doc):
	return bool(doc.meta.get_field("default_lot") and doc.meta.get_field("sd_lot"))


def _lot_dimension_field(doctype=None):
	from yrp.stock.dimensions import get_stock_dimensions

	meta = frappe.get_meta(doctype) if doctype else None
	for dimension in get_stock_dimensions():
		if dimension.get("dimension_doctype") != "Lot":
			continue
		fieldname = dimension.get("fieldname")
		if not meta or meta.get_field(fieldname):
			return fieldname
	return None


def sync_linked_lots(doc, method=None):
	"""Normalize PO links while retaining existing child-row identities."""
	if not _has_link_fields(doc):
		return

	linked_rows = []
	seen = set()
	for row in doc.get("sd_lot") or []:
		if row.lot and row.lot not in seen:
			_check_lot_permission(row.lot)
			linked_rows.append(row)
			seen.add(row.lot)

	# The Desk Purchase Order now stores dimensions on each PO Item, matching
	# Stock Entry. Keep the old hidden linked-Lot rows synchronized for existing
	# reports and submitted-PO APIs, but make the item rows the entry source.
	item_dimension_field = _lot_dimension_field("Purchase Order Item")
	for item in doc.get("items") or []:
		lot = item.get(item_dimension_field) if item_dimension_field else None
		if lot and lot not in seen:
			_check_lot_permission(lot)
			linked_rows.append(doc.append("sd_lot", {"lot": lot}))
			seen.add(lot)

	dimension_field = _lot_dimension_field("Purchase Order")
	header_lot = doc.get(dimension_field) if dimension_field else None
	if not doc.get("default_lot") and header_lot:
		doc.default_lot = header_lot
	if not doc.get("default_lot") and len(linked_rows) == 1:
		doc.default_lot = linked_rows[0].lot
	if doc.get("default_lot") and doc.default_lot not in seen:
		_check_lot_permission(doc.default_lot)
		linked_rows.append(doc.append("sd_lot", {"lot": doc.default_lot}))
		seen.add(doc.default_lot)

	doc.set("sd_lot", linked_rows)
	if doc.docstatus == 0 and dimension_field and doc.default_lot and not header_lot:
		doc.set(dimension_field, doc.default_lot)


def _parse_name_list(value):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if value is None:
		return []
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("Expected a list of document names."))
	if any(not isinstance(name, str) for name in value):
		frappe.throw(_("Every document name must be a string."))
	return list(dict.fromkeys(name.strip() for name in value if name.strip()))


def _check_lot_permission(lot, permission_type="read"):
	lot_doc = frappe.get_doc("Lot", lot)
	lot_doc.check_permission(permission_type)
	return lot_doc


@frappe.whitelist()
def get_purchase_order_lots(purchase_order):
	doc = frappe.get_doc("Purchase Order", purchase_order)
	doc.check_permission("read")
	return [row.lot for row in doc.get("sd_lot") or [] if row.lot]


@frappe.whitelist()
def get_purchase_orders_for_lot(lot):
	_check_lot_permission(lot)
	parent_names = frappe.get_all(
		"Lot MultiSelect",
		filters={
			"lot": lot,
			"parenttype": "Purchase Order",
			"parentfield": "sd_lot",
		},
		pluck="parent",
	)
	if not parent_names:
		return []
	return frappe.get_list(
		"Purchase Order",
		filters={"name": ["in", sorted(set(parent_names))], "docstatus": 1},
		pluck="name",
	)


def _lot_has_grn_on_po(purchase_order, lot):
	dimension_field = _lot_dimension_field("Goods Received Note Item")
	if not dimension_field:
		return False
	grns = frappe.get_all(
		"Goods Received Note",
		filters={
			"against": "Purchase Order",
			"against_id": purchase_order,
			"docstatus": ["in", [0, 1]],
		},
		pluck="name",
	)
	if not grns:
		return False
	return bool(
		frappe.get_all(
			"Goods Received Note Item",
			filters={"parent": ["in", grns], dimension_field: lot},
			limit=1,
		)
	)


@frappe.whitelist()
def update_po_lot_links(doc_name, add_lots=None, remove_lots=None, comment=None):
	add_lots = _parse_name_list(add_lots)
	remove_lots = _parse_name_list(remove_lots)
	doc = frappe.get_doc("Purchase Order", doc_name)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("Cannot change Lots on a cancelled Purchase Order."))

	existing = [row.lot for row in doc.get("sd_lot") or [] if row.lot]
	existing_set = set(existing)
	to_add = [lot for lot in add_lots if lot not in existing_set]
	to_remove = [lot for lot in remove_lots if lot in existing_set]
	if not to_add and not to_remove:
		return existing
	if not (comment or "").strip():
		frappe.throw(_("Reason is required when linked Lots are changed."))

	for lot in to_add:
		_check_lot_permission(lot)
	for lot in to_remove:
		_check_lot_permission(lot)
		if _lot_has_grn_on_po(doc.name, lot):
			frappe.throw(
				_(
					"Lot {0} is referenced by a Goods Received Note on this Purchase Order "
					"and cannot be unlinked."
				).format(lot)
			)

	remove_set = set(to_remove)
	doc.set("sd_lot", [row for row in doc.get("sd_lot") or [] if row.lot not in remove_set])
	for lot in to_add:
		doc.append("sd_lot", {"lot": lot})
	remaining = [row.lot for row in doc.get("sd_lot") or [] if row.lot]
	if doc.get("default_lot") not in remaining:
		doc.default_lot = remaining[0] if remaining else None
	doc.save()

	actions = []
	if to_add:
		actions.append(_("Linked: {0}").format(", ".join(to_add)))
	if to_remove:
		actions.append(_("Unlinked: {0}").format(", ".join(to_remove)))
	actions.append(_("Reason: {0}").format(comment.strip()))
	doc.add_comment("Comment", text="<br>".join(escape_html(action) for action in actions))
	return [row.lot for row in doc.get("sd_lot") or [] if row.lot]


@frappe.whitelist()
def update_lot_po_links(lot, add_pos=None, remove_pos=None, comment=None):
	_check_lot_permission(lot, "write")
	for purchase_order in _parse_name_list(add_pos):
		if frappe.db.get_value("Purchase Order", purchase_order, "docstatus") != 1:
			frappe.throw(_("Purchase Order {0} is not submitted.").format(purchase_order))
		update_po_lot_links(purchase_order, add_lots=[lot], comment=comment)
	for purchase_order in _parse_name_list(remove_pos):
		update_po_lot_links(purchase_order, remove_lots=[lot], comment=comment)


def validate_grn_lots(doc, method=None):
	"""Apply linked-Lot restrictions for PO GRNs on every server save path."""
	if doc.get("against") != "Purchase Order" or not doc.get("against_id"):
		return
	dimension_field = _lot_dimension_field("Goods Received Note Item")
	if not dimension_field:
		return
	po = frappe.get_doc("Purchase Order", doc.against_id)
	allowed_lots = {row.lot for row in po.get("sd_lot") or [] if row.lot}
	# An empty linked list deliberately means unrestricted, matching legacy policy.
	if not allowed_lots:
		return
	invalid_lots = sorted(
		{
			row.get(dimension_field)
			for row in doc.get("items") or []
			if row.get(dimension_field) and row.get(dimension_field) not in allowed_lots
		}
	)
	if invalid_lots:
		frappe.throw(
			_("Goods Received Note contains Lots not linked to Purchase Order {0}: {1}").format(
				doc.against_id,
				", ".join(invalid_lots),
			)
		)

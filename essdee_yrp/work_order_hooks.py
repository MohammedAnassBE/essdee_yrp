# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def onload(doc, method=None):
	"""Render Essdee Work Order items as logical rows with Size columns."""
	del method
	if not doc.get("production_detail"):
		return

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
	from yrp.stock.save_stock_items import group_items_for_ui

	doc.set_onload(
		"deliverable_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("deliverables") or []),
			"Work Order Deliverables",
		),
	)
	doc.set_onload(
		"receivable_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("receivables") or []),
			"Work Order Receivables",
		),
	)


def validate(doc, method=None):
	set_includes_packing(doc)
	validate_lot_process_selection(doc)


def set_includes_packing(doc):
	"""Copy Essdee's Process packing rule without coupling base Work Order."""
	if not doc.meta.get_field("includes_packing"):
		return
	doc.includes_packing = 0
	if doc.get("process_name") and frappe.get_meta("Process").get_field("includes_packing"):
		doc.includes_packing = frappe.db.get_value(
			"Process", doc.process_name, "includes_packing"
		) or 0


def validate_lot_process_selection(doc):
	"""Keep the Work Order's Item/IPD tied to its selected Process and Lot.

	The clients require an explicit filtered Item selection, and API/import
	callers receive the same guard. Production Detail is derived and never
	accepted as an independent user choice.
	"""
	if not doc.get("process_name") or not doc.get("lot"):
		return

	from essdee_yrp.api.work_order import _get_work_order_selection_context

	context = _get_work_order_selection_context(
		doc.lot, doc.process_name, check_permission=False
	)
	options = context["options"]
	if not options:
		scope = _("cloth IPDs") if context["is_cloth_process"] else _("garment IPD")
		frappe.throw(
			_("Lot {0} has no {1} configured for process {2}.").format(
				doc.lot, scope, doc.process_name
			)
		)

	item_matches = [option for option in options if option["item"] == doc.get("item")]
	if not item_matches:
		frappe.throw(
			_("Item {0} is not available for process {1} in Lot {2}. Valid items: {3}.").format(
				doc.get("item") or _("(not selected)"),
				doc.process_name,
				doc.lot,
				", ".join(context["item_options"]) or _("none"),
			)
		)
	if len(item_matches) > 1:
		frappe.throw(
			_(
				"Item {0} has multiple Production Details for process {1} in Lot {2}. "
				"Keep one Lot fabric row per cloth Item/IPD."
			).format(doc.item, doc.process_name, doc.lot)
		)

	expected_ipd = item_matches[0]["production_detail"]
	if doc.get("production_detail") and doc.production_detail != expected_ipd:
		frappe.throw(
			_("Production Detail {0} does not match Item {1} in Lot {2}; expected {3}.").format(
				doc.production_detail, doc.item, doc.lot, expected_ipd
			)
		)
	doc.production_detail = expected_ipd


def validate_cloth_process_item(doc):
	"""Compatibility alias for integrations importing the previous hook."""
	if not doc.get("process_name") or not doc.get("lot"):
		return
	validate_lot_process_selection(doc)

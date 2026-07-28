# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate(doc, method=None):
	validate_lot_process_selection(doc)


def validate_lot_process_selection(doc):
	"""Keep the Work Order's Item/IPD tied to its selected Process and Lot.

	The clients auto-fill this pair, but API/import callers receive the same
	guard.  Production Detail is derived and never accepted as an independent
	user choice.
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

	if not doc.get("item") and len(options) == 1:
		doc.item = options[0]["item"]

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

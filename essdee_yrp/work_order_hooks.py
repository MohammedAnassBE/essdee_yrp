# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate(doc, method=None):
	validate_cloth_process_item(doc)


def validate_cloth_process_item(doc):
	"""A Work Order for a cloth process (Process.is_cloth_process) must point
	at one of its Lot's fabric cloth items. The Desk filters the Item link the
	same way — this guards API/import paths."""
	if not doc.get("process_name") or not doc.get("lot") or not doc.get("item"):
		return
	if not frappe.db.get_value("Process", doc.process_name, "is_cloth_process"):
		return
	cloth_items = frappe.get_all(
		"Lot Fabric Detail",
		filters={"parent": doc.lot, "parenttype": "Lot"},
		pluck="cloth_item",
	)
	if doc.item not in cloth_items:
		frappe.throw(
			_("Item {0} is not one of Lot {1}'s fabric cloths ({2}).").format(
				doc.item, doc.lot, ", ".join(cloth_items) or _("none configured")
			)
		)

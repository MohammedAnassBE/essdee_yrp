# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate_correction_ipd_items(doc, method=None):
	"""Every Work Order Correction deliverable must be sanctioned by the WO's
	Item Production Detail: its item is valid only if it is the IPD's yarn item
	or an item in the IPD's `item_bom` table. The Desk filters the Item link the
	same way for Work Orders — this guards API/import paths. v1: deliverables only."""
	ipd_name = doc.get("production_detail")
	if not ipd_name:
		return
	ipd = frappe.get_doc("Item Production Detail", ipd_name)
	allowed = set()
	if ipd.get("yarn_item"):
		allowed.add(ipd.yarn_item)
	for row in ipd.get("item_bom") or []:
		if row.item:
			allowed.add(row.item)
	for row in doc.get("deliverables") or []:
		if not row.item_variant:
			continue
		template = frappe.db.get_value("Item Variant", row.item_variant, "item")
		if template not in allowed:
			frappe.throw(
				_(
					"Deliverable {0} (item {1}) is not sanctioned by Item Production Detail {2}: "
					"it is neither the yarn item nor an Item BOM item."
				).format(row.item_variant, template, ipd_name)
			)

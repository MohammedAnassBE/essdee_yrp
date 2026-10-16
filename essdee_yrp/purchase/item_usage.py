import frappe
from yrp.yrp.doctype.yrp_item.yrp_item import _item_family_has_yrp_stock

TRANSACTION_ITEM_LINKS = {
	"Purchase Order": (
		("Purchase Order Item", "item_code"),
		("Purchase Order Item", "fg_item"),
		("Purchase Order Item Supplied", "main_item_code"),
		("Purchase Order Item Supplied", "rm_item_code"),
	),
	"YRP Goods Received Note": (("YRP Goods Received Note Item", "item_variant"),),
	"YRP Delivery Challan": (("YRP Delivery Challan Item", "item_variant"),),
	"YRP Work Order": (
		("YRP Work Order Deliverables", "item_variant"),
		("YRP Work Order Receivables", "item_variant"),
		("YRP Work Order Calculated Item", "item_variant"),
		("YRP Work Order Excess Usage Item", "item_variant"),
		("YRP Work Order Track Piece", "item_variant"),
	),
	"YRP Purchase Invoice": (
		("YRP Purchase Invoice Item", "item"),
		("YRP PI Work Order Billed Detail", "item_variant"),
	),
}


def has_item_transactions(item):
	"""Include submitted rows even before any stock has moved."""
	if _item_family_has_yrp_stock(item):
		return True
	family = [item, *frappe.get_all("Item", filters={"variant_of": item}, pluck="name", limit=0)]
	return any(
		_has_submitted_rows(doctype, links, family)
		for doctype, links in TRANSACTION_ITEM_LINKS.items()
	)


def _has_submitted_rows(doctype, links, family):
	conditions = [
		f"""exists (
			select 1 from `tab{child}` entry
			where entry.parent = document.name and entry.parenttype = %(doctype)s
			and entry.`{field}` in %(family)s
		)"""
		for child, field in links
	]
	return bool(frappe.db.sql(
		f"""select document.name from `tab{doctype}` document
		where document.docstatus = 1 and ({' or '.join(conditions)}) limit 1""",
		{"doctype": doctype, "family": family},
	))

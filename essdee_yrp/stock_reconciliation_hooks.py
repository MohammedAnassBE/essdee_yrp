"""Essdee Desk projection for Stock Reconciliation items."""


def onload(doc, method=None):
	"""Show primary Item attributes as columns without rewriting stock targets."""
	del method

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
	from yrp.stock.save_stock_items import group_items_for_ui

	doc.set_onload(
		"item_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("items") or []),
			'YRP Stock Reconciliation',
		),
	)

"""One-off repair of GRN Rework Items created against the Transit Warehouse.

Internal-unit GRNs used to open their Rework Item on Transit, so rework could be
cleared before Complete Transfer, which then failed. This points each such Rework
Item at its GRN's delivery warehouse. Stock is not touched: items that already
cleared rework from Transit are listed and must be reverted from Desk (Revert)
before Complete Transfer.

Dry run (default, no writes):
	bench --site SITE execute essdee_yrp.migration.repair_rework_item_warehouse.run
Apply:
	bench --site SITE execute essdee_yrp.migration.repair_rework_item_warehouse.run --kwargs "{'apply': 1}"
"""

import frappe


def run(apply=0, verbose=1):
	candidates = get_candidates()
	if apply:
		for row in candidates:
			frappe.db.set_value(
				"SD YRP GRN Rework Item", row.name, "warehouse", row.to_warehouse, update_modified=False
			)
		frappe.db.commit()
	cleared = [row.name for row in candidates if row.conversions]
	if verbose:
		print(f"{'Updated' if apply else 'Would update'} {len(candidates)} Rework Item(s).")
		for row in candidates:
			print(f"  {row.name}: {row.warehouse} -> {row.to_warehouse} (GRN {row.grn_number})")
		if cleared:
			print(f"Already cleared from Transit, revert before Complete Transfer: {', '.join(cleared)}")
	return {"candidates": len(candidates), "cleared_from_transit": cleared, "applied": bool(apply)}


def get_candidates():
	transit = frappe.db.get_single_value("YRP Stock Settings", "transit_warehouse")
	if not transit:
		return []
	return frappe.db.sql(
		"""
		SELECT rework.name, rework.warehouse, rework.grn_number, grn.to_warehouse,
			(SELECT COUNT(*) FROM `tabYRP Stock Ledger Entry` sle
			WHERE sle.voucher_type = 'SD YRP GRN Rework Item' AND sle.voucher_no = rework.name
				AND sle.is_cancelled = 0) AS conversions
		FROM `tabSD YRP GRN Rework Item` rework
		JOIN `tabYRP Goods Received Note` grn ON grn.name = rework.grn_number
		WHERE rework.warehouse = %(transit)s
			AND IFNULL(grn.to_warehouse, '') NOT IN ('', %(transit)s)
		ORDER BY rework.name
		""",
		{"transit": transit},
		as_dict=True,
	)

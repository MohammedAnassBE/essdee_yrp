"""One-off: restore the Process Item's group on migrated Work Order invoice commercial rows.

The F15 -> F16 migration copied the garment (physical) row's Item Group onto the
grouped Process row, e.g. "Stitching to Checking Expenses" became "Products".

Run from the bench directory:
	bench --site <site> console
	>>> exec(open("apps/essdee_yrp/scripts/fix_work_order_invoice_item_groups.py").read())
	>>> run()                # dry run, prints the rows
	>>> run(dry_run=False)   # writes and commits
"""

import frappe

QUERY = """
	SELECT commercial.name, commercial.parent, commercial.item,
		commercial.item_group AS stored_group, item.item_group AS master_group
	FROM `tabSD YRP Essdee Purchase Invoice Item` commercial
	JOIN `tabYRP Purchase Invoice` invoice ON invoice.name = commercial.parent
	JOIN `tabItem` item ON item.name = commercial.item
	WHERE commercial.parenttype = 'YRP Purchase Invoice'
	  AND invoice.against = 'YRP Work Order'
	  AND COALESCE(commercial.item_group, '') != item.item_group
"""


def run(dry_run=True):
	rows = frappe.db.sql(QUERY, as_dict=True)
	for row in rows:
		print(f"{row.parent}\t{row.item}\t{row.stored_group} -> {row.master_group}")
		if not dry_run:
			frappe.db.set_value(
				"SD YRP Essdee Purchase Invoice Item",
				row.name,
				"item_group",
				row.master_group,
				update_modified=False,
			)
	if not dry_run:
		frappe.db.commit()
	print(f"{len(rows)} row(s) {'would change' if dry_run else 'updated'}")

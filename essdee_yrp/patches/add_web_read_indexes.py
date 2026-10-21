"""Add leading keys for measured document relationships."""

from collections import defaultdict

import frappe

CANDIDATES = (
	("YRP Goods Received Note Item", ("lot",)),
	("YRP Delivery Challan Item", ("lot",)),
	("Purchase Order Item", ("lot",)),
	("SD YRP Lot MultiSelect", ("lot",)),
	("YRP Stock Entry", ("against_id", "against")),
	("YRP Goods Received Note", ("against_id", "against")),
	("YRP Goods Received Note", ("delivery_challan",)),
	("YRP Goods Received Note", ("lot",)),
	("YRP Delivery Challan", ("work_order",)),
	("YRP Delivery Challan", ("purchase_order",)),
	("YRP Delivery Challan", ("lot",)),
	("Purchase Order", ("lot",)),
	("Purchase Order", ("default_lot",)),
	("SD YRP Cutting Plan", ("work_order",)),
	("SD YRP Finishing Plan", ("lot",)),
	("SD YRP Cutting Marker", ("cutting_plan",)),
	("SD YRP Cutting LaySheet", ("cutting_plan",)),
	("YRP Work Order", ("lot",)),
	("YRP Stock Entry", ("cut_panel_movement",)),
	("YRP Goods Received Note", ("cut_panel_movement",)),
	("YRP Delivery Challan", ("cut_panel_movement",)),
	# Cancel/delete link checks run SELECT DISTINCT on every Dynamic Link options
	# column when Frappe's 12-hour dynamic_link_map cache is cold (F-B37).
	("e-Invoice Log", ("reference_doctype",)),
	("e-Waybill Log", ("reference_doctype",)),
	("Integration Request", ("reference_doctype",)),
	("Payment Entry", ("source_doctype",)),
	("Payment Entry Reference", ("advance_voucher_type",)),
)


def execute():
	for doctype, columns in CANDIDATES:
		if not frappe.db.table_exists(doctype) or not all(frappe.db.has_column(doctype, col) for col in columns):
			continue
		indexes = defaultdict(list)
		table = frappe.db.escape("tab" + doctype).strip("'").replace("`", "``")
		for row in frappe.db.sql(f"SHOW INDEX FROM `{table}`", as_dict=True):
			indexes[row.Key_name].append((row.Seq_in_index, row.Column_name))
		if any(tuple(col for _, col in sorted(parts))[:len(columns)] == columns for parts in indexes.values()):
			continue
		base = "web_read_" + "_".join(columns)
		name = base
		suffix = 1
		while name in indexes:
			name = f"{base}_{suffix}"
			suffix += 1
		frappe.db.add_index(doctype, list(columns), name)
		print(f"Added {doctype}: {name} ({', '.join(columns)})")

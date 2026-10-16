import frappe


def execute():
	if not frappe.db.table_exists("SD YRP Lot Fabric Conversion"):
		return
	from essdee_yrp.fabric_substitution import _rebuild_lot_fabric_conversions

	for lot in frappe.get_all("SD YRP Lot", pluck="name", order_by="name"):
		_rebuild_lot_fabric_conversions(lot)

import frappe


def execute():
	if not (
		frappe.db.table_exists("Lot Fabric Conversion")
		and frappe.get_meta("Lot").has_field("lot_fabric_conversions")
	):
		return
	default_process = frappe.db.get_single_value(
		"IPD Settings", "default_knitting_process"
	)
	if not default_process:
		return
	lots = frappe.db.sql(
		"""
		SELECT DISTINCT wo.lot
		FROM `tabGoods Received Note` grn
		JOIN `tabWork Order` wo ON wo.name = grn.against_id
		WHERE grn.docstatus = 1
			AND grn.against = 'Work Order'
			AND wo.process_name = %s
			AND IFNULL(wo.lot, '') != ''
		ORDER BY wo.lot
		""",
		(default_process,),
		pluck="lot",
	)
	from essdee_yrp.fabric_substitution import _rebuild_lot_fabric_conversions

	for lot in lots:
		_rebuild_lot_fabric_conversions(lot)

# One-time backfill: count fabric GRNs submitted before the Lot Fabric Program
# feature existed. Without this, pre-feature receipts are invisible to the WO
# popup balances, and CANCELLING a pre-feature GRN would drive received_weight
# negative (the on_cancel hook fires with no matching prior increment).
import frappe


def execute():
	if not frappe.db.has_column("Work Order", "lot"):
		return
	from essdee_yrp.fabric_tracking import rebuild_fabric_tracking

	lots = frappe.db.sql_list(
		"SELECT DISTINCT parent FROM `tabLot Fabric Detail` WHERE parenttype = 'Lot'"
	)
	for lot in lots:
		rebuild_fabric_tracking(lot)

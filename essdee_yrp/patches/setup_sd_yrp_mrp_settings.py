# Register the replicated MRP Settings (Single) + its sd_yrp consumer mapping on
# already-installed sites. The DocType JSON is synced by migrate; this patch just
# ensures the Spine consumer handler-mapping row for "MRP Settings" exists (the
# original setup_sd_yrp_spine_consumer patch is marked done and won't re-run).
import frappe


def execute():
	frappe.reload_doc("essdee_yrp", "doctype", "mrp_settings")
	from essdee_yrp.sd_yrp_sync import ensure_consumer_config

	ensure_consumer_config()

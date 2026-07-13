import frappe

# The three fabric sub-process tabs (Knitting / Dyeing / Compacting) were removed
# from the Item Production Detail form in favour of the single generic Fabric
# Processes tab. Fixture sync only inserts/updates records, so dropping them from
# custom_field.json does not delete the already-provisioned Custom Fields on
# existing sites. This patch removes them explicitly. Idempotent: a no-op once the
# records are gone. The inner fabric fields stay (hidden) so legacy cloth IPDs keep
# their data and the synthesize-from-tabs fallback keeps working.

TAB_FIELDS = (
	"Item Production Detail-fabric_knitting_tab",
	"Item Production Detail-fabric_dyeing_tab",
	"Item Production Detail-fabric_compacting_tab",
)


def execute():
	frappe.db.delete("Custom Field", {"name": ["in", TAB_FIELDS]})
	frappe.clear_cache(doctype="Item Production Detail")

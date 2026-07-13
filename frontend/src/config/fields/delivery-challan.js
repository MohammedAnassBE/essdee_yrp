/**
 * Delivery Challan — per-DocType field config consumed by DocDetail.vue.
 *
 * Mirrors yrp's Supplier+Warehouse pair rule (docs/claude/conventions.md
 * 2026-05-23): the from_warehouse autocomplete filters to warehouses
 * belonging to from_location (the from-side Supplier), and to_warehouse
 * filters to warehouses belonging to supplier (the to-side Supplier).
 *
 * Both factories return null when the controlling party is empty, so the
 * LinkField falls through to the default name-search (lists every warehouse
 * — the user can still pick freely). Once the party is set the factory
 * re-runs reactively and the next dropdown open shows the filtered set.
 */
import { searchLink } from "@/api/client"

const linkSearchHandlers = {
	// Desk parity (delivery_challan.js set_query): only submitted, not-closed
	// Work Orders are valid DC targets — a draft WO fails server-side on save.
	work_order: () =>
		(q) => searchLink("Work Order", q, { docstatus: 1, open_status: ["!=", "Close"] }),
	from_warehouse: (form) =>
		form.from_location
			? (q) => searchLink("Warehouse", q, { supplier: form.from_location })
			: null,
	to_warehouse: (form) =>
		form.supplier
			? (q) => searchLink("Warehouse", q, { supplier: form.supplier })
			: null,
}

// Q18: same single vendor-party term as Work Order ("Job-worker").
const labels = {
	supplier: "Job-worker",
	supplier_name: "Job-worker Name",
}

// Transfer status (2026-07-10): `is_internal_unit` is recomputed server-side
// from the from_location + supplier company-location flags (the DC controller's
// compute_internal_unit), and `transfer_complete`/STE figures merely indicate
// its progress — the user never edits any of them. DocDetail renders them as
// read-only indicator badges at the TOP of the Details tab instead of an
// editable/ordinary section.
const transferFields = [
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
]

export default {
	linkSearchHandlers,
	labels,
	hideFormFields: transferFields,
	hideViewFields: transferFields,
}

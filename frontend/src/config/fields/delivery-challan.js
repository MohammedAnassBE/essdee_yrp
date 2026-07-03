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

export default {
	linkSearchHandlers,
	labels,
}

/**
 * Goods Received Note — per-DocType field config.
 *
 * Mirrors yrp's Supplier+Warehouse pair rule (conventions.md 2026-05-23 +
 * 2026-05-29). On GRN the from-side party is `supplier` (Sender) and the
 * to-side party is `delivery_location` (Receiver):
 *   from_warehouse → filtered by supplier
 *   to_warehouse   → filtered by delivery_location
 *
 * Returns null when the party is empty so the LinkField falls through to
 * listing all warehouses — the user can still pick freely.
 */
import { searchLink } from "@/api/client"

const linkSearchHandlers = {
	from_warehouse: (form) =>
		form.supplier
			? (q) => searchLink("Warehouse", q, { supplier: form.supplier })
			: null,
	to_warehouse: (form) =>
		form.delivery_location
			? (q) => searchLink("Warehouse", q, { supplier: form.delivery_location })
			: null,
}

// Q18: unify the vendor-party term ("Job-worker") with WO + DC. On a GRN the
// sender party is `supplier`; `delivery_location` is the receiving side.
const labels = {
	supplier: "Job-worker",
}

// Q13: surface help on the pivotal Against selector (Desk hides its description
// from /web users) so a floor user knows what the choice drives.
const help = {
	against: "Receive against a Work Order (job-work return) or a Purchase Order (bought-in goods). This drives which items and quantities load below.",
}

export default {
	linkSearchHandlers,
	labels,
	help,
}

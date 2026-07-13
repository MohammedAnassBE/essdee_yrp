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
	// Desk parity (goods_received_note.js set_query): the source document must
	// be submitted and not closed — a draft WO/PO fails server-side on save.
	against_id: (form) =>
		form.against
			? (q) => searchLink(form.against, q, { docstatus: 1, open_status: ["!=", "Close"] })
			: null,
	// Desk parity: only submitted DCs of the selected Work Order.
	delivery_challan: (form) =>
		(q) => searchLink("Delivery Challan", q, {
			docstatus: 1,
			work_order: form.against === "Work Order" ? form.against_id || "" : "",
		}),
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

// Transfer status (2026-07-10, same rule as Delivery Challan): recomputed
// server-side via compute_internal_unit (from the party company-location
// flags) / maintained by the engine — rendered as indicator badges at the
// top of the Details tab, never as editable/ordinary fields.
const transferFields = [
	"is_internal_unit",
	"transfer_complete",
	"ste_transferred",
	"ste_transferred_percent",
]

export default {
	linkSearchHandlers,
	labels,
	help,
	hideFormFields: transferFields,
	hideViewFields: transferFields,
}

/**
 * Essdee YRP — Home "My Work Today" work-queues.
 *
 * Four operational queues, each rendered as a clickable card on HomePage that
 * deep-links to its DocType list pre-filtered to the same condition. Counts are
 * fetched live (frappe.desk.reportview.get_count) in parallel and degrade to
 * "—" on error so the home never crashes.
 *
 * Each queue descriptor:
 *   { key, label, sub, icon, tone, doctype, filters, route, count, error }
 * where `filters` is the deep-link filter as a JSON array of [field, op, value]
 * triples — the exact shape DynamicListPage's `?filters=` base filter parses.
 *
 * Tones map to coloured square icons in HomePage (amber / info / emerald /
 * slate). Visibility is gated per-queue on canRead(doctype) by the caller.
 */

import { reactive, ref } from "vue"
import { getCount } from "@/api/client"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"

// get_count takes a {field: value} object filter; the cards deep-link with the
// array-of-triples form. Convert one to the other so a single source of truth
// (the triples) drives both the count and the URL.
function triplesToObject(triples) {
	const obj = {}
	for (const [field, op, value] of triples) {
		obj[field] = [op, value]
	}
	return obj
}

export function useHomeQueues() {
	const { canRead } = usePermissions()

	// Static queue definitions. `filters` is the deep-link/base-filter triples.
	const queues = reactive([
		{
			key: "open-lots",
			label: "Open Lots",
			sub: "Lots still in production",
			icon: "pi pi-inbox",
			tone: "amber",
			doctype: "Lot",
			filters: [["status", "=", "Open"]],
			count: null, // null = still loading / unknown; rendered as "—"
			error: false,
		},
		{
			key: "open-work-orders",
			label: "Open Work Orders",
			sub: "Submitted, not closed or cancelled",
			icon: "pi pi-bars",
			tone: "slate",
			doctype: "Work Order",
			filters: [
				["docstatus", "=", 1],
				["status", "not in", ["Closed", "Cancelled"]],
			],
			count: null,
			error: false,
		},
		{
			key: "draft-dcs",
			label: "Draft Delivery Challans",
			sub: "Not yet submitted",
			icon: "pi pi-send",
			tone: "info",
			doctype: "Delivery Challan",
			filters: [["docstatus", "=", 0]],
			count: null,
			error: false,
		},
		{
			key: "draft-grns",
			label: "Draft GRNs",
			sub: "Goods Received Notes not yet submitted",
			icon: "pi pi-plus-circle",
			tone: "emerald",
			doctype: "Goods Received Note",
			filters: [["docstatus", "=", 0]],
			count: null,
			error: false,
		},
	])

	const loading = ref(false)

	// Resolve route slug per queue (used by the card to navigate). Computed once.
	for (const q of queues) {
		q.route = getRegistryByDoctype(q.doctype)?.route || ""
	}

	// Visible queues = those the user can read. The caller renders only these.
	function visibleQueues() {
		return queues.filter((q) => canRead(q.doctype))
	}

	// Load counts for every readable queue in parallel. Each count is isolated:
	// one failing query shows "—" on that card only.
	async function loadCounts() {
		loading.value = true
		const targets = visibleQueues()
		await Promise.all(
			targets.map(async (q) => {
				try {
					const c = await getCount(q.doctype, triplesToObject(q.filters))
					q.count = typeof c === "number" ? c : Number(c) || 0
					q.error = false
				} catch (_) {
					q.count = null
					q.error = true
				}
			})
		)
		loading.value = false
	}

	return { queues, visibleQueues, loadCounts, loading }
}

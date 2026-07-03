// Prev/next document navigation for the detail page — Frappe v15 Desk parity.
//
// Right arrow → next document, left arrow → previous document, stepping through
// the list the user came from (its filters + sort), captured in useListContext.
//
// The neighbour lookup reuses Frappe's OWN whitelisted method
// `frappe.desk.form.utils.get_next` — the exact call v15's form arrows make. It
// resolves the adjacent name with a composite (sort-value, then name) tie-break,
// honours filters, and respects permissions, so there is no fragile client-side
// ordering logic to get wrong. It returns the neighbour name, or null at a list
// boundary (its "No further records" msgprint rides a 200 response, which our
// api/client request() ignores — so no spurious toast).

import { ref, computed } from "vue"
import { callMethod } from "@/api/client"
import { getListContext } from "@/composables/useListContext"

const GET_NEXT = "frappe.desk.form.utils.get_next"

// Parse an order_by string ("modified desc", "creation asc", "modified desc, name asc")
// into { field, order } for get_next's sort_field / sort_order. Takes the FIRST
// clause (get_next sorts on one field, name as the implicit tiebreak), strips any
// `tabDocType`. qualifier and backticks, and defaults to modified/desc.
function parseOrderBy(orderBy) {
	const first = String(orderBy || "").split(",")[0].trim()
	if (!first) return { field: "modified", order: "desc" }
	const parts = first.split(/\s+/)
	const rawField = (parts[0] || "").replace(/`/g, "")
	const order = (parts[1] || "desc").toLowerCase() === "asc" ? "asc" : "desc"
	// A table-qualified sort (`tabSomething`.field) can't be handed to get_next as a
	// bare parent column — it reads get_value(doctype, name, sort_field), so a child
	// field name would query a column the parent doesn't have. Fall back to the safe
	// default. (Today the list only sorts by parent columns, so this is defensive.)
	if (/^tab[^.]+\./i.test(rawField)) return { field: "modified", order }
	return { field: rawField || "modified", order }
}

/**
 * @param {object} opts
 * @param {import('vue').Ref<string>|()=>string} opts.doctype  current doctype (ref or getter)
 * @param {import('vue').Ref<string>|()=>string} opts.docRoute current /web route segment
 * @param {import('vue').Ref<string>|()=>string} opts.name     current document name
 * @param {import('vue').Ref<boolean>|()=>boolean} opts.enabled resolve only while true (view mode, real doc)
 * @param {(route:string,name:string)=>void} navigate          performs the route change
 */
export function useDocNav({ doctype, docRoute, name, enabled }, navigate) {
	const read = (v) => (typeof v === "function" ? v() : v?.value)

	const prevName = ref(null)
	const nextName = ref(null)
	// Monotonic token so a stale in-flight resolve can't overwrite the names for
	// the document now on screen. This matters for the re-resolve-on-the-SAME-mount
	// path — reloadView() after submit/cancel/amend. Stepping to another document
	// remounts the whole view (AppLayout keys <router-view> by route path), so each
	// navigation already gets a fresh useDocNav with token=0.
	let token = 0

	function context() {
		const dt = read(doctype)
		const ctx = getListContext(dt)
		if (ctx) {
			const { field, order } = parseOrderBy(ctx.orderBy)
			return { sortField: field, sortOrder: order, filters: ctx.filters }
		}
		// No captured list (direct link / cold reload / cross-doctype hop): fall
		// back to the list's default ordering over the whole doctype.
		return { sortField: "modified", sortOrder: "desc", filters: [] }
	}

	async function resolve() {
		prevName.value = null
		nextName.value = null
		const dt = read(doctype)
		const value = read(name)
		if (!read(enabled) || !dt || !value || value === "new") return

		const { sortField, sortOrder, filters } = context()
		const hasFilters = Array.isArray(filters) ? filters.length > 0 : !!filters && Object.keys(filters).length > 0
		const argsFor = (prev) => ({
			doctype: dt,
			value,
			prev,
			sort_field: sortField,
			sort_order: sortOrder,
			...(hasFilters ? { filters } : {}),
		})

		const my = ++token
		try {
			// prev=1 → previous, prev=0 → next (get_next's own convention).
			const [prev, next] = await Promise.all([
				callMethod(GET_NEXT, argsFor(1)),
				callMethod(GET_NEXT, argsFor(0)),
			])
			if (my !== token) return // a newer resolve() superseded this one
			prevName.value = prev || null
			nextName.value = next || null
		} catch (_) {
			if (my !== token) return
			prevName.value = null
			nextName.value = null
		}
	}

	function go(target) {
		const route = read(docRoute)
		if (!target || !route) return
		navigate(route, target)
	}

	return {
		prevName,
		nextName,
		hasPrev: computed(() => !!prevName.value),
		hasNext: computed(() => !!nextName.value),
		goPrev: () => go(prevName.value),
		goNext: () => go(nextName.value),
		resolve,
	}
}

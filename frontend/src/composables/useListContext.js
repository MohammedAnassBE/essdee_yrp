// Last-list-viewed context, so a detail page can step to the prev/next document
// through EXACTLY the list the user came from — Frappe v15 Desk parity for the
// form's ‹ › record navigation (see useDocNav).
//
// Why a module-level singleton (not a per-component composable): the list and the
// detail are different route components. The list's filter/sort state lives in its
// own `useDocList` instance and is destroyed when we navigate into a document. We
// stash the resolved query here on row-click; the detail page reads it back.
//
// Stored per doctype as { docRoute, orderBy, filters } where:
//   orderBy  — the list's order_by string, e.g. "modified desc" (parsed later)
//   filters  — the EXACT filter param the list queried with (object OR Frappe
//              tuples); search (or_filters) is deliberately excluded — Frappe's
//              own get_next ignores or_filters too, so stepping matches v15.
//
// Mirrored to sessionStorage so the context survives a hard refresh of the detail
// page (the in-memory Map alone would be lost on reload). sessionStorage is
// per-tab, so contexts never bleed across tabs; within a tab it's last-write-wins
// per doctype (the most recent list row-click for that doctype).

const STORE_KEY = "essdee:list-nav-ctx"

// doctype -> { docRoute, orderBy, filters }
const mem = new Map()
let hydrated = false

function hydrateOnce() {
	if (hydrated) return
	hydrated = true
	try {
		const raw = sessionStorage.getItem(STORE_KEY)
		if (!raw) return
		const obj = JSON.parse(raw)
		if (obj && typeof obj === "object") {
			for (const [k, v] of Object.entries(obj)) mem.set(k, v)
		}
	} catch (_) {
		/* sessionStorage unavailable / corrupt — start empty */
	}
}

function persist() {
	try {
		const obj = {}
		for (const [k, v] of mem.entries()) obj[k] = v
		sessionStorage.setItem(STORE_KEY, JSON.stringify(obj))
	} catch (_) {
		/* quota / unavailable — in-memory still works for this session */
	}
}

/**
 * Record the query the user is navigating away from, keyed by doctype.
 * @param {string} doctype
 * @param {{ docRoute: string, orderBy?: string, filters?: any }} ctx
 */
export function captureListContext(doctype, ctx) {
	if (!doctype || !ctx) return
	hydrateOnce()
	mem.set(doctype, {
		docRoute: ctx.docRoute || "",
		orderBy: ctx.orderBy || "",
		filters: ctx.filters ?? [],
	})
	persist()
}

/**
 * Read the last-viewed list context for a doctype, or null if none.
 * @param {string} doctype
 * @returns {{ docRoute: string, orderBy: string, filters: any } | null}
 */
export function getListContext(doctype) {
	hydrateOnce()
	if (!doctype) return null
	return mem.get(doctype) || null
}

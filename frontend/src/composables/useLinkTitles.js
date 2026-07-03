/**
 * useLinkTitles — resolve Link-field codes (e.g. `S-0003`, `PC-00007`) to the
 * human title a floor manager actually recognises ("Facing Vendor", "Dyeing
 * Charges"). This is the engine behind UX quick-win Q1 ("resolve link codes →
 * human names") in both the detail view and the list.
 *
 * Two resolution sources, cheapest first:
 *   1. A `<field>_name` SIBLING already present on the row/doc — many yrp links
 *      ship one via `fetch_from` (e.g. `supplier_name`). Zero network cost.
 *      That lookup is synchronous and lives in the consuming template; this
 *      composable handles the generic case below.
 *   2. A GENERIC cached resolver — for any Link whose target has a `title_field`
 *      but no sibling, batch-fetch the titles by name (one request per target
 *      doctype per view) and cache them. `display()` returns the raw code until
 *      the title arrives, then re-renders reactively.
 *
 * The cache is MODULE-LEVEL and reactive, so it is shared across every view and
 * every navigation in the session — a Supplier resolved on a Work Order detail
 * is instantly named on the Delivery Challan list. Negative results (no
 * title_field, or fetch failed) are cached too, so we never refetch a dead end.
 */
import { reactive } from "vue"
import { getList, getMeta } from "@/api/client"

// `${doctype}::${name}` → title string, or null (resolved, no human title).
// undefined = not yet resolved. Reactive: setting a key re-renders readers.
const titleCache = reactive({})

// doctype → title_field string, "" = no title field (use code), or undefined =
// not yet looked up. Avoids re-fetching meta per name.
const titleFieldCache = reactive({})

// In-flight prime() promises keyed by doctype, so concurrent components asking
// for the same target don't fan out duplicate requests.
const inflight = {}

function key(doctype, name) {
	return `${doctype}::${name}`
}

async function resolveTitleField(doctype) {
	if (doctype in titleFieldCache) return titleFieldCache[doctype]
	try {
		const bundle = await getMeta(doctype)
		const parent = Array.isArray(bundle) ? bundle[0] : null
		const tf = parent?.title_field || ""
		// A title_field that IS `name` adds nothing over the code — treat as none.
		titleFieldCache[doctype] = tf && tf !== "name" ? tf : ""
	} catch (_) {
		titleFieldCache[doctype] = ""
	}
	return titleFieldCache[doctype]
}

/**
 * Fetch + cache titles for a set of (doctype, name) pairs. Groups by doctype,
 * one list request each, skipping names already cached. Safe to call on every
 * doc load / page change — it no-ops for already-resolved values.
 */
async function prime(pairs) {
	const byDoctype = {}
	for (const { doctype, name } of pairs || []) {
		if (!doctype || !name) continue
		if (key(doctype, name) in titleCache) continue
		;(byDoctype[doctype] ||= new Set()).add(String(name))
	}
	await Promise.all(
		Object.entries(byDoctype).map(async ([doctype, nameSet]) => {
			const names = [...nameSet]
			const tf = await resolveTitleField(doctype)
			if (!tf) {
				// No human title for this doctype — cache null so display() shows the
				// code and we never look again.
				for (const n of names) titleCache[key(doctype, n)] = null
				return
			}
			const flightKey = `${doctype}::${names.join(",")}`
			if (!inflight[flightKey]) {
				inflight[flightKey] = getList(doctype, {
					fields: ["name", tf],
					filters: [["name", "in", names]],
					limit_page_length: names.length,
				})
					.then(({ data }) => {
						const found = new Set()
						for (const row of data || []) {
							const t = row[tf]
							titleCache[key(doctype, row.name)] =
								t && String(t) !== String(row.name) ? String(t) : null
							found.add(String(row.name))
						}
						// Names with no row (deleted / no perm) → cache null, don't retry.
						for (const n of names) {
							if (!found.has(n)) titleCache[key(doctype, n)] = null
						}
					})
					.catch(() => {
						// Transient failure (network / 5xx / timeout): do NOT cache. Leaving
						// the keys unset lets prime() retry them on the next view — and since
						// titleFor() reading a missing key still tracks reactivity, the names
						// fill in once a later prime() succeeds. The doctype shows the raw
						// code meanwhile. (Only the deterministic no-title-field / no-row
						// cases above cache null permanently — those genuinely won't change.)
					})
					.finally(() => {
						delete inflight[flightKey]
					})
			}
			await inflight[flightKey]
		}),
	)
}

/**
 * The resolved title for (doctype, name), or null if none/unresolved. Reactive:
 * reading this inside a computed/render re-runs when the title arrives.
 */
function titleFor(doctype, name) {
	if (!doctype || !name) return null
	const v = titleCache[key(doctype, name)]
	return v == null ? null : v
}

/**
 * Display parts for a Link value: `{ primary, code }`.
 *  - `siblingName` (the `<field>_name` value, when the caller has one) wins.
 *  - else the generically-resolved title.
 *  - else the raw code as primary with no secondary.
 * When a human name is found, `code` carries the raw value to render muted
 * beside it ("Facing Vendor · S-0003"). When the primary IS the code, `code`
 * is "" so the template shows the code once.
 */
function linkParts(doctype, name, siblingName) {
	const code = name == null ? "" : String(name)
	const human = (siblingName && String(siblingName)) || titleFor(doctype, name)
	if (human && human !== code) return { primary: human, code }
	return { primary: code, code: "" }
}

export function useLinkTitles() {
	return { prime, titleFor, linkParts }
}

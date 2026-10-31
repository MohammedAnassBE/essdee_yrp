import { onScopeDispose, toValue } from "vue"

import { getList } from "../api/frappe.js"
import { useListRealtime } from "./live/useListRealtime.js"

/**
 * Calls `onChange()` when a document linked to one parent changes anywhere (another user, tab or job).
 * `relations` lists `{ doctype, filters }` where `filters` selects the parent's documents, e.g.
 * `{ doctype: "YRP Delivery Challan", filters: { work_order: "WO-1" } }`; an empty list watches nothing.
 * A change to a document already shown (`knownNames`) refreshes at once; for other names one
 * list read checks whether they now belong to this parent, so unrelated documents cost no refresh.
 *
 * @param {import("vue").MaybeRefOrGetter<{ doctype: string, filters: Record<string, unknown> }[]>} relations
 * @param {{ knownNames: () => Iterable<string>, onChange: () => unknown, findLinked?: typeof findLinkedNames }} options
 */
export function useRelatedDocumentsRealtime(relations, { knownNames, onChange, findLinked = findLinkedNames }) {
	const relationList = () => (toValue(relations) || []).filter((relation) => relation?.doctype)
	let isDisposed = false
	const subscription = useListRealtime(() => relationList().map((relation) => relation.doctype), async ({ events, hasUnnamed }) => {
		const isRelated = hasUnnamed || await hasRelatedChange(relationList(), events, new Set(knownNames()), findLinked)
		// A lookup can outlive the page; a disposed page must not refetch.
		if (isRelated && !isDisposed) await onChange()
	})
	onScopeDispose(() => { isDisposed = true })
	return subscription
}

export async function hasRelatedChange(relations, events, known, findLinked = findLinkedNames) {
	if (events.some((event) => known.has(event.name))) return true
	for (const relation of relations) {
		const names = [...new Set(events.filter((event) => event.doctype === relation.doctype).map((event) => event.name))]
		if (names.length && (await findLinked(relation, names)).length) return true
	}
	return false
}

export async function findLinkedNames({ doctype, filters }, names) {
	const conditions = Object.entries(filters || {}).map(([fieldname, value]) => [doctype, fieldname, "=", value])
	const rows = await getList(doctype, { fields: ["name"], filters: [...conditions, [doctype, "name", "in", names]], pageLength: names.length })
	return rows.map((row) => row.name)
}

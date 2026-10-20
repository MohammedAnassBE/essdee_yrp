import { ref, watch } from "vue"
import { getDocPermissions } from "../api/frappe.js"

// Share concurrent checks between document actions, without retaining stale permissions.
const pending = new Map()
export function useDocumentPermissions(source, enabled = () => true, fetchPermissions = getDocPermissions) {
	const permissions = ref(null)
	watch(() => [...source(), enabled()], async ([doctype, name, _status, active], _old, onCleanup) => {
		let stale = false
		onCleanup(() => { stale = true })
		permissions.value = null
		if (!active || !name) return
		const key = JSON.stringify([doctype, name, Number(_status ?? 0)])
		try {
			if (!pending.has(key)) {
				const request = Promise.resolve().then(() => fetchPermissions(doctype, name))
				pending.set(key, request)
				request.finally(() => { if (pending.get(key) === request) pending.delete(key) }).catch(() => {})
			}
			const result = await pending.get(key)
			if (!stale) permissions.value = result
		} catch {
			// Actions stay hidden when permissions cannot be evaluated.
		}
	}, { immediate: true })
	return permissions
}

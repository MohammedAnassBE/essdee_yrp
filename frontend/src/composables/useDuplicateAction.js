import { computed, toValue } from "vue"
import { useRouter } from "vue-router"
import { getDuplicateValues } from "../api/frappe.js"

/** Menu-only "Duplicate" action for DocumentActionStrip; null when it cannot run. */
export function useDuplicateAction({ canCreate, newRouteName, name, busy = false, queryKey = "duplicate_from", router = useRouter() }) {
	return computed(() => {
		const source = toValue(name)
		const routeName = toValue(newRouteName)
		if (!toValue(canCreate) || !source || !routeName) return null
		return {
			key: "duplicate",
			label: "Duplicate",
			icon: "pi pi-clone",
			command: () => runDuplicate(router, { newRouteName: routeName, name: source, queryKey: toValue(queryKey) }),
			disabled: Boolean(toValue(busy)),
			loading: false,
			menuOnly: true,
		}
	})
}

export function runDuplicate(router, { newRouteName, name, queryKey = "duplicate_from" }) {
	return router.push({ name: newRouteName, query: { [queryKey]: name } })
}

/** Draft values for a new-document page opened with ?duplicate_from=<name>, else null. */
export async function loadDuplicateValues(doctype, route, queryKey = "duplicate_from") {
	const source = toValue(route)?.query?.[queryKey]
	return source ? await getDuplicateValues(doctype, String(source)) : null
}

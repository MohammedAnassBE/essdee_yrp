import { getCurrentScope, onScopeDispose, ref, toValue, watch } from "vue"
import { getCount } from "../api/frappe.js"
import { createDebouncedSearch } from "../utils/debouncedSearch.js"

/** Debounced "a `doctype` named `name` already exists" check for new documents; returns the matched name or "". UX only, the server still enforces uniqueness. */
export function useNameExists(doctype, name, { enabled = () => true, count = getCount, timers = {} } = {}) {
	const existingName = ref("")
	const search = createDebouncedSearch(
		async ([target, value]) => ((await count(target, [["name", "=", value]])) > 0 ? value : ""),
		{ onResult: (result) => { existingName.value = result }, onError: () => {}, onSettled: () => {} },
		{ delay: 300, ...timers },
	)
	watch(() => [toValue(doctype), String(toValue(name) ?? "").trim(), Boolean(toValue(enabled))], ([target, value, active]) => {
		existingName.value = ""
		if (active && target && value) search.queue([target, value])
		else search.invalidate()
	}, { immediate: true })
	if (getCurrentScope()) onScopeDispose(search.invalidate)
	return existingName
}

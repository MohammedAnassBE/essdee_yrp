import { watch } from "vue"
import { useRoute } from "vue-router"

/** Query values for the report's own filter `fields`; list filters take a one-item list. */
export function reportQueryValues(query = {}, filters = {}, fields = []) {
	const values = {}
	for (const field of fields) {
		const value = Array.isArray(query[field]) ? query[field][0] : query[field]
		if (typeof value !== "string" || !value) continue
		values[field] = Array.isArray(filters[field]) ? [value] : value
	}
	return values
}

/** Fills `filters` from `?field=value` links (e.g. a Lot's Reports list), then calls `run` to generate. */
export function useReportQueryPrefill(filters, fields, run) {
	const route = useRoute()
	watch(() => fields.map((field) => route?.query?.[field]), () => {
		const values = reportQueryValues(route?.query, filters, fields)
		if (!Object.keys(values).length) return
		Object.assign(filters, values)
		run?.()
	}, { immediate: true })
}

import { computed, onScopeDispose, reactive, shallowRef, toValue } from "vue"

import { activeKeywords, columnKey, createRowFilter, filteredTotalRow, splitTotalRow } from "../components/reports/inlineFilters.js"

export const INLINE_FILTER_DELAY = 250

/**
 * Desk's DataTable `inlineFilters` for a /web report table: one keyword per column, applied after a
 * short pause in typing. `rows` is the unfiltered result while no keyword is set, so callers can keep
 * using it as the reset key for incremental mounting.
 */
export function useInlineFilters(rows, columns, { cellValue, cellText = cellValue, delay = INLINE_FILTER_DELAY } = {}) {
	const inputs = reactive({})
	const keywords = shallowRef({})
	let timer = null

	const split = computed(() => splitTotalRow(toValue(rows) || []))
	const rowFilter = computed(() => createRowFilter(split.value.dataRows, toValue(columns) || [], { cellValue, cellText }))
	const appliedKeywords = computed(() => activeKeywords(keywords.value, rowFilter.value))
	const isFiltered = computed(() => Object.keys(appliedKeywords.value).length > 0)
	const matchingIndices = computed(() => isFiltered.value ? rowFilter.value.getMatchingIndices(appliedKeywords.value) : null)
	const filteredRows = computed(() => {
		if (!isFiltered.value) return toValue(rows) || []
		const { dataRows, totalRow } = split.value
		const matches = matchingIndices.value.map(index => dataRows[index])
		if (!totalRow) return matches
		return [...matches, filteredTotalRow(matches, toValue(columns) || [], cellValue, totalRow)]
	})
	const dataRowCount = computed(() => split.value.dataRows.length)
	const matchingCount = computed(() => matchingIndices.value?.length ?? dataRowCount.value)

	function applyKeywords() {
		clearTimeout(timer)
		timer = null
		keywords.value = { ...inputs }
	}

	function setFilter(key, keyword) {
		inputs[key] = keyword
		clearTimeout(timer)
		timer = setTimeout(applyKeywords, delay)
	}

	function clearFilters() {
		for (const key of Object.keys(inputs)) delete inputs[key]
		applyKeywords()
	}

	onScopeDispose(() => clearTimeout(timer))

	return {
		columnKey,
		inputs,
		keywords: appliedKeywords,
		isFiltered,
		/** Row indices into the unfiltered data rows (total row excluded), or null when nothing is filtered. */
		matchingIndices,
		filteredRows,
		dataRowCount,
		matchingCount,
		setFilter,
		applyKeywords,
		clearFilters,
	}
}

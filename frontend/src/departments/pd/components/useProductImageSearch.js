import { nextTick, onBeforeUnmount, ref, watch } from "vue"

import { searchProductImages } from "../../../api/pd.js"
import { hasMinimumQuery } from "../pdViews.js"

export function useProductImageSearch() {
	const query = ref("")
	const results = ref([])
	const searching = ref(false)
	const hasSearched = ref(false)
	const actionError = ref("")
	let searchTimer = null
	let searchSequence = 0

	function prepareSearch(value) {
		clearTimeout(searchTimer)
		const sequence = ++searchSequence
		searching.value = false
		hasSearched.value = false
		if (hasMinimumQuery(value)) return sequence
		results.value = []
		return 0
	}

	async function runSearch(value, sequence) {
		searching.value = true
		actionError.value = ""
		try {
			const rows = await searchProductImages(String(value).trim())
			if (sequence === searchSequence) results.value = rows || []
		} catch (reason) {
			if (sequence === searchSequence) actionError.value = reason?.message || "Unable to search Product Images."
		} finally {
			if (sequence === searchSequence) {
				searching.value = false
				hasSearched.value = true
			}
		}
	}

	function scheduleSearch(value) {
		const sequence = prepareSearch(value)
		if (sequence) searchTimer = setTimeout(() => runSearch(value, sequence), 300)
	}

	async function refreshSearch(value) {
		query.value = value
		await nextTick()
		const sequence = prepareSearch(value)
		if (sequence) await runSearch(value, sequence)
	}

	watch(query, scheduleSearch)
	onBeforeUnmount(() => {
		clearTimeout(searchTimer)
		++searchSequence
	})

	return { query, results, searching, hasSearched, actionError, refreshSearch }
}

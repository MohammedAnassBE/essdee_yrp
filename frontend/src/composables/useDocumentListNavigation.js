import { computed, onBeforeUnmount, ref, toValue, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getList } from "../api/frappe.js"
import { parentGroupBy } from "../components/common/listItemFilters.js"
import {
	adjacentWindowStart,
	navigationContextMatches,
	readNavigationState,
	resolveAdjacentNames,
	writeNavigationState,
} from "../utils/listNavigation.js"

function historyReference() {
	if (typeof window === "undefined") return null
	const value = window.history.state?.essdeeListNavigation
	return value && typeof value === "object" ? { ...value } : null
}

export function useDocumentListNavigation({ currentName, disabled }) {
	const route = useRoute()
	const router = useRouter()
	const previousName = ref(null)
	const previousModified = ref("")
	const nextName = ref(null)
	const nextModified = ref("")
	const loading = ref(false)
	const changed = ref(false)
	const error = ref("")
	const hasContext = ref(false)
	const sourceFullPath = ref("")
	let activeReference = null
	let activeState = null
	let loadSequence = 0
	let disposed = false

	const navigationDisabled = computed(() => Boolean(toValue(disabled)) || loading.value || changed.value || Boolean(error.value))

	function reset() {
		previousName.value = null
		previousModified.value = ""
		nextName.value = null
		nextModified.value = ""
		loading.value = false
		changed.value = false
		error.value = ""
		hasContext.value = false
		sourceFullPath.value = ""
		activeReference = null
		activeState = null
	}

	function applyAdjacent(adjacent) {
		previousName.value = adjacent.previousName
		previousModified.value = adjacent.previousModified
		nextName.value = adjacent.nextName
		nextModified.value = adjacent.nextModified
		changed.value = adjacent.changed
	}

	async function fetchAdjacent(reference, state) {
		const rows = await getList(state.doctype, {
			fields: ["name", "modified"],
			filters: state.filters,
			orderBy: state.orderBy,
			start: adjacentWindowStart(reference.index),
			pageLength: 3,
			groupBy: parentGroupBy(state.filters, state.doctype),
		})
		return resolveAdjacentNames({ reference, rows })
	}

	async function load() {
		const sequence = ++loadSequence
		const name = String(toValue(currentName) || "")
		reset()
		if (!name || typeof window === "undefined") return

		const reference = historyReference()
		const state = readNavigationState(window.sessionStorage, reference?.stateKey)
		if (!navigationContextMatches(reference, state, route.name, name)) return

		hasContext.value = true
		sourceFullPath.value = state.sourceFullPath || ""
		activeReference = reference
		activeState = state
		loading.value = true
		try {
			const adjacent = await fetchAdjacent(reference, state)
			if (disposed || sequence !== loadSequence) return
			applyAdjacent(adjacent)
		} catch (reason) {
			if (disposed || sequence !== loadSequence) return
			error.value = reason?.message || "Unable to load list navigation."
		} finally {
			if (!disposed && sequence === loadSequence) loading.value = false
		}
	}

	async function go(offset) {
		if (navigationDisabled.value || !activeReference || !activeState || typeof window === "undefined") return false
		const sequence = ++loadSequence
		const sourceReference = activeReference
		const sourceState = activeState
		loading.value = true
		try {
			const adjacent = await fetchAdjacent(sourceReference, sourceState)
			if (disposed || sequence !== loadSequence) return false
			applyAdjacent(adjacent)
			if (adjacent.changed) return false

			const name = offset < 0 ? adjacent.previousName : adjacent.nextName
			const modified = offset < 0 ? adjacent.previousModified : adjacent.nextModified
			if (!name || !modified) return false
			const index = Math.max(0, Number(sourceReference.index || 0) + offset)
			const pageSize = Math.max(1, Number(sourceState.pageSize) || 20)
			const state = {
				...sourceState,
				globalIndex: index,
				pageStart: Math.floor(index / pageSize) * pageSize,
			}
			const stateKey = writeNavigationState(window.sessionStorage, state)
			const reference = {
				...sourceReference,
				stateKey,
				index,
				currentName: name,
				currentModified: modified,
			}
			await router.replace({
				name: reference.targetRouteName,
				params: { ...route.params, [state.targetParamName]: name },
				query: route.query,
				hash: route.hash,
				state: { essdeeListNavigation: reference },
			})
			return true
		} catch (reason) {
			if (!disposed && sequence === loadSequence) error.value = reason?.message || "Unable to load list navigation."
			return false
		} finally {
			if (!disposed && sequence === loadSequence) loading.value = false
		}
	}

	watch(
		[() => String(toValue(currentName) || ""), () => route.fullPath],
		load,
		{ immediate: true, flush: "post" },
	)

	onBeforeUnmount(() => {
		disposed = true
		loadSequence += 1
	})

	return {
		previousName,
		nextName,
		loading,
		changed,
		error,
		hasContext,
		sourceFullPath,
		navigationDisabled,
		goPrevious: () => go(-1),
		goNext: () => go(1),
	}
}

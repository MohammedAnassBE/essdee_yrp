import { computed, ref, watch } from "vue"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import { resolveLotTab } from "./lotLayout.js"

/** Active tab in `?tab=` (legacy keys resolve to a tab plus an expanded section) and the expanded sections. */
export function useLotLayout(tabs, route, router) {
	const resolved = computed(() => resolveLotTab(route.query.tab, tabs))
	const activeTab = computed({
		get: () => resolved.value.tab,
		set: (tab) => router.replace({ query: { ...route.query, tab }, hash: route.hash, state: preserveListNavigationState() }),
	})
	const expanded = ref(resolved.value.section ? [resolved.value.section] : [])
	const scrollTo = computed(() => resolved.value.section)
	watch(scrollTo, (section) => {
		if (section && !expanded.value.includes(section)) expanded.value = [...expanded.value, section]
	})
	function openSection(key) {
		if (activeTab.value !== "lot") activeTab.value = "lot"
		if (!expanded.value.includes(key)) expanded.value = [...expanded.value, key]
	}
	return { activeTab, expanded, scrollTo, openSection }
}

/** Editor Cloth Program/BOM data, fetched once on first visit to either tab of a saved Lot. */
export function useLotTabWorkspace(lotId, activeTab, fetchWorkspace) {
	const workspace = ref(null)
	const loading = ref(false)
	const error = ref("")
	async function load() {
		loading.value = true
		error.value = ""
		try {
			workspace.value = await fetchWorkspace(lotId)
		} catch (reason) {
			error.value = reason?.message || "Unable to load this Lot."
		} finally {
			loading.value = false
		}
	}
	watch(activeTab, (tab) => {
		if (lotId && tab !== "lot" && !workspace.value && !loading.value) load()
	}, { immediate: true })
	return { tabWorkspace: workspace, tabLoading: loading, tabError: error, loadTabWorkspace: load }
}

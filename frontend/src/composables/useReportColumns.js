import { computed, onScopeDispose, ref, unref, watch } from "vue"

import {
	getLinkFieldOptions,
	getLinkedValues,
	getReportLayout,
	resetReportLayout as resetReportLayoutRequest,
	saveReportLayout as saveReportLayoutRequest,
} from "../api/webReports.js"
import {
	buildLinkedValueBatches,
	cellAlign,
	createHydrationLifecycle,
	getLayoutColumnsForSave,
	hydrateLinkedValueBatches,
	reconcileReportLayout,
	reportCellValue,
	toLayoutColumn,
} from "./reportColumns.js"

export function useReportColumns({ reportKey, sourceColumns, sourceRows }) {
	const layout = ref(null)
	const linkSources = ref({})
	const fieldsBySource = ref({})
	const linkedValues = ref({})
	const loadingLayout = ref(false)
	const layoutRequestError = ref("")
	const hydrationError = ref("")
	const hydrationLifecycle = createHydrationLifecycle()

	const columns = computed(() => reconcileReportLayout(
		unref(sourceColumns) || [],
		layout.value,
		fieldsBySource.value,
	))
	const displayColumns = computed(() => columns.value.filter((column) => column.visible))
	const hasLinkedColumns = computed(() => displayColumns.value.some((column) => column.kind === "linked"))
	const rows = computed(() => {
		const source = unref(sourceRows) || []
		return hasLinkedColumns.value ? attachLinkedValues(source, linkedValues.value) : source
	})
	const layoutError = computed(() => layoutRequestError.value || hydrationError.value)

	async function loadLayout() {
		loadingLayout.value = true
		layoutRequestError.value = ""
		try {
			applyLayoutResponse(await getReportLayout(reportKey))
			await loadSavedFieldOptions()
		} catch (reason) {
			layoutRequestError.value = reason?.message || "Unable to load report columns."
		} finally {
			loadingLayout.value = false
		}
	}

	async function loadFieldOptions(source) {
		if (fieldsBySource.value[source]) return fieldsBySource.value[source]
		const fields = await getLinkFieldOptions(reportKey, source)
		fieldsBySource.value = { ...fieldsBySource.value, [source]: fields || [] }
		return fieldsBySource.value[source]
	}

	function applyLayout(nextColumns) {
		layout.value = (nextColumns || []).map(toLayoutColumn)
	}

	async function saveLayout(nextColumns) {
		const response = await saveReportLayoutRequest(reportKey, getLayoutColumnsForSave(nextColumns))
		applyLayoutResponse(response)
		await loadSavedFieldOptions()
	}

	async function resetLayout() {
		applyLayoutResponse(await resetReportLayoutRequest(reportKey))
		fieldsBySource.value = {}
		linkedValues.value = {}
	}

	async function hydrate() {
		const request = hydrationLifecycle.begin()
		linkedValues.value = {}
		hydrationError.value = ""
		const batches = buildLinkedValueBatches(unref(sourceRows) || [], displayColumns.value)
		if (!batches.length) return
		try {
			const values = await hydrateLinkedValueBatches(
				batches,
				(requests) => getLinkedValues(reportKey, requests, { signal: request.signal }),
				request.isCurrent,
			)
			if (values && request.isCurrent()) linkedValues.value = values
		} catch (reason) {
			if (!request.isCurrent() || reason?.name === "AbortError") return
			hydrationError.value = reason?.message || "Unable to load linked report values."
		}
	}

	function applyLayoutResponse(response = {}) {
		layout.value = Array.isArray(response.layout) ? response.layout : null
		linkSources.value = response.link_sources || {}
	}

	async function loadSavedFieldOptions() {
		const sources = new Set((layout.value || [])
			.filter((column) => column.kind === "linked")
			.map((column) => column.source_column))
		await Promise.all([...sources].map(loadFieldOptions))
	}

	watch(
		() => [unref(sourceRows), displayColumns.value.map((column) => column.key).join("|")],
		() => hydrate(),
		{ flush: "post" },
	)
	onScopeDispose(hydrationLifecycle.invalidate)

	return {
		layout,
		linkSources,
		fieldsBySource,
		columns,
		displayColumns,
		rows,
		hasLinkedColumns,
		loadingLayout,
		layoutError,
		loadLayout,
		loadFieldOptions,
		applyLayout,
		saveLayout,
		resetLayout,
		cellAlign,
		cellValue: reportCellValue,
	}
}

function attachLinkedValues(rows, values) {
	return rows.map((row) => {
		if (row?.is_total_row) return row
		const linked = {}
		for (const [source, names] of Object.entries(values)) {
			linked[source] = names[row?.[source]] || {}
		}
		return { ...row, __linked: linked }
	})
}


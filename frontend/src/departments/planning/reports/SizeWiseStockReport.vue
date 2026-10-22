<template>
	<ReportShell :export-source="{ reportKey: 'planning-size-wise-stock' }" title="Size-wise Stock" :generated="generated" :loading="loading" :error="reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
		<template #filters>
			<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
			<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
			<LinkField v-model="filters.product_category" doctype="SD YRP Product Category" label="Product Category" :show-open-button="false" show-clear />
			<label class="common-field"><span class="erp-field-label">Lot Status</span><Select v-model="filters.lot_status" :options="['Open', 'Closed']" aria-label="Lot Status" fluid /></label>
			<OrderedProcessSelect v-model="filters.process_list" />
			<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
		</template>
		<template #actions><Button label="Paste" icon="pi pi-clipboard" severity="secondary" outlined :disabled="isBusy" @click="pasteVisible = true" /></template>
		<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :error="reportError" @rebuild="rebuild" /></template>
		<section v-for="matrix in matrices" :key="matrix.title" class="finishing-stack">
			<h3>{{ matrix.title }}</h3>
			<PlanningReportTable :title="matrix.title" :columns="matrix.columns" :rows="matrix.rows" :cell-align="cellAlign" :formatted-cell="formattedCell" />
		</section>
	</ReportShell>
	<PasteListDialog v-model:visible="pasteVisible" @apply="paste" />
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import PlanningReportTable from "./PlanningReportTable.vue"
import OrderedProcessSelect from "./OrderedProcessSelect.vue"
import { usePlanningQuantityColumns } from "./usePlanningQuantityColumns.js"
import PasteListDialog from "../../../components/reports/PasteListDialog.vue"
import { mergeNames } from "../../../components/reports/pasteValues.js"
import { stockHint, populatedFilters, sizeMatrixColumns } from "./productionReportFilters.js"

function defaultFilters() { return { lot: [], item: [], product_category: "", lot_status: "Open", process_list: [] } }
const filters = reactive(defaultFilters())
const hint = computed(() => stockHint(filters))
const pasteVisible = ref(false)
const { state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, generate: generateReport, filtersChanged, clear } = useWebReport({ reportKey: "planning-size-wise-stock" })
const { columns, rows, cellAlign, formattedCell } = usePlanningQuantityColumns("planning-size-wise-stock", sourceColumns, sourceRows)
const matrices = computed(() => {
	const groups = new Map()
	for (const row of rows.value) {
		const title = row.matrix === "Lot" ? `Lot: ${row.lot} · ${row.item}` : `Style: ${row.item}`
		if (!groups.has(title)) groups.set(title, { title, columns: sizeMatrixColumns(columns.value, row), rows: [] })
		groups.get(title).rows.push(row)
	}
	return [...groups.values()]
})
function requestFilters() { return populatedFilters({ ...filters, process_list: JSON.stringify(filters.process_list) }) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function paste({ target, names }) { filters[target] = mergeNames(filters[target], names) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request, { process_list: typeof request.process_list === "string" ? JSON.parse(request.process_list) : request.process_list || [] }) }, { flush: "sync" })
</script>

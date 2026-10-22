<template>
	<section aria-label="In-house Quantity">
		<ReportShell :export-source="{ reportKey: 'planning-inhouse-quantity' }" title="In-house Quantity" :generated="generated" :loading="loading" :error="reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" required :show-open-button="false" show-clear />
				<LinkField v-model="filters.process" doctype="YRP Process" label="Process" required :show-open-button="false" show-clear />
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :error="reportError" @rebuild="rebuild" /></template>
			
			<h3 v-if="payload?.summary?.item">Item: {{ payload.summary.item }}</h3>
			<PlanningReportTable title="In-house Quantity" :columns="columns" :rows="rows" :cell-tone="(column, row) => row.tones?.[column.fieldname] || ''" :cell-align="cellAlign" :formatted-cell="formattedCell" :cell-span="cellSpan" />
		</ReportShell>

	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed, reactive, watch } from "vue"
import { useRoute } from "vue-router"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { usePlanningQuantityColumns } from "./usePlanningQuantityColumns.js"
import LinkField from "../../../components/common/LinkField.vue"
import { quantityHint, quantityDeepLink, populatedFilters } from "./productionReportFilters.js"
import { blockCellSpan, blockSpans } from "./inhouseQuantityBlocks.js"

function defaultFilters() { return { lot: "", process: "" } }
const filters = reactive(defaultFilters())
const hint = computed(() => quantityHint(filters))
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, payload, reportSummary,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-inhouse-quantity" })
const { columns, rows, cellAlign, formattedCell } = usePlanningQuantityColumns("planning-inhouse-quantity", sourceColumns, sourceRows)
const cellSpan = computed(() => blockCellSpan(blockSpans(rows.value)))

function requestFilters() { return populatedFilters(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })
const route = useRoute()
watch(() => [route.query.lot, route.query.process], () => {
	const values = quantityDeepLink(route.query)
	Object.assign(filters, values)
	if (!quantityHint(values)) generate()
}, { immediate: true })
</script>

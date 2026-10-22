<template>
	<ReportShell :export-source="{ reportKey: 'planning-colour-wise-diff' }" title="Colour-wise Diff" :generated="generated" :loading="loading" :error="reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
		<template #filters>
			<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" required :show-open-button="false" show-clear />
			<OrderedProcessSelect v-model="filters.process_list" />
			<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
		</template>
		<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :error="reportError" @rebuild="rebuild" /></template>
		<PlanningReportTable title="Colour-wise Diff" :columns="columns" :rows="rows" inline-filters :cell-align="cellAlign" :formatted-cell="formattedCell" />
	</ReportShell>
</template>

<script setup>
import Button from "primevue/button"
import { computed, reactive, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import OrderedProcessSelect from "./OrderedProcessSelect.vue"
import { usePlanningQuantityColumns } from "./usePlanningQuantityColumns.js"
import { populatedFilters } from "./productionReportFilters.js"

function defaultFilters() { return { lot: "", process_list: [] } }
const filters = reactive(defaultFilters())
const hint = computed(() => filters.lot ? "" : "Lot is required.")
const { state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, generate: generateReport, filtersChanged, clear } = useWebReport({ reportKey: "planning-colour-wise-diff" })
const { columns, rows, cellAlign, formattedCell } = usePlanningQuantityColumns("planning-colour-wise-diff", sourceColumns, sourceRows)
function requestFilters() { return populatedFilters({ ...filters, process_list: JSON.stringify(filters.process_list) }) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request, { process_list: typeof request.process_list === "string" ? JSON.parse(request.process_list) : request.process_list || [] }) }, { flush: "sync" })
</script>

<template>
	<section class="planning-wide-report" aria-label="Work Order">
		<ReportShell :actions="[{ label: 'Pick Columns', icon: 'pi pi-table', disabled: !generated || !allColumns.length, command: () => { pickerVisible = true } }]" :export-source="{ reportKey: 'planning-work-order' }" title="Work Order" :generated="generated" :loading="loading" :error="layoutError || reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<label class="common-field"><span class="erp-field-label">Based on</span><Select v-model="filters.based_on" :options="['Date', 'WO Status']" aria-label="Based on" fluid /></label>
				<template v-if="filters.based_on === 'Date'"><DateField v-model="filters.from_date" label="From Date" required show-clear /><DateField v-model="filters.to_date" label="To Date" required show-clear /></template>
				<label v-else class="common-field"><span class="erp-field-label">WO Status</span><Select v-model="filters.status" :options="['', 'Open', 'Close']" aria-label="WO Status" fluid /></label>
				<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" :show-open-button="false" show-clear />
				<LinkField v-model="filters.process_name" doctype="YRP Process" label="Process" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" :show-open-button="false" show-clear />
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" :show-open-button="false" show-clear />
				<small>Pending = Received − Delivered</small>
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :has-linked-columns="hasLinkedColumns" :error="reportError" @rebuild="rebuild" /></template>
			
			<PlanningReportTable title="Work Order" :columns="columns" :rows="rows" :cell-value="cellValue" inline-filters :cell-align="cellAlign" :formatted-cell="formattedCell" />
		</ReportShell>
		<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
		
	</section>
</template>

<script setup>
import Select from "primevue/select"
import { computed, reactive, watch } from "vue"
import DateField from "../../../components/common/DateField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import ReportColumnPicker from "../../../components/reports/ReportColumnPicker.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { usePlanningReportColumns } from "./usePlanningReportColumns.js"
import LinkField from "../../../components/common/LinkField.vue"
import { workOrderDefaults, workOrderHint, workOrderRequest } from "./productionReportFilters.js"

function defaultFilters() { return workOrderDefaults() }
const filters = reactive(defaultFilters())
const hint = computed(() => workOrderHint(filters))
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-work-order" })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadFieldOptions, applyLayout, saveLayout, resetLayout,
	cellAlign, cellValue, pickerVisible, formattedCell,
} = usePlanningReportColumns("planning-work-order", sourceColumns, sourceRows)

function requestFilters() { return workOrderRequest(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })

</script>

<style scoped>
/* Wide tables scroll anyway; give names and IDs room instead of breaking at every hyphen. */
.planning-wide-report :deep(td.report-cell--text) { min-width: 16ch; }
</style>

<template>
	<section class="planning-wide-report" aria-label="Work In Progress">
		<ReportShell :actions="[{ label: 'Paste', icon: 'pi pi-clipboard', disabled: isBusy, command: () => { pasteVisible = true } }, { label: 'Pick Columns', icon: 'pi pi-table', disabled: !generated || !allColumns.length, command: () => { pickerVisible = true } }, { label: 'Download', icon: 'pi pi-download', visible: isBackgroundResult, command: download }]" :export-source="{ reportKey: 'planning-work-in-progress' }" title="Work In Progress" :generated="generated" :loading="loading" :error="layoutError || reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.category" doctype="SD YRP Product Category" label="Category" :show-open-button="false" show-clear />
				<LinkField v-model="filters.product_season" doctype="SD YRP Product Season" label="Product Season" :show-open-button="false" show-clear />
				<label class="common-field"><span class="erp-field-label">Lot Status</span><Select v-model="filters.lot_status" :options="['Open', 'Closed']" aria-label="Lot Status" fluid /></label>
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
				<DateField v-model="filters.from_date" label="From Date (Lot creation)" show-clear />
				<DateField v-model="filters.to_date" label="To Date (Lot creation)" show-clear />
				<OrderedProcessSelect v-model="filters.process_list" />
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="isBackgroundResult || reused" :has-linked-columns="hasLinkedColumns" :error="reportError" determinate @rebuild="rebuild" /></template>
			<template #metrics><div v-for="metric in reportSummary" :key="metric.label" class="report-metric"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div></template>
			<PlanningReportTable title="Work In Progress" :columns="columns" :rows="rows" :cell-value="cellValue" inline-filters :cell-align="cellAlign" :formatted-cell="formattedCell" :cell-link="progressCellLink" />
		</ReportShell>
		<PasteListDialog v-model:visible="pasteVisible" @apply="paste" />
		<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
	</section>
</template>

<script setup>
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import DateField from "../../../components/common/DateField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import ReportColumnPicker from "../../../components/reports/ReportColumnPicker.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import PlanningReportTable from "./PlanningReportTable.vue"
import OrderedProcessSelect from "./OrderedProcessSelect.vue"
import { usePlanningReportColumns } from "./usePlanningReportColumns.js"
import PasteListDialog from "../../../components/reports/PasteListDialog.vue"
import { mergeNames } from "../../../components/reports/pasteValues.js"
import { wipHint, populatedFilters, progressTotals, progressCellLink, progressCellValue } from "./productionReportFilters.js"

function defaultFilters() { return { lot: [], item: [], category: "", product_season: "", lot_status: "Open", from_date: "", to_date: "", process_list: [] } }
const filters = reactive(defaultFilters())
const hint = computed(() => wipHint(filters))
const pasteVisible = ref(false)
const { state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, reportSummary, isBackgroundResult, download, generate: generateReport, filtersChanged, clear } = useWebReport({ reportKey: "planning-work-in-progress" })
const { columns: allColumns, displayColumns: columns, rows: layoutRows, linkSources, fieldsBySource, hasLinkedColumns, layoutError, loadFieldOptions, applyLayout, saveLayout, resetLayout, cellValue, cellAlign, pickerVisible, formattedCell } = usePlanningReportColumns("planning-work-in-progress", sourceColumns, sourceRows, { cellValue: progressCellValue })
const rows = computed(() => progressTotals(layoutRows.value, columns.value, cellValue))
function requestFilters() { return populatedFilters({ ...filters, process_list: JSON.stringify(filters.process_list) }) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function paste({ target, names }) { filters[target] = mergeNames(filters[target], names) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request, { process_list: typeof request.process_list === "string" ? JSON.parse(request.process_list) : request.process_list || [] }) }, { flush: "sync" })
</script>

<style scoped>
/* Wide tables scroll anyway; give names and IDs room instead of breaking at every hyphen. */
.planning-wide-report :deep(td.report-cell--text) { min-width: 16ch; }
</style>

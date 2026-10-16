<template>
	<section aria-label="Work Order Pending">
		<ReportShell title="Work Order Pending" :generated="generated" :loading="loading" :error="layoutError || reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<AsyncLinkMultiSelect v-model="filters.production_order" doctype="YRP Production Order" label="Production Orders" />
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
				<AsyncLinkMultiSelect v-model="filters.item_variant" doctype="Item" label="Item Variants" :filters="{ variant_of: ['is', 'set'] }" />
				<AsyncLinkMultiSelect v-model="filters.process" doctype="YRP Process" label="Processes" />
				<AsyncLinkMultiSelect v-model="filters.supplier" doctype="Supplier" label="Suppliers" />
				<DateField v-model="filters.from_date" label="From Date" show-clear /><DateField v-model="filters.to_date" label="To Date" show-clear />
				<label class="common-field"><span class="erp-field-label">Status</span><Select v-model="filters.status" :options="['', 'Open', 'Close Request', 'Close']" aria-label="Status" fluid /></label>
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #actions>
				<Button label="Pick Columns" icon="pi pi-table" severity="secondary" outlined :disabled="!generated || !allColumns.length" @click="pickerVisible = true" />
				<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined :disabled="!generated || !rows.length" @click="downloadCsv" />
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :has-linked-columns="hasLinkedColumns" :error="reportError" @rebuild="rebuild" /></template>
			<template #metrics><div v-for="(metric, index) in reportSummary || []" :key="index" class="report-metric"><div><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div></div></template>
			<PlanningReportTable title="Work Order Pending" :columns="columns" :rows="rows" :cell-align="cellAlign" :formatted-cell="formattedCell" />
		</ReportShell>
		<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
		
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, reactive, watch } from "vue"
import DateField from "../../../components/common/DateField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import ReportColumnPicker from "../../../components/reports/ReportColumnPicker.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { usePlanningReportColumns } from "./usePlanningReportColumns.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { pairedDateHint, populatedFilters } from "./productionReportFilters.js"

function defaultFilters() { return { production_order: [], lot: [], item: [], item_variant: [], process: [], supplier: [], from_date: '', to_date: '', status: '' } }
const filters = reactive(defaultFilters())
const hint = computed(() => pairedDateHint(filters))
const {
	state, sourceColumns, sourceRows, reportSummary, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-work-order-pending" })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadFieldOptions, applyLayout, saveLayout, resetLayout,
	cellAlign, pickerVisible, formattedCell, downloadCsv,
} = usePlanningReportColumns("planning-work-order-pending", sourceColumns, sourceRows)

function requestFilters() { return populatedFilters(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })

</script>


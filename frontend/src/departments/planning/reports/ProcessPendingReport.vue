<template>
	<section aria-label="Process Pending">
		<ReportShell title="Process Pending" :generated="generated" :loading="loading" :error="reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
				<LinkField v-model="filters.category" doctype="SD YRP Product Category" label="Category" :show-open-button="false" show-clear />
				<label class="common-field"><span class="erp-field-label">Lot Status *</span><Select v-model="filters.lot_status" :options="['Open', 'Closed']" aria-label="Lot Status" fluid /></label>
				<LinkField v-model="filters.process" doctype="YRP Process" label="Process" :placeholder="defaultProcess || 'MRP Settings finishing inward process'" :show-open-button="false" show-clear />
				<small v-if="defaultProcess">Default process: {{ defaultProcess }}</small>
				<WorkspaceLoadError v-if="defaultsError" class="process-defaults-error" title="Default process unavailable" :message="defaultsError" @retry="loadDefaults" />
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #actions>
				<Button label="Paste" icon="pi pi-clipboard" severity="secondary" outlined :disabled="isBusy" @click="pasteVisible = true" />
				<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined :disabled="!generated || !rows.length" @click="downloadCsv" />
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :error="reportError" @rebuild="rebuild" /></template>
			
			<template #metrics><div v-for="metric in reportSummary || []" :key="metric.label" class="report-metric"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></div></template>
			<PlanningReportTable title="Process Pending" :columns="columns" :rows="rows" :cell-link="(column, row) => column.fieldname === 'lot' && row.lot && !row.is_total_row ? '/planning/lots/' + encodeURIComponent(row.lot) : ''" :cell-align="cellAlign" :formatted-cell="formattedCell">
				<template #annotation="{ column, row }"><small v-if="pendingAnnotation(column, row)" class="pending-days" :title="pendingAnnotation(column, row).title">{{ pendingAnnotation(column, row).label }}</small></template>
			</PlanningReportTable>
		</ReportShell>
		<PasteListDialog v-model:visible="pasteVisible" @apply="paste" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { callMethod } from "../../../api/frappe.js"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { pendingAnnotation } from "./processPendingAnnotations.js"
import { usePlanningQuantityColumns } from "./usePlanningQuantityColumns.js"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { populatedFilters } from "./productionReportFilters.js"
import PasteListDialog from "../../../components/reports/PasteListDialog.vue"
import { mergeNames } from "../../../components/reports/pasteValues.js"

function defaultFilters() { return { lot: [], item: [], category: "", lot_status: "Open", process: "" } }
const filters = reactive(defaultFilters())
const hint = computed(() => filters.lot_status ? "" : "Lot Status is required.")
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, payload, reportSummary,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-process-pending" })
const { columns, rows, cellAlign, formattedCell, downloadCsv } = usePlanningQuantityColumns("planning-process-pending", sourceColumns, sourceRows)

function requestFilters() { return populatedFilters(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })
const pasteVisible = ref(false)
function paste({ target, names }) { filters[target] = mergeNames(filters[target], names) }
const defaultProcess = ref("")
const defaultsError = ref("")
async function loadDefaults() {
	defaultsError.value = ""
	try { defaultProcess.value = (await callMethod("essdee_yrp.planning.reports.process_pending.get_defaults")).process }
	catch (error) { defaultsError.value = error.message || "Unable to load the default process." }
}
onMounted(loadDefaults)
</script>

<style scoped>
.pending-days { display: block; margin-top: 0.25rem; color: var(--erp-text-muted); font-size: 0.75rem; }
.process-defaults-error { width: 100%; margin: 0; padding: var(--erp-space-2); }
</style>

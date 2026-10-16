<template>
	<section aria-label="Dispatch Percentage">
		<ReportShell title="Dispatch Percentage" :generated="generated" :loading="loading" :error="layoutError || reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<label class="common-field"><span class="erp-field-label">Percentage *</span><InputNumber v-model="filters.percentage" :min="1" :max="100" :max-fraction-digits="3" aria-label="Percentage" fluid /></label>
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
				<Button label="Paste values" severity="secondary" outlined @click="openPaste" />
				<small>First date each Finishing Plan reached the percentage.</small>
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #actions>
				<Button label="Pick Columns" icon="pi pi-table" severity="secondary" outlined :disabled="!generated || !allColumns.length" @click="pickerVisible = true" />
				<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined :disabled="!generated || !rows.length" @click="downloadCsv" />
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :has-linked-columns="hasLinkedColumns" :error="reportError" @rebuild="rebuild" /></template>
			
			<PlanningReportTable title="Dispatch Percentage" :columns="columns" :rows="rows" :cell-align="cellAlign" :formatted-cell="formattedCell" />
		</ReportShell>
		<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
		<Dialog v-model:visible="pasteVisible" header="Paste values" modal>
			<div class="finishing-stack"><label class="common-field"><span class="erp-field-label">Apply to</span><Select v-model="pasteTarget" :options="['Lot', 'Item']" aria-label="Apply to" fluid /></label>
			<label class="common-field"><span class="erp-field-label">One value per line or comma separated</span><Textarea v-model="pastedText" rows="8" aria-label="Values" fluid /></label></div>
			<template #footer><Button label="Apply" :disabled="!pastedText.trim()" @click="applyPaste" /></template>
		</Dialog>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import ReportColumnPicker from "../../../components/reports/ReportColumnPicker.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { usePlanningReportColumns } from "./usePlanningReportColumns.js"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Textarea from "primevue/textarea"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { mergePastedValues, percentageHint, populatedFilters } from "./productionReportFilters.js"

function defaultFilters() { return { percentage: 75, lot: [], item: [] } }
const filters = reactive(defaultFilters())
const hint = computed(() => percentageHint(filters.percentage))
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-dispatch-percentage" })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadFieldOptions, applyLayout, saveLayout, resetLayout,
	cellAlign, pickerVisible, formattedCell, downloadCsv,
} = usePlanningReportColumns("planning-dispatch-percentage", sourceColumns, sourceRows)

function requestFilters() { return populatedFilters(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })
const pasteVisible = ref(false)
const pasteTarget = ref("Lot")
const pastedText = ref("")
function openPaste() { pasteTarget.value = "Lot"; pastedText.value = ""; pasteVisible.value = true }
function applyPaste() {
	const key = pasteTarget.value === "Item" ? "item" : "lot"
	filters[key] = mergePastedValues(filters[key], pastedText.value)
	pasteVisible.value = false
}
</script>


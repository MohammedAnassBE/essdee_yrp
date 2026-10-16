<template>
	<ReportShell title="Work In Progress" :generated="generated" :loading="isBusy" :error="error" :has-results="sourceRows.length > 0" copyable @generate="generate" @reset="reset">
		<template #filters>
			<div>
				<LinkField v-model="filters.category" label="Product Category" doctype="SD YRP Product Category" :invalid="Boolean(errors.category)" :show-open-button="false" aria-describedby="wip-category-error" />
				<small v-if="errors.category" id="wip-category-error" class="wip-error" role="alert">{{ errors.category }}</small>
			</div>
			<LinkField v-model="filters.product_season" label="Product Season" doctype="SD YRP Product Season" :show-open-button="false" />
			<div class="common-field">
				<label for="wip-lot-status" class="erp-field-label">Lot Status <span class="erp-required-mark">*</span></label>
				<Select input-id="wip-lot-status" v-model="filters.lot_status" :options="['Open', 'Closed']" :invalid="Boolean(errors.lot_status)" aria-required="true" fluid />
				<small v-if="errors.lot_status" class="wip-error" role="alert">{{ errors.lot_status }}</small>
			</div>
			<WipLinkMultiSelect v-model="filters.lot" class="wip-multi-filter" label="Lot" doctype="SD YRP Lot" />
			<WipLinkMultiSelect v-model="filters.item" class="wip-multi-filter" label="Item" doctype="Item" />
			<DateField v-model="filters.from_date" label="Lot From Date" :invalid="Boolean(errors.from_date)" :error="errors.from_date" />
			<DateField v-model="filters.to_date" label="Lot To Date" :invalid="Boolean(errors.to_date)" :error="errors.to_date" />
			<WipLinkMultiSelect v-model="filters.process_list" class="wip-multi-filter" label="Processes" doctype="YRP Process" ordered />
		</template>
		<template #actions>
			<Button label="Paste" icon="pi pi-clipboard" severity="secondary" outlined :disabled="isBusy" @click="pasteVisible = true" />
			<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined :disabled="!generated || !sourceRows.length || isBusy" @click="download" />
		</template>
		<template #metrics>
			<div v-for="metric in reportSummary || []" :key="metric.label" class="report-metric">
				<div><span>{{ metric.label }}</span><strong>{{ formatNumber(metric.value) }}</strong></div>
			</div>
		</template>
		<p class="wip-description">Lot-wise movement from order to dispatch</p>
		<p v-if="notInIpdProcesses.length" class="wip-description" role="note">No columns for: {{ notInIpdProcesses.join(', ') }} (not in the IPD of any lot with sewing work orders).</p>
		<div class="erp-table-wrap report-table-frame wip-table" tabindex="0" aria-label="Work In Progress table">
			<table class="erp-table">
				<thead>
					<tr><th v-for="(group, index) in groups" :key="index" :colspan="group.span" scope="colgroup">{{ group.label }}</th></tr>
					<tr><th v-for="column in sourceColumns" :key="column.fieldname" scope="col">{{ column.label }}</th></tr>
				</thead>
				<tbody>
					<tr v-for="row in sourceRows" :key="row.lot || 'total'" :class="{ 'wip-total': row.is_total_row }">
						<td v-for="column in sourceColumns" :key="column.fieldname" :class="[cellTone(row, column), { 'wip-number': column.fieldtype === 'Float' }]">{{ cellText(row, column) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
	<PasteListDialog v-model:visible="pasteVisible" @apply="paste" />
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import { computed, reactive, ref, watch } from "vue"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PasteListDialog from "./PasteListDialog.vue"
import WipLinkMultiSelect from "./WipLinkMultiSelect.vue"
import { cellText, cellTone, columnGroups, reportCsv, validateWipFilters } from "./workInProgress.js"

const defaults = () => ({ category: "", product_season: "", lot_status: "Open", lot: [], item: [], from_date: "", to_date: "", process_list: [] })
const filters = reactive(defaults())
const errors = ref({})
const pasteVisible = ref(false)
const report = useWebReport({ reportKey: "merch-work-in-progress" })
const { sourceColumns, sourceRows, reportSummary, payload, generated, isBusy, error } = report
const groups = computed(() => columnGroups(sourceColumns.value))
const notInIpdProcesses = computed(() => payload.value?.not_in_ipd_processes || [])
const formatNumber = (value) => Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })
watch(filters, () => { errors.value = {}; report.filtersChanged(filters) }, { deep: true })
function generate() {
	errors.value = validateWipFilters(filters)
	if (!Object.keys(errors.value).length) report.generate({ ...filters })
}
function reset() { Object.assign(filters, defaults()); errors.value = {}; report.clear() }
function paste({ target, names }) { filters[target] = [...new Set([...filters[target], ...names])] }
function download() {
	const url = URL.createObjectURL(new Blob([reportCsv(sourceRows.value, sourceColumns.value)], { type: "text/csv;charset=utf-8" }))
	const anchor = document.createElement("a")
	anchor.href = url
	anchor.download = "Work_In_Progress.csv"
	anchor.click()
	setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<style scoped>
:deep(.report-shell__filters) { flex-direction: column; align-items: stretch; }
:deep(.report-filter-grid) { align-items: start; grid-template-columns: repeat(4, minmax(0, 1fr)); }
:deep(.report-filter-grid > *) { min-width: 0; }
.wip-multi-filter { grid-column: span 2; }
.wip-error { display: block; color: var(--erp-danger); font-size: var(--erp-font-size-caption); margin-top: 5px; }
.wip-description { margin: 0; color: var(--erp-text-muted); }
.wip-table { max-width: 100%; overflow: auto; }
.wip-table table { width: max-content; min-width: 100%; border-collapse: collapse; }
.wip-table th, .wip-table td { padding: 8px 12px; border: 1px solid var(--erp-border); white-space: nowrap; }
.wip-table th { background: var(--erp-surface-soft); }
.wip-number { text-align: right; font-variant-numeric: tabular-nums; }
.wip-total { font-weight: 750; background: var(--erp-surface-soft); }
.wip-negative { color: var(--erp-danger); }
.wip-positive { color: var(--erp-success-text); }
@media (max-width: 1000px) {
	:deep(.report-filter-grid) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 600px) {
	:deep(.report-filter-grid) { grid-template-columns: minmax(0, 1fr); }
	.wip-multi-filter { grid-column: auto; }
	:deep(.report-shell__commands) { display: flex; flex-wrap: wrap; }
	:deep(.report-shell__commands .p-button) { flex: 1 1 calc(50% - 6px); }
}
</style>

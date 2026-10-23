<template>
	<ReportShell :actions="[{ label: 'Pick Columns', icon: 'pi pi-table', disabled: !generated || !allColumns.length, command: () => { pickerVisible = true } }, { label: 'Download', icon: 'pi pi-download', visible: isBackgroundResult, command: download }]" :export-source="{ reportKey: 'cut-bundle-balance' }"
		title="Cut Bundle Balance"
		:generated="generated"
		:loading="loading"
		:error="layoutError"
		:has-results="rows.length > 0"
		:generate-disabled="isBusy"
		:status-only="statusOnly"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="All lots" :show-open-button="false" show-clear />
			<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" placeholder="All suppliers" :show-open-button="false" show-clear />
		</template>
		<template #status>
			<ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="isBackgroundResult || reused" :has-linked-columns="hasLinkedColumns" :error="reportError" determinate @rebuild="rebuild" />
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Balance rows</span><strong>{{ number(dataRows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Bundle quantity</span><strong>{{ number(totalQuantity) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-tags" /><div><span>Lots</span><strong>{{ number(uniqueLots) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-building" /><div><span>Suppliers</span><strong>{{ number(uniqueSuppliers) }}</strong></div></div>
		</template>

		<div class="erp-table-wrap cut-bundle-balance__table-wrap" role="region" aria-label="Cut Bundle Balance results" tabindex="0">
			<table class="erp-data-table cut-bundle-balance__table">
				<colgroup><col v-for="column in columns" :key="column.key" :style="{ width: `${column.width}px` }" /></colgroup>
				<thead>
					<tr><th v-for="column in columns" :key="column.key" :class="cellAlign(column)">{{ column.label }}</th></tr>
					<ReportFilterRow :columns="columns" :filter="inlineFilter" />
				</thead>
				<tbody>
					<tr v-for="(row, index) in inlineFilter.filteredRows.value" :key="`${row.name || 'row'}-${index}`" :class="{ 'report-total-row': row.is_total_row }">
						<td v-for="column in columns" :key="column.key" :class="cellAlign(column)">
							<strong v-if="column.kind === 'base' && column.fieldname === 'qty'">{{ number(cellValue(row, column)) }}</strong>
							<span v-else>{{ cellText(row, column) || "—" }}</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
	<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"

import { useInlineFilters } from "../../composables/useInlineFilters.js"
import { useReportColumns } from "../../composables/useReportColumns.js"
import { useWebReport } from "../../composables/useWebReport.js"
import LinkField from "../../components/common/LinkField.vue"
import ReportColumnPicker from "../../components/reports/ReportColumnPicker.vue"
import ReportFilterRow from "../../components/reports/ReportFilterRow.vue"
import { cutBundleFormFilters } from "../../components/reports/reportFilterState.js"
import ReportRunStatus from "../../components/reports/ReportRunStatus.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { number } from "../../components/reports/reportUtils.js"
import { formatDisplayByFieldtype } from "../../utils/dateFormat.js"

const filters = reactive(defaultFilters())
const pickerVisible = ref(false)
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, activeFilters,
	trackingStartedAt, loading, isBusy, generated, isBackgroundResult, statusOnly,
	generate: generateReport, filtersChanged, clear, download,
} = useWebReport({ reportKey: "cut-bundle-balance" })
const {
	columns: allColumns, displayColumns: reportColumns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadLayout, loadFieldOptions, applyLayout,
	saveLayout, resetLayout, cellAlign, cellValue,
} = useReportColumns({ reportKey: "cut-bundle-balance", sourceColumns, sourceRows })

const columns = computed(() => reportColumns.value.filter(column => column.fieldname !== "name"))
const inlineFilter = useInlineFilters(rows, columns, { cellValue, cellText: (row, column) => column.kind === "base" && column.fieldname === "qty" ? number(cellValue(row, column)) : cellText(row, column) })
function cellText(row, column) { return formatDisplayByFieldtype(cellValue(row, column), column.fieldtype, { fallback: "" }) }
const dataRows = computed(() => inlineFilter.filteredRows.value.filter((row) => !row.is_total_row))
const totalQuantity = computed(() => dataRows.value.reduce((total, row) => total + Number(row.qty || 0), 0))
const uniqueLots = computed(() => new Set(dataRows.value.map((row) => row.lot).filter(Boolean)).size)
const uniqueSuppliers = computed(() => new Set(dataRows.value.map((row) => row.supplier).filter(Boolean)).size)

function defaultFilters() {
	return { lot: "", supplier: "" }
}

async function generate() {
	await generateReport(requestFilters())
}

function requestFilters() { return { lot: filters.lot, supplier: filters.supplier } }
function rebuild() { return generateReport(requestFilters(), { refresh: true }) }

function reset() {
	Object.assign(filters, defaultFilters())
	clear()
}
function restoreFilters(request) {
	if (request) Object.assign(filters, cutBundleFormFilters(request))
}

watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, restoreFilters, { flush: "sync" })
onMounted(loadLayout)
</script>

<style scoped>
.cut-bundle-balance__table-wrap{max-width:100%;overflow:auto}.cut-bundle-balance__table{min-width:1120px}.cut-bundle-balance__table td{max-width:220px}.cut-bundle-balance__table td span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cut-bundle-balance__table td strong{color:var(--erp-accent-hover);font-variant-numeric:tabular-nums}
</style>

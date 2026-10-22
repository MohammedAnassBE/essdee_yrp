<template>
	<ReportShell
		:export-source="deskExportSource('stock-balance', activeFilters, columns, [], inlineFilter.matchingIndices.value)"
		title="Stock Balance"
		:generated="generated"
		:loading="loading"
		:error="filterError || layoutError"
		:has-results="rows.length > 0"
		:generate-disabled="isBusy || !dimensionsLoaded"
		:status-only="statusOnly"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<DateField v-model="filters.fromDate" label="From date" required />
			<DateField v-model="filters.toDate" label="To date" required />
			<details class="stock-advanced" :open="advancedOpen" @toggle="advancedOpen = $event.currentTarget.open">
				<summary><span>More filters</span><small>{{ optionalFilterCount ? `${optionalFilterCount} active` : "Optional" }}</small><i class="pi pi-chevron-down" /></summary>
				<div class="stock-advanced__grid">
					<MultiSelectField
						v-for="picker in itemPickers" :key="picker.fieldname" :data-item-filter="picker.fieldname"
						v-model="filters[picker.fieldname]" :label="picker.label" :options="itemOptions(picker)"
						:placeholder="`Search ${picker.label}…`" filter-match-mode="stock-balance-server"
						:reset-filter-on-hide="true" @before-show="searchItems(picker)" @filter="searchItems(picker, $event.value)"
					/>
					<LinkField v-model="filters.warehouse" class="stock-link-filter" doctype="Warehouse" label="Warehouse" placeholder="Search warehouse…" :show-open-button="false" show-clear />
					<MultiSelectField
						v-for="dimension in dimensions" :key="dimension.fieldname" :data-dimension="dimension.fieldname"
						:model-value="filters.dimensions[dimension.fieldname] || []" :label="dimension.label"
						:options="dimensionOptions(dimension)" :placeholder="`Search ${dimension.label}…`"
						filter-match-mode="stock-balance-server" :reset-filter-on-hide="true"
						@update:model-value="filters.dimensions[dimension.fieldname] = $event"
						@before-show="searchDimension(dimension)" @filter="searchDimension(dimension, $event.value)"
					/>
					<div class="stock-checks">
						<label><input v-model="filters.removeZero" type="checkbox" /> Remove zero balance</label>
						<label><input v-model="filters.showAttributes" type="checkbox" /> Variant attributes</label>
						<label><input v-model="filters.showAgeing" type="checkbox" /> Stock ageing</label>
						<label><input v-model="filters.showInwardSplit" type="checkbox" /> Inward date split</label>
					</div>
				</div>
			</details>
		</template>
		<template #actions>
			<Button label="Pick Columns" icon="pi pi-table" severity="secondary" outlined class="erp-action-button" :disabled="!generated || !allColumns.length" @click="pickerVisible = true" />
			<Button v-if="isBackgroundResult" label="Download" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" @click="download" />
		</template>
		<template #status>
			<ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="isBackgroundResult || reused" :has-linked-columns="hasLinkedColumns" :error="reportError" @rebuild="rebuild" />
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Stock rows</span><strong>{{ number(dataRows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Balance quantity</span><strong>{{ number(totals.balanceQty, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-arrow-down-left" /><div><span>In quantity</span><strong>{{ number(totals.inQty, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-arrow-up-right" /><div><span>Out quantity</span><strong>{{ number(totals.outQty, 3) }}</strong></div></div>
		</template>

		<div class="erp-table-wrap report-table-frame stock-table-wrap" role="region" aria-label="Stock Balance results" tabindex="0">
			<table class="erp-data-table stock-table">
				<colgroup><col v-for="column in columns" :key="column.key" :style="{ width: `${column.width}px` }" /></colgroup>
				<thead><tr><th v-for="column in columns" :key="column.key" :class="cellAlign(column)">{{ column.label || column.fieldname }}</th></tr><ReportFilterRow :columns="columns" :filter="inlineFilter" /></thead>
				<tbody>
					<tr v-for="(row, rowIndex) in renderedRows" :key="rowIndex" :class="{ 'report-total-row': row.is_total_row }">
						<td v-for="column in columns" :key="column.key" :class="cellClass(column, row)"><span :class="column.fieldname === 'inward_split' ? 'multiline-cell' : ''">{{ stockCellValue(cellValue(row, column), column) }}</span></td>
					</tr>
					<tr v-if="unrenderedCount" ref="moreRowsSentinel" class="stock-more"><td :colspan="columns.length"><div class="stock-more__inner"><span>Showing {{ renderedRows.length.toLocaleString() }} of {{ inlineFilter.filteredRows.value.length.toLocaleString() }} rows</span><Button label="Show more rows" size="small" severity="secondary" text @click="renderMoreRows" /></div></td></tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
	<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
</template>

<script setup>
import Button from "primevue/button"
import { FilterService } from "@primevue/core/api"
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"

import { callMethod, searchLink } from "../../api/frappe.js"
import { useIncrementalRows } from "../../composables/useIncrementalRows.js"
import { useInlineFilters } from "../../composables/useInlineFilters.js"
import { useReportColumns } from "../../composables/useReportColumns.js"
import { useWebReport } from "../../composables/useWebReport.js"
import DateField from "../common/DateField.vue"
import LinkField from "../common/LinkField.vue"
import MultiSelectField from "../common/MultiSelectField.vue"
import ReportColumnPicker from "./ReportColumnPicker.vue"
import ReportFilterRow from "./ReportFilterRow.vue"
import { stockBalanceFormFilters } from "./reportFilterState.js"
import ReportRunStatus from "./ReportRunStatus.vue"
import ReportShell from "./ReportShell.vue"
import { deskExportSource } from "./reportExport.js"
import { number, oneMonthAgoIso, stockCellValue, todayIso } from "./reportUtils.js"

// The server searches document-specific fields (for example Lot.item).
FilterService.register("stock-balance-server", () => true)
const itemPickers = [{ fieldname: "parentItem", label: "Item", variant: 0 }, { fieldname: "item", label: "Item Variant", variant: 1 }]
const itemSuggestions = reactive({})
const itemSearches = {}
const filters = reactive(defaultFilters())
const dimensions = ref([])
const dimensionsLoaded = ref(false)
const dimensionSuggestions = reactive({})
const dimensionSearches = {}
let restoringFilters = false
const filterError = ref("")
const pickerVisible = ref(false)
const advancedOpen = ref(typeof window === "undefined" || !window.matchMedia("(max-width: 430px)").matches)
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, activeFilters,
	trackingStartedAt, loading, isBusy, generated, isBackgroundResult, statusOnly,
	generate: generateReport, filtersChanged, clear, download,
} = useWebReport({ reportKey: "stock-balance" })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadLayout, loadFieldOptions, applyLayout,
	saveLayout, resetLayout, cellAlign, cellValue,
} = useReportColumns({ reportKey: "stock-balance", sourceColumns, sourceRows })
const inlineFilter = useInlineFilters(rows, columns, { cellValue, cellText: (row, column) => stockCellValue(cellValue(row, column), column) })
const dataRows = computed(() => inlineFilter.filteredRows.value.filter((row) => !row.is_total_row))
// Export rebuilds rows on the server, so only the mounted table is stepped.
const { renderedRows, unrenderedCount, sentinel: moreRowsSentinel, renderMoreRows } = useIncrementalRows(inlineFilter.filteredRows, { resetOn: [sourceRows, inlineFilter.keywords] })
const totals = computed(() => dataRows.value.reduce((result, row) => {
	result.balanceQty += Number(row.bal_qty || 0); result.inQty += Number(row.in_qty || 0); result.outQty += Number(row.out_qty || 0); return result
}, { balanceQty: 0, inQty: 0, outQty: 0 }))
const optionalFilterCount = computed(() => [filters.item.length, filters.parentItem.length, filters.warehouse].filter(Boolean).length
	+ dimensions.value.filter((dimension) => filters.dimensions[dimension.fieldname]?.length).length
	+ Number(filters.showAttributes) + Number(filters.showAgeing) + Number(filters.showInwardSplit))

function defaultFilters() {
	return { fromDate: oneMonthAgoIso(), toDate: todayIso(), item: [], parentItem: [], warehouse: "", dimensions: {}, removeZero: true, showAttributes: false, showAgeing: false, showInwardSplit: false }
}
function cellClass(column, row) {
	return [cellAlign(column), column.fieldname === "in_qty" && Number(row.in_qty) > 0 ? "stock-in" : "", column.fieldname === "out_qty" && Number(row.out_qty) > 0 ? "stock-out" : ""]
}
function requestFilters() {
	return {
		from_date: filters.fromDate, to_date: filters.toDate, item: filters.item, parent_item: filters.parentItem,
		warehouse: filters.warehouse,
		...Object.fromEntries(dimensions.value.map((dimension) => [dimension.fieldname, filters.dimensions[dimension.fieldname] || []])),
		remove_zero_balance_item: filters.removeZero ? 1 : 0, show_variant_attributes: filters.showAttributes ? 1 : 0,
		show_stock_ageing_data: filters.showAgeing ? 1 : 0, show_inward_date_split: filters.showInwardSplit ? 1 : 0,
	}
}
async function generate() {
	if (!dimensionsLoaded.value) return
	if (!filters.fromDate || !filters.toDate) { filterError.value = "From date and To date are required."; return }
	if (filters.fromDate > filters.toDate) { filterError.value = "From date cannot be after To date."; return }
	filterError.value = ""
	await generateReport(requestFilters())
}
function rebuild() { if (dimensionsLoaded.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); filterError.value = ""; clear() }
function restoreFilters(request) {
	if (!request) return
	restoringFilters = true
	Object.assign(filters, stockBalanceFormFilters(request, dimensions.value))
	nextTick(() => { restoringFilters = false })
}

function itemOptions(picker) {
	const options = new Map((itemSuggestions[picker.fieldname] || []).map((row) => [row.value, { label: row.description ? `${row.value} · ${row.description}` : row.value, value: row.value }]))
	for (const value of filters[picker.fieldname]) if (!options.has(value)) options.set(value, { label: value, value })
	return [...options.values()]
}
async function searchItems(picker, txt = "") {
	const key = picker.fieldname
	const sequence = itemSearches[key] = (itemSearches[key] || 0) + 1
	try {
		const rows = await callMethod("yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance.get_item_filter_options", { txt, variant: picker.variant })
		if (sequence === itemSearches[key]) itemSuggestions[key] = rows || []
	} catch (error) { filterError.value = error.message || "Could not load item options." }
}

function dimensionOptions(dimension) {
	const options = new Map((dimensionSuggestions[dimension.fieldname] || []).map((row) => [row.name, { label: row.label || row.name, value: row.name }]))
	for (const value of filters.dimensions[dimension.fieldname] || []) {
		if (!options.has(value)) options.set(value, { label: value, value })
	}
	return [...options.values()]
}
async function searchDimension(dimension, text = "") {
	const fieldname = dimension.fieldname
	const sequence = dimensionSearches[fieldname] = (dimensionSearches[fieldname] || 0) + 1
	try {
		const rows = await searchLink(dimension.dimension_doctype, text)
		if (sequence === dimensionSearches[fieldname]) dimensionSuggestions[fieldname] = rows
	} catch (error) { filterError.value = error.message || "Could not load dimension options." }
}
async function loadDimensions() {
	try {
		dimensions.value = await callMethod("yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance.get_filter_dimensions") || []
		restoreFilters(activeFilters.value)
		dimensionsLoaded.value = true
	} catch (error) { filterError.value = error.message || "Could not load stock dimensions." }
}

watch(filters, () => {
	if (dimensionsLoaded.value && !restoringFilters) filtersChanged(requestFilters())
}, { deep: true })
watch(activeFilters, restoreFilters, { flush: "sync" })
onMounted(loadLayout)
onMounted(loadDimensions)
</script>

<style scoped>
.erp-field-label b {
	color: var(--erp-danger);
}

.stock-checks {
	display: grid;
	grid-column: span 2;
	grid-template-columns: repeat(2, minmax(145px, 1fr));
	min-width: 330px;
	min-height: var(--erp-control-height);
	align-content: center;
	gap: 5px var(--erp-space-4);
	padding: 7px 10px;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.stock-checks label {
	display: flex;
	align-items: center;
	gap: 5px;
	color: #52645b;
	font-size: var(--erp-font-size-min);
	white-space: nowrap;
}

.stock-checks input {
	accent-color: var(--erp-accent);
}

.stock-advanced {
	display: block;
	grid-column: 1 / -1;
}

.stock-advanced__grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	gap: var(--erp-space-2) var(--erp-space-3);
}

.stock-advanced summary {
	display: none;
}

.stock-table {
	min-width: 1280px;
}

.stock-table td span:not(.multiline-cell) {
	display: block;
	max-width: 300px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.stock-in {
	color: var(--erp-accent) !important;
	font-weight: 800;
}

.stock-out {
	color: var(--erp-danger) !important;
	font-weight: 800;
}

.multiline-cell {
	white-space: pre-line;
}

.stock-more__inner {
	position: sticky;
	left: 0;
	display: inline-flex;
	align-items: center;
	gap: var(--erp-space-3);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

@media (max-width: 800px) {
	.stock-advanced__grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.stock-checks {
		grid-column: 1 / -1;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		min-width: 0;
		gap: 6px var(--erp-space-2);
	}

	.stock-checks label {
		min-width: 0;
		min-height: 44px;
		white-space: normal;
	}

	.stock-checks input {
		width: 17px;
		height: 17px;
		flex: 0 0 auto;
	}
}

@media (max-width: 430px) {
	.stock-advanced {
		grid-column: 1 / -1;
		padding: 0 10px;
		border: 1px solid var(--erp-border);
		border-radius: var(--erp-control-radius);
		background: var(--erp-surface);
	}

	.stock-advanced summary {
		display: flex;
		min-height: 44px;
		align-items: center;
		gap: 8px;
		color: var(--erp-text);
		font-size: var(--erp-font-size-caption);
		font-weight: 750;
		cursor: pointer;
		list-style: none;
	}

	.stock-advanced summary::-webkit-details-marker { display: none; }
	.stock-advanced summary small { margin-left: auto; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 650; }
	.stock-advanced summary i { color: var(--erp-text-muted); font-size: 11px; transition: transform 140ms ease; }
	.stock-advanced[open] summary i { transform: rotate(180deg); }

	.stock-advanced__grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: var(--erp-space-2);
		padding: 0 0 10px;
	}

	.stock-advanced:not([open]) > .stock-advanced__grid {
		display: none;
	}

	.stock-checks {
		grid-column: 1;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		min-width: 0;
	}
}
</style>

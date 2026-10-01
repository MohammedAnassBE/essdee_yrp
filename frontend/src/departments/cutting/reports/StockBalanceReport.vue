<template>
	<ReportShell
		title="Stock Balance"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="rows.length > 0"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<label><span class="erp-field-label">From date <b>*</b></span><input v-model="filters.fromDate" type="date" required /></label>
			<label><span class="erp-field-label">To date <b>*</b></span><input v-model="filters.toDate" type="date" required /></label>
			<LinkField v-model="filters.item" doctype="Item" label="Item variant" placeholder="Search variant…" :show-open-button="false" show-clear />
			<LinkField v-model="filters.parentItem" doctype="Item" label="Item" placeholder="Search item…" :filters="{ has_variants: 1 }" :show-open-button="false" show-clear />
			<LinkField v-model="filters.warehouse" doctype="Warehouse" label="Warehouse" placeholder="Search warehouse…" :show-open-button="false" show-clear />
			<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
			<LinkField v-model="filters.receivedType" doctype="YRP Received Type" label="Received type" placeholder="Search received type…" :show-open-button="false" show-clear />
			<div class="stock-checks">
				<label><input v-model="filters.removeZero" type="checkbox" /> Remove zero balance</label>
				<label><input v-model="filters.showAttributes" type="checkbox" /> Variant attributes</label>
				<label><input v-model="filters.showAgeing" type="checkbox" /> Stock ageing</label>
				<label><input v-model="filters.showInwardSplit" type="checkbox" /> Inward date split</label>
			</div>
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Stock rows</span><strong>{{ number(rows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Balance quantity</span><strong>{{ number(totals.balanceQty, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-arrow-down-left" /><div><span>In quantity</span><strong>{{ number(totals.inQty, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-arrow-up-right" /><div><span>Out quantity</span><strong>{{ number(totals.outQty, 3) }}</strong></div></div>
		</template>

		<div class="erp-table-wrap stock-table-wrap">
			<table class="erp-data-table stock-table">
				<thead><tr><th v-for="column in columns" :key="column.fieldname" :class="numericColumn(column) ? 'erp-number' : ''">{{ column.label || column.fieldname }}</th></tr></thead>
				<tbody>
					<tr v-for="(row, rowIndex) in rows" :key="rowIndex">
						<td v-for="column in columns" :key="column.fieldname" :class="cellClass(column, row)"><span :class="column.fieldname === 'inward_split' ? 'multiline-cell' : ''">{{ stockCellValue(row[column.fieldname], column) }}</span></td>
					</tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getStockBalanceReport } from "../../../api/cuttingReports.js"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "./ReportShell.vue"
import { errorMessage, number, oneMonthAgoIso, stockCellValue, todayIso } from "./reportUtils.js"

const filters = reactive(defaultFilters())
const rows = ref([])
const columns = ref([])
const loading = ref(false)
const generated = ref(false)
const error = ref("")
const totals = computed(() => rows.value.reduce((out, row) => {
	out.balanceQty += Number(row.bal_qty || 0); out.inQty += Number(row.in_qty || 0); out.outQty += Number(row.out_qty || 0); return out
}, { balanceQty: 0, inQty: 0, outQty: 0 }))

function defaultFilters() {
	return { fromDate: oneMonthAgoIso(), toDate: todayIso(), item: "", parentItem: "", warehouse: "", lot: "", receivedType: "", removeZero: true, showAttributes: false, showAgeing: false, showInwardSplit: false }
}
function numericColumn(column) { return ["Float", "Currency", "Int"].includes(column?.fieldtype) }
function cellClass(column, row) {
	return [numericColumn(column) ? "erp-number" : "", column.fieldname === "in_qty" && Number(row.in_qty) > 0 ? "stock-in" : "", column.fieldname === "out_qty" && Number(row.out_qty) > 0 ? "stock-out" : ""]
}
async function generate() {
	if (!filters.fromDate || !filters.toDate) { error.value = "From date and To date are required."; return }
	if (filters.fromDate > filters.toDate) { error.value = "From date cannot be after To date."; return }
	error.value = ""
	loading.value = true
	try {
		const response = await getStockBalanceReport({
			from_date: filters.fromDate, to_date: filters.toDate, item: filters.item, parent_item: filters.parentItem,
			warehouse: filters.warehouse, lot: filters.lot, received_type: filters.receivedType,
			remove_zero_balance_item: filters.removeZero ? 1 : 0, show_variant_attributes: filters.showAttributes ? 1 : 0,
			show_stock_ageing_data: filters.showAgeing ? 1 : 0, show_inward_date_split: filters.showInwardSplit ? 1 : 0,
		}) || {}
		rows.value = response.result || []
		columns.value = (response.columns || []).map((column, index) => typeof column === "string" ? { fieldname: `column_${index}`, label: column } : column)
		generated.value = true
	} catch (exception) { error.value = errorMessage(exception, "Unable to generate the Stock Balance report.") }
	finally { loading.value = false }
}
function reset() { Object.assign(filters, defaultFilters()); rows.value = []; columns.value = []; generated.value = false; error.value = "" }
</script>

<style scoped>
.erp-field-label b { color: var(--erp-danger); }
.stock-checks { display: grid; grid-column: span 2; grid-template-columns: repeat(2, minmax(145px, 1fr)); gap: 5px 16px; align-content: center; min-width: 330px; min-height: 36px; padding: 7px 10px; background: white; border: 1px solid var(--erp-border); border-radius: 7px; }
.stock-checks label { display: flex; align-items: center; gap: 5px; color: #52645b; font-size: 0.65rem; white-space: nowrap; }
.stock-checks input { accent-color: var(--erp-accent); }
.stock-table-wrap { max-height: 58vh; }
.stock-table { min-width: 1280px; }
.stock-table thead { position: sticky; top: 0; z-index: 2; }
.stock-in { color: var(--erp-accent) !important; font-weight: 800; }
.stock-out { color: var(--erp-danger) !important; font-weight: 800; }
.multiline-cell { white-space: pre-line; }
@media (max-width: 760px) { .stock-checks { grid-column: span 1; min-width: 0; } }
</style>

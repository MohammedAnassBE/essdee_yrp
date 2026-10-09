<template>
	<ReportShell
		class="purchase-order-itemwise-report"
		title="Purchase Order Itemwise"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="rows.length > 0"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :show-open-button="false" show-clear />
			<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" placeholder="Search supplier…" :show-open-button="false" show-clear />
			<LinkField v-model="filters.purchaseOrder" doctype="Purchase Order" label="Purchase Order" placeholder="Search Purchase Order…" :show-open-button="false" show-clear />
			<label class="purchase-report-select" for="purchase-report-open-status"><span>Open Status</span><Select v-model="filters.openStatus" input-id="purchase-report-open-status" :options="openStatuses" show-clear fluid /></label>
			<details class="purchase-report-advanced" :open="advancedOpen" @toggle="advancedOpen = $event.currentTarget.open">
				<summary><span>More filters</span><small>{{ optionalFilterCount ? `${optionalFilterCount} active` : "Optional" }}</small><i class="pi pi-chevron-down" /></summary>
				<div class="purchase-report-advanced__grid">
					<LinkField v-model="filters.deliveryLocation" doctype="Supplier" label="Delivery Location" placeholder="Search location…" :show-open-button="false" show-clear />
					<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
					<label class="purchase-report-select" for="purchase-report-status"><span>Status</span><Select v-model="filters.status" input-id="purchase-report-status" :options="statuses" show-clear fluid /></label>
					<label class="purchase-report-select" for="purchase-report-docstatus"><span>Docstatus</span><Select v-model="filters.docstatus" input-id="purchase-report-docstatus" :options="docstatuses" option-label="label" option-value="value" show-clear fluid /></label>
					<label class="purchase-report-select" for="purchase-report-date-basis"><span>Date Filter Based On</span><Select v-model="filters.dateBasedOn" input-id="purchase-report-date-basis" :options="dateBases" show-clear fluid /></label>
					<DateField v-if="filters.dateBasedOn" v-model="filters.fromDate" label="From Date" />
					<DateField v-if="filters.dateBasedOn" v-model="filters.toDate" label="To Date" />
				</div>
			</details>
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Item rows</span><strong>{{ number(rows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-shopping-cart" /><div><span>Ordered quantity</span><strong>{{ number(totals.ordered, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-check-circle" /><div><span>Delivered quantity</span><strong>{{ number(totals.delivered, 3) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-clock" /><div><span>Pending quantity</span><strong>{{ number(totals.pending, 3) }}</strong></div></div>
		</template>

		<div class="erp-table-wrap purchase-order-itemwise-report__table-wrap" role="region" aria-label="Purchase Order Itemwise results" tabindex="0">
			<table class="erp-data-table purchase-order-itemwise-report__table">
				<thead><tr><th v-for="column in columns" :key="column.fieldname" :class="numericColumn(column) ? 'erp-number' : ''">{{ column.label || column.fieldname }}</th></tr></thead>
				<tbody>
					<tr v-for="(row, rowIndex) in rows" :key="`${row.name || 'row'}-${rowIndex}`">
						<td v-for="column in columns" :key="column.fieldname" :class="cellClass(column, row)">
							<RouterLink v-if="column.fieldname === 'name' && row.name" :to="{ name: 'purchase-purchase-order', params: { purchaseOrderId: row.name } }">{{ row.name }}</RouterLink>
							<span v-else-if="column.fieldname === 'status'" class="purchase-order-itemwise-report__status" :class="statusClass(row.status)">{{ cellValue(row[column.fieldname], column) }}</span>
							<span v-else>{{ cellValue(row[column.fieldname], column) }}</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
</template>

<script setup>
import Select from "primevue/select"
import { computed, reactive, ref } from "vue"

import { getPurchaseOrderItemwiseReport } from "../../api/purchaseReports.js"
import DateField from "../common/DateField.vue"
import LinkField from "../common/LinkField.vue"
import ReportShell from "./ReportShell.vue"
import { errorMessage, number, stockCellValue, todayIso } from "./reportUtils.js"

const rows = ref([])
const columns = ref([])
const loading = ref(false)
const generated = ref(false)
const error = ref("")
const advancedOpen = ref(typeof window === "undefined" || !window.matchMedia("(max-width: 430px)").matches)
const filters = reactive(defaultFilters())
const today = todayIso()
const statuses = ["Draft", "Ordered", "Cancelled", "Delivered", "Partially Delivered", "Partially Cancelled"]
const openStatuses = ["Open", "Closed"]
const docstatuses = [
	{ label: "Draft", value: "0" },
	{ label: "Submitted", value: "1" },
	{ label: "Cancelled", value: "2" },
]
const dateBases = ["Posting Date", "Delivery Date"]
const totals = computed(() => rows.value.reduce((result, row) => {
	result.ordered += Number(row.qty || 0)
	result.delivered += Number(row.delivered_qty || 0)
	result.pending += Number(row.pending_qty || 0)
	return result
}, { ordered: 0, delivered: 0, pending: 0 }))
const optionalFilterCount = computed(() => [
	filters.deliveryLocation, filters.lot, filters.status, filters.docstatus, filters.dateBasedOn,
].filter((value) => value !== "" && value !== null && value !== undefined).length)

function defaultFilters() {
	return {
		item: "", supplier: "", purchaseOrder: "", deliveryLocation: "", lot: "",
		status: "", openStatus: "Open", docstatus: "", dateBasedOn: "", fromDate: "", toDate: "",
	}
}
function numericColumn(column) { return ["Float", "Currency", "Int"].includes(column?.fieldtype) }
function cellValue(value, column) { return stockCellValue(value, column) }
function cellClass(column, row) {
	return [
		numericColumn(column) ? "erp-number" : "",
		column.fieldname === "pending_qty" ? pendingClass(row) : "",
	]
}
function pendingClass(row) {
	const pending = Number(row.pending_qty || 0)
	if (pending < 0) return "purchase-order-itemwise-report__pending--excess"
	if (pending <= 0 || !row.delivery_date) return ""
	if (row.delivery_date < today) return "purchase-order-itemwise-report__pending--overdue"
	if (row.delivery_date === today) return "purchase-order-itemwise-report__pending--today"
	return "purchase-order-itemwise-report__pending--future"
}
function statusClass(status) {
	return `purchase-order-itemwise-report__status--${String(status || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
}
async function generate() {
	if (filters.dateBasedOn && filters.fromDate && filters.toDate && filters.fromDate > filters.toDate) {
		error.value = "From Date cannot be after To Date."
		return
	}
	error.value = ""
	loading.value = true
	try {
		const response = await getPurchaseOrderItemwiseReport({
			item: filters.item,
			supplier: filters.supplier,
			purchase_order: filters.purchaseOrder,
			delivery_location: filters.deliveryLocation,
			lot: filters.lot,
			status: filters.status,
			open_status: filters.openStatus,
			docstatus: filters.docstatus,
			date_based_on: filters.dateBasedOn,
			from_date: filters.dateBasedOn ? filters.fromDate : "",
			to_date: filters.dateBasedOn ? filters.toDate : "",
		}) || {}
		rows.value = response.result || []
		columns.value = (response.columns || []).map((column, index) => (
			typeof column === "string" ? { fieldname: `column_${index}`, label: column } : column
		))
		generated.value = true
	} catch (exception) {
		error.value = errorMessage(exception, "Unable to generate the Purchase Order Itemwise report.")
	} finally {
		loading.value = false
	}
}
function reset() {
	Object.assign(filters, defaultFilters())
	rows.value = []
	columns.value = []
	generated.value = false
	error.value = ""
}
</script>

<style scoped>
.purchase-report-select {
	display: grid;
	gap: 6px;
	min-width: 0;
}

.purchase-report-select > span {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 680;
}

.purchase-report-advanced {
	display: block;
	grid-column: 1 / -1;
}

.purchase-report-advanced__grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	gap: var(--erp-space-2) var(--erp-space-3);
}

.purchase-report-advanced summary {
	display: none;
}

.purchase-order-itemwise-report__table {
	min-width: 2050px;
}

.purchase-order-itemwise-report__table td > span {
	display: block;
	max-width: 280px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.purchase-order-itemwise-report__status {
	display: inline-flex !important;
	width: max-content;
	max-width: none !important;
	padding: 3px 8px;
	color: #485b53;
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	background: #edf1ef;
	border-radius: 999px;
}

.purchase-order-itemwise-report__status--ordered { color: #245c9b; background: #eaf2fb; }
.purchase-order-itemwise-report__status--partially-delivered { color: #8a5b08; background: #fff6d9; }
.purchase-order-itemwise-report__status--delivered { color: #087654; background: #e8f8f1; }
.purchase-order-itemwise-report__status--overdue { color: var(--erp-danger); background: #fff0f1; }
.purchase-order-itemwise-report__status--cancelled,
.purchase-order-itemwise-report__status--partially-cancelled { color: #68756f; background: #edf1ef; }
.purchase-order-itemwise-report__status--draft { color: #9a5a12; background: #fff0de; }
.purchase-order-itemwise-report__pending--future { color: #087654; font-weight: 800; }
.purchase-order-itemwise-report__pending--today { color: #245c9b; font-weight: 800; }
.purchase-order-itemwise-report__pending--overdue { color: var(--erp-danger); font-weight: 800; }
.purchase-order-itemwise-report__pending--excess { color: #b55c10; font-weight: 800; }

@media (max-width: 800px) {
	.purchase-report-advanced summary {
		display: flex;
		min-height: 44px;
		align-items: center;
		gap: 8px;
		padding: 8px 10px;
		color: var(--erp-text);
		font-size: var(--erp-font-size-caption);
		font-weight: 750;
		cursor: pointer;
		background: var(--erp-surface);
		border: 1px solid var(--erp-border);
		border-radius: var(--erp-control-radius);
	}

	.purchase-report-advanced summary small {
		margin-left: auto;
		color: var(--erp-text-muted);
		font-weight: 650;
	}

	.purchase-report-advanced[open] summary {
		margin-bottom: var(--erp-space-2);
	}

	.purchase-report-advanced__grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}

@media (max-width: 520px) {
	.purchase-report-advanced__grid {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>

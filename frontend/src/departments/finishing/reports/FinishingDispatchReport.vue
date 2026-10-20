<template>
	<section data-finishing-report="dispatch-report" aria-label="Dispatch Report">
		<ReportShell title="Dispatch Report" :generated="generated" :loading="loading" :has-results="rows.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<DateField v-model="filters.fromDate" label="From Date" required />
				<DateField v-model="filters.toDate" label="To Date" required />
				<AsyncLinkMultiSelect v-model="filters.lots" doctype="SD YRP Lot" label="Lot" />
				<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Item" :filters="{ has_variants: 1 }" />
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-box" /><div><span>Packed Boxes</span><strong>{{ formatQuantity(totals.packedBoxes) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-th-large" /><div><span>Packed Pieces</span><strong>{{ formatQuantity(totals.packedPieces) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-truck" /><div><span>Dispatched Boxes</span><strong class="finishing-type--dispatched">{{ formatQuantity(totals.dispatchedBoxes) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-send" /><div><span>Dispatched Pieces</span><strong class="finishing-type--dispatched">{{ formatQuantity(totals.dispatchedPieces) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-minus-circle" /><div><span>Diff Boxes</span><strong class="finishing-type--diff">{{ formatQuantity(totals.diffBoxes) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-minus-circle" /><div><span>Diff Pieces</span><strong class="finishing-type--diff">{{ formatQuantity(totals.diffPieces) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Dispatch Report" :period="period" />
				<div v-for="(row, index) in rows" :key="row.lot" class="finishing-scroll" role="region" tabindex="0" :aria-label="`Packed and dispatched for ${row.lot}`">
					<table class="finishing-table">
						<thead>
							<tr>
								<th class="finishing-table__index">#</th>
								<th>Lot</th>
								<th>Item</th>
								<th>Type</th>
								<th v-for="size in row.sizes" :key="size" class="erp-number">{{ size }} (Pcs)</th>
								<th class="erp-number">Total Boxes</th>
								<th class="erp-number">Pcs/Box</th>
								<th class="erp-number">Total Pieces</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td rowspan="3" class="finishing-table__index">{{ index + 1 }}</td>
								<td rowspan="3" class="finishing-table__colour">{{ row.lot }}</td>
								<td rowspan="3">{{ row.item }}</td>
								<td class="finishing-type--packed">Packed</td>
								<td v-for="size in row.sizes" :key="size" class="erp-number">{{ blank(row.packed_qty?.[size]) }}</td>
								<td class="erp-number finishing-table__row-total">{{ blank(row.packed_total_boxes) }}</td>
								<td rowspan="3" class="erp-number">{{ row.pieces_per_box }}</td>
								<td class="erp-number finishing-table__row-total">{{ blank(row.packed_total_pieces) }}</td>
							</tr>
							<tr>
								<td class="finishing-type--dispatched">Dispatched</td>
								<td v-for="size in row.sizes" :key="size" class="erp-number">{{ blank(row.dispatched_qty?.[size]) }}</td>
								<td class="erp-number finishing-table__row-total">{{ blank(row.dispatched_total_boxes) }}</td>
								<td class="erp-number finishing-table__row-total">{{ blank(row.dispatched_total_pieces) }}</td>
							</tr>
							<tr>
								<td class="finishing-type--diff">Diff</td>
								<td v-for="size in row.sizes" :key="size" class="erp-number finishing-type--diff">{{ blank(dispatchDiff(row.packed_qty?.[size], row.dispatched_qty?.[size])) }}</td>
								<td class="erp-number finishing-type--diff">{{ formatQuantity(row.packed_total_boxes - row.dispatched_total_boxes) }}</td>
								<td class="erp-number finishing-type--diff">{{ formatQuantity(row.packed_total_pieces - row.dispatched_total_pieces) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="Dispatch Report could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getDispatchReport } from "../../../api/finishing.js"
import DateField from "../../../components/common/DateField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { firstDayOfMonthIso, formatDate, todayIso } from "../../../components/reports/reportUtils.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { dispatchDiff, dispatchTotals } from "./finishingReports.js"
import { dateRangeError, useReportRequest } from "./useReportRequest.js"
import "../finishing.css"

const filters = reactive(defaultFilters())
const rows = ref([])
const period = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const totals = computed(() => dispatchTotals(rows.value))

function defaultFilters() {
	return { fromDate: firstDayOfMonthIso(), toDate: todayIso(), lots: [], items: [] }
}

function blank(value) {
	return value ? formatQuantity(value) : ""
}

function generate() {
	const message = dateRangeError(filters.fromDate, filters.toDate, "Please select both From Date and To Date")
	run(message, () => getDispatchReport({ from_date: filters.fromDate, to_date: filters.toDate, lots: filters.lots, items: filters.items }), (data) => {
		rows.value = data?.data || []
		period.value = `${formatDate(filters.fromDate)} - ${formatDate(filters.toDate)}`
	})
}

function reset() {
	Object.assign(filters, defaultFilters())
	rows.value = []
	clear()
}
</script>

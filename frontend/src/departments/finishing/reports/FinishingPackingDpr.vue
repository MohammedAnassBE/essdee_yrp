<template>
	<section data-finishing-report="packing-dpr" aria-label="Packing DPR">
		<ReportShell title="Packing DPR" :generated="generated" :loading="loading" :has-results="rows.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<label class="finishing-report-toggle"><Checkbox v-model="filters.summary" binary input-id="packing-dpr-summary" @change="clearResults" /><span>Summary</span></label>
				<DateField v-if="!filters.summary" v-model="filters.date" label="Date" required />
				<template v-else>
					<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Item" :filters="{ has_variants: 1 }" />
					<AsyncLinkMultiSelect v-model="filters.lots" doctype="SD YRP Lot" label="Lot" />
					<DateField v-model="filters.fromDate" label="From Date" required />
					<DateField v-model="filters.toDate" label="To Date" required />
				</template>
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-th-large" /><div><span>Total Pieces</span><strong>{{ formatQuantity(totals.pieces) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-box" /><div><span>Total Boxes</span><strong>{{ formatQuantity(totals.boxes) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Finishing Packed Details" :period="period" />
				<section v-for="group in groups" :key="group.date" class="finishing-section" :aria-label="`Packed on ${formatDate(group.date)}`">
					<p v-if="resultSummary" class="finishing-report-date"><strong>{{ formatDate(group.date) }}</strong> {{ formatQuantity(sumBy(group.rows, "total_pieces")) }} pieces · {{ formatQuantity(sumBy(group.rows, "total_boxes")) }} boxes</p>
					<div v-for="(row, index) in group.rows" :key="`${group.date}-${row.lot}`" class="finishing-scroll" role="region" tabindex="0" :aria-label="`Packed details for ${row.lot}`">
						<table class="finishing-table">
							<thead>
								<tr>
									<th class="finishing-table__index">#</th>
									<th>Lot</th>
									<th>Item</th>
									<th v-for="size in row.sizes" :key="size" class="erp-number">{{ size }} (Pcs)</th>
									<th class="erp-number">Total Pieces</th>
									<th class="erp-number">Pcs/Box</th>
									<th class="erp-number">Total Boxes</th>
								</tr>
							</thead>
							<tbody>
								<tr>
									<td class="finishing-table__index">{{ index + 1 }}</td>
									<td class="finishing-table__colour">{{ row.lot }}</td>
									<td>{{ row.item }}</td>
									<td v-for="size in row.sizes" :key="size" class="erp-number">{{ row.size_qty?.[size] ? formatQuantity(row.size_qty[size]) : "" }}</td>
									<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total_pieces) }}</td>
									<td class="erp-number">{{ row.pieces_per_box }}</td>
									<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total_boxes) }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="Packing DPR could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import { computed, reactive, ref } from "vue"

import { getPackingDpr } from "../../../api/finishing.js"
import DateField from "../../../components/common/DateField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate, todayIso } from "../../../components/reports/reportUtils.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { groupByDate, packedTotals, sumBy } from "./finishingReports.js"
import { dateRangeError, useReportRequest } from "./useReportRequest.js"

const filters = reactive(defaultFilters())
const rows = ref([])
const resultSummary = ref(false)
const resultPeriod = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const totals = computed(() => packedTotals(rows.value))
const groups = computed(() => groupByDate(rows.value))
const period = computed(() => resultPeriod.value)

function defaultFilters() {
	return { summary: false, date: todayIso(), items: [], lots: [], fromDate: "", toDate: "" }
}

function validationError() {
	if (!filters.summary) return filters.date ? "" : "Please select a date"
	return dateRangeError(filters.fromDate, filters.toDate)
}

function generate() {
	const message = validationError()
	const summary = filters.summary
	run(message, () => getPackingDpr({ date: filters.date, from_date: filters.fromDate, to_date: filters.toDate, summary: summary ? 1 : 0, lots: filters.lots, items: filters.items }), (data) => {
		rows.value = data?.data || []
		resultSummary.value = summary
		resultPeriod.value = summary ? `${formatDate(filters.fromDate)} - ${formatDate(filters.toDate)}` : formatDate(filters.date)
	})
}

function clearResults() {
	rows.value = []
	clear()
}

function reset() {
	Object.assign(filters, defaultFilters())
	clearResults()
}
</script>

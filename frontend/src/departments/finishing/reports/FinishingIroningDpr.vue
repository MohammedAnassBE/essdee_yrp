<template>
	<section data-finishing-report="ironing-dpr" aria-label="Ironing DPR">
		<ReportShell :export-source="{ doctype: 'SD YRP Finishing Plan' }" title="Ironing DPR" :generated="generated" :loading="loading" :has-results="reports.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<label class="finishing-report-toggle"><Checkbox v-model="filters.summary" binary input-id="ironing-dpr-summary" @change="clearResults" /><span>Summary</span></label>
				<DateField v-if="!filters.summary" v-model="filters.date" label="Date" required />
				<template v-else>
					<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Item" :filters="{ has_variants: 1 }" />
					<AsyncLinkMultiSelect v-model="filters.lots" doctype="SD YRP Lot" label="Lot" />
					<DateField v-model="filters.fromDate" label="From Date" required />
					<DateField v-model="filters.toDate" label="To Date" required />
				</template>
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-tags" /><div><span>Lots</span><strong>{{ formatQuantity(reports.length) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-list" /><div><span>Rows</span><strong>{{ formatQuantity(rowCount) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-th-large" /><div><span>Total Qty</span><strong>{{ formatQuantity(totalQty) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Finishing Plan Ironing DPR" :period="period" />
				<section v-for="group in groups" :key="group.date" class="finishing-section" :aria-label="`Ironing on ${formatDate(group.date)}`">
					<p v-if="resultSummary" class="finishing-report-date"><strong>{{ formatDate(group.date) }}</strong> {{ group.rows.length }} lots · {{ formatQuantity(group.rows.reduce((sum, report) => sum + sumBy(report.rows, "total_qty"), 0)) }} qty</p>
					<article v-for="report in group.rows" :key="`${group.date}-${report.lot}`" class="finishing-section">
						<h3 class="ironing-dpr__lot">LOT: {{ report.lot }} <small>Item: {{ report.item }}</small></h3>
						<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`Ironing quantities for ${report.lot}`">
							<table class="finishing-table report-table">
								<thead>
									<tr>
										<th class="finishing-table__index report-cell--num">No</th>
										<th v-if="ironingShowsPart(report)" class="report-cell--text">Part</th>
										<th class="report-cell--text">Colour</th>
										<th v-for="size in report.primary_attributes" :key="size" class="erp-number report-cell--num">{{ size }}</th>
										<th class="erp-number report-cell--num">Total Qty</th>
									</tr>
								</thead>
								<tbody>
									<tr v-for="row in report.rows" :key="`${row.s_no}-${row.colour}`">
										<td class="finishing-table__index report-cell--num">{{ row.s_no }}</td>
										<td v-if="ironingShowsPart(report)" class="report-cell--text">{{ row.part || "" }}</td>
										<td class="finishing-table__colour">{{ row.colour || "" }}</td>
										<td v-for="size in report.primary_attributes" :key="size" class="erp-number report-cell--num">{{ formatQuantity(row[size] || 0) }}</td>
										<td class="erp-number report-cell--num finishing-table__row-total report-cell--last-column">{{ formatQuantity(row.total_qty || 0) }}</td>
									</tr>
									<tr class="finishing-table__total-row report-total-row">
										<td :colspan="ironingShowsPart(report) ? 3 : 2" class="report-cell--text">Total</td>
										<td v-for="size in report.primary_attributes" :key="size" class="erp-number report-cell--num">{{ formatQuantity(sumBy(report.rows, size)) }}</td>
										<td class="erp-number report-cell--num report-cell--last-column">{{ formatQuantity(sumBy(report.rows, "total_qty")) }}</td>
									</tr>
								</tbody>
							</table>
						</div>
					</article>
				</section>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="Ironing DPR could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import { computed, reactive, ref } from "vue"

import { getIroningDpr } from "../../../api/finishing.js"
import DateField from "../../../components/common/DateField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate, todayIso } from "../../../components/reports/reportUtils.js"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { groupByDate, ironingShowsPart, sumBy } from "./finishingReports.js"
import { dateRangeError, useReportRequest } from "./useReportRequest.js"

const filters = reactive(defaultFilters())
const reports = ref([])
const resultSummary = ref(false)
const period = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const groups = computed(() => groupByDate(reports.value))
const rowCount = computed(() => reports.value.reduce((sum, report) => sum + (report.rows || []).length, 0))
const totalQty = computed(() => reports.value.reduce((sum, report) => sum + sumBy(report.rows, "total_qty"), 0))

function defaultFilters() {
	return { summary: false, date: todayIso(), items: [], lots: [], fromDate: "", toDate: "" }
}

function validationError() {
	if (!filters.summary) return filters.date ? "" : "Select a date before generating the report"
	return dateRangeError(filters.fromDate, filters.toDate, "Select From Date and To Date before generating the report")
}

function generate() {
	const summary = filters.summary
	run(validationError(), () => getIroningDpr({ date: filters.date, from_date: filters.fromDate, to_date: filters.toDate, summary: summary ? 1 : 0, lots: filters.lots, items: filters.items }), (data) => {
		reports.value = data || []
		resultSummary.value = summary
		period.value = summary ? `${formatDate(filters.fromDate)} - ${formatDate(filters.toDate)}` : formatDate(filters.date)
	})
}

function clearResults() {
	reports.value = []
	clear()
}

function reset() {
	Object.assign(filters, defaultFilters())
	clearResults()
}
</script>

<style scoped>
.ironing-dpr__lot { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); font-weight: 700; }
.ironing-dpr__lot small { margin-left: 8px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-table); font-weight: 600; }
</style>

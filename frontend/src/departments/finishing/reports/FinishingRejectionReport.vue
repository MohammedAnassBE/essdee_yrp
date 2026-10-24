<template>
	<section data-finishing-report="rejection-details" aria-label="Rejection Details">
		<ReportShell :export-source="{ doctype: 'SD YRP Finishing Plan' }" title="Rejection Details" :generated="generated" :loading="loading" :has-results="seriesRows.length > 0" copyable :before-copy="expandAllForCopy" keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<DateField v-model="filters.startDate" label="Start Date" required />
				<DateField v-model="filters.endDate" label="End Date" required />
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :show-open-button="false" show-clear />
				<label class="common-field"><span class="finishing-field-label">Colour</span><InputText v-model="filters.colour" placeholder="Colour" fluid /></label>
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-list" /><div><span>Sources</span><strong>{{ formatQuantity(seriesRows.length) }}</strong></div></div>
				<div v-for="type in data.types" :key="type" class="report-metric"><i class="pi pi-times-circle" /><div><span>{{ type }}</span><strong>{{ formatQuantity(data.total_detail?.[type]) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-ban" /><div><span>Total Rejected</span><strong>{{ formatQuantity(data.total_sum) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Rejection Details" :period="period">
					<Button label="Download Excel" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" :loading="downloading" @click="download" />
				</FinishingReportHeading>
				<FinishingSeriesTable :rows="seriesRows" :types="data.types || []" :expanded="expanded" :expand-all="copyingAll" @toggle="toggle" @open-grn="openGrn">
					<template #detail="{ detail }">
						<div v-for="(group, key) in detail.rejection_detail" :key="key" class="finishing-section">
							<h4 class="rejection-report__group">{{ key }}</h4>
							<div class="finishing-scroll">
								<table class="finishing-table report-table">
									<thead><tr><th class="report-cell--text">Size</th><th v-for="(item, index) in group.items" :key="index" class="erp-number report-cell--num">{{ item[detail.size] }}</th></tr></thead>
									<tbody><tr><td class="report-cell--text">Rejected Qty</td><td v-for="(item, index) in group.items" :key="index" class="erp-number report-cell--num" :class="{ 'report-cell--last-column': index === group.items.length - 1 }">{{ formatQuantity(item.rejected_qty) }}</td></tr></tbody>
								</table>
							</div>
						</div>
					</template>
				</FinishingSeriesTable>
			</div>
		</ReportShell>
		<RelatedDocumentWorkspaceDialog v-model:visible="grnOpen" doctype="YRP Goods Received Note" :name="grnName" @closed="grnOpen = false" />
		<DocumentErrorDialog :message="error" title="Rejection Details could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import { computed, nextTick, reactive, ref } from "vue"

import { downloadRejectionDetails, getRejectionDetails } from "../../../api/finishing.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate } from "../../../components/reports/reportUtils.js"
import RelatedDocumentWorkspaceDialog from "../../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import FinishingSeriesTable from "../components/FinishingSeriesTable.vue"
import { firstColourLabel } from "./finishingReports.js"
import { dateRangeError, useReportRequest } from "./useReportRequest.js"

const filters = reactive(defaultFilters())
const data = ref({})
const applied = ref({})
const period = ref("")
const expanded = ref("")
const downloading = ref(false)
const grnOpen = ref(false)
const grnName = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const seriesRows = computed(() => Object.entries(data.value.report_detail || {}).map(([series, detail]) => ({
	series,
	detail,
	colour: firstColourLabel(detail.rejection_detail),
	values: detail.types || {},
	total: detail.total,
})))

function lastMonth() {
	const today = new Date()
	const start = new Date(today.getFullYear(), today.getMonth() - 1, 1)
	const end = new Date(today.getFullYear(), today.getMonth(), 0)
	const iso = (date) => [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-")
	return { startDate: iso(start), endDate: iso(end) }
}

function defaultFilters() {
	return { ...lastMonth(), lot: "", item: "", colour: "" }
}

function requestFilters() {
	return { start_date: filters.startDate, end_date: filters.endDate, lot: filters.lot, item: filters.item, colour: filters.colour }
}

function generate() {
	const message = dateRangeError(filters.startDate, filters.endDate, "Please enter both Start Date and End Date").replace("From Date cannot be after To Date", "Start Date should be less than End Date")
	const request = requestFilters()
	run(message, () => getRejectionDetails(request), (value) => {
		data.value = value || {}
		applied.value = request
		expanded.value = ""
		period.value = `${formatDate(request.start_date)} - ${formatDate(request.end_date)}`
	})
}

async function download() {
	downloading.value = true
	try {
		await downloadRejectionDetails(applied.value)
	} catch (reason) {
		error.value = reason?.message || "Unable to download Rejection Details."
	} finally {
		downloading.value = false
	}
}

const copyingAll = ref(false)
async function expandAllForCopy() {
	copyingAll.value = true
	await nextTick()
	return () => { copyingAll.value = false }
}

function toggle(series) {
	expanded.value = expanded.value === series ? "" : series
}

function openGrn(name) {
	grnName.value = name
	grnOpen.value = true
}

function reset() {
	Object.assign(filters, defaultFilters())
	data.value = {}
	clear()
}
</script>

<style scoped>
.rejection-report__group { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 700; }
</style>

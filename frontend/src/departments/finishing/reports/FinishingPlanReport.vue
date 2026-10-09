<template>
	<section data-finishing-report="finishing-plan-report" aria-label="Finishing Plan Report">
		<ReportShell title="Finishing Plan Report" :generated="generated" :loading="loading" :has-results="rows.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :filters="{ has_variants: 1 }" :show-open-button="false" show-clear />
				<LinkField v-model="filters.season" doctype="SD YRP Product Season" label="Season" placeholder="Search season…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.productCategory" doctype="SD YRP Product Category" label="Product Category" placeholder="Search category…" :show-open-button="false" show-clear />
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-box" /><div><span>Finishing Plans</span><strong>{{ formatQuantity(rows.length) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Finishing Plan Report" :period="period">
					<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" @click="downloadCsv" />
				</FinishingReportHeading>
				<div class="finishing-scroll fp-report__scroll" role="region" tabindex="0" aria-label="Finishing Plan Report results">
					<table ref="table" class="finishing-table fp-report__table">
						<thead>
							<tr>
								<th v-for="column in columns" :key="column.fieldname" :class="headerClass(column)" :style="frozenStyle(column, true)">{{ column.label }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, index) in rows" :key="index">
								<td v-for="column in columns" :key="column.fieldname" :class="cellClass(column, row)" :style="frozenStyle(column, false)">{{ formatReportCell(column, row) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="Finishing Plan Report could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue"

import { runFinishingPlanReport } from "../../../api/finishing.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { FROZEN_COLUMNS, formatReportCell, normalizeReportColumn, reportCellTone } from "./finishingReports.js"
import { useReportRequest } from "./useReportRequest.js"

const NUMERIC = new Set(["Int", "Float", "Currency", "Percent"])
const filters = reactive(defaultFilters())
const columns = ref([])
const rows = ref([])
const period = ref("")
const table = ref(null)
const frozenLefts = ref({})
const { loading, generated, error, run, clear } = useReportRequest()

function defaultFilters() {
	return { lot: "", item: "", season: "", productCategory: "" }
}

function headerClass(column) {
	return { "erp-number": NUMERIC.has(column.fieldtype), "fp-report__frozen": FROZEN_COLUMNS.includes(column.fieldname), "fp-report__frozen-edge": column.fieldname === FROZEN_COLUMNS.at(-1) }
}

function cellClass(column, row) {
	const tone = reportCellTone(column, row)
	return { ...headerClass(column), [`finishing-value--${tone}`]: Boolean(tone), "finishing-table__colour": column.fieldname === "item" }
}

function frozenStyle(column, header) {
	const left = frozenLefts.value[column.fieldname]
	if (left === undefined) return {}
	return { position: "sticky", left: `${left}px`, zIndex: header ? 3 : 2 }
}

function measureFrozen() {
	const cells = table.value?.querySelectorAll("thead th") || []
	const lefts = {}
	let offset = 0
	columns.value.forEach((column, index) => {
		if (!FROZEN_COLUMNS.includes(column.fieldname)) return
		lefts[column.fieldname] = offset
		offset += cells[index]?.offsetWidth || 0
	})
	frozenLefts.value = window.innerWidth > 700 ? lefts : {}
}

function generate() {
	const values = { lot: filters.lot, item: filters.item, season: filters.season, product_category: filters.productCategory }
	const applied = Object.fromEntries(Object.entries(values).filter(([, value]) => value))
	run("", () => runFinishingPlanReport(applied), async (data) => {
		columns.value = (data?.columns || []).map(normalizeReportColumn)
		rows.value = data?.result || []
		period.value = Object.values(applied).join(" · ")
		frozenLefts.value = {}
		await nextTick()
		measureFrozen()
	})
}

function reset() {
	Object.assign(filters, defaultFilters())
	columns.value = []
	rows.value = []
	clear()
}

function csvCell(value) {
	const text = String(value ?? "")
	return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function downloadCsv() {
	const lines = [columns.value.map((column) => column.label), ...rows.value.map((row) => columns.value.map((column) => row[column.fieldname] ?? ""))]
	const url = URL.createObjectURL(new Blob(["﻿", lines.map((line) => line.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }))
	const link = document.createElement("a")
	link.href = url
	link.download = "finishing_plan_report.csv"
	link.click()
	window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

onMounted(() => window.addEventListener("resize", measureFrozen))
onBeforeUnmount(() => window.removeEventListener("resize", measureFrozen))
</script>

<style scoped>
.fp-report__scroll { max-height: min(70vh, 720px); }
.fp-report__frozen { background: var(--erp-surface); }
thead .fp-report__frozen { background: var(--erp-surface-muted); }
.fp-report__frozen-edge { box-shadow: inset -1px 0 0 var(--erp-border-strong); }
</style>

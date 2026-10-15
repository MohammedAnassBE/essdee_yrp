<template>
	<section data-finishing-report="finishing-plan-report" aria-label="Finishing Plan Report">
		<ReportShell title="Finishing Plan Report" :generated="generated" :loading="loading" :error="layoutError" :has-results="rows.length > 0" :generate-disabled="isBusy" :status-only="statusOnly" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :filters="{ has_variants: 1 }" :show-open-button="false" show-clear />
				<LinkField v-model="filters.season" doctype="SD YRP Product Season" label="Season" placeholder="Search season…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.productCategory" doctype="SD YRP Product Category" label="Product Category" placeholder="Search category…" :show-open-button="false" show-clear />
			</template>
			<template #actions>
				<Button label="Pick Columns" icon="pi pi-table" severity="secondary" outlined class="erp-action-button" :disabled="!generated || !allColumns.length" @click="pickerVisible = true" />
				<Button v-if="isBackgroundResult" label="Download" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" @click="download" />
			</template>
			<template #status>
				<ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="isBackgroundResult || reused" :has-linked-columns="hasLinkedColumns" :error="reportError" @rebuild="rebuild" />
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-box" /><div><span>Finishing Plans</span><strong>{{ formatQuantity(dataRows.length) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Finishing Plan Report" :period="period">
					<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" @click="downloadCsv" />
				</FinishingReportHeading>
				<div class="finishing-scroll fp-report__scroll" role="region" tabindex="0" aria-label="Finishing Plan Report results">
					<table ref="table" class="finishing-table fp-report__table">
						<colgroup><col v-for="column in columns" :key="column.key" :style="{ width: `${column.width}px` }" /></colgroup>
						<thead>
							<tr>
								<th v-for="column in columns" :key="column.key" :class="headerClass(column)" :style="frozenStyle(column, true)">{{ column.label }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, index) in rows" :key="index" :class="{ 'report-total-row': row.is_total_row }">
								<td v-for="column in columns" :key="column.key" :class="cellClass(column, row)" :style="frozenStyle(column, false)">{{ formattedCell(column, row) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		</ReportShell>
		<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import { useReportColumns } from "../../../composables/useReportColumns.js"
import { useWebReport } from "../../../composables/useWebReport.js"
import LinkField from "../../../components/common/LinkField.vue"
import ReportColumnPicker from "../../../components/reports/ReportColumnPicker.vue"
import { finishingPlanFormFilters } from "../../../components/reports/reportFilterState.js"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { FROZEN_COLUMNS, formatReportCell, frozenColumnOffsets, reportCellTone } from "./finishingReports.js"

const filters = reactive(defaultFilters())
const period = ref("")
const table = ref(null)
const frozenLefts = ref({})
const pickerVisible = ref(false)
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError, activeFilters,
	trackingStartedAt, loading, isBusy, generated, isBackgroundResult, statusOnly,
	generate: generateReport, filtersChanged, clear, download,
} = useWebReport({ reportKey: "finishing-plan" })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	hasLinkedColumns, layoutError, loadLayout, loadFieldOptions, applyLayout,
	saveLayout, resetLayout, cellAlign, cellValue,
} = useReportColumns({ reportKey: "finishing-plan", sourceColumns, sourceRows })
const dataRows = computed(() => rows.value.filter((row) => !row.is_total_row))

function defaultFilters() {
	return { lot: "", item: "", season: "", productCategory: "" }
}

function headerClass(column) {
	return { [cellAlign(column)]: true, "fp-report__frozen": isFrozen(column), "fp-report__frozen-edge": column.kind === "base" && column.fieldname === FROZEN_COLUMNS.at(-1) }
}

function cellClass(column, row) {
	const tone = column.kind === "base" ? reportCellTone(column, row) : ""
	return { ...headerClass(column), [`finishing-value--${tone}`]: Boolean(tone), "finishing-table__colour": column.kind === "base" && column.fieldname === "item" }
}

function isFrozen(column) { return column.kind === "base" && FROZEN_COLUMNS.includes(column.fieldname) }
function formattedCell(column, row) { return formatReportCell(column, { [column.fieldname]: cellValue(row, column) }) }

function frozenStyle(column, header) {
	if (!isFrozen(column)) return {}
	const left = frozenLefts.value[column.key]
	if (left === undefined) return {}
	return { position: "sticky", left: `${left}px`, zIndex: header ? 3 : 2 }
}

function measureFrozen() {
	const cells = table.value?.querySelectorAll("thead th") || []
	const widths = columns.value.map((_column, index) => cells[index]?.offsetWidth || 0)
	const lefts = frozenColumnOffsets(columns.value, widths)
	frozenLefts.value = window.innerWidth > 700 ? lefts : {}
}

async function generate() {
	const values = { lot: filters.lot, item: filters.item, season: filters.season, product_category: filters.productCategory }
	const applied = Object.fromEntries(Object.entries(values).filter(([, value]) => value))
	period.value = Object.values(applied).join(" · ")
	await generateReport(applied)
}

function requestFilters() {
	return Object.fromEntries(Object.entries({ lot: filters.lot, item: filters.item, season: filters.season, product_category: filters.productCategory }).filter(([, value]) => value))
}

function rebuild() { return generateReport(requestFilters(), { refresh: true }) }

function reset() {
	Object.assign(filters, defaultFilters())
	period.value = ""
	clear()
}

function restoreFilters(request) {
	if (!request) return
	Object.assign(filters, finishingPlanFormFilters(request))
	period.value = Object.values(request).filter(Boolean).join(" · ")
}

function csvCell(value) {
	const text = String(value ?? "")
	return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function downloadCsv() {
	const lines = [columns.value.map((column) => column.label), ...rows.value.map((row) => columns.value.map((column) => cellValue(row, column) ?? ""))]
	const url = URL.createObjectURL(new Blob(["﻿", lines.map((line) => line.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }))
	const link = document.createElement("a")
	link.href = url
	link.download = "finishing_plan_report.csv"
	link.click()
	window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, restoreFilters, { flush: "sync" })
watch(columns, async () => {
	frozenLefts.value = {}
	await nextTick()
	measureFrozen()
})
onMounted(() => {
	window.addEventListener("resize", measureFrozen)
	loadLayout()
})
onBeforeUnmount(() => window.removeEventListener("resize", measureFrozen))
</script>

<style scoped>
.fp-report__scroll { max-height: min(70vh, 720px); }
.fp-report__frozen { background: var(--erp-surface); }
thead .fp-report__frozen { background: var(--erp-surface-muted); }
.fp-report__frozen-edge { box-shadow: inset -1px 0 0 var(--erp-border-strong); }
</style>

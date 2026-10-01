<template>
	<ReportShell
		title="Daily Production Report"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="hasResults"
		copyable
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<div class="report-mode" role="group" aria-label="Report mode">
				<span class="report-mode__label">Report mode</span>
				<div>
					<button type="button" :class="{ 'is-active': !summaryMode }" :aria-pressed="!summaryMode" @click="setMode(false)">
						<i class="pi pi-calendar" />Daily
					</button>
					<button type="button" :class="{ 'is-active': summaryMode }" :aria-pressed="summaryMode" @click="setMode(true)">
						<i class="pi pi-clone" />Summary
					</button>
				</div>
			</div>
			<label v-if="!summaryMode">
				<span class="erp-field-label">Date <b>*</b></span>
				<input v-model="filters.date" type="date" required />
			</label>
			<template v-else>
				<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Items" placeholder="Search items…" />
				<AsyncLinkMultiSelect v-model="filters.lots" doctype="SD YRP Lot" label="Lots" placeholder="Search lots…" />
				<label>
					<span class="erp-field-label">From date</span>
					<input v-model="filters.fromDate" type="date" />
				</label>
				<label>
					<span class="erp-field-label">To date</span>
					<input v-model="filters.toDate" type="date" />
				</label>
			</template>
			<label>
				<span class="erp-field-label">Cutting location</span>
				<select v-model="filters.location">
					<option value="">All locations</option>
					<option value="Machine Cutting">Machine Cutting</option>
					<option value="Manual Cutting">Manual Cutting</option>
				</select>
			</label>
		</template>

		<template #metrics>
			<div class="report-metric production-metric"><span class="production-metric__icon"><i class="pi pi-box" /></span><div><span>Bundles generated</span><strong>{{ number(metrics.bundleGenerated) }}</strong><small>Lay sheets with bundles</small></div></div>
			<div class="report-metric production-metric"><span class="production-metric__icon"><i class="pi pi-tag" /></span><div><span>Labels printed</span><strong>{{ number(metrics.labelPrinted) }}</strong><small>{{ labelCoverage }}% of bundles</small></div></div>
			<div class="report-metric production-metric"><span class="production-metric__icon"><i class="pi pi-file-plus" /></span><div><span>Created</span><strong>{{ number(metrics.created) }}</strong><small>Created in period</small></div></div>
			<div class="report-metric production-metric production-metric--primary"><span class="production-metric__icon"><i class="pi pi-chart-line" /></span><div><span>Cut output</span><strong>{{ number(metrics.pieces) }}</strong><small>{{ metrics.groups }} style / lot groups</small></div></div>
		</template>

		<header class="production-results-heading">
			<div>
				<p>{{ summaryMode ? "Multi-day production" : "Production output" }}</p>
				<h3>{{ resultHeading }}</h3>
				<span>{{ resultContext }}</span>
			</div>
			<span class="production-results-heading__rows"><b>{{ number(metrics.rows) }}</b> production rows</span>
		</header>

		<template v-if="summaryMode">
			<section v-for="day in summaryData" :key="day.date" class="summary-day">
				<header class="summary-day__header">
					<div class="summary-day__date"><span>{{ dateParts(day.date).day }}</span><div><p>{{ dateParts(day.date).month }}</p><h3>{{ dateParts(day.date).year }}</h3></div></div>
					<div class="summary-day__counts">
						<span><small>Bundles</small><b>{{ number(day.bundle_generated) }}</b></span>
						<span><small>Labels</small><b>{{ number(day.label_printed) }}</b></span>
						<span><small>Created</small><b>{{ number(day.created) }}</b></span>
						<span class="summary-day__output"><small>Cut output</small><b>{{ number(dayPieces(day)) }}</b></span>
					</div>
				</header>
				<ProductionMatrix :groups="day.report_data || []" />
			</section>
		</template>
		<ProductionMatrix v-else :groups="reportData" />
	</ReportShell>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getDailyProductionReport, getDailyProductionSummary } from "../../../api/cuttingReports.js"
import AsyncLinkMultiSelect from "./AsyncLinkMultiSelect.vue"
import ProductionMatrix from "./ProductionMatrix.vue"
import ReportShell from "./ReportShell.vue"
import { errorMessage, formatDate, number, reportRowCount, todayIso } from "./reportUtils.js"

const summaryMode = ref(false)
const filters = reactive(defaultFilters())
const loading = ref(false)
const generated = ref(false)
const error = ref("")
const report = ref(null)
const summaryData = ref([])

const reportData = computed(() => report.value?.report_data || [])
const hasResults = computed(() => summaryMode.value ? summaryData.value.length > 0 : reportData.value.length > 0)
const metrics = computed(() => {
	if (!summaryMode.value) {
		return {
			bundleGenerated: report.value?.bundle_generated || 0,
			labelPrinted: report.value?.label_printed || 0,
			created: report.value?.created || 0,
			rows: reportRowCount(reportData.value),
			pieces: groupPieces(reportData.value),
			groups: reportData.value.length,
		}
	}
	return summaryData.value.reduce(
		(acc, day) => {
			acc.bundleGenerated += Number(day.bundle_generated || 0)
			acc.labelPrinted += Number(day.label_printed || 0)
			acc.created += Number(day.created || 0)
			acc.rows += reportRowCount(day.report_data)
			acc.pieces += groupPieces(day.report_data)
			acc.groups += day.report_data?.length || 0
			return acc
		},
		{ bundleGenerated: 0, labelPrinted: 0, created: 0, rows: 0, pieces: 0, groups: 0 },
	)
})
const labelCoverage = computed(() => metrics.value.bundleGenerated
	? Math.round((metrics.value.labelPrinted / metrics.value.bundleGenerated) * 100)
	: 0)
const resultHeading = computed(() => summaryMode.value
	? `${summaryData.value.length} production ${summaryData.value.length === 1 ? "day" : "days"}`
	: formatDate(filters.date))
const resultContext = computed(() => {
	const location = filters.location || "All cutting locations"
	if (!summaryMode.value) return `${location} · ${metrics.value.groups} style / lot groups`
	const filterCount = filters.items.length + filters.lots.length
	return `${location} · ${filterCount ? `${filterCount} selected item / lot filters` : "Date-range summary"}`
})

function defaultFilters() {
	return { date: todayIso(), items: [], lots: [], fromDate: "", toDate: "", location: "" }
}

function clearResult() {
	report.value = null
	summaryData.value = []
	generated.value = false
	error.value = ""
}

function setMode(value) {
	if (summaryMode.value === value) return
	summaryMode.value = value
	clearResult()
}

function groupPieces(groups) {
	return (groups || []).reduce((total, group) => total + Number(group.total_sum || 0), 0)
}

function dayPieces(day) {
	return groupPieces(day.report_data)
}

function dateParts(value) {
	const parts = formatDate(value).split("-")
	const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	return { day: parts[0] || "—", month: monthNames[Number(parts[1]) - 1] || parts[1] || "", year: parts[2] || "" }
}

function validate() {
	if (!summaryMode.value && !filters.date) return "Date is required."
	if (!summaryMode.value) return ""
	if (Boolean(filters.fromDate) !== Boolean(filters.toDate)) return "Select both From date and To date."
	if (filters.fromDate && filters.toDate && filters.fromDate > filters.toDate) return "From date cannot be after To date."
	if (!filters.items.length && !filters.lots.length && !(filters.fromDate && filters.toDate)) {
		return "Select at least one Item or Lot, or a complete date range."
	}
	return ""
}

async function generate() {
	error.value = validate()
	if (error.value) return
	loading.value = true
	try {
		if (summaryMode.value) {
			summaryData.value = await getDailyProductionSummary({
				items: filters.items,
				lots: filters.lots,
				location: filters.location,
				from_date: filters.fromDate,
				to_date: filters.toDate,
			}) || []
			report.value = null
		} else {
			report.value = await getDailyProductionReport({ date: filters.date, location: filters.location })
			summaryData.value = []
		}
		generated.value = true
	} catch (exception) {
		error.value = errorMessage(exception)
	} finally {
		loading.value = false
	}
}

function reset() {
	Object.assign(filters, defaultFilters())
	summaryMode.value = false
	clearResult()
}
</script>

<style scoped>
.report-mode { display: grid; gap: 5px; }
.report-mode__label { color: #52665d; font-size: 0.7rem; font-weight: 750; }
.report-mode > div { display: grid; grid-template-columns: 1fr 1fr; min-height: 36px; padding: 3px; background: #e9efec; border: 1px solid #d7e1dc; border-radius: 8px; }
.report-mode button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; padding: 4px 9px; color: #68786f; font: inherit; font-size: 0.68rem; font-weight: 750; background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.report-mode button i { font-size: 0.64rem; }
.report-mode button.is-active { color: #087654; background: white; box-shadow: 0 1px 5px rgb(40 73 57 / 12%); }
.erp-field-label b { color: var(--erp-danger); }
.production-metric__icon { display: grid !important; width: 30px; height: 30px; flex: 0 0 auto; color: #087654 !important; background: #e9f6ef; border-radius: 8px; place-items: center; }
.production-metric small { display: block; margin-top: 1px; color: #819087; font-size: 0.58rem; }
.production-metric--primary { border-color: #cbe5d7 !important; background: #f1faf5 !important; }
.production-results-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; padding: 1px 2px 0; }
.production-results-heading p { margin: 0 0 2px; color: var(--erp-accent); font-size: 0.59rem; font-weight: 800; letter-spacing: 0.09em; text-transform: uppercase; }
.production-results-heading h3 { margin: 0; color: var(--erp-text); font-size: 0.96rem; }
.production-results-heading > div > span { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: 0.67rem; }
.production-results-heading__rows { color: #63756c; font-size: 0.66rem; }
.production-results-heading__rows b { color: var(--erp-text); font-size: 0.78rem; }
.summary-day { display: grid; gap: 12px; padding: 12px; background: #fbfdfc; border: 1px solid var(--erp-border); border-radius: 12px; }
.summary-day__header { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 2px 2px 0; }
.summary-day__date { display: flex; align-items: center; gap: 9px; }
.summary-day__date > span { display: grid; width: 38px; height: 38px; color: white; font-size: 0.95rem; font-weight: 850; background: var(--erp-accent); border-radius: 9px; place-items: center; }
.summary-day__date p { margin: 0; color: var(--erp-text-muted); font-size: 0.63rem; font-weight: 800; text-transform: uppercase; }
.summary-day__date h3 { margin: 1px 0 0; font-size: 0.78rem; }
.summary-day__counts { display: flex; gap: 6px; flex-wrap: wrap; }
.summary-day__counts span { display: grid; min-width: 64px; padding: 5px 8px; color: #52675d; background: white; border: 1px solid var(--erp-border); border-radius: 7px; }
.summary-day__counts small { font-size: 0.55rem; font-weight: 750; text-transform: uppercase; }
.summary-day__counts b { margin-top: 1px; color: #2d4339; font-size: 0.72rem; }
.summary-day__counts .summary-day__output { border-color: #cae6d7; background: #edf8f2; }
.summary-day__counts .summary-day__output b { color: #087654; }
@media (max-width: 700px) {
	.production-results-heading, .summary-day__header { align-items: stretch; flex-direction: column; }
}
</style>

<template>
	<ReportShell
		title="Daily Production Report"
		:generated="generated"
		:loading="loading"
		:error="validationError"
		:has-results="hasResults"
		:generate-disabled="isBusy"
		:status-only="statusOnly"
		copyable
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<div class="report-mode" role="group" aria-label="Report mode">
				<span class="report-mode__label erp-field-label">Report mode</span>
				<div>
					<button type="button" :class="{ 'is-active': !summaryMode }" :aria-pressed="!summaryMode" @click="setMode(false)">
						<i class="pi pi-calendar" />Daily
					</button>
					<button type="button" :class="{ 'is-active': summaryMode }" :aria-pressed="summaryMode" @click="setMode(true)">
						<i class="pi pi-clone" />Summary
					</button>
				</div>
			</div>
			<DateField v-if="!summaryMode" v-model="filters.date" class="production-report-filter" label="Date" required />
			<template v-else>
				<AsyncLinkMultiSelect v-model="filters.items" class="production-report-filter" doctype="Item" label="Items" placeholder="Search items…" />
				<AsyncLinkMultiSelect v-model="filters.lots" class="production-report-filter" doctype="SD YRP Lot" label="Lots" placeholder="Search lots…" />
				<DateField v-model="filters.fromDate" class="production-report-filter" label="From date" show-clear />
				<DateField v-model="filters.toDate" class="production-report-filter" label="To date" show-clear />
			</template>
			<label class="production-report-filter">
				<span class="erp-field-label">Cutting location</span>
				<select class="erp-native-select" v-model="filters.location">
					<option value="">All locations</option>
					<option value="Machine Cutting">Machine Cutting</option>
					<option value="Manual Cutting">Manual Cutting</option>
				</select>
			</label>
		</template>
		<template #actions>
			<Button v-if="isBackgroundResult" label="Download" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" @click="download" />
		</template>
		<template #status>
			<ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="isBackgroundResult || reused" :error="reportError" determinate @rebuild="rebuild" />
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
import Button from "primevue/button"
import { computed, reactive, ref, watch } from "vue"

import { useWebReport } from "../../../composables/useWebReport.js"
import DateField from "../../../components/common/DateField.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import AsyncLinkMultiSelect from "./AsyncLinkMultiSelect.vue"
import { dprFormState } from "./dailyProductionReportState.js"
import ProductionMatrix from "./ProductionMatrix.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate, number, reportRowCount, todayIso } from "../../../components/reports/reportUtils.js"

const summaryMode = ref(false)
const filters = reactive(defaultFilters())
const validationError = ref("")
const {
	state, payload, job, generatedAt, reused, error: reportError, trackingStartedAt, activeFilters,
	loading, isBusy, generated, isBackgroundResult, statusOnly,
	generate: generateReport, filtersChanged, clear, download,
} = useWebReport({ reportKey: "cutting-dpr" })

const report = computed(() => dailyPayload(payload.value))
const summaryData = computed(() => summaryPayload(payload.value))
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
		(result, day) => {
			result.bundleGenerated += Number(day.bundle_generated || 0)
			result.labelPrinted += Number(day.label_printed || 0)
			result.created += Number(day.created || 0)
			result.rows += reportRowCount(day.report_data)
			result.pieces += groupPieces(day.report_data)
			result.groups += day.report_data?.length || 0
			return result
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
	validationError.value = ""
	clear()
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
	if (filters.fromDate && filters.toDate && filters.fromDate > filters.toDate) return "From date cannot be after To date."
	if (!filters.items.length && !filters.lots.length && !filters.fromDate && !filters.toDate) {
		return "Select at least one Item or Lot, or a date boundary."
	}
	return ""
}

async function generate() {
	validationError.value = validate()
	if (validationError.value) return
	await generateReport(requestFilters())
}

function requestFilters() {
	if (!summaryMode.value) return { mode: "daily", date: filters.date, location: filters.location }
	return {
		mode: "summary",
		items: filters.items,
		lots: filters.lots,
		location: filters.location,
		from_date: filters.fromDate,
		to_date: filters.toDate,
	}
}

function rebuild() { return generateReport(requestFilters(), { refresh: true }) }

function reset() {
	Object.assign(filters, defaultFilters())
	summaryMode.value = false
	clearResult()
}

function restoreFilters(request) {
	if (!request) return
	const restored = dprFormState(request)
	summaryMode.value = restored.summaryMode
	Object.assign(filters, restored.filters)
}

function dailyPayload(envelope) {
	if (!envelope || summaryMode.value) return null
	if (envelope.report_data) return envelope
	if (envelope.payload?.report_data) return envelope.payload
	if (envelope.result && !Array.isArray(envelope.result)) return envelope.result
	return null
}

function summaryPayload(envelope) {
	if (!envelope || !summaryMode.value) return []
	if (Array.isArray(envelope.summary_data)) return envelope.summary_data
	if (Array.isArray(envelope.payload)) return envelope.payload
	if (Array.isArray(envelope.payload?.summary_data)) return envelope.payload.summary_data
	return Array.isArray(envelope.result) ? envelope.result : []
}

watch(() => requestFilters(), (values) => filtersChanged(values), { deep: true })
watch(activeFilters, restoreFilters, { flush: "sync" })
</script>

<style scoped>
.report-mode {
	display: grid;
	gap: 5px;
}

.report-mode > div {
	display: grid;
	grid-template-columns: 1fr 1fr;
	min-height: var(--erp-control-height);
	padding: 3px;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface-muted);
}

.report-mode button {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	gap: 5px;
	padding: 4px 9px;
	border: 0;
	border-radius: 6px;
	background: transparent;
	color: var(--erp-text-muted);
	cursor: pointer;
	font: inherit;
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-medium);
}

.report-mode button i {
	font-size: var(--erp-font-size-min);
}

.report-mode button.is-active {
	background: var(--erp-surface);
	color: var(--erp-accent-ink);
	box-shadow: var(--erp-shadow-xs);
	font-weight: var(--erp-font-weight-semibold);
}

.erp-field-label b {
	color: var(--erp-danger);
}

.production-metric__icon {
	display: grid !important;
	width: 30px;
	height: 30px;
	flex: 0 0 auto;
	border-radius: var(--erp-control-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent) !important;
	place-items: center;
}

.production-metric small {
	display: block;
	margin-top: 1px;
	color: #718078;
	font-size: var(--erp-font-size-min);
}

.production-metric--primary {
	border-color: #cbe5d7 !important;
	background: var(--erp-mint) !important;
}

.production-results-heading {
	display: flex;
	align-items: flex-end;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: 1px 2px 0;
}

.production-results-heading p {
	margin: 0 0 2px;
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.production-results-heading h3 {
	margin: 0;
	color: var(--erp-text);
	font-size: 15px;
}

.production-results-heading > div > span,
.production-results-heading__rows {
	display: block;
	margin-top: 3px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.production-results-heading__rows b {
	color: var(--erp-text);
	font-size: 13px;
}

.summary-day {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-3);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface-soft);
}

.summary-day__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 14px;
	padding: 2px 2px 0;
}

.summary-day__date {
	display: flex;
	align-items: center;
	gap: 9px;
}

.summary-day__date > span {
	display: grid;
	width: 38px;
	height: 38px;
	border-radius: var(--erp-control-radius);
	background: var(--erp-accent);
	color: white;
	font-size: 15px;
	font-weight: 850;
	place-items: center;
}

.summary-day__date p {
	margin: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	text-transform: uppercase;
}

.summary-day__date h3 {
	margin: 1px 0 0;
	font-size: 13px;
}

.summary-day__counts {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
}

.summary-day__counts span {
	display: grid;
	min-width: 68px;
	padding: 5px var(--erp-space-2);
	border: 1px solid var(--erp-border);
	border-radius: 7px;
	background: var(--erp-surface);
	color: #52675d;
}

.summary-day__counts small {
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	text-transform: uppercase;
}

.summary-day__counts b {
	margin-top: 1px;
	color: #2d4339;
	font-size: var(--erp-font-size-caption);
}

.summary-day__counts .summary-day__output {
	border-color: #cae6d7;
	background: var(--erp-mint);
}

.summary-day__counts .summary-day__output b {
	color: var(--erp-accent);
}

@media (max-width: 700px) {
	.report-mode button { min-height: 44px; }
	.production-results-heading,
	.summary-day__header {
		align-items: stretch;
		flex-direction: column;
	}
}

@media (max-width: 430px) {
	.report-mode,
	.production-report-filter { grid-column: 1 / -1; }
}
</style>

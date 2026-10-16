<template>
	<section aria-label="Month-wise Detail">
		<ReportShell title="Month-wise Detail" :generated="generated" :loading="loading" :error="reportError" :has-results="rows.length > 0" :generate-disabled="isBusy || Boolean(hint)" :status-only="statusOnly" empty-title="No rows for these filters." copyable @generate="generate" @reset="reset">
			<template #filters>
				<AsyncLinkMultiSelect v-model="filters.lot" doctype="SD YRP Lot" label="Lots" />
				<AsyncLinkMultiSelect v-model="filters.item" doctype="Item" label="Items" :filters="{ has_variants: 1 }" />
				<DateField v-model="filters.from_date" label="From Date" show-clear />
				<DateField v-model="filters.to_date" label="To Date" show-clear />
				<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
			</template>
			<template #actions>
				<Button label="Download CSV" icon="pi pi-download" severity="secondary" outlined :disabled="!generated || !rows.length" @click="downloadCsv" />
			</template>
			<template #status><ReportRunStatus :state="state" :job="job" :generated-at="generatedAt" :tracking-started-at="trackingStartedAt" :show-generated="reused" :error="reportError" @rebuild="rebuild" /></template>
			
			<section v-for="group in itemGroups" :key="group.item" class="finishing-stack"><h3>{{ group.item }}</h3>
			<PlanningReportTable title="Month-wise Detail" :columns="columns" :rows="group.rows" :cell-align="cellAlign" :formatted-cell="formattedCell" />
			</section>
		</ReportShell>

	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed, reactive, watch } from "vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import ReportRunStatus from "../../../components/reports/ReportRunStatus.vue"
import { useWebReport } from "../../../composables/useWebReport.js"
import PlanningReportTable from "./PlanningReportTable.vue"
import { usePlanningQuantityColumns } from "./usePlanningQuantityColumns.js"
import DateField from "../../../components/common/DateField.vue"
import AsyncLinkMultiSelect from "../../cutting/reports/AsyncLinkMultiSelect.vue"
import { monthWiseHint, populatedFilters } from "./productionReportFilters.js"

function defaultFilters() { return { lot: [], item: [], from_date: "", to_date: "" } }
const filters = reactive(defaultFilters())
const hint = computed(() => monthWiseHint(filters))
const {
	state, sourceColumns, sourceRows, job, generatedAt, reused, error: reportError,
	trackingStartedAt, loading, isBusy, generated, statusOnly, activeFilters, payload, reportSummary,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "planning-month-wise-detail" })
const { columns, rows, cellAlign, formattedCell, downloadCsv } = usePlanningQuantityColumns("planning-month-wise-detail", sourceColumns, sourceRows)

function requestFilters() { return populatedFilters(filters) }
function generate() { if (!hint.value) return generateReport(requestFilters()) }
function rebuild() { if (!hint.value) return generateReport(requestFilters(), { refresh: true }) }
function reset() { Object.assign(filters, defaultFilters()); clear() }
watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (request) => { if (request) Object.assign(filters, defaultFilters(), request) }, { flush: "sync" })
const itemGroups = computed(() => [...new Set(rows.value.map((row) => row.item))].map((item) => ({ item, rows: rows.value.filter((row) => row.item === item) })))
</script>

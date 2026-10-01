<template>
	<ReportShell
		title="Cutting Detail Report"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="reportData.length > 0"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<label><span class="erp-field-label">From date <b>*</b></span><input v-model="filters.startDate" type="date" required /></label>
			<label><span class="erp-field-label">To date <b>*</b></span><input v-model="filters.endDate" type="date" required /></label>
			<label>
				<span class="erp-field-label">Cutting location</span>
				<select v-model="filters.location"><option value="">All locations</option><option value="Machine Cutting">Machine Cutting</option><option value="Manual Cutting">Manual Cutting</option></select>
			</label>
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Bundles generated</span><strong>{{ number(report?.bundle_generated) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-tag" /><div><span>Labels printed</span><strong>{{ number(report?.label_printed) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-file-plus" /><div><span>Created</span><strong>{{ number(report?.created) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Detail rows</span><strong>{{ number(reportRowCount(reportData)) }}</strong></div></div>
		</template>

		<ProductionMatrix :groups="reportData" />
	</ReportShell>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getCuttingDetailReport } from "../../../api/cuttingReports.js"
import ProductionMatrix from "./ProductionMatrix.vue"
import ReportShell from "./ReportShell.vue"
import { errorMessage, firstDayOfMonthIso, number, reportRowCount, todayIso } from "./reportUtils.js"

const filters = reactive(defaultFilters())
const report = ref(null)
const loading = ref(false)
const generated = ref(false)
const error = ref("")
const reportData = computed(() => report.value?.report_data || [])

function defaultFilters() { return { startDate: firstDayOfMonthIso(), endDate: todayIso(), location: "" } }
async function generate() {
	if (!filters.startDate || !filters.endDate) { error.value = "From date and To date are required."; return }
	if (filters.startDate > filters.endDate) { error.value = "From date cannot be after To date."; return }
	error.value = ""
	loading.value = true
	try {
		report.value = await getCuttingDetailReport({ start_date: filters.startDate, end_date: filters.endDate, location: filters.location })
		generated.value = true
	} catch (exception) { error.value = errorMessage(exception) }
	finally { loading.value = false }
}
function reset() { Object.assign(filters, defaultFilters()); report.value = null; generated.value = false; error.value = "" }
</script>

<style scoped>
.erp-field-label b { color: var(--erp-danger); }
</style>

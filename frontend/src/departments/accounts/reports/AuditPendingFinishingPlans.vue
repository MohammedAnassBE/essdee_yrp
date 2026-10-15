<template>
	<section aria-label="Audit Pending Finishing Plans">
		<ReportShell title="Audit Pending Finishing Plans" :generated="generated" :loading="loading" :error="error" :has-results="sourceRows.length > 0" :generate-disabled="isBusy || Boolean(dateError)" :status-only="statusOnly" empty-title="No Finishing Plans are waiting for audit." empty-description="" copyable @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" :show-open-button="false" show-clear />
				<LinkField v-model="filters.item" doctype="Item" label="Item" placeholder="Search item…" :show-open-button="false" show-clear />
				<DateField v-model="filters.from_date" label="Requested From" :required="Boolean(filters.to_date)" />
				<div class="audit-pending__date">
					<DateField v-model="filters.to_date" label="To" :required="Boolean(filters.from_date)" />
					<small v-if="dateError" role="status">{{ dateError }}</small>
				</div>
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-check-square" /><div><span>Plans pending</span><strong>{{ sourceRows.length }}</strong></div></div>
			</template>
			<div class="finishing-scroll" role="region" tabindex="0" aria-label="Audit pending results">
				<table class="finishing-table audit-pending__table">
					<thead><tr><th v-for="column in sourceColumns" :key="column.fieldname" :class="{ 'audit-pending__number': column.fieldname === 'days_pending' }">{{ column.label }}</th></tr></thead>
					<tbody>
						<tr v-for="row in sourceRows" :key="row.name">
							<td v-for="column in sourceColumns" :key="column.fieldname" :class="{ 'audit-pending__number': column.fieldname === 'days_pending', 'audit-pending__warn': column.fieldname === 'days_pending' && row.days_pending >= 7 }">
								<RouterLink v-if="column.fieldname === 'name'" :to="`/finishing/plans/${encodeURIComponent(row.name)}`">{{ row.name }}</RouterLink>
								<template v-else>{{ formatCell(row, column) }}</template>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</ReportShell>
	</section>
</template>

<script setup>
import { computed, reactive, watch } from "vue"
import { RouterLink } from "vue-router"

import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate } from "../../../components/reports/reportUtils.js"
import { useWebReport } from "../../../composables/useWebReport.js"
import "../../finishing/finishing.css"

const filters = reactive(defaultFilters())
const {
	sourceColumns, sourceRows, loading, isBusy, generated, error, statusOnly, activeFilters,
	generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: "accounts-audit-pending-finishing-plans" })

const dateError = computed(() => {
	if (Boolean(filters.from_date) !== Boolean(filters.to_date)) return "Select both Requested From and To dates."
	if (filters.from_date && filters.from_date > filters.to_date) return "Requested From must be on or before To."
	return ""
})

function defaultFilters() {
	return { lot: "", item: "", from_date: "", to_date: "" }
}

function requestFilters() {
	return Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
}

function generate() {
	if (dateError.value || isBusy.value) return
	return generateReport(requestFilters())
}

function reset() {
	Object.assign(filters, defaultFilters())
	clear()
}

function formatCell(row, column) {
	const value = row[column.fieldname]
	return column.fieldtype === "Date" ? formatDate(value) : (value ?? "—")
}

watch(filters, () => filtersChanged(requestFilters()), { deep: true })
watch(activeFilters, (values) => {
	if (values) Object.assign(filters, defaultFilters(), values)
}, { flush: "sync" })
</script>

<style scoped>
.audit-pending__date { display: grid; gap: var(--erp-space-1); }
.audit-pending__date small { color: var(--erp-text-muted); }
.audit-pending__table .audit-pending__number { text-align: right; font-variant-numeric: tabular-nums; }
.audit-pending__table .audit-pending__warn { color: var(--erp-warning); background: var(--erp-warning-soft); }
.audit-pending__table th:first-child, .audit-pending__table td:first-child { position: sticky; left: 0; background: var(--erp-surface); }
.audit-pending__table th:first-child { z-index: 3; }
.audit-pending__table td:first-child { z-index: 2; }
</style>

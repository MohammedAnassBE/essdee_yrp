<template>
	<section data-attendance-strength aria-label="Attendance Strength Report">
		<ReportShell :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="Attendance Strength Report" :loading="loading" :generated="generated" :has-results="hasResults" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<DateField v-model="filters.date" label="Date" show-clear :disabled="loading" />
				<TimeField v-model="filters.fromTime" label="From Time" show-clear :disabled="loading" />
				<TimeField v-model="filters.toTime" label="To Time" show-clear :disabled="loading" />
			</template>
			<p class="attendance-strength__context">Shifts: {{ (data.shifts || []).join(', ') || '—' }}</p>
			<section v-for="table in tables" :key="table.label" class="attendance-strength__section" :aria-label="table.label + ' results'">
				<header class="attendance-strength__heading">
					<h2>{{ table.label }}</h2>
				</header>
				<div v-if="table.rows.length" class="attendance-strength__table erp-table-wrap" role="region" :aria-label="table.label" tabindex="0">
					<table class="erp-table">
						<thead><tr><th v-for="column in table.columns" :key="column.fieldname" scope="col" :class="{ numeric: isNumeric(column) }">{{ column.label || column.fieldname }}</th></tr></thead>
						<tbody><tr v-for="(row, index) in table.body" :key="index"><td v-for="column in table.columns" :key="column.fieldname" :class="{ numeric: isNumeric(column) }">{{ display(cell(row, column), column) }}</td></tr></tbody>
						<tfoot v-if="table.total"><tr><th v-for="(column, index) in table.columns" :key="column.fieldname" :scope="index === 0 ? 'row' : undefined" :class="{ numeric: isNumeric(column) }">{{ display(cell(table.total, column), column) }}</th></tr></tfoot>
					</table>
				</div>
				<p v-else class="attendance-strength__context">No {{ table.label.toLowerCase() }} rows returned.</p>
			</section>
		</ReportShell>
		<DocumentErrorDialog :title="errorTitle" :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"
import { getAttendanceStrength } from "../../api/sewing.js"
import DateField from "../common/DateField.vue"
import TimeField from "../common/TimeField.vue"
import DocumentErrorDialog from "../documents/DocumentErrorDialog.vue"
import ReportShell from "./ReportShell.vue"
import { stockCellValue, todayIso } from "./reportUtils.js"

const filters = reactive({ date: todayIso(), fromTime: "", toTime: "" })
const data = ref({}), loading = ref(false), generated = ref(false), error = ref("")
const errorTitle = ref("Unable to generate Strength Report")
let mounted = true
const hasResults = computed(() => Boolean(data.value.rows?.length || data.value.employee_punches?.length))
const punchColumns = [
	["employee", "Employee ID"], ["employee_name", "Employee Name"], ["department", "Department"],
	["designation", "Designation"], ["manpower_agent", "Manpower Agent"], ["shift_type", "Shift"], ["first_punch", "First Punch"],
].map(([fieldname, label]) => ({ fieldname, label }))
const tables = computed(() => {
	const rows = data.value.rows || []
	const total = Number(data.value.add_total_row) === 1 && rows.length ? rows[rows.length - 1] : null
	return [
		{ label: "Workers Strength Summary", columns: (data.value.columns || []).map((column, index) => ({ ...column, index })).filter(column => !Number(column.hidden)), rows, body: total ? rows.slice(0, -1) : rows, total },
		{ label: "Employee First Punch", columns: punchColumns, rows: data.value.employee_punches || [], body: data.value.employee_punches || [], total: null },
	]
})

async function generate() {
	if (loading.value) return
	for (const [key, label] of [["date", "Date"], ["fromTime", "From Time"], ["toTime", "To Time"]]) {
		if (!filters[key]) {
			errorTitle.value = `${label} required`
			error.value = `Choose ${label === "Date" ? "a Date" : label} to generate the Strength Report.`
			return
		}
	}
	loading.value = true; error.value = ""
	const date = filters.date
	try {
		const result = await getAttendanceStrength(date, filters.fromTime, filters.toTime)
		if (mounted) { data.value = result || {}; generated.value = true }
	} catch (reason) {
		if (mounted) { errorTitle.value = "Unable to generate Strength Report"; error.value = reason.message || "Unable to generate the Strength Report. Please try again." }
	} finally { if (mounted) loading.value = false }
}
function reset() {
	Object.assign(filters, { date: "", fromTime: "", toTime: "" })
	data.value = {}; generated.value = false; error.value = ""
}
watch(() => [filters.date, filters.fromTime, filters.toTime], () => { data.value = {}; generated.value = false })
onBeforeUnmount(() => { mounted = false })

function cell(row, column) { return Array.isArray(row) ? row[column.index] : row[column.fieldname] }
function isNumeric(column) { return ["Int", "Float", "Currency", "Percent"].includes(column.fieldtype) }
function display(value, column) {
	if (Array.isArray(value)) return value.join(", ")
	if (value && typeof value === "object") return JSON.stringify(value)
	return stockCellValue(value, column)
}
</script>

<style scoped>
[data-attendance-strength], .attendance-strength__section { min-width: 0; }
.attendance-strength__section { display: grid; gap: var(--erp-space-2); }
.attendance-strength__heading { display: flex; justify-content: space-between; align-items: center; gap: var(--erp-space-2); }
h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); font-weight: 700; }
.attendance-strength__context { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
.attendance-strength__table { width: 100%; max-width: 100%; min-width: 0; max-height: 46vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--erp-font-size-caption); }
th, td { padding: 9px 12px; white-space: nowrap; text-align: left; border-bottom: 1px solid var(--erp-border); }
thead th { position: sticky; top: 0; z-index: 1; color: var(--erp-text-secondary); background: var(--erp-surface-soft); }
tfoot th { background: var(--erp-surface-soft); font-weight: 700; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; }
.attendance-strength__table:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
@media (max-width: 560px) {
	.attendance-strength__heading { align-items: flex-start; flex-direction: column; }
	:deep(.report-filter-grid) { grid-template-columns: minmax(0, 1fr); }
	:deep(.report-shell__commands) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
	:deep(.report-shell__commands .p-button) { width: 100%; min-width: 0; }
	:deep(.report-shell__copy-button) { grid-column: 1 / -1; }
}
</style>

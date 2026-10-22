<template>
	<ReportShell :export-source="{ doctype: 'SD YRP Cutting LaySheet' }"
		title="Daily Cut Sheet Report"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="rows.length > 0"
		copyable
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<DateField v-model="filters.date" label="Date" required />
			<label>
				<span class="erp-field-label">Cutting location</span>
				<select class="erp-native-select" v-model="filters.location">
					<option value="">All locations</option>
					<option value="Machine Cutting">Machine Cutting</option>
					<option value="Manual Cutting">Manual Cutting</option>
				</select>
			</label>
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Style / lot groups</span><strong>{{ number(rows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Cut rows</span><strong>{{ number(rowCount) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-users" /><div><span>Cutters</span><strong>{{ number(cutterCount) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-calendar" /><div><span>Production date</span><strong>{{ formatDate(filters.date) }}</strong></div></div>
		</template>

		<div class="cut-sheet-stack">
			<article v-for="(group, groupIndex) in rows" :key="`${group.style_no}-${group.lot_no}-${groupIndex}`" class="cut-sheet-card">
				<header class="erp-section-header cut-sheet-card__header">
					<div><h3>{{ group.style_no || "Unspecified item" }}</h3><span>{{ group.lot_no || "No lot" }} · {{ group.location || "No location" }}</span></div>
					<span class="erp-count-badge">{{ group.items?.length || 0 }} rows</span>
				</header>
				<div class="erp-table-wrap cut-sheet-card__table">
					<table class="erp-data-table cut-sheet-table">
						<thead><tr><th>#</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th>Cutter</th><th v-for="size in group.primary_attribute_values || []" :key="size">{{ size }}</th><th>Today total</th></tr></thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="rowIndex">
								<td>{{ rowIndex + 1 }}</td>
								<td v-for="attribute in group.attributes || []" :key="attribute">{{ attributeValue(row, attribute) }}</td>
								<td><span class="cutter-chip">{{ row.cutter || "Unassigned" }}</span></td>
								<td v-for="size in group.primary_attribute_values || []" :key="size">
									<div class="panel-values"><span v-for="panel in positivePanels(row.values?.[size])" :key="panel.name"><b>{{ panel.name }}</b>{{ quantity(panel.value) }}</span><i v-if="!positivePanels(row.values?.[size]).length">—</i></div>
								</td>
								<td><div class="panel-values panel-values--total"><span v-for="panel in positivePanels(row.total_panel_qty)" :key="panel.name"><b>{{ panel.name }}</b>{{ quantity(panel.value) }}</span></div></td>
							</tr>
						</tbody>
					</table>
				</div>
			</article>
		</div>
	</ReportShell>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getDailyCutSheetReport } from "../../../api/cuttingReports.js"
import DateField from "../../../components/common/DateField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { attributeValue, errorMessage, formatDate, number, quantity, reportRowCount, todayIso } from "../../../components/reports/reportUtils.js"

const filters = reactive(defaultFilters())
const rows = ref([])
const loading = ref(false)
const generated = ref(false)
const error = ref("")
const rowCount = computed(() => reportRowCount(rows.value))
const cutterCount = computed(() => new Set(rows.value.flatMap((group) => (group.items || []).map((row) => row.cutter || ""))).size)

function defaultFilters() { return { date: todayIso(), location: "" } }
function positivePanels(values) {
	return Object.entries(values || {}).filter(([, value]) => Number(value) > 0).map(([name, value]) => ({ name, value }))
}
async function generate() {
	if (!filters.date) { error.value = "Date is required."; return }
	error.value = ""
	loading.value = true
	try {
		rows.value = await getDailyCutSheetReport({ date: filters.date, location: filters.location }) || []
		generated.value = true
	} catch (exception) { error.value = errorMessage(exception) }
	finally { loading.value = false }
}
function reset() {
	Object.assign(filters, defaultFilters())
	rows.value = []
	generated.value = false
	error.value = ""
}
</script>

<style scoped>
.erp-field-label b {
	color: var(--erp-danger);
}

.cut-sheet-stack {
	display: grid;
	gap: var(--erp-space-3);
}

.cut-sheet-card {
	min-width: 0;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
}

.cut-sheet-card__header {
	padding: 10px var(--erp-space-3);
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.cut-sheet-card__header h3 {
	max-width: min(720px, 58vw);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.cut-sheet-card__header span:not(.erp-count-badge) {
	display: block;
	max-width: min(720px, 58vw);
	margin-top: 3px;
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.cut-sheet-card__table {
	border: 0;
	border-radius: 0;
}

.cut-sheet-table {
	min-width: 880px;
}

.cutter-chip {
	display: inline-flex;
	padding: 2px 6px;
	border-radius: var(--erp-pill-radius);
	background: #edf5f1;
	color: #315e4c;
	font-size: var(--erp-font-size-min);
}

.panel-values {
	display: flex;
	min-width: 78px;
	flex-direction: column;
	gap: 2px;
}

.panel-values span {
	display: flex;
	justify-content: space-between;
	gap: var(--erp-space-2);
	color: #52645b;
	font-size: var(--erp-font-size-min);
}

.panel-values b {
	color: var(--erp-text);
	font-weight: 700;
}

.panel-values i {
	color: #96a39d;
	font-style: normal;
}

.panel-values--total span {
	color: var(--erp-accent);
	font-weight: 750;
}
</style>

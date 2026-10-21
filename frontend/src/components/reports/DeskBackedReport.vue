<template>
	<ReportShell :title="config.title" :generated="generated" :loading="loading" :error="filterError || layoutError" :has-results="rows.length > 0" :generate-disabled="isBusy" :status-only="statusOnly" @generate="generate" @reset="reset">
		<template #filters>
			<template v-for="field in visibleFilters" :key="field.fieldname">
				<LinkField v-if="field.fieldtype === 'Link'" v-model="filters[field.fieldname]" :doctype="field.options" :label="field.label" :filters="field.filters" :required="Boolean(field.reqd)" :show-open-button="false" show-clear />
				<DateField v-else-if="field.fieldtype === 'Date'" v-model="filters[field.fieldname]" :label="field.label" :required="Boolean(field.reqd)" />
				<label v-else-if="field.fieldtype === 'Int'" class="desk-report-field"><span>{{ field.label }}</span><InputNumber v-model="filters[field.fieldname]" :required="Boolean(field.reqd)" :use-grouping="false" :max-fraction-digits="0" fluid /></label>
				<label v-else-if="field.fieldtype === 'Select'" class="desk-report-field"><span>{{ field.label }}</span><Select v-model="filters[field.fieldname]" :options="field.options" option-label="label" option-value="value" fluid /></label>
				<label v-else-if="field.fieldtype === 'Check'" class="desk-report-check"><Checkbox v-model="filters[field.fieldname]" binary :true-value="1" :false-value="0" /><span>{{ field.label }}</span></label>
			</template>
		</template>
		<template #actions><Button label="Pick Columns" icon="pi pi-table" severity="secondary" outlined :disabled="!generated || !allColumns.length" @click="pickerVisible = true" /></template>
		<template #status><ReportRunStatus :state="state" :job="job" :error="reportError" @rebuild="generate" /></template>
		<div class="erp-table-wrap report-table-frame" role="region" :aria-label="`${config.title} results`" tabindex="0">
			<table class="erp-data-table desk-report-table">
				<thead><tr><th v-for="column in columns" :key="column.key" :class="cellAlign(column)" :style="{ minWidth: `${column.width}px` }">{{ column.label }}</th></tr></thead>
				<tbody><tr v-for="(row, index) in rows" :key="index" :class="{ 'report-total-row': row.is_total_row }"><td v-for="column in columns" :key="column.key" :class="[cellAlign(column), cellToneClass(row, column)]">{{ stockCellValue(cellValue(row, column), column) }}</td></tr></tbody>
			</table>
		</div>
	</ReportShell>
	<ReportColumnPicker v-model:visible="pickerVisible" :columns="allColumns" :link-sources="linkSources" :fields-by-source="fieldsBySource" :load-field-options="loadFieldOptions" :apply-layout="applyLayout" :save-layout="saveLayout" :reset-layout="resetLayout" :error="layoutError" />
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import InputNumber from "primevue/inputnumber"
import Select from "primevue/select"
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useReportColumns } from "../../composables/useReportColumns.js"
import { useWebReport } from "../../composables/useWebReport.js"
import DateField from "../common/DateField.vue"
import LinkField from "../common/LinkField.vue"
import { deskReportConfig, deskReportDefaults, deskReportQueryFilters } from "./deskReportConfig.js"
import ReportColumnPicker from "./ReportColumnPicker.vue"
import ReportRunStatus from "./ReportRunStatus.vue"
import ReportShell from "./ReportShell.vue"
import { stockCellValue, todayIso } from "./reportUtils.js"

const props = defineProps({ reportKey: { type: String, required: true }, supplier: { type: String, default: "" } })
const config = deskReportConfig[props.reportKey]
const route = useRoute()
const defaults = () => ({ ...deskReportDefaults(props.reportKey, todayIso()), ...(props.supplier ? { supplier: props.supplier } : {}), ...deskReportQueryFilters(props.reportKey, route.query) })
const filters = reactive(defaults())
const visibleFilters = computed(() => config.filters.filter(field => !field.depends_on || filters[field.depends_on]))
const filterError = ref("")
const pickerVisible = ref(false)
const {
	state, sourceColumns, sourceRows, job, error: reportError, activeFilters,
	loading, isBusy, generated, statusOnly, generate: generateReport, filtersChanged, clear,
} = useWebReport({ reportKey: props.reportKey })
const {
	columns: allColumns, displayColumns: columns, rows, linkSources, fieldsBySource,
	layoutError, loadLayout, loadFieldOptions, applyLayout, saveLayout, resetLayout, cellAlign, cellValue,
} = useReportColumns({ reportKey: props.reportKey, sourceColumns, sourceRows })

function cellToneClass(row, column) {
	const tone = config.cellTone?.(column.fieldname, cellValue(row, column))
	return ["success", "danger", "warning"].includes(tone) ? `desk-report-cell--${tone}` : ""
}

async function generate() {
	const missing = config.filters.find(field => field.reqd && !filters[field.fieldname])
	filterError.value = missing ? `${missing.label} is required.` : ""
	if (filterError.value) return
	if (visibleFilters.value.some(field => field.fieldname === "from_date") && filters.from_date && filters.to_date && filters.from_date > filters.to_date) {
		filterError.value = "From Date cannot be after To Date."
		return
	}
	await generateReport({ ...filters })
}
function reset() {
	Object.assign(filters, defaults())
	filterError.value = ""
	clear()
}
watch(filters, () => filtersChanged({ ...filters }), { deep: true })
watch(activeFilters, request => { if (request) Object.assign(filters, request) }, { flush: "sync" })
watch(() => props.supplier, () => reset())
watch(() => route.query, () => reset(), { deep: true })
onMounted(() => {
	if (Object.keys(deskReportQueryFilters(props.reportKey, route.query)).length) reset()
	loadLayout()
})
</script>

<style scoped>
.desk-report-field { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 680; }
.desk-report-check { display: flex; align-items: center; gap: 8px; font-size: var(--erp-font-size-caption); }
.desk-report-table { width: max-content; min-width: 100%; }
.desk-report-table td { white-space: pre-line; }
.desk-report-table .desk-report-cell--success { color: var(--erp-success-text); font-weight: 650; }
.desk-report-table .desk-report-cell--danger { color: var(--erp-danger); font-weight: 650; }
.desk-report-table .desk-report-cell--warning { color: var(--erp-warning); font-weight: 650; }
</style>

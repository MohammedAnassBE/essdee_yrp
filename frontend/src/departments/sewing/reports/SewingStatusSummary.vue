<template>
	<section data-sewing-report="status-summary" aria-label="Status Summary">
		<ReportShell :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="Status Summary" :loading="loading" :generated="generated" :has-results="visible.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<MultiSelectField v-for="field in identities" :key="field.key" :input-id="`status-${field.key}`" v-model="filters[field.key]" :options="options(field.key)" :label="field.label" :aria-label="field.label" :placeholder="`All ${field.label}s`" :max-selected-labels="1" display="comma" />
				<DateField v-model="filters.fromDate" label="Input From Date" show-clear />
				<DateField v-model="filters.toDate" label="Input To Date" show-clear />
			</template>
			<template #metrics><div class="report-metric"><i class="pi pi-list" /><div><span>Visible rows</span><strong>{{ visible.length }}</strong></div></div></template>
			<SewingReportMatrix label="Status Summary quantities and readiness" :columns="columns" :rows="visible" :totals="totals" total-label="Visible total" inline-filters />
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingStatusSummary } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), loading = ref(false), generated = ref(false), error = ref("")
let mounted = true
const identities = [{ key: "lot", label: "Lot" }, { key: "item", label: "Item" }, { key: "colour", label: "Colour" }, { key: "part", label: "Part" }]
const identityKeys = { Item: "item", "SD YRP Lot": "lot", Colour: "colour", Part: "part" }
const dateColumns = new Set(["FI Date", "Input Date", "Last Sewing Output"])
const frozenWidths = { Item: 224, "SD YRP Lot": 120, Colour: 128, Part: 76, "FI Date": 104, "Input Date": 104, "Last Sewing Output": 108, "Total Running Days": 80 }
const rows = computed(() => (data.value.data || []).filter(row => !row.is_total))
const columns = computed(() => [
	...(data.value.header1 || []).map(label => ({ key: identityKeys[label] || label, label, frozen: true, width: frozenWidths[label], numeric: label === "Total Running Days", fieldtype: dateColumns.has(label) ? "Date" : undefined })),
	...(data.value.header2 || []).map(label => ({ key: label, label, numeric: true })),
	...(data.value.header3 || []).map(label => ({ key: label === "Work Order Status" ? "work_order_status" : label, label })),
])
function options(key) {
	const descriptions = new Map()
	for (const row of rows.value) if (row[key] != null && row[key] !== "" && !descriptions.has(row[key])) descriptions.set(row[key], key === "lot" ? row.item || "" : "")
	return [...descriptions].map(([value, description]) => ({ label: value, value, description }))
}
const visible = computed(() => rows.value.filter(row => identities.every(({ key }) => !props.filters[key].length || props.filters[key].includes(row[key]))
	&& (!props.filters.fromDate || (row.input_date || row["Input Date"] || "") >= props.filters.fromDate)
	&& (!props.filters.toDate || Boolean(row.input_date || row["Input Date"]) && (row.input_date || row["Input Date"]) <= props.filters.toDate)))
// The only client arithmetic is summing authoritative numeric cells for the
// visible rows. Stage balances/readiness/dates are never derived here.
const totals = computed(() => Object.fromEntries((data.value.header2 || []).map(key => [key, visible.value.reduce((sum, row) => sum + Number(row[key] || 0), 0)])))
async function load() {
	if (loading.value || !supplier.value) return
	if (props.filters.fromDate && props.filters.toDate && props.filters.fromDate > props.filters.toDate) { error.value = "Input From Date cannot be after Input To Date."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const result = await getSewingStatusSummary(supplier.value)
		if (mounted && isCurrent(generation)) { data.value = result || {}; generated.value = true }
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to load Status Summary."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function reset() { Object.assign(props.filters, { lot: [], item: [], colour: [], part: [], fromDate: "", toDate: "" }) }
watch(supplier, load, { immediate: true })
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

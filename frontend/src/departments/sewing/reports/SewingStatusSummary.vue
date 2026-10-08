<template>
	<section data-sewing-report="status-summary" aria-label="Status Summary">
		<ReportShell title="Status Summary" :loading="loading" :generated="generated" :has-results="visible.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<div v-for="field in identities" :key="field.key" class="common-field">
					<label :for="`status-${field.key}`">{{ field.label }}</label>
					<MultiSelect :input-id="`status-${field.key}`" v-model="filters[field.key]" :options="options(field.key)" :aria-label="field.label" :placeholder="`All ${field.label}s`" :max-selected-labels="1" filter fluid />
				</div>
				<DateField v-model="filters.fromDate" label="Input From Date" show-clear />
				<DateField v-model="filters.toDate" label="Input To Date" show-clear />
			</template>
			<template #metrics><div class="report-metric"><i class="pi pi-list" /><div><span>Visible rows</span><strong>{{ visible.length }}</strong></div></div></template>
			<SewingReportMatrix label="Status Summary quantities and readiness" :columns="columns" :rows="visible" :totals="totals" total-label="Visible total" />
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import MultiSelect from "primevue/multiselect"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingStatusSummary } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
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
const rows = computed(() => (data.value.data || []).filter(row => !row.is_total))
const columns = computed(() => [
	...(data.value.header1 || []).map(label => ({ key: identityKeys[label] || label, label })),
	...(data.value.header2 || []).map(label => ({ key: label, label, numeric: true })),
	...(data.value.header3 || []).map(label => ({ key: label, label })),
])
function options(key) { return [...new Set(rows.value.map(row => row[key]).filter(value => value != null && value !== ""))] }
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

<template>
	<section data-sewing-report="monthly-summary" aria-label="Monthly Summary">
		<ReportShell :actions="[{ label: 'Print', icon: 'pi pi-print', visible: generated && data.rows?.length > 0 && !loading, command: handlePrint }]" :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="Monthly Summary" :loading="loading" :generated="generated" :has-results="data.rows?.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<DateField v-model="filters.fromDate" label="From Date" :disabled="loading" />
				<DateField v-model="filters.toDate" label="To Date" :disabled="loading" />
				<LinkField v-model="filters.inputType" doctype="SD YRP Sewing Plan Input Type" label="Input Type" :show-open-button="false" show-clear :disabled="loading || filters.showGrn" />
				<div class="common-field monthly-grn"><label for="monthly-grn">GRN mode</label><Checkbox input-id="monthly-grn" v-model="filters.showGrn" binary :disabled="loading" /></div>
			</template>
			<SewingReportMatrix label="Monthly quantities by date and Item / Part" :columns="columns" :rows="data.rows || []" :totals="data.grand_total" total-label="Grand Total" inline-filters />
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingMonthlySummary } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { buildMonthlySummaryPrintUrl } from "../../../utils/sewingPrint.js"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), loading = ref(false), generated = ref(false), error = ref("")
let mounted = true
const columns = computed(() => [
	{ key: "date", label: "Date", fieldtype: "Date" }, ...(data.value.styles || []).map(style => ({ key: style, label: style, numeric: true })), { key: "total", label: "Total", numeric: true },
])
async function load() {
	if (loading.value || !supplier.value) return
	const filters = props.filters
	if (!filters.fromDate || !filters.toDate) { error.value = "Choose From Date and To Date."; return }
	if (filters.fromDate > filters.toDate) { error.value = "From Date cannot be after To Date."; return }
	if (!filters.showGrn && !filters.inputType) { error.value = "Choose an Input Type or enable GRN mode."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const result = await getSewingMonthlySummary(supplier.value, filters)
		if (mounted && isCurrent(generation)) { data.value = result || {}; generated.value = true }
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to generate Monthly Summary."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function handlePrint() {
	const url = buildMonthlySummaryPrintUrl({ supplier: supplier.value, filters: props.filters })
	// noopener keeps the print dialog from freezing this tab.
	window.open(url, "_blank", "noopener")
}
function reset() {
	Object.assign(props.filters, { fromDate: "", toDate: "", inputType: "", showGrn: false })
	data.value = {}; generated.value = false
}
watch(() => [props.filters.fromDate, props.filters.toDate, props.filters.inputType, props.filters.showGrn], () => { data.value = {}; generated.value = false })
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.monthly-grn { display: grid; align-content: start; gap: 10px; font-size: var(--erp-font-size-caption); font-weight: 650; }
/* While scrolling, the matrix shrinks to the page; once Copy Report makes it overflow:visible it widens to its table. */
[data-sewing-report="monthly-summary"] :deep(.sewing-report-matrix) { min-width: auto; }
</style>

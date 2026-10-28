<template>
	<section data-sewing-report="dpr" aria-label="DPR">
		<ReportShell :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="DPR" :loading="loading" :generated="generated" :has-results="blockers.length > 0 || sections.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<div class="common-field"><label for="dpr-mode" class="erp-field-label">DPR Mode</label><select class="erp-native-select" id="dpr-mode" v-model="filters.mode" :disabled="loading"><option value="daily">Daily</option><option value="range">Date range</option></select></div>
				<DateField v-if="filters.mode === 'daily'" v-model="filters.date" label="DPR Date" :disabled="loading" />
				<template v-else>
					<DateField v-model="filters.fromDate" label="From Date" :disabled="loading" /><DateField v-model="filters.toDate" label="To Date" :disabled="loading" />
					<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" :search-handler="searchLots" :show-open-button="false" show-clear :disabled="loading" />
					<LinkField v-model="filters.item" doctype="Item" label="Item" :search-handler="searchItems" :show-open-button="false" show-clear :disabled="loading" />
				</template>
				<LinkField v-model="filters.workStation" doctype="YRP Work Station" label="Work Station" :show-open-button="false" show-clear :disabled="loading" />
				<LinkField v-model="filters.inputType" doctype="SD YRP Sewing Plan Input Type" label="Input Type" :filters="inputTypeFilters" :show-open-button="false" show-clear :disabled="loading" />
			</template>
			<template v-if="blockers.length">
				<Message severity="warn" :closable="false">These Lot / Colour combinations are hidden from the DPR because their FI date is not yet updated. Update them in FI Updates.</Message>
				<SewingReportMatrix label="Pending FI: blocking Lots, Colours and Parts" :columns="blockerColumns" :rows="blockers" />
			</template>
			<section v-for="section in sections" :key="section.key" class="dpr-section">
				<header class="dpr-section__header">
					<h2>Daily Production Report · {{ formatDate(section.date) }} · {{ section.stage }}</h2>
					<p class="dpr-section__total"><span>Total Qty</span><strong>{{ section.total.toLocaleString(undefined, { maximumFractionDigits: 3 }) }}</strong></p>
				</header>
				<SewingReportMatrix v-for="table in section.tables" :key="table.lot" :label="`${formatDate(section.date)} ${section.stage} ${table.lot}`" layout-key="dpr-lot" :columns="table.columns" :rows="table.rows">
					<template #cell-remarks="{ row }"><InputText v-model="remarks[`${section.key}|${table.lot}|${row.key}`]" class="dpr-remarks" size="small" :aria-label="`Remarks for ${row.colour} ${row.station}`" placeholder="Remarks" /></template>
				</SewingReportMatrix>
			</section>
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingDpr, getSewingItemSummaryOptions, getSewingSupplierLots } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDate } from "../../../components/reports/reportUtils.js"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"
import { dprSections } from "./sewingReportTables.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, beginRequest, isCurrent } = useSewingContext()
const result = ref({}), loading = ref(false), generated = ref(false), error = ref(""), remarks = ref({})
let mounted = true
const inputTypeFilters = { name: ["!=", "Order Qty"] }
const blockerColumns = [{ key: "lot", label: "Lot" }, { key: "colour", label: "Colour" }, { key: "part", label: "Part" }]
const reports = computed(() => result.value.reports || (result.value.date ? [result.value] : []))
const blockers = computed(() => {
	const entries = [...(result.value.pending_fi || []), ...reports.value.flatMap(report => report.pending_fi || [])]
	return [...new Map(entries.map(row => [JSON.stringify([row.lot, row.colour, row.part]), row])).values()]
})
const sections = computed(() => dprSections(reports.value))
async function searchLots(text) { return getSewingSupplierLots(supplier.value, text) }
async function searchItems(text) {
	const items = (await getSewingItemSummaryOptions(supplier.value))?.items || []
	const query = text.toLowerCase()
	return items.filter(item => item.toLowerCase().includes(query)).slice(0, 20).map(name => ({ name, label: name }))
}
async function load() {
	if (loading.value || !supplier.value) return
	const filters = props.filters
	if (filters.mode === "daily" && !filters.date) { error.value = "Choose a DPR Date."; return }
	if (filters.mode === "range" && !filters.fromDate && !filters.toDate && !filters.lot && !filters.item) { error.value = "Choose a Date Range, Lot, or Item."; return }
	if (filters.mode === "range" && Boolean(filters.fromDate) !== Boolean(filters.toDate)) { error.value = "Choose both From Date and To Date."; return }
	if (filters.mode === "range" && filters.fromDate > filters.toDate) { error.value = "From Date cannot be after To Date."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const data = await getSewingDpr(supplier.value, filters)
		if (mounted && isCurrent(generation)) { result.value = data || {}; remarks.value = {}; generated.value = true }
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to generate DPR."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function reset() { Object.assign(props.filters, { mode: "daily", date: "", fromDate: "", toDate: "", workStation: "", inputType: "", lot: "", item: "" }) }
watch(() => [props.filters.mode, props.filters.date, props.filters.fromDate, props.filters.toDate, props.filters.workStation, props.filters.inputType, props.filters.lot, props.filters.item], () => { generated.value = false; result.value = {} })
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.common-field {
	display: grid;
	gap: 6px;
	min-width: 0;
}

.dpr-section { display: grid; min-width: 0; gap: 12px; }
.dpr-section__header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.dpr-section__total { display: grid; justify-items: end; margin: 0; }
.dpr-section__total span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.dpr-section__total strong { color: var(--erp-accent); font-size: 20px; font-variant-numeric: tabular-nums; }
.dpr-remarks { min-width: 120px; }
h2 { margin: 0; color: var(--erp-text); font-size: 15px; overflow-wrap: anywhere; }
</style>

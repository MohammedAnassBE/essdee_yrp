<template>
	<section data-sewing-report="item-summary" aria-label="Item Summary">
		<ReportShell :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="Item Summary" :loading="loading || optionsLoading" :generated="generated" :has-results="data.groups?.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<MultiSelectField input-id="item-summary-lots" v-model="filters.lots" :options="lotOptions" label="Lot" aria-label="Lot" placeholder="Choose Lots" :max-selected-labels="1" display="comma" :disabled="loading || optionsLoading || !optionsReady" />
				<div class="common-field"><label for="item-summary-items">Item</label><MultiSelect input-id="item-summary-items" v-model="filters.items" :options="options.items" aria-label="Item" placeholder="Choose Items" :max-selected-labels="1" filter fluid :disabled="loading || optionsLoading || !optionsReady" /></div>
			</template>
			<article v-for="(group, index) in data.groups || []" :key="index" class="item-summary-group">
				<h2>{{ group.item }} · {{ group.lot }}</h2>
				<SewingReportMatrix :label="`${group.item} ${group.lot} quantities by date and input stage`" :columns="columns(group)" :rows="rows(group)" />
			</article>
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import MultiSelect from "primevue/multiselect"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingItemSummary, getSewingItemSummaryOptions } from "../../../api/sewing.js"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), options = ref({ lots: [], items: [], lotItems: {} }), loading = ref(false), optionsLoading = ref(false), optionsReady = ref(false), generated = ref(false), error = ref("")
let mounted = true, optionsSequence = 0
const lotOptions = computed(() => options.value.lots.map(lot => ({ label: lot, value: lot, description: options.value.lotItems[lot] || "" })))
function columns(group) {
	return [
		{ key: "date", label: "Date" }, { key: "input_type", label: "Input Type" }, { key: "work_station", label: "Work Station" }, { key: "colour", label: "Colour" },
		...(group.has_part ? [{ key: "part", label: "Part" }] : []),
		...(group.headers || []).map(size => ({ key: `size:${size}`, label: size, numeric: true })), { key: "total", label: "Total", numeric: true },
	]
}
// Map cells for presentation only; grouping, order and totals are server-owned.
function rows(group) { return (group.rows || []).map(row => ({ ...row, ...Object.fromEntries(Object.entries(row.values || {}).map(([size, value]) => [`size:${size}`, value])) })) }
async function loadOptions() {
	const unit = supplier.value, generation = requestGeneration.value, sequence = ++optionsSequence
	optionsReady.value = false; optionsLoading.value = true; error.value = ""
	options.value = { lots: [], items: [], lotItems: {} }
	const current = () => mounted && unit === supplier.value && isCurrent(generation) && sequence === optionsSequence
	try {
		const result = await getSewingItemSummaryOptions(unit)
		if (!current()) return
		options.value = { lots: result?.lots || [], items: result?.items || [], lotItems: result?.lot_items || {} }
		props.filters.lots = props.filters.lots.filter(lot => options.value.lots.includes(lot))
		props.filters.items = props.filters.items.filter(item => options.value.items.includes(item))
		optionsReady.value = true
	} catch (reason) {
		if (current()) error.value = reason.message || "Unable to load Item Summary options."
	} finally { if (current()) optionsLoading.value = false }
}
async function generate() {
	if (loading.value || optionsLoading.value || !supplier.value) return
	// Generate also retries a failed options request, without fetching the report.
	if (!optionsReady.value) { await loadOptions(); return }
	if (!props.filters.lots.length && !props.filters.items.length) { error.value = "Select at least one Lot or Item."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const result = await getSewingItemSummary(supplier.value, props.filters)
		if (mounted && isCurrent(generation)) { data.value = result || {}; generated.value = true }
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to generate Item Summary."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function reset() { props.filters.lots = []; props.filters.items = []; data.value = {}; generated.value = false }
watch(() => [props.filters.lots, props.filters.items], () => { data.value = {}; generated.value = false }, { deep: true })
watch(supplier, () => {
	data.value = {}; generated.value = false; loading.value = false
	if (supplier.value) loadOptions()
}, { immediate: true })
onBeforeUnmount(() => { mounted = false; optionsSequence++; beginRequest() })
</script>

<style scoped>
.item-summary-group { display: grid; min-width: 0; gap: 9px; }
h2 { margin: 0; color: var(--erp-text); font-size: 15px; overflow-wrap: anywhere; }
/* While scrolling, the matrix shrinks to the page; once Copy Report makes it overflow:visible it widens to its table. */
.item-summary-group :deep(.sewing-report-matrix) { min-width: auto; }
</style>

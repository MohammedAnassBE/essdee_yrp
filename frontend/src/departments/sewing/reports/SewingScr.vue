<template>
	<section data-sewing-report="scr" aria-label="SCR">
		<ReportShell :export-source="{ doctype: 'SD YRP Sewing Plan' }" title="SCR" :loading="loading" :generated="generated" :has-results="rows.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Choose a Lot" :search-handler="searchLots" :show-open-button="false" show-clear :disabled="loading" />
				<div class="common-field"><label for="scr-colours">Colour</label><MultiSelect input-id="scr-colours" v-model="filters.colours" :options="data.colours || []" aria-label="Colour" placeholder="All Colours" :max-selected-labels="1" filter fluid :disabled="loading" /></div>
			</template>
			<article v-if="rows.length" class="scr-report">
				<header class="scr-heading"><h2>{{ data.item }}</h2><span class="scr-title">SCR</span></header>
				<p>{{ filters.lot }}<span v-if="lines.length"> · {{ lines.join(', ') }}</span></p>
				<SewingReportMatrix :label="`${data.item} SCR quantities by type, colour and size`" :columns="columns" :rows="rows" :cell-tone="tone" />
			</article>
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import MultiSelect from "primevue/multiselect"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingScr, getSewingSupplierLots } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"
import { isNegativeBalance, scrColumns, scrLines, scrRows } from "./sewingReportTables.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), loading = ref(false), generated = ref(false), error = ref("")
let mounted = true, searchSequence = 0
// Cells and type totals, including signed stage balances, come from the server.
const columns = computed(() => scrColumns(data.value))
const rows = computed(() => scrRows(data.value, props.filters.colours))
const lines = computed(() => scrLines(data.value, props.filters.colours))
function tone(row, column) { return (column.numeric && isNegativeBalance(row.type, row[column.key])) ? "negative" : undefined }
async function searchLots(text) {
	const generation = requestGeneration.value, unit = supplier.value, sequence = ++searchSequence
	const rows = await getSewingSupplierLots(unit, text)
	return mounted && !loading.value && unit === supplier.value && isCurrent(generation) && sequence === searchSequence ? rows : []
}
async function load() {
	if (loading.value || !supplier.value) return
	if (!props.filters.lot) { error.value = "Choose a Lot belonging to this Sewing Unit."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const result = await getSewingScr(supplier.value, props.filters.lot)
		if (!mounted || !isCurrent(generation)) return
		if (result?.status === "failed") { error.value = result.message || "Unable to generate SCR for this Lot."; return }
		data.value = result || {}; generated.value = true
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to generate SCR."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function reset() { props.filters.lot = ""; props.filters.colours = [] }
watch(() => props.filters.lot, () => { data.value = {}; generated.value = false; props.filters.colours = [] })
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.scr-report { display: grid; min-width: 0; gap: 9px; }
.scr-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.scr-title { color: var(--erp-text-muted); font-weight: var(--erp-font-weight-bold); }
h2 { margin: 0; color: var(--erp-text); font-size: 15px; overflow-wrap: anywhere; }
p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
</style>

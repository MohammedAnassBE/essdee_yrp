<template>
	<section data-sewing-report="scr" aria-label="SCR">
		<ReportShell title="SCR" :loading="loading" :generated="generated" :has-results="groups.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Choose a Lot" :search-handler="searchLots" :show-open-button="false" show-clear :disabled="loading" />
				<div class="common-field"><label for="scr-colours">Colour</label><MultiSelect input-id="scr-colours" v-model="filters.colours" :options="data.colours || []" aria-label="Colour" placeholder="All Colours" :max-selected-labels="1" filter fluid :disabled="loading" /></div>
			</template>
			<article v-for="group in groups" :key="group.key" class="scr-colour">
				<h2>{{ group.colour }}{{ group.part ? ` · ${group.part}` : '' }}</h2>
				<p>{{ data.item }} · {{ filters.lot }}<span v-if="group.lines?.length"> · {{ group.lines.join(', ') }}</span></p>
				<SewingReportMatrix :label="`${group.colour} recorded quantities by size and input stage`" :columns="columns" :rows="matrixRows(group)" :totals="group.type_wise_total" />
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

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), loading = ref(false), generated = ref(false), error = ref("")
let mounted = true, searchSequence = 0
const columns = computed(() => [{ key: "size", label: "Size" }, ...(data.value.headers || []).map(label => ({ key: label, label, numeric: true }))])
const groups = computed(() => (data.value.colours || Object.keys(data.value.data || {}))
	.filter(key => !props.filters.colours.length || props.filters.colours.includes(key))
	.map(key => ({ ...data.value.data[key], key })))
// Respect primary-value and stage order. All cell/received-type totals come
// directly from the server, including signed configured stage balances.
function matrixRows(group) { return (data.value.primary_values || Object.keys(group.values || {})).map(size => ({ size, ...(group.values?.[size] || {}) })) }
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
.scr-colour { display: grid; min-width: 0; gap: 9px; }
h2 { margin: 0; color: var(--erp-text); font-size: 15px; overflow-wrap: anywhere; }
p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
</style>

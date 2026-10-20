<template>
	<section data-sewing-plan-tab="consumption" class="sewing-consumption" :aria-busy="loading || state.busy" aria-label="Sewing consumption">
		<div class="sewing-consumption__toolbar"><div class="sewing-consumption__filters"><LinkField v-model="state.lot" doctype="SD YRP Lot" label="Lot" placeholder="Select a Lot" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="searchLots" /></div><Button label="Refresh" aria-label="Refresh consumption" icon="pi pi-refresh" severity="secondary" :disabled="!state.lot || loading || state.busy" @click="load()" /><Button label="Print" icon="pi pi-print" severity="secondary" outlined :disabled="!state.data?.ipd || loading || state.busy" @click="handlePrint" /></div>
		<p v-if="!state.lot" class="erp-empty-state">Select a Lot to view consumption mappings.</p>
		<div v-else-if="loading && !state.data" role="status"><p>Loading consumption mappings</p><Skeleton height="160px" /></div>
		<WorkspaceLoadError v-else-if="state.loadError && !state.data" message="Retry to load consumption mappings." @retry="load()" />
		<template v-else-if="state.data">
			<Message v-if="state.loadError" severity="warn" :closable="false">Displayed consumption may be out of date. Your draft is retained. <Button label="Retry" text :disabled="loading || state.busy" @click="load()" /></Message>
			<p v-if="loading" role="status">Refreshing consumption…</p>
			<Message v-if="state.refreshRequired" severity="warn" :closable="false">Consumption was saved. Refresh the mapping before saving again.</Message>
			<div class="sewing-consumption__context"><strong>{{ state.data.ipd }}</strong></div>
			<p v-if="!state.data.sections?.length && !state.data.cloth_acc_data?.length" class="erp-empty-state">No consumption mappings for this Lot.</p>
			<SewingConsumptionTable v-for="(section, index) in state.data.sections || []" :key="index" :label="section.item" :uom="section.item_bom_uom" :columns="section.item_attributes" :rows="section.rows" show-bom values-in-row :disabled="loading || state.busy || state.refreshRequired || !canWrite" @edit="edit(section.rows[$event.index], 'quantity', $event.value)" />
			<template v-for="(group, index) in state.data.cloth_acc_data || []" :key="index">
				<SewingConsumptionTable :label="`Cloth accessories ${index + 1}`" :columns="group.attributes?.filter(attribute => attribute !== 'Consumption Weight')" :rows="group.columns" editable-field="Consumption Weight" :disabled="loading || state.busy || state.refreshRequired || !canWrite" @edit="edit(group.columns[$event.index], 'Consumption Weight', $event.value)" />
			</template>
			<div class="sewing-consumption__actions"><Button label="Save consumption" icon="pi pi-check" :disabled="loading || state.busy || state.refreshRequired || !canWrite || !hasRows" @click="save" /><small v-if="!canWrite">You do not have permission to update consumption.</small></div>
			<Message v-if="success" severity="success" :closable="false" role="status">{{ success }}</Message>
		</template>
		<DocumentErrorDialog :message="error || mutationError" @dismiss="dismissError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { getSewingConsumption, getSewingSupplierLots } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { buildSewingConsumptionPrintUrl } from "../../../utils/sewingPrint.js"
import SewingConsumptionTable from "../components/SewingConsumptionTable.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ state: { type: Object, required: true }, actions: { type: Object, default: () => ({}) }, mutate: { type: Function, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const loading = ref(false), error = ref(""), success = ref("")
const canWrite = computed(() => Boolean(props.actions?.plan?.can_write))
const mutationError = computed(() => props.state.operation?.status === "rejected" && !props.state.operation.acknowledged && matchesOperation(props.state.operation) ? props.state.operation.error : "")
function matchesOperation(operation) { return operation?.supplier === supplier.value && operation.lot === props.state.lot }
let mounted = true, searchSequence = 0
const editableRows = computed(() => [
	...(props.state.data?.sections || []).flatMap(section => (section.rows || []).map(row => ({ row, field: "quantity" }))),
	...(props.state.data?.cloth_acc_data || []).flatMap(group => (group.columns || []).map(row => ({ row, field: "Consumption Weight" }))),
].filter(({ row, field }) => Object.hasOwn(row, field)))
const hasRows = computed(() => editableRows.value.length > 0)
function edit(row, field, value) {
	if (loading.value || props.state.busy || props.state.refreshRequired || !canWrite.value || !Object.hasOwn(row, field)) return
	row[field] = value
	success.value = ""
}
async function searchLots(text) {
	if (!mounted || loading.value || props.state.busy || !supplier.value) return []
	const generation = requestGeneration.value, unit = supplier.value, sequence = ++searchSequence
	const current = () => mounted && !loading.value && !props.state.busy && supplier.value === unit && isCurrent(generation) && sequence === searchSequence
	try {
		const rows = await getSewingSupplierLots(unit, text)
		return current() ? rows : []
	} catch (reason) { if (current()) error.value = reason.message || 'Unable to load consumption Lots.'; return [] }
}
async function load() {
	if (!supplier.value || !props.state.lot) return false
	const generation = beginRequest(), lot = props.state.lot
	loading.value = true; props.state.loadError = ""
	try {
		const data = await getSewingConsumption(supplier.value, lot)
		if (!mounted || !isCurrent(generation) || lot !== props.state.lot) return false
		// Clone the complete JSON response, keeping unknown metadata and ordering.
		// The only draft mutations are returned quantity/Consumption Weight keys.
		props.state.data = JSON.parse(JSON.stringify(data))
		props.state.refreshRequired = false
		return true
	} catch (reason) {
		if (mounted && isCurrent(generation)) { props.state.loadError = reason.message || "Unable to load consumption mappings."; error.value = props.state.loadError }
		return false
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function handlePrint() {
	const url = buildSewingConsumptionPrintUrl({ ipd: props.state.data.ipd, lot: props.state.lot })
	// noopener keeps the print dialog from freezing this tab.
	window.open(url, "_blank", "noopener")
}
function save() {
	if (!supplier.value || !props.state.lot || !props.state.data || !hasRows.value || !canWrite.value || loading.value || props.state.busy || props.state.refreshRequired) return
	if (editableRows.value.some(({ row, field }) => row[field] === "" || !Number.isFinite(Number(row[field])) || Number(row[field]) < 0)) { error.value = "Consumption values must be finite and non-negative."; return }
	const payload = JSON.parse(JSON.stringify(props.state.data))
	error.value = ""; success.value = ""
	props.mutate({ supplier: supplier.value, lot: props.state.lot, sections: payload.sections, cloth_acc_data: payload.cloth_acc_data })
}
function dismissError() {
	error.value = ""
	if (props.state.operation?.status === "rejected" && matchesOperation(props.state.operation)) props.state.operation.acknowledged = true
}
watch(() => props.state.lot, () => {
	beginRequest(); props.state.data = null; props.state.loadError = ""; props.state.refreshRequired = false; success.value = ""; error.value = ""
	if (props.state.lot && !props.state.busy) load()
})
onMounted(() => {
	if (props.state.lot && !props.state.data && !props.state.busy) load()
	watch(() => props.state.busy, async (busy, wasBusy) => {
		const operation = props.state.operation
		if (busy || !wasBusy || operation?.status !== "succeeded" || !matchesOperation(operation)) return
		const refreshed = await load()
		if (mounted && operation.version === props.state.operation?.version && !operation.noticeShown) {
			success.value = refreshed ? "Consumption saved." : "Consumption saved. Refresh the mapping to recover current values."
			operation.noticeShown = true
		}
	})
})
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-consumption { min-width: 0; max-width: 100%; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-consumption__toolbar { display: flex; align-items: flex-end; gap: var(--erp-space-3); margin-bottom: var(--erp-space-3); }
.sewing-consumption__filters { display: grid; width: min(360px, 100%); grid-template-columns: minmax(0, 1fr); }
.sewing-consumption__filters > * { min-width: 0; }
.sewing-consumption__context { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-block: 10px 6px; color: var(--erp-text); font-size: 14px; overflow-wrap: anywhere; }
.sewing-consumption__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding-block: 8px 14px; }
small { color: var(--erp-text-muted); font-size: 11px; }
@media (max-width: 600px) { .sewing-consumption__toolbar { align-items: stretch; flex-direction: column; } .sewing-consumption__toolbar > .p-button { align-self: flex-start; } }
</style>

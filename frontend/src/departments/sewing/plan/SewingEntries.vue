<template>
	<section data-sewing-plan-tab="entries" class="sewing-entries" :aria-busy="loading || state.busy" aria-label="Sewing entries">
		<header><div><h2>Entries</h2><p>Saved inputs grouped by entry date.</p></div><Button label="Refresh" aria-label="Refresh entries" icon="pi pi-refresh" severity="secondary" :disabled="loading || state.busy" @click="load()" /></header>
		<div class="sewing-entries__filters">
			<LinkField v-model="state.filters.workStation" doctype="YRP Work Station" label="Work Station" placeholder="All Work Stations" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('YRP Work Station', text)" />
			<LinkField v-model="state.filters.inputType" doctype="SD YRP Sewing Plan Input Type" label="Input Type" placeholder="All Input Types" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('SD YRP Sewing Plan Input Type', text)" />
			<LinkField v-model="state.filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="All Lots" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('SD YRP Lot', text)" />
		</div>
		<div v-if="loading && !loaded" role="status"><p>Loading entries</p><Skeleton height="160px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" :message="loadError" @retry="load()" />
		<template v-else>
			<Message v-if="loadError" severity="warn" :closable="false">{{ loadError }} <Button label="Retry" text :disabled="loading || state.busy" @click="load()" /></Message>
			<Message v-if="state.refreshRequired" severity="warn" :closable="false">Refresh entries before cancelling another entry.</Message>
			<p v-if="!groups.length" class="erp-empty-state">No entries match these filters.</p>
			<section v-for="group in groups" :key="group.date" :data-entry-date="group.date" class="sewing-entries__date" :aria-label="`Entries on ${group.date}`">
				<h3>{{ group.date }}</h3>
				<article v-for="entry in group.entries" :key="entry.id" :data-entry-id="entry.id" class="sewing-entries__record">
					<div class="sewing-entries__record-heading"><div class="sewing-entries__context"><strong>{{ entry.id }}</strong><span>{{ entry.entry_time }}</span><span>{{ entry.lot }} · {{ entry.item_name }}</span><span>{{ entry.work_station }}</span><span>{{ entry.input_type }} · {{ entry.received_type }}</span></div><Button v-if="entry.is_cancellable" :label="`Cancel ${entry.id}`" severity="danger" outlined :disabled="loading || state.busy || state.refreshRequired" @click="selected = entry.id" /></div>
					<SewingQuantityMatrix :colours="matrix(entry).colours" :model-value="matrix(entry).quantities" :primary-values="entry.primary_values" :label="entry.id" quantity-label="Quantity" :editable="false" />
				</article>
			</section>
			<Message v-if="success" severity="success" :closable="false" role="status">{{ success }}</Message>
		</template>
		<DocumentConfirmationDialog :visible="Boolean(selected)" title="Cancel Sewing entry" :message="`Cancel ${selected}? Saved quantities for this entry will be removed.`" confirm-label="Cancel entry" cancel-label="Keep entry" :busy="state.busy" @update:visible="value => { if (!value && !state.busy) selected = '' }" @confirm="cancel" />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { searchLink } from "../../../api/frappe.js"
import { cancelSewingEntry, getSewingEntries, getSewingSupplierLots } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import SewingQuantityMatrix from "../components/SewingQuantityMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ state: { type: Object, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const records = ref({}), loading = ref(false), loaded = ref(false), loadError = ref(""), error = ref(""), success = ref(""), selected = ref("")
let mounted = true
const searches = new Map()
const groups = computed(() => {
	const dates = new Map()
	for (const [id, entry] of Object.entries(records.value)) {
		if (!dates.has(entry.entry_date)) dates.set(entry.entry_date, [])
		dates.get(entry.entry_date).push({ ...entry, id })
	}
	return [...dates].sort(([a], [b]) => b.localeCompare(a)).map(([date, entries]) => ({ date, entries }))
})
function matrix(entry) {
	const quantities = {}
	const colours = Object.fromEntries(Object.entries(entry.details || {}).map(([key, colour]) => [key, { ...colour, values: Object.fromEntries(Object.entries(colour.values || {}).map(([size, quantity]) => {
		const identity = `${entry.id}:${key}:${size}`
		quantities[identity] = quantity
		return [size, { order_detail: identity }]
	})) }]))
	return { colours, quantities }
}
async function search(doctype, text) {
	if (!mounted || loading.value || props.state.busy || !supplier.value) return []
	const generation = requestGeneration.value, unit = supplier.value, sequence = (searches.get(doctype) || 0) + 1
	searches.set(doctype, sequence)
	const rows = doctype === "SD YRP Lot" ? await getSewingSupplierLots(unit, text) : await searchLink(doctype, text)
	return mounted && !loading.value && !props.state.busy && supplier.value === unit && isCurrent(generation) && searches.get(doctype) === sequence ? rows : []
}
async function load() {
	if (!supplier.value) return false
	const generation = beginRequest()
	loading.value = true; loadError.value = ""
	try {
		const data = await getSewingEntries(supplier.value, props.state.filters)
		if (!mounted || !isCurrent(generation)) return false
		records.value = data || {}; loaded.value = true; props.state.refreshRequired = false
		return true
	} catch (reason) {
		if (mounted && isCurrent(generation)) loadError.value = reason.message || "Unable to load Sewing entries."
		return false
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
async function cancel() {
	if (!selected.value || props.state.busy || loading.value || props.state.refreshRequired || !records.value[selected.value]?.is_cancellable) return
	const id = selected.value, generation = beginRequest()
	props.state.busy = true; error.value = ""; success.value = ""
	try {
		await cancelSewingEntry(id)
		// Even if this tab unmounted during the write, prevent another mutation
		// until the Supplier-keyed shell's next authoritative read succeeds.
		props.state.refreshRequired = true
		if (!mounted || !isCurrent(generation)) return
		selected.value = ""
		const refreshed = await load()
		if (mounted) success.value = refreshed ? "Entry cancelled." : "Entry cancelled. Refresh entries to recover current records."
	} catch (reason) {
		if (mounted && isCurrent(generation)) { selected.value = ""; error.value = reason.message || "Unable to cancel this entry." }
	} finally { props.state.busy = false }
}
onMounted(() => watch(() => [supplier.value, props.state.filters.workStation, props.state.filters.inputType, props.state.filters.lot], () => { if (!props.state.busy) load() }, { immediate: true }))
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-entries { min-width: 0; max-width: 100%; }
header, .sewing-entries__record-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 12px; }
h2, h3 { margin: 0; color: var(--erp-text); font-size: 16px; }
h3 { font-size: 14px; margin-bottom: 10px; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-entries__filters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.sewing-entries__filters > * { min-width: 0; }
.sewing-entries__date { margin-top: 20px; }
.sewing-entries__record { min-width: 0; margin-bottom: 16px; }
.sewing-entries__context { display: flex; flex-wrap: wrap; gap: 6px 14px; min-width: 0; overflow-wrap: anywhere; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
.sewing-entries__record-heading :deep(.p-button) { flex-shrink: 0; }
@media (max-width: 700px) { .sewing-entries__filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sewing-entries__record-heading { align-items: flex-start; flex-direction: column; } }
</style>

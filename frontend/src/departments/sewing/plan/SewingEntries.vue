<template>
	<section data-sewing-plan-tab="entries" class="sewing-entries" :aria-busy="loading || state.busy" aria-label="Sewing entries">
		<div class="sewing-entries__toolbar">
			<div class="sewing-entries__filters">
				<LinkField v-model="state.filters.workStation" doctype="YRP Work Station" label="Work Station" placeholder="All Work Stations" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('YRP Work Station', text)" />
				<LinkField v-model="state.filters.inputType" doctype="SD YRP Sewing Plan Input Type" label="Input Type" placeholder="All Input Types" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('SD YRP Sewing Plan Input Type', text)" />
				<LinkField v-model="state.filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="All Lots" :show-open-button="false" show-clear :disabled="loading || state.busy" :search-handler="text => search('SD YRP Lot', text)" />
			</div>
			<Button label="Refresh" aria-label="Refresh entries" icon="pi pi-refresh" severity="secondary" :disabled="loading || state.busy" @click="load()" />
		</div>
		<div v-if="!loaded && (loading || state.busy)" role="status"><p>{{ state.busy ? 'Cancelling entry' : 'Loading entries' }}</p><Skeleton height="160px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" message="Retry to load Sewing entries." @retry="load()" />
		<template v-else>
			<Message v-if="loadError" severity="warn" :closable="false">Displayed entries may be out of date. <Button label="Retry" text :disabled="loading || state.busy" @click="load()" /></Message>
			<p v-if="loading && loaded" role="status">Refreshing entries…</p>
			<Message v-if="state.refreshRequired" severity="warn" :closable="false">Refresh entries before cancelling another entry.</Message>
			<p v-if="!groups.length" class="erp-empty-state">No entries match these filters.</p>
			<section v-for="group in groups" :key="group.date" :data-entry-date="group.date" class="sewing-entries__date" :aria-label="`Entries on ${formatDisplayDate(group.date)}`">
				<h3>{{ formatDisplayDate(group.date) }}</h3>
				<article v-for="entry in group.entries" :key="entry.id" :data-entry-id="entry.id" class="sewing-entries__record">
					<div class="sewing-entries__record-heading"><div class="sewing-entries__context"><span>{{ entry.entry_time }}</span><span>{{ entry.lot }}</span><span>{{ entry.item_name }}</span><span class="sewing-entries__meta--strong">{{ entry.work_station }}</span><span class="sewing-entries__meta--strong">{{ entry.input_type }}</span><span class="sewing-entries__meta--strong">{{ entry.received_type }}</span></div><Button v-if="entry.is_cancellable" label="Cancel entry" :aria-label="`Cancel entry from ${formatDisplayDate(group.date)} ${entry.entry_time} for ${entry.lot} at ${entry.work_station}`" severity="danger" outlined :disabled="loading || state.busy || state.refreshRequired" @click="selected = entry.id" /></div>
					<SewingQuantityMatrix :colours="matrix(entry).colours" :model-value="matrix(entry).quantities" :primary-values="entry.primary_values" label="Saved Sewing entry" :show-caption="false" quantity-label="Quantity" :editable="false" />
				</article>
			</section>
			<Button v-if="hasMore" label="Load more" severity="secondary" outlined :loading="loading" :disabled="loading || state.busy" @click="load(true)" />
			<Message v-if="success" severity="success" :closable="false" role="status">{{ success }}</Message>
		</template>
		<DocumentConfirmationDialog :visible="Boolean(selected)" title="Cancel Sewing entry" message="Cancel this entry? Its saved quantities will be removed." confirm-label="Cancel entry" cancel-label="Keep entry" :busy="state.busy" @update:visible="value => { if (!value && !state.busy) selected = '' }" @confirm="cancel" />
		<DocumentErrorDialog :message="loadPopup || error" @dismiss="dismissError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { searchLink } from "../../../api/frappe.js"
import { getSewingEntries, getSewingSupplierLots } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import SewingQuantityMatrix from "../components/SewingQuantityMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"

const props = defineProps({ state: { type: Object, required: true }, mutate: { type: Function, required: true } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const records = ref({}), loading = ref(false), loaded = ref(false), loadError = ref(""), success = ref(""), selected = ref("")
const loadPopup = ref("")
const hasMore = ref(false), nextStart = ref(0)
const error = computed(() => props.state.operation?.status === "rejected" && !props.state.operation.acknowledged && props.state.operation.supplier === supplier.value ? props.state.operation.error : "")
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
	const current = () => mounted && !loading.value && !props.state.busy && supplier.value === unit && isCurrent(generation) && searches.get(doctype) === sequence
	try {
		const rows = doctype === "SD YRP Lot" ? await getSewingSupplierLots(unit, text) : await searchLink(doctype, text)
		return current() ? rows : []
	} catch (reason) { if (current()) loadPopup.value = reason.message || 'Unable to load entry filters.'; return [] }
}
async function load(append = false) {
	if (!supplier.value) return false
	const generation = beginRequest()
	loading.value = true; loadError.value = ""
	try {
		const data = await getSewingEntries(supplier.value, props.state.filters, append ? nextStart.value : 0)
		if (!mounted || !isCurrent(generation)) return false
		records.value = append ? { ...records.value, ...data.rows } : data.rows || {}
		hasMore.value = Boolean(data.has_more); nextStart.value = data.next_start || 0
		loaded.value = true; props.state.refreshRequired = false
		return true
	} catch (reason) {
		if (mounted && isCurrent(generation)) { loadError.value = reason.message || "Unable to load Sewing entries."; loadPopup.value = loadError.value }
		return false
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function cancel() {
	if (!selected.value || props.state.busy || loading.value || props.state.refreshRequired || !records.value[selected.value]?.is_cancellable) return
	success.value = ""
	props.mutate(selected.value)
}
function dismissError() {
	// A read failure must not acknowledge a separate, still-unseen write error.
	if (loadPopup.value) loadPopup.value = ''
	else if (props.state.operation?.status === "rejected") props.state.operation.acknowledged = true
}
onMounted(() => watch(() => [supplier.value, props.state.filters.workStation, props.state.filters.inputType, props.state.filters.lot, props.state.busy], async () => {
	if (props.state.busy) return
	selected.value = ""
	records.value = {}; loaded.value = false; hasMore.value = false; nextStart.value = 0
	const operation = props.state.operation
	const refreshed = await load()
	if (mounted && operation?.status === "succeeded" && operation.version === props.state.operation?.version && !operation.noticeShown) {
		success.value = refreshed ? "Entry cancelled." : "Entry cancelled. Refresh entries to recover current records."
		operation.noticeShown = true
	}
}, { immediate: true }))
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-entries { min-width: 0; max-width: 100%; }
.sewing-entries__record-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 10px 12px; border: 1px solid var(--erp-border); border-bottom: 0; border-radius: var(--erp-control-radius) var(--erp-control-radius) 0 0; background: color-mix(in srgb, var(--erp-accent) 4%, var(--erp-surface)); }
h3 { margin: 0 0 8px; color: var(--erp-text); font-size: 15px; font-weight: 720; letter-spacing: -0.01em; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-entries__toolbar { display: flex; align-items: flex-end; gap: var(--erp-space-3); margin-bottom: var(--erp-space-3); }
.sewing-entries__toolbar > .p-button { flex: 0 0 auto; }
.sewing-entries__filters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; min-width: 0; flex: 1; }
.sewing-entries__filters > * { min-width: 0; }
.sewing-entries__date { margin-top: var(--erp-space-4); }
.sewing-entries__record { min-width: 0; margin-bottom: 16px; }
.sewing-entries__context { display: flex; flex-wrap: wrap; gap: 6px 14px; min-width: 0; overflow-wrap: anywhere; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
.sewing-entries__meta--strong { color: var(--erp-text); font-weight: 700; }
.sewing-entries__record :deep(.sewing-quantity-matrix) { border-top-left-radius: 0; border-top-right-radius: 0; }
.sewing-entries__record-heading :deep(.p-button) { flex-shrink: 0; }
@media (max-width: 700px) { .sewing-entries__toolbar { align-items: stretch; flex-direction: column; } .sewing-entries__toolbar > .p-button { align-self: flex-start; } .sewing-entries__filters { width: 100%; grid-template-columns: repeat(2, minmax(0, 1fr)); } .sewing-entries__record-heading { align-items: flex-start; flex-direction: column; } }
</style>

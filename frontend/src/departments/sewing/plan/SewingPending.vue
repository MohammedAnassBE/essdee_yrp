<template>
	<section data-sewing-plan-tab="pending" class="sewing-pending" :aria-busy="loading" aria-label="Sewing pending">
		<div class="sewing-pending__toolbar">
			<div class="sewing-pending__filters">
				<div class="common-field"><label for="sewing-pending-from">From Type</label><Select input-id="sewing-pending-from" v-model="state.filters.fromType" :options="types" aria-label="From Type" placeholder="From Type" :disabled="loading || !types.length" fluid /></div>
				<div class="common-field"><label for="sewing-pending-to">To Type</label><Select input-id="sewing-pending-to" v-model="state.filters.toType" :options="types" aria-label="To Type" placeholder="To Type" :disabled="loading || !types.length" fluid /></div>
				<LinkMultiSelectField v-model="state.filters.lots" doctype="SD YRP Lot" input-id="sewing-pending-lots" label="Lot" aria-label="Lot" placeholder="All Lots" :max-selected-labels="1" display="comma" :disabled="loading" />
				<LinkMultiSelectField v-model="state.filters.items" doctype="Item" input-id="sewing-pending-items" label="Item" aria-label="Item" placeholder="All Items" :max-selected-labels="1" display="comma" :disabled="loading" />
				<LinkField v-model="state.filters.workStation" doctype="YRP Work Station" label="Work Station" :placeholder="lineWise ? 'All Work Stations' : 'Not used with GRN Quantity'" :help-text="lineWise ? '' : 'GRN is recorded per Work Order, not per Work Station.'" :show-open-button="false" show-clear :disabled="loading || !lineWise" />
			</div>
			<Button label="Refresh" aria-label="Refresh pending" icon="pi pi-refresh" severity="secondary" :disabled="loading" @click="load()" />
		</div>
		<p v-if="sameTypes" class="field-error" role="alert">From Type and To Type must be different.</p>
		<div v-else-if="!loaded && loading" role="status"><p>Loading pending quantities</p><Skeleton height="160px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" message="Retry to load Sewing pending quantities." @retry="load()" />
		<template v-else-if="loaded">
			<Message v-if="loadError" severity="warn" :closable="false">Displayed pending quantities may be out of date. <Button label="Retry" text :disabled="loading" @click="load()" /></Message>
			<p v-if="loading" role="status">Refreshing pending quantities…</p>
			<div class="sewing-pending__summary" :aria-label="`${data.from_type} minus ${data.to_type}`">
				<article v-for="card in cards" :key="card.key" class="sewing-pending__card erp-card"><strong>{{ format(data.totals?.[card.key]) }}</strong><span>{{ card.label }}</span></article>
			</div>
			<p v-if="!data.groups?.length" class="erp-empty-state">No pending quantities match these filters.</p>
			<section v-for="group in data.groups" :key="group.work_station" :data-pending-work-station="group.work_station" class="sewing-pending__group" :aria-label="`Pending for ${groupLabel(group)}`">
				<header class="sewing-pending__group-heading"><h3>{{ groupLabel(group) }}</h3><span>{{ data.from_type }} {{ format(group.totals.from_qty) }} · {{ data.to_type }} {{ format(group.totals.to_qty) }} · Pending <b>{{ format(group.totals.pending) }}</b></span></header>
				<article v-for="row in group.rows" :key="rowKey(group, row)" class="sewing-pending__row">
					<button type="button" class="sewing-pending__row-heading" :aria-expanded="Boolean(state.expanded[rowKey(group, row)])" @click="toggle(group, row)">
						<i :class="['pi', state.expanded[rowKey(group, row)] ? 'pi-chevron-down' : 'pi-chevron-right']" aria-hidden="true" />
						<span class="sewing-pending__context"><span class="sewing-pending__meta--strong">{{ row.lot }}</span><span>{{ row.item }}</span><span v-if="row.work_order">{{ row.work_order }}</span></span>
						<span class="sewing-pending__quantities"><span>{{ data.from_type }} {{ format(row.from_qty) }}</span><span>{{ data.to_type }} {{ format(row.to_qty) }}</span><span class="sewing-pending__meta--strong">Pending {{ format(row.pending) }}</span></span>
					</button>
					<SewingReportMatrix v-if="state.expanded[rowKey(group, row)]" :label="`${row.lot} ${row.item} pending by colour and size`" layout-key="sewing-pending-grid" :columns="gridColumns(row)" :rows="gridRows(row)" :totals="gridTotals(row)" />
				</article>
			</section>
		</template>
		<DocumentErrorDialog :message="popup" @dismiss="popup = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { getSewingPending } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import LinkMultiSelectField from "../../../components/common/LinkMultiSelectField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"
import { gridColumns, gridRows, gridTotals, isLineWise, pendingArgs, pendingGroupLabel, pendingRowKey as rowKey } from "./pending.js"

const props = defineProps({ state: { type: Object, required: true } })
const { supplier, beginRequest, isCurrent } = useSewingContext()
const data = ref({}), types = ref([]), loading = ref(false), loaded = ref(false), loadError = ref(""), popup = ref("")
let mounted = true, lastRequest = ""
const lineWise = computed(() => isLineWise(props.state.filters))
const sameTypes = computed(() => Boolean(props.state.filters.fromType) && props.state.filters.fromType === props.state.filters.toType)
const cards = computed(() => [
	{ key: "from_qty", label: data.value.from_type || "From" },
	{ key: "to_qty", label: data.value.to_type || "To" },
	{ key: "pending", label: "Pending" },
])
const format = value => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })
const groupLabel = group => pendingGroupLabel(group, data.value.is_line_wise)
function toggle(group, row) {
	const key = rowKey(group, row)
	props.state.expanded[key] = !props.state.expanded[key]
}
async function load() {
	if (!supplier.value || sameTypes.value) return
	const generation = beginRequest()
	loading.value = true; loadError.value = ""
	try {
		const result = await getSewingPending(pendingArgs(supplier.value, props.state.filters))
		if (!mounted || !isCurrent(generation)) return
		data.value = result || {}
		types.value = result?.types || []
		// The first response fills the default types; that echo is not a new request.
		props.state.filters.fromType = result?.from_type || ""
		props.state.filters.toType = result?.to_type || ""
		lastRequest = JSON.stringify(pendingArgs(supplier.value, props.state.filters))
		loaded.value = true
	} catch (reason) {
		if (mounted && isCurrent(generation)) { loadError.value = reason.message || "Unable to load Sewing pending quantities."; popup.value = loadError.value }
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
watch(lineWise, value => { if (!value) props.state.filters.workStation = "" })
onMounted(() => watch(() => JSON.stringify(pendingArgs(supplier.value, props.state.filters)), request => {
	if (request !== lastRequest) load()
}, { immediate: true }))
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-pending { min-width: 0; max-width: 100%; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-pending__toolbar { display: flex; align-items: flex-end; gap: var(--erp-space-3); margin-bottom: var(--erp-space-3); }
.sewing-pending__toolbar > .p-button { flex: 0 0 auto; }
.sewing-pending__filters { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; min-width: 0; flex: 1; }
.sewing-pending__filters > * { min-width: 0; }
.sewing-pending__summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-3); margin: var(--erp-space-3) 0; }
.sewing-pending__card { display: grid; gap: 3px; padding: var(--erp-space-3) var(--erp-space-4); box-shadow: var(--erp-shadow-xs); }
.sewing-pending__card strong { color: var(--erp-text); font-size: 1.35rem; font-variant-numeric: tabular-nums; line-height: 1; }
.sewing-pending__card span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: var(--erp-font-weight-semibold); }
.sewing-pending__group { margin-top: var(--erp-space-4); }
.sewing-pending__group-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 14px; margin-bottom: 8px; }
.sewing-pending__group-heading span { color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-variant-numeric: tabular-nums; }
h3 { margin: 0; color: var(--erp-text); font-size: 15px; font-weight: 720; letter-spacing: -0.01em; }
.sewing-pending__row { min-width: 0; margin-bottom: 8px; }
.sewing-pending__row-heading { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-accent) 4%, var(--erp-surface)); color: var(--erp-text-secondary); font: inherit; font-size: var(--erp-font-size-caption); text-align: left; cursor: pointer; }
.sewing-pending__row-heading[aria-expanded="true"] { border-bottom-left-radius: 0; border-bottom-right-radius: 0; border-bottom: 0; }
.sewing-pending__row-heading:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
.sewing-pending__context, .sewing-pending__quantities { display: flex; flex-wrap: wrap; gap: 6px 14px; min-width: 0; overflow-wrap: anywhere; }
.sewing-pending__context { flex: 1; }
.sewing-pending__quantities { justify-content: flex-end; font-variant-numeric: tabular-nums; }
.sewing-pending__meta--strong { color: var(--erp-text); font-weight: 700; }
.sewing-pending__row :deep(.sewing-report-matrix) { border-top-left-radius: 0; border-top-right-radius: 0; }
@media (max-width: 900px) { .sewing-pending__filters { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .sewing-pending__toolbar { align-items: stretch; flex-direction: column; } .sewing-pending__toolbar > .p-button { align-self: flex-start; } .sewing-pending__filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sewing-pending__row-heading { align-items: flex-start; flex-wrap: wrap; } .sewing-pending__quantities { justify-content: flex-start; } }
</style>

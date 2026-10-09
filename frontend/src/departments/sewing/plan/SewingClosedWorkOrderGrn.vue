<template>
	<section data-sewing-plan-tab="closed-work-order-grn" class="sewing-closed-grn" :aria-busy="loading || state.busy" aria-label="Closed Work Order receipts">
		<div class="sewing-closed-grn__toolbar"><div class="sewing-closed-grn__picker"><LinkField v-model="state.workOrder" doctype="YRP Work Order" label="Closed Work Order" placeholder="Select a closed Work Order" :show-open-button="false" show-clear :disabled="loading || state.busy || state.refreshRequired" :search-handler="searchOrders" /></div><Button label="Refresh" aria-label="Refresh closed Work Orders" icon="pi pi-refresh" severity="secondary" :disabled="loading || state.busy" @click="refreshOrders" /></div>
		<Message v-if="state.result" severity="success" :closable="false" role="status">{{ state.result.name }} · {{ state.result.docstatus === 1 ? 'Submitted' : `Status ${state.result.docstatus}` }}</Message>
		<Message v-if="state.refreshRequired" severity="warn" :closable="false">Receipt acknowledged. Refresh closed Work Orders before creating another receipt.</Message>
		<Message v-if="state.loadError" severity="warn" :closable="false">Closed Work Order data could not be refreshed. Your draft is retained. <Button label="Retry" text :disabled="loading || state.busy" @click="refreshOrders" /></Message>
		<p v-if="loading && state.data" role="status">Refreshing closed Work Orders…</p>
		<p v-if="!state.workOrder" class="erp-empty-state">Select a closed Work Order to enter a receipt.</p>
		<p v-else-if="loading && !state.data" role="status">Loading closed Work Order quantities</p>
		<template v-else-if="state.data && state.namingField">
			<div class="sewing-closed-grn__context"><strong>{{ state.data.work_order }}</strong><span>{{ state.data.supplier }}</span><span>{{ state.data.lot }}</span><span>{{ state.data.item }}</span><span>{{ state.data.process }}</span></div>
			<p v-if="!state.data.has_pending_items" class="erp-empty-state">No pending receivable quantities for this Work Order.</p>
			<ClosedWorkOrderGrnEditor v-else :groups="state.data.item_details" :values="state.values" :naming-field="state.namingField" :disabled="loading || state.busy || state.refreshRequired || !canCreate" />
			<div class="sewing-closed-grn__actions"><Button label="Create &amp; Submit GRN" icon="pi pi-check" :disabled="loading || state.busy || state.refreshRequired || !canCreate || !state.data.has_pending_items" @click="submit" /><small v-if="!canCreate">Create and Submit permission for Goods Received Note are required.</small></div>
		</template>
		<DocumentErrorDialog :message="error || mutationError" @dismiss="dismissError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { getClosedGrnNamingField, getClosedSewingWorkOrders, getClosedWorkOrderGrnDetails } from "../../../api/sewing.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ClosedWorkOrderGrnEditor from "../components/ClosedWorkOrderGrnEditor.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ state: { type: Object, required: true }, actions: { type: Object, default: () => ({}) }, mutate: { type: Function, required: true } })
const { supplier, beginRequest, isCurrent, requestGeneration } = useSewingContext()
const loading = ref(false), error = ref("")
const canCreate = computed(() => Boolean(props.actions.goods_received_note?.can_create && props.actions.goods_received_note?.can_submit))
const mutationError = computed(() => props.state.operation?.status === "rejected" && !props.state.operation.acknowledged ? props.state.operation.error : "")
let mounted = true, searchSequence = 0

async function searchOrders(text) {
	if (!mounted || loading.value || props.state.busy || props.state.refreshRequired || !supplier.value) return []
	const generation = requestGeneration.value, unit = supplier.value, sequence = ++searchSequence
	const current = () => mounted && supplier.value === unit && isCurrent(generation) && sequence === searchSequence && !props.state.busy && !props.state.refreshRequired
	try {
		const rows = await getClosedSewingWorkOrders(unit, text)
		return current() ? rows : []
	} catch (reason) { if (current()) error.value = reason.message || 'Unable to load closed Work Orders.'; return [] }
}
function initialValues() {
	const now = new Date(), date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
	return { naming_series: props.state.namingField.default || "", posting_date: date, posting_time: now.toTimeString().slice(0, 8), delivery_date: date, supplier_document_date: date, supplier_document_no: "", vehicle_no: "", dc_no: "", comments: "", edit_posting_date_and_time: 1 }
}
async function loadDetails() {
	if (!props.state.workOrder || props.state.busy || props.state.refreshRequired) return
	const generation = beginRequest(), order = props.state.workOrder, unit = supplier.value
	loading.value = true; props.state.loadError = ""
	try {
		const [data, field] = await Promise.all([getClosedWorkOrderGrnDetails(order, unit), props.state.namingField || getClosedGrnNamingField()])
		if (!mounted || !isCurrent(generation) || order !== props.state.workOrder) return
		props.state.namingField = field
		props.state.data = JSON.parse(JSON.stringify(data))
		props.state.values = initialValues()
	} catch (reason) { if (mounted && isCurrent(generation)) { props.state.loadError = reason.message || "Unable to load closed Work Order quantities."; error.value = props.state.loadError } }
	finally { if (mounted && isCurrent(generation)) loading.value = false }
}
async function refreshOrders() {
	if (!supplier.value || props.state.busy || loading.value) return
	const generation = beginRequest(), unit = supplier.value
	loading.value = true; props.state.loadError = ""
	try {
		await getClosedSewingWorkOrders(unit)
		if (!mounted || !isCurrent(generation)) return
		props.state.refreshRequired = false
	} catch (reason) { if (mounted && isCurrent(generation)) { props.state.loadError = reason.message || "Unable to reload closed Work Orders."; error.value = props.state.loadError } }
	finally { if (mounted && isCurrent(generation)) loading.value = false }
	if (mounted && isCurrent(generation) && !props.state.loadError && props.state.workOrder && !props.state.data) await loadDetails()
}
function submit() {
	if (!canCreate.value || loading.value || props.state.busy || props.state.refreshRequired || !props.state.data?.has_pending_items) return
	const required = ['naming_series', 'posting_date', 'posting_time', 'delivery_date', 'supplier_document_no', 'supplier_document_date', 'vehicle_no']
	if (required.some(key => !String(props.state.values[key] ?? "").trim())) { error.value = "Complete the required receipt fields."; return }
	const cells = props.state.data.item_details.flatMap(group => group.items.flatMap(row => Object.values(row.values || {})))
	if (cells.some(cell => !Number.isFinite(Number(cell.qty)) || Number(cell.qty) < 0) || !cells.some(cell => Number(cell.qty) > 0)) { error.value = "Enter a finite, non-negative quantity and receive at least one item."; return }
	// F16 ungrouping requires the returned logical Item name/attribute structure.
	// These identify cells only; the service rebuilds every stock field under lock.
	const itemDetails = props.state.data.item_details.map(group => ({ items: group.items.map(row => ({
		name: row.name, attributes: row.attributes, primary_attribute: row.primary_attribute,
		dimensions: { received_type: row.dimensions?.received_type },
		values: Object.fromEntries(Object.entries(row.values || {}).map(([key, cell]) => [key, { qty: Number(cell.qty || 0), ref_doctype: cell.ref_doctype, ref_docname: cell.ref_docname }])),
	})) }))
	error.value = ""
	props.mutate({ work_order: props.state.workOrder, supplier: supplier.value, values: { ...props.state.values }, item_details: itemDetails })
}
function dismissError() { error.value = ""; if (props.state.operation?.status === "rejected") props.state.operation.acknowledged = true }
watch(() => props.state.workOrder, () => {
	beginRequest(); props.state.data = null; props.state.loadError = ""; error.value = ""
	if (props.state.workOrder && !props.state.busy && !props.state.refreshRequired) loadDetails()
})
onMounted(() => {
	if (props.state.workOrder && !props.state.data && !props.state.busy && !props.state.refreshRequired) loadDetails()
	watch(() => props.state.busy, (busy, wasBusy) => { if (!busy && wasBusy && props.state.operation?.status === "succeeded") refreshOrders() })
})
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-closed-grn { min-width: 0; max-width: 100%; }
.sewing-closed-grn__toolbar { display: flex; align-items: flex-end; gap: var(--erp-space-3); margin-bottom: var(--erp-space-3); }
p, small { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
p { margin: 5px 0 0; }
.sewing-closed-grn__picker { width: min(420px, 100%); }
.sewing-closed-grn__context { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-block: 16px 6px; font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
.sewing-closed-grn__actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding-block: 6px 14px; }
.p-message { margin-bottom: 12px; }
@media (max-width: 600px) { .sewing-closed-grn__toolbar { align-items: stretch; flex-direction: column; } .sewing-closed-grn__toolbar > .p-button { align-self: flex-start; } }
</style>

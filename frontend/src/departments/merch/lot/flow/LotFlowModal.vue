<template>
	<Dialog :visible="visible" modal dismissable-mask :draggable="false" class="pf-modal" @update:visible="emit('update:visible', $event)">
		<template #header>
			<div v-if="view" class="pf-modal__header">
				<div class="pf-modal__heading">
					<div class="pf-modal__title">
						<h2>{{ isStep ? view.node.process : view.workOrder.name }}</h2>
						<LotFlowStatus v-if="isStep" :status="view.node.status" chip />
						<DocumentStatusBadge v-else :docstatus="view.workOrder.docstatus" :label="view.workOrder.status" />
					</div>
					<p>
						<template v-for="(part, index) in subtitle" :key="index">
							<span v-if="index"> · </span><strong v-if="index === 1">{{ part }}</strong><template v-else>{{ part }}</template>
						</template>
					</p>
				</div>
				<div class="pf-modal__actions">
					<LotFlowReports :reports="reports" :lot="lot" :process="isStep ? view.node.process : view.workOrder.process_name" />
					<a v-if="target" class="pf-modal__open" :href="workOrderHref(target)" target="_blank" rel="noopener">Open {{ target.target.label }} <i class="pi pi-external-link" aria-hidden="true" /></a>
				</div>
			</div>
		</template>
		<div v-if="loading" class="pf-modal__loading" aria-live="polite">
			<p class="pf-modal__none"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Loading…</p>
			<Skeleton v-for="index in 4" :key="index" height="2.5rem" />
		</div>
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<template v-else-if="detail && isStep">
			<div v-if="!detail.work_orders.length" class="pf-empty-panel">
				<i class="pi pi-inbox" aria-hidden="true" />
				<div><strong>No Work Order yet</strong><span>Nothing has been sent for {{ view.node.process }}. The planned quantities by size are below.</span></div>
			</div>
			<div class="pf-stats">
				<div v-for="meter in view.node.meters" :key="meter.kind" class="pf-stat" :class="meter.kind === 'Delivered' ? '' : tone(statusTone(meter.value, meter.total))">
					<span>{{ meter.kind }}</span><b>{{ formatNumber(meter.value) }} <small>/ {{ formatNumber(meter.total) }} {{ meter.uom }}</small></b><i>{{ meter.label }}</i>
				</div>
				<template v-if="detail.work_orders.length">
					<div class="pf-stat"><span>First DC</span><b>{{ formatDisplayDate(stepDates.firstDc) }}</b></div>
					<div class="pf-stat"><span>Last GRN</span><b>{{ formatDisplayDate(stepDates.lastGrn) }}</b></div>
				</template>
			</div>
			<LotWorkOrderBreakdown v-if="detail.work_orders.length" :work-orders="detail.work_orders" :cloth="detail.cloth" @open="emit('open-work-order', $event)" />
			<h3 class="pf-modal__h">{{ detail.work_orders.length > 1 ? "All Work Orders combined · by size" : detail.work_orders.length ? "By size" : "Planned by size" }}</h3>
			<LotStepTables :kind="view.node.kind" :sizes="detail.sizes" :grid="detail.grid" :cloth="detail.cloth" :packing="detail.packing" :has-orders="detail.work_orders.some((row) => row.docstatus === 1)" />
			<template v-if="detail.work_orders.length">
				<h3 class="pf-modal__h">Documents</h3>
				<LotFlowDocuments :groups="detail.documents" :packing="detail.packing" />
			</template>
		</template>
		<template v-else-if="detail">
			<LotClothTables v-if="detail.kind === 'cloth'" :cloth="detail.cloth" :work-order="detail.work_order" />
			<template v-else>
				<div class="pf-modal__meta"><span><em>First DC</em>{{ formatDisplayDate(detail.work_order.first_dc) }}</span><span><em>Last GRN</em>{{ formatDisplayDate(detail.work_order.last_grn) }}</span></div>
				<LotStepTables :sizes="detail.sizes" :grid="detail.grid" :cloth="detail.cloth" work-order />
			</template>
			<h3 class="pf-modal__h">Documents</h3>
			<LotFlowDocuments :groups="detail.documents" />
		</template>
	</Dialog>
</template>
<script setup>
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"
import { getLotStepDetail, getLotWorkOrderDetail } from "../../../../api/merch.js"
import DocumentStatusBadge from "../../../../components/documents/DocumentStatusBadge.vue"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import LotClothTables from "./LotClothTables.vue"
import LotFlowDocuments from "./LotFlowDocuments.vue"
import LotFlowReports from "./LotFlowReports.vue"
import LotFlowStatus from "./LotFlowStatus.vue"
import LotStepTables from "./LotStepTables.vue"
import LotWorkOrderBreakdown from "./LotWorkOrderBreakdown.vue"
import { formatNumber, statusTone, workOrderHref } from "./processFlow.js"
/** Centred step or Work Order detail; `view` is `{ node }` for a step or `{ workOrder }` for a Work Order. */
const props = defineProps({
	visible: Boolean,
	view: { type: Object, default: null },
	lot: { type: String, required: true },
	item: { type: String, default: "" },
	reports: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:visible", "open-work-order"])
const detail = ref(null)
const loading = ref(false)
const error = ref("")
let sequence = 0
const isStep = computed(() => Boolean(props.view?.node))
const tone = (value) => (value ? `pf-tone-${value}` : "")
const subtitle = computed(() => {
	if (isStep.value) {
		const count = props.view.node.work_orders.length
		return [props.view.node.stage, count ? `${count} Work Order${count === 1 ? "" : "s"}` : "No Work Order yet", props.item]
	}
	const row = props.view.workOrder
	return [row.process_name, row.supplier_name, row.item]
})
const target = computed(() => {
	if (!isStep.value) return props.view?.workOrder
	return props.view.node.work_orders.length === 1 ? props.view.node.work_orders[0] : null
})
const stepDates = computed(() => {
	const rows = detail.value?.work_orders || []
	const firstDc = rows.map((row) => row.first_dc).filter(Boolean).sort()[0]
	const lastGrn = rows.map((row) => row.last_grn).filter(Boolean).sort().at(-1)
	return { firstDc, lastGrn }
})
async function load() {
	const request = ++sequence
	detail.value = null
	error.value = ""
	loading.value = true
	try {
		const result = isStep.value ? await getLotStepDetail(props.lot, props.view.node.key) : await getLotWorkOrderDetail(props.view.workOrder.name)
		if (request === sequence) detail.value = result
	} catch (reason) {
		if (request === sequence) error.value = reason?.message || "Unable to load this detail."
	} finally {
		if (request === sequence) loading.value = false
	}
}
watch(() => [props.visible, props.view], () => {
	if (props.visible && props.view) load()
}, { immediate: true })
</script>

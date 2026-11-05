<template>
	<div class="pf-root">
		<div v-if="loading" aria-label="Loading process flow"><Skeleton height="64px" /><Skeleton height="220px" class="pf-skeleton" /></div>
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<template v-else-if="flow">
			<section v-if="flow.cloth.length" class="pf-part" aria-label="Cloth process">
				<header class="pf-part__head"><h3>Cloth Process</h3><span>{{ flow.cloth.length }} cloth item{{ flow.cloth.length === 1 ? "" : "s" }} · steps from each fabric IPD</span></header>
				<p class="pf-headline"><strong>{{ clothHeadline(flow.cloth) }}</strong></p>
				<LotClothLanes :lanes="flow.cloth" :fabrics="fabrics" @open-work-order="openWorkOrder" />
				<div class="pf-part-divider" />
			</section>
			<section class="pf-part" aria-label="Item process">
				<header class="pf-part__head"><h3>Item Process</h3><span>Cutting → cut stage → Stitching → piece stage → Packing</span></header>
				<template v-if="flow.items.length">
					<p class="pf-headline"><strong>{{ itemHeadline(flow.items) }}</strong></p>
					<nav class="pf-strip" aria-label="Item process stages">
						<template v-for="(step, index) in flow.items" :key="step.key">
							<i v-if="index" class="pi pi-angle-right pf-strip__sep" aria-hidden="true" />
							<button type="button" class="pf-pill" :class="`pf-pill--${step.status}`" :title="`${step.process}: ${STATUS_LABELS[step.status]}`" @click="jump(step, index)">
								<LotFlowStatus :status="step.status" /><span>{{ step.process }}</span><em>{{ step.status === "idle" ? "—" : `${receivedShare(step)}%` }}</em>
							</button>
						</template>
					</nav>
					<LotItemSteps :steps="flow.items" :lot="lot" :reports="reports" :flash="flash" @open-step="openStep" @open-work-order="openWorkOrder" />
					<div class="pf-legend">
						<span><LotFlowStatus status="done" /> Completed</span><span><LotFlowStatus status="partial" /> Partially completed</span><span><LotFlowStatus status="idle" /> Not started</span>
						<span><i class="pf-bar pf-fill--delivered" /> Delivered</span><span><i class="pf-bar pf-fill--partial" /> Received (colour = step status)</span><span><i class="pf-bar pf-fill--dispatch" /> Dispatch</span>
					</div>
				</template>
				<p v-else class="pf-empty-note">Choose an Item Production Detail to see the item process.</p>
			</section>
		</template>
		<LotFlowModal v-model:visible="modalVisible" :view="view" :lot="lot" :item="item" :reports="reports" @open-work-order="openWorkOrder" />
	</div>
</template>
<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import { getLotProcessFlow, getMerchCapabilities } from "../../../../api/merch.js"
import { merchReportTabs } from "../../../departmentReports.js"
import LotClothLanes from "./LotClothLanes.vue"
import LotFlowModal from "./LotFlowModal.vue"
import LotFlowStatus from "./LotFlowStatus.vue"
import LotItemSteps from "./LotItemSteps.vue"
import { STATUS_LABELS, clothHeadline, itemHeadline, receivedShare } from "./processFlow.js"
import "./processFlow.css"
/** Summary tab process flow: cloth lanes, item steps and the shared detail modal. */
const props = defineProps({
	lot: { type: String, required: true },
	item: { type: String, default: "" },
	fabrics: { type: Array, default: () => [] },
})
const flow = ref(null)
const loading = ref(true)
const error = ref("")
const reports = ref([])
const view = ref(null)
const modalVisible = ref(false)
const flash = ref("")
let sequence = 0
let flashTimer = 0
async function load() {
	const request = ++sequence
	loading.value = true
	error.value = ""
	try {
		const [result, capabilities] = await Promise.all([getLotProcessFlow(props.lot), getMerchCapabilities().catch(() => ({}))])
		if (request !== sequence) return
		flow.value = result
		reports.value = merchReportTabs("merch", capabilities?.reports || {})
	} catch (reason) {
		if (request === sequence) error.value = reason?.message || "Unable to load the process flow."
	} finally {
		if (request === sequence) loading.value = false
	}
}
function openStep(node) {
	view.value = { node }
	modalVisible.value = true
}
function openWorkOrder(workOrder) {
	view.value = { workOrder }
	modalVisible.value = true
}
async function jump(step, index) {
	flash.value = step.key
	await nextTick()
	document.getElementById(`pf-node-${index}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" })
	clearTimeout(flashTimer)
	flashTimer = setTimeout(() => { flash.value = "" }, 1400)
}
watch(() => props.lot, (lot) => lot && load(), { immediate: true })
onBeforeUnmount(() => {
	++sequence
	clearTimeout(flashTimer)
})
</script>

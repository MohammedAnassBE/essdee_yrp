<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		header="Lot OCR Details"
		class="ppo-lot-ocr-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="emit('update:visible', $event)"
	>
		<div v-if="loading" class="ppo-lot-ocr__state" role="status">
			<i class="pi pi-spin pi-spinner" aria-hidden="true" />
			<strong>Loading Lot movement details…</strong>
		</div>
		<div v-else-if="error" class="ppo-lot-ocr__state ppo-lot-ocr__state--error" role="alert">
			<i class="pi pi-exclamation-circle" aria-hidden="true" />
			<strong>{{ error }}</strong>
			<Button label="Retry" icon="pi pi-refresh" severity="secondary" outlined @click="load" />
		</div>
		<div v-else ref="capture" class="ppo-lot-ocr__capture">
			<header class="ppo-lot-ocr__context">
				<div><span>Lot</span><strong>{{ context.lot || lot }}</strong></div>
				<div><span>Production Order</span><strong>{{ context.production_order || productionOrder }}</strong></div>
				<div><span>Item</span><strong>{{ context.item || item || "—" }}</strong></div>
			</header>

			<div class="ppo-lot-ocr__table-wrap" tabindex="0" role="region" aria-label="Lot OCR process quantities">
				<table>
					<thead>
						<tr><th>S.No</th><th>Process</th><th>Documents</th><th>Type</th><th v-for="size in sizes" :key="size">{{ size }}</th><th>Total</th></tr>
					</thead>
					<tbody>
						<template v-for="(process, processIndex) in processRows" :key="process.name">
							<tr class="ppo-lot-ocr__process-start">
								<td rowspan="3" class="ppo-lot-ocr__serial">{{ processIndex + 1 }}</td>
								<th rowspan="3" class="ppo-lot-ocr__process">{{ process.name }}</th>
								<td rowspan="3" class="ppo-lot-ocr__documents">
									<div v-if="process.wo_list.length"><span>Work Orders</span><strong v-for="document in process.wo_list" :key="document">{{ document }}</strong></div>
									<div v-if="process.cp_list.length"><span>Cutting Plans</span><strong v-for="document in process.cp_list" :key="document">{{ document }}</strong></div>
									<em v-if="!process.wo_list.length && !process.cp_list.length">—</em>
								</td>
								<th>Sent</th>
								<td v-for="size in sizes" :key="`${process.name}-sent-${size}`">{{ formatNumber(quantity(process, size, "sent")) }}</td>
								<td class="ppo-lot-ocr__total">{{ formatNumber(process.total_sent) }}</td>
							</tr>
							<tr>
								<th>Received</th>
								<td v-for="size in sizes" :key="`${process.name}-received-${size}`">{{ formatNumber(quantity(process, size, "received")) }}</td>
								<td class="ppo-lot-ocr__total">{{ formatNumber(process.total_received) }}</td>
							</tr>
							<tr class="ppo-lot-ocr__difference">
								<th>Difference</th>
								<td v-for="size in sizes" :key="`${process.name}-difference-${size}`" :class="differenceClass(difference(process, size))">{{ signedNumber(difference(process, size)) }}</td>
								<td class="ppo-lot-ocr__total" :class="differenceClass(totalDifference(process))">{{ signedNumber(totalDifference(process)) }}</td>
							</tr>
						</template>
						<tr v-if="!processRows.length" class="ppo-lot-ocr__empty"><td :colspan="sizes.length + 5">No submitted Work Order movement is available for this Lot.</td></tr>
						<tr class="ppo-lot-ocr__dispatch">
							<td>—</td><th>Dispatch</th>
							<td class="ppo-lot-ocr__documents"><div v-if="finishingPlans.length"><span>Finishing Plans</span><strong v-for="document in finishingPlans" :key="document">{{ document }}</strong></div><em v-else>—</em></td>
							<th>Dispatched</th>
							<td v-for="size in sizes" :key="`dispatch-${size}`">{{ formatNumber(dispatchDetail[size]) }}</td>
							<td class="ppo-lot-ocr__total">{{ formatNumber(payload.total_dispatch) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>

		<Message v-if="copyFeedback" :severity="copyError ? 'error' : 'success'" :closable="false">{{ copyFeedback }}</Message>
		<template #footer>
			<Button label="Close" severity="secondary" text @click="emit('update:visible', false)" />
			<Button label="Copy" icon="pi pi-copy" :loading="copying" :disabled="loading || Boolean(error)" @click="copyDetails" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { computed, ref, watch } from "vue"

import { getLotOcrDetails } from "../../api/sales.js"
import { copyElementAsImage } from "../../components/reports/copyElementAsImage.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	productionOrder: { type: String, default: "" },
	lot: { type: String, default: "" },
	item: { type: String, default: "" },
})
const emit = defineEmits(["update:visible"])
const loading = ref(false)
const error = ref("")
const payload = ref({})
const capture = ref(null)
const copying = ref(false)
const copyFeedback = ref("")
const copyError = ref(false)
let loadSequence = 0

const context = computed(() => payload.value.context || {})
const sizes = computed(() => payload.value.sizes || [])
const processRows = computed(() => Object.entries(payload.value.processes || {}).map(([name, process]) => ({
	name,
	...process,
	wo_list: process?.wo_list || [],
	cp_list: process?.cp_list || [],
	data: process?.data || {},
})))
const dispatchDetail = computed(() => payload.value.dispatch_detail || {})
const finishingPlans = computed(() => payload.value.finishing_plan_list || [])

async function load() {
	if (!props.visible || !props.productionOrder || !props.lot) return
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	payload.value = {}
	copyFeedback.value = ""
	try {
		const result = await getLotOcrDetails(props.productionOrder, props.lot)
		if (sequence === loadSequence) payload.value = result || {}
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load Lot OCR details."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

async function copyDetails() {
	copying.value = true
	copyFeedback.value = ""
	copyError.value = false
	let exportHost = null
	try {
		const source = capture.value
		if (!source) throw new Error("Nothing available to copy.")
		const table = source.querySelector("table")
		const exportWidth = Math.max(source.clientWidth, table?.scrollWidth || 0)
		exportHost = document.createElement("div")
		Object.assign(exportHost.style, { position: "fixed", left: "-100000px", top: "0", pointerEvents: "none" })
		const exportNode = source.cloneNode(true)
		exportNode.dataset.ocrExport = "true"
		Object.assign(exportNode.style, { width: `${exportWidth}px`, maxWidth: "none", overflow: "visible" })
		const exportTableWrap = exportNode.querySelector(".ppo-lot-ocr__table-wrap")
		if (exportTableWrap) Object.assign(exportTableWrap.style, { width: "100%", maxWidth: "none", overflow: "visible" })
		exportHost.appendChild(exportNode)
		document.body.appendChild(exportHost)
		await copyElementAsImage(exportNode)
		copyFeedback.value = "Lot OCR details copied to clipboard."
	} catch (reason) {
		copyError.value = true
		copyFeedback.value = reason?.message || "Unable to copy Lot OCR details."
	} finally {
		exportHost?.remove()
		copying.value = false
	}
}

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function formatNumber(value) { return number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function quantity(process, size, field) { return number(process.data?.[size]?.[field]) }
function difference(process, size) { return quantity(process, size, "received") - quantity(process, size, "sent") }
function totalDifference(process) { return number(process.total_received) - number(process.total_sent) }
function signedNumber(value) { const numeric = number(value); return numeric > 0 ? `+${formatNumber(numeric)}` : formatNumber(numeric) }
function differenceClass(value) { return number(value) < 0 ? "ppo-lot-ocr__negative" : number(value) > 0 ? "ppo-lot-ocr__positive" : "" }

watch(() => [props.visible, props.productionOrder, props.lot], ([visible]) => {
	if (visible) load()
	else { loadSequence += 1; copyFeedback.value = "" }
}, { immediate: true })
</script>

<style scoped>
.ppo-lot-ocr__capture { display: grid; min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.ppo-lot-ocr__context { display: grid; grid-template-columns: .8fr 1fr 1.5fr; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 82%, white); }
.ppo-lot-ocr__context > div { display: grid; min-width: 0; gap: 3px; padding: 11px 13px; border-right: 1px solid var(--erp-border); }
.ppo-lot-ocr__context > div:last-child { border-right: 0; }
.ppo-lot-ocr__context span, .ppo-lot-ocr__documents span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: .045em; text-transform: uppercase; }
.ppo-lot-ocr__context strong { overflow: hidden; color: var(--erp-text); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.ppo-lot-ocr__table-wrap { max-width: 100%; overflow: auto; }
.ppo-lot-ocr__table-wrap:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: -2px; }
.ppo-lot-ocr__table-wrap table { width: 100%; min-width: 820px; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.ppo-lot-ocr__table-wrap th, .ppo-lot-ocr__table-wrap td { height: 39px; padding: 7px 9px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); text-align: right; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.ppo-lot-ocr__table-wrap th:last-child, .ppo-lot-ocr__table-wrap td:last-child { border-right: 0; }
.ppo-lot-ocr__table-wrap thead th { height: 35px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .035em; text-transform: uppercase; background: var(--erp-surface-muted); white-space: nowrap; }
.ppo-lot-ocr__table-wrap thead th:nth-child(-n + 4), .ppo-lot-ocr__process, .ppo-lot-ocr__documents { text-align: left; }
.ppo-lot-ocr__serial { width: 54px; text-align: center !important; }
.ppo-lot-ocr__process { min-width: 135px; color: var(--erp-text) !important; font-weight: 780; vertical-align: top; background: var(--erp-surface-soft); }
.ppo-lot-ocr__documents { min-width: 190px; vertical-align: top; }
.ppo-lot-ocr__documents > div { display: grid; gap: 3px; margin-bottom: 8px; }
.ppo-lot-ocr__documents > div:last-child { margin-bottom: 0; }
.ppo-lot-ocr__documents strong { color: var(--erp-text); font-size: 11px; line-height: 1.35; overflow-wrap: anywhere; }
.ppo-lot-ocr__documents em { color: var(--erp-text-muted); font-style: normal; }
.ppo-lot-ocr__process-start > * { border-top: 2px solid color-mix(in srgb, var(--erp-border-strong) 70%, white); }
.ppo-lot-ocr__difference > * { background: color-mix(in srgb, var(--erp-surface-muted) 56%, white); }
.ppo-lot-ocr__total { color: var(--erp-text) !important; font-weight: 800; background: var(--erp-surface-soft); }
.ppo-lot-ocr__negative { color: var(--erp-danger) !important; font-weight: 780; }
.ppo-lot-ocr__positive { color: var(--erp-success-text) !important; font-weight: 780; }
.ppo-lot-ocr__dispatch > * { color: var(--erp-accent-hover); font-weight: 780; background: color-mix(in srgb, var(--erp-accent-soft) 54%, white); border-top: 2px solid var(--erp-accent-border); }
.ppo-lot-ocr__dispatch > th { text-align: left; }
.ppo-lot-ocr__empty td { height: 90px; color: var(--erp-text-muted); text-align: center; }
.ppo-lot-ocr__state { display: grid; min-height: 260px; gap: 10px; padding: 28px; color: var(--erp-text-muted); text-align: center; place-content: center; justify-items: center; }
.ppo-lot-ocr__state i { color: var(--erp-accent); font-size: 25px; }
.ppo-lot-ocr__state strong { color: var(--erp-text); font-size: 13px; }
.ppo-lot-ocr__state--error i { color: var(--erp-danger); }
@media (max-width: 680px) {
	.ppo-lot-ocr__context { grid-template-columns: 1fr 1fr; }
	.ppo-lot-ocr__context > div:nth-child(2) { border-right: 0; }
	.ppo-lot-ocr__context > div:last-child { grid-column: 1 / -1; border-top: 1px solid var(--erp-border); }
}
</style>

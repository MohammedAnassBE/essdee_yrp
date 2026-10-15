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

			<LotOcrTable :payload="payload" />
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
import LotOcrTable from "./LotOcrTable.vue"

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
.ppo-lot-ocr__context span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: .045em; text-transform: uppercase; }
.ppo-lot-ocr__context strong { overflow: hidden; color: var(--erp-text); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
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

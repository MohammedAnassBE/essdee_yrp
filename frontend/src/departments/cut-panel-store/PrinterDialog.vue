<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="false"
		:closable="!busy"
		:close-on-escape="!busy"
		header="Print Labels"
		class="cut-panel-printer-dialog erp-dialog--sm"
		@update:visible="emit('update:visible', $event)"
	>
		<div class="printer-dialog__content">
			<div v-if="loading" class="printer-dialog__loading"><i class="pi pi-spin pi-spinner" /><span>{{ statusText }}</span></div>
			<template v-else>
				<label><span>Printer *</span><Select v-model="selected" :options="printers" filter fluid placeholder="Select printer" /></label>
				<label v-if="showResolution"><span>Printer Resolution *</span><Select v-model="selectedResolution" :options="resolutions" fluid placeholder="Select resolution" /></label>
				<small v-if="error" role="alert">{{ error }}</small>
			</template>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button v-if="error" label="Retry" icon="pi pi-refresh" severity="secondary" :disabled="loading || busy" @click="loadPrinters" />
			<Button :label="confirmLabel" icon="pi pi-print" :loading="busy" :disabled="loading || !selected || (showResolution && !selectedResolution)" @click="confirm" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"

import { getQzPrinters } from "../../api/qzPrinter.js"

const props = defineProps({
	visible: Boolean,
	busy: Boolean,
	showResolution: { type: Boolean, default: false },
	resolutions: { type: Array, default: () => ["200dpi", "300dpi"] },
	defaultResolution: { type: String, default: "300dpi" },
	filterPrinters: { type: Function, default: null },
	confirmLabel: { type: String, default: "Print" },
})
const emit = defineEmits(["update:visible", "confirm", "error"])
const loading = ref(false)
const printers = ref([])
const selected = ref("")
const selectedResolution = ref("")
const error = ref("")
let loadSequence = 0
const status = ref("connecting")
const STATUS_TEXT = {
	"connecting": "Connecting to QZ Tray… If the browser or QZ Tray asks for permission, click Allow (the QZ Tray window may be behind other windows).",
	"approve-printers": "Finding printers… Approve the QZ Tray prompt on this computer if it asks.",
}
const statusText = computed(() => STATUS_TEXT[status.value] || STATUS_TEXT.connecting)

watch(() => props.visible, (visible) => {
	if (visible) loadPrinters()
	else {
		loadSequence += 1
		loading.value = false
	}
})

async function loadPrinters() {
	const sequence = ++loadSequence
	loading.value = true; error.value = ""; printers.value = []; selected.value = ""; status.value = "connecting"
	selectedResolution.value = props.resolutions.includes(props.defaultResolution) ? props.defaultResolution : props.resolutions[0] || ""
	try {
		const detected = await getQzPrinters({ onStatus: (stage) => { if (sequence === loadSequence) status.value = stage } })
		if (sequence !== loadSequence || !props.visible) return
		const available = props.filterPrinters ? await props.filterPrinters(detected) : detected
		if (sequence !== loadSequence || !props.visible) return
		printers.value = Array.isArray(available) ? available : []
		selected.value = printers.value[0] || ""
		if (!printers.value.length) {
			error.value = props.filterPrinters ? "No configured label printer is available." : "No label printer is available."
			emit("error", error.value)
		}
	} catch (reason) {
		if (sequence !== loadSequence || !props.visible) return
		error.value = reason.message || "Unable to load printers."
		emit("error", error.value)
	}
	finally { if (sequence === loadSequence) loading.value = false }
}

function confirm() {
	emit("confirm", props.showResolution ? { printer: selected.value, printerType: selectedResolution.value } : selected.value)
}
</script>

<style scoped>
.printer-dialog__content { display: grid; min-height: 86px; gap: 12px; }
.printer-dialog__content label { display: grid; gap: 7px; }
.printer-dialog__content label > span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.printer-dialog__content small { color: var(--erp-danger); font-size: var(--erp-font-size-caption); }
.printer-dialog__loading { display: flex; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>

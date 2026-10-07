<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="false"
		:closable="!busy"
		header="Print Labels"
		class="cut-panel-printer-dialog"
		:style="{ width: 'min(520px, calc(100vw - 24px))' }"
		@update:visible="emit('update:visible', $event)"
	>
		<div class="printer-dialog__content">
			<div v-if="loading" class="printer-dialog__loading"><i class="pi pi-spin pi-spinner" /><span>Connecting to QZ Tray and finding printers…</span></div>
			<template v-else>
				<label><span>Printer *</span><Select v-model="selected" :options="printers" filter fluid placeholder="Select printer" /></label>
				<small v-if="error" role="alert">{{ error }}</small>
			</template>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Print" icon="pi pi-print" :loading="busy" :disabled="loading || !selected" @click="emit('confirm', selected)" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import { ref, watch } from "vue"

import { getQzPrinters } from "../../api/qzPrinter.js"

const props = defineProps({ visible: Boolean, busy: Boolean })
const emit = defineEmits(["update:visible", "confirm"])
const loading = ref(false)
const printers = ref([])
const selected = ref("")
const error = ref("")

watch(() => props.visible, (visible) => { if (visible) loadPrinters() })

async function loadPrinters() {
	loading.value = true; error.value = ""; printers.value = []; selected.value = ""
	try {
		printers.value = await getQzPrinters()
		selected.value = printers.value[0] || ""
	} catch (reason) { error.value = reason.message || "Unable to load printers." }
	finally { loading.value = false }
}
</script>

<style scoped>
.printer-dialog__content { display: grid; min-height: 86px; gap: 10px; }
.printer-dialog__content label { display: grid; gap: 7px; }
.printer-dialog__content label > span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.printer-dialog__content small { color: var(--p-red-600); font-size: var(--erp-font-size-caption); }
.printer-dialog__loading { display: flex; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>

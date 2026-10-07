<template>
	<Dialog :visible="visible" modal dismissable-mask :header="`Print Labels · ${row?.lot || ''}`" class="bulk-print-dialog" @update:visible="emit('update:visible', $event)">
		<div class="print-form">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div v-if="loading" class="print-loading"><i class="pi pi-spin pi-spinner"></i><span>Checking workflow and finding printers…</span></div>
			<template v-else-if="context && !context.approval_required">
				<label><span>Printer *</span><Select v-model="printer" :options="printers" filter fluid /></label>
				<label><span>Print Order By</span><Select v-model="printOrder" :options="['Panel', 'Bundle No']" fluid /></label>
			</template>
			<Message v-else-if="context?.approval_required" severity="warn" :closable="false">Grammage approval is required. Difference {{ number(context.difference) }} kg exceeds tolerance {{ number(context.tolerance) }} kg.</Message>
		</div>
		<template #footer><Button label="Close" severity="secondary" text :disabled="printing" @click="emit('update:visible', false)" /><Button v-if="context && !context.approval_required" label="Print" icon="pi pi-print" :loading="printing" :disabled="!printer" @click="print" /></template>
	</Dialog>
	<DocumentErrorDialog :message="actionError" title="Labels could not be printed" @dismiss="actionError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Select from "primevue/select"
import { ref, watch } from "vue"

import { completeBulkLabelPrint, getBulkPrintContext, prepareBulkLabels } from "../../../api/cuttingBulkLaySheets.js"
import { getQzPrinters, printQzRaw } from "../../../api/qzPrinter.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({ visible: Boolean, bulkName: { type: String, required: true }, row: { type: Object, default: null } })
const emit = defineEmits(["update:visible", "printed"])
const loading = ref(false)
const printing = ref(false)
const error = ref("")
const actionError = ref("")
const context = ref(null)
const printers = ref([])
const printer = ref("")
const printOrder = ref("Panel")

watch(() => props.visible, async (visible) => {
	if (!visible || !props.row) return
	loading.value = true; error.value = ""; actionError.value = ""; context.value = null; printers.value = []; printer.value = ""
	try {
		context.value = await getBulkPrintContext(props.bulkName, props.row.name)
		if (!context.value?.approval_required) { printers.value = await getQzPrinters(); printer.value = printers.value[0] || "" }
	} catch (reason) { error.value = reason?.message || "Unable to prepare label printing." }
	finally { loading.value = false }
})
async function print() {
	printing.value = true; error.value = ""
	try {
		const result = await prepareBulkLabels(context.value, printOrder.value)
		await printQzRaw(printer.value, result.zpl)
		const payload = await completeBulkLabelPrint(props.bulkName, props.row.name, result.grn)
		emit("printed", payload); emit("update:visible", false)
	} catch (reason) { actionError.value = reason?.message || "Unable to print labels." }
	finally { printing.value = false }
}
function number(value) { return Number(value || 0).toFixed(4) }
</script>

<style scoped>
.print-form { display: grid; width: min(520px, calc(100vw - 64px)); gap: 13px; }.print-form label { display: grid; gap: 6px; }.print-form label span { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 650; }.print-loading { display: flex; min-height: 100px; align-items: center; justify-content: center; gap: 9px; color: var(--erp-text-muted); }
</style>

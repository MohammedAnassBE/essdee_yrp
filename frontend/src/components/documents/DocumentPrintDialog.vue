<template>
	<Dialog :visible="visible" modal :closable="!printing" :close-on-escape="!printing" header="Print document" class="erp-dialog--sm" @update:visible="emit('update:visible', $event)">
		<p v-if="loading" role="status">Loading print options…</p>
		<div v-else-if="loaded" class="document-print-dialog__fields">
			<label>Print Format<Select v-model="format" :options="formats" :disabled="printing" required fluid /></label>
			<label v-if="!isRaw">Letter Head<Select v-model="letterHead" :options="letterHeads" :disabled="printing" show-clear fluid placeholder="No letter head" /></label>
			<label v-if="isRaw">Printer<Select v-model="printer" :options="printers" :loading="loadingPrinters" :disabled="loadingPrinters || printing" required fluid /></label>
		</div>
		<p v-if="error" role="alert">{{ error }}</p>
		<template #footer>
			<Button label="Print" icon="pi pi-print" :loading="loading || printing" :disabled="loading || printing || !loaded || !format || (isRaw && (loadingPrinters || !printer))" @click="print" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"
import { getPrintOptions, getRawPrintCommands } from "../../api/frappe.js"
import { getQzPrinters, printQzRaw } from "../../api/qzPrinter.js"
import { buildPrintUrl, openPrintUrl } from "../../utils/printUrl.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
})
const emit = defineEmits(["update:visible"])
const loading = ref(false)
const loaded = ref(false)
const error = ref("")
const formats = ref([])
const rawFormats = ref([])
const isRaw = computed(() => rawFormats.value.includes(format.value))
const printers = ref([])
const printer = ref("")
const loadingPrinters = ref(false)
const printing = ref(false)
const letterHeads = ref([])
const format = ref("")
const letterHead = ref("")

watch(() => [props.visible, props.doctype, props.name], async ([visible, doctype, name], _old, onCleanup) => {
	let stale = false
	onCleanup(() => { stale = true })
	rawFormats.value = []
	loaded.value = false
	error.value = ""
	loading.value = false
	if (!visible || !name) return
	loading.value = true
	try {
		const options = await getPrintOptions(doctype, name)
		if (stale) return
		formats.value = options.formats
		rawFormats.value = options.raw_formats || []
		letterHeads.value = options.letter_heads
		format.value = options.default_format
		letterHead.value = options.default_letter_head || ""
		loaded.value = true
	} catch (reason) {
		if (!stale) error.value = reason?.message || "Unable to load print options."
	} finally {
		if (!stale) loading.value = false
	}
}, { immediate: true })

watch(() => [props.visible, isRaw.value], async ([visible, raw], _old, onCleanup) => {
	let stale = false
	onCleanup(() => { stale = true })
	printers.value = []; printer.value = ""; loadingPrinters.value = false
	error.value = ""
	if (!visible || !raw) return
	loadingPrinters.value = true
	try {
		const detected = await getQzPrinters()
		if (stale) return
		printers.value = detected
		printer.value = detected[0] || ""
		if (!printer.value) error.value = "No printer is available."
	} catch (reason) {
		if (!stale) error.value = reason?.message || "Unable to load printers."
	} finally {
		if (!stale) loadingPrinters.value = false
	}
})

async function print() {
	if (loading.value || printing.value || !loaded.value || !format.value) return
	if (isRaw.value) {
		if (loadingPrinters.value || !printer.value) return
		printing.value = true; error.value = ""
		try {
			const result = await getRawPrintCommands(props.doctype, props.name, format.value)
			await printQzRaw(printer.value, result.raw_commands)
			emit("update:visible", false)
		} catch (reason) {
			error.value = reason?.message || "Unable to print raw commands."
		} finally { printing.value = false }
		return
	}
	if (!openPrintUrl(buildPrintUrl({ doctype: props.doctype, name: props.name, format: format.value, letterHead: letterHead.value }))) {
		error.value = "Please enable pop-ups to print."
		return
	}
	emit("update:visible", false)
}
</script>

<style scoped>
.document-print-dialog__fields { display: grid; gap: 16px; }
.document-print-dialog__fields label { display: grid; gap: 6px; }
</style>

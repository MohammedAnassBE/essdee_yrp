<template>
	<Dialog :visible="visible" modal :closable="!printing" :close-on-escape="!printing" header="Print document" class="erp-dialog--sm" @update:visible="emit('update:visible', $event)">
		<p v-if="loading" role="status">Loading print options…</p>
		<div v-else-if="loaded" class="document-print-dialog__fields">
			<label>Print Format<Select v-model="format" :options="formats" :disabled="printing" required fluid /></label>
			<label v-if="!isRaw">Letter Head<Select v-model="letterHead" :options="letterHeads" :disabled="printing" show-clear fluid placeholder="No letter head" /></label>
			<template v-if="needsPreparedInput">
				<label>{{ preparer.label }}<InputNumber v-model="preparedInput" input-id="document-print-prepared-input" :use-grouping="false" :max-fraction-digits="0" :required="true" :invalid="Boolean(preparedError)" :disabled="printing" aria-describedby="document-print-prepared-description" fluid /></label>
				<p id="document-print-prepared-description" class="document-print-dialog__hint">{{ preparer.getDescription(preparedSettings) }}<template v-if="preparedError"><br><span role="alert">{{ preparedError }}</span></template></p>
			</template>
			<label v-if="isRaw">Printer<Select v-model="printer" :options="printers" :loading="loadingPrinters" :disabled="loadingPrinters || printing" required fluid /></label>
		</div>
		<p v-if="error" role="alert">{{ error }}</p>
		<template #footer>
			<Button label="Print" icon="pi pi-print" :loading="loading || printing || preparing" :disabled="loading || printing || preparing || !loaded || !format || (isRaw && (loadingPrinters || !printer))" @click="print" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"
import { getPrintOptions, getRawPrintCommands } from "../../api/frappe.js"
import { getQzPrinters, printQzRaw } from "../../api/qzPrinter.js"
import { getPrintPreparer, withPrintParam } from "../../utils/printPreparers.js"
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
const preparer = computed(() => getPrintPreparer(props.doctype, format.value))
const preparing = ref(false)
const preparedSettings = ref(null)
const preparedInput = ref(null)
const preparedError = ref("")
const preparedValue = computed(() => preparer.value && preparedSettings.value ? preparer.value.getValue(preparedSettings.value) : null)
const needsPreparedInput = computed(() => Boolean(preparer.value && preparedSettings.value && preparedValue.value === null))

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

watch(() => [props.visible, props.name, preparer.value], async ([visible, name, activePreparer], _old, onCleanup) => {
	let stale = false
	onCleanup(() => { stale = true })
	preparedSettings.value = null; preparedInput.value = null; preparedError.value = ""; preparing.value = false
	if (!visible || !name || !activePreparer) return
	preparing.value = true
	try {
		const settings = await activePreparer.load(name)
		if (!stale) preparedSettings.value = settings || {}
	} catch (reason) {
		if (!stale) error.value = reason?.message || "Unable to load print settings."
	} finally {
		if (!stale) preparing.value = false
	}
})

function getPreparedUrl(url) {
	if (!preparer.value) return url
	if (!preparedSettings.value) return ""
	if (needsPreparedInput.value) {
		preparedError.value = preparer.value.validate(preparedInput.value)
		if (preparedError.value) return ""
	}
	return withPrintParam(url, preparer.value.param, preparedValue.value ?? preparedInput.value)
}

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
	if (preparing.value) return
	const url = getPreparedUrl(buildPrintUrl({ doctype: props.doctype, name: props.name, format: format.value, letterHead: letterHead.value }))
	if (!url) return
	if (!openPrintUrl(url)) {
		error.value = "Please enable pop-ups to print."
		return
	}
	emit("update:visible", false)
}
</script>

<style scoped>
.document-print-dialog__fields { display: grid; gap: 16px; }
.document-print-dialog__fields label { display: grid; gap: 6px; }
.document-print-dialog__hint { margin: -8px 0 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-sm, 12px); }
</style>

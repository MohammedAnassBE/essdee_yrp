<template>
	<Dialog :visible="visible" modal header="Print document" class="erp-dialog--sm" @update:visible="emit('update:visible', $event)">
		<p v-if="loading" role="status">Loading print options…</p>
		<div v-else-if="loaded" class="document-print-dialog__fields">
			<label>Print Format<Select v-model="format" :options="formats" required fluid /></label>
			<label>Letter Head<Select v-model="letterHead" :options="letterHeads" show-clear fluid placeholder="No letter head" /></label>
		</div>
		<p v-if="error" role="alert">{{ error }}</p>
		<template #footer>
			<Button label="Print" icon="pi pi-print" :loading="loading" :disabled="loading || !loaded || !format" @click="print" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import { ref, watch } from "vue"
import { getPrintOptions } from "../../api/frappe.js"
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
const letterHeads = ref([])
const format = ref("")
const letterHead = ref("")

watch(() => [props.visible, props.doctype, props.name], async ([visible, doctype, name], _old, onCleanup) => {
	let stale = false
	onCleanup(() => { stale = true })
	loaded.value = false
	error.value = ""
	loading.value = false
	if (!visible || !name) return
	loading.value = true
	try {
		const options = await getPrintOptions(doctype, name)
		if (stale) return
		formats.value = options.formats
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

function print() {
	if (loading.value || !loaded.value || !format.value) return
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

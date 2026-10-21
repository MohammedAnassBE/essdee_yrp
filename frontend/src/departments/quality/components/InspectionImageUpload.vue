<template>
	<div class="inspection-upload" :aria-busy="uploading">
		<div class="inspection-upload__actions">
			<Button label="Take photo" icon="pi pi-camera" severity="secondary" :disabled="disabled || uploading" @click="camera?.click()" />
			<Button :label="acceptAny ? 'Choose file' : 'Choose from gallery'" icon="pi pi-upload" severity="secondary" :disabled="disabled || uploading" @click="gallery?.click()" />
			<input ref="camera" type="file" accept="image/*" capture="environment" aria-label="Take photo" :disabled="disabled || uploading" hidden @change="upload" />
			<input ref="gallery" type="file" :accept="acceptAny ? undefined : 'image/*'" :aria-label="acceptAny ? 'Choose file' : 'Choose from gallery'" :disabled="disabled || uploading" hidden @change="upload" />
		</div>
		<div v-if="uploading" role="status" aria-live="polite">
			<progress :value="progress" max="100" :aria-label="`Uploading ${progress}%`" />
			<span>Uploading {{ progress }}%</span>
		</div>
		<div v-if="modelValue" class="inspection-upload__preview">
			<a :href="modelValue" target="_blank" rel="noopener" aria-label="Open uploaded attachment">
				<img v-if="!acceptAny || isImage" :src="modelValue" alt="Quality approval sheet" />
				<span v-else>{{ fileLabel }}</span>
			</a>
			<Button label="Remove" icon="pi pi-times" severity="danger" text :disabled="disabled || uploading" @click="emit('update:modelValue', '')" />
		</div>
		<DocumentErrorDialog :message="error" title="Attachment could not be uploaded" @dismiss="error = ''" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed, onBeforeUnmount, ref } from "vue"
import { uploadFile } from "../../../api/frappe.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { INSPECTION_DOCTYPE } from "../qualityViews.js"

const props = defineProps({
	modelValue: { type: String, default: "" },
	docname: { type: String, default: "" },
	doctype: { type: String, default: INSPECTION_DOCTYPE },
	fieldname: { type: String, default: "upload_quality_approval_sheet" },
	acceptAny: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "uploading-change"])
const camera = ref(null)
const gallery = ref(null)
const uploading = ref(false)
const progress = ref(0)
const error = ref("")
const isImage = computed(() => /\.(avif|webp|png|jpe?g|gif|heic)(?:\?|$)/i.test(props.modelValue))
const fileLabel = computed(() => props.modelValue.split("/").pop())
let controller = null
let active = true

async function upload(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (!file || props.disabled || uploading.value) return
	if (!props.acceptAny && !file.type.startsWith("image/")) {
		error.value = "Choose an image for the approval sheet."
		return
	}
	uploading.value = true
	emit("uploading-change", true)
	progress.value = 0
	error.value = ""
	controller = new AbortController()
	try {
		const result = await uploadFile(file, {
			isPrivate: 0,
			doctype: props.doctype,
			docname: props.docname || undefined,
			fieldname: props.fieldname,
			signal: controller.signal,
			onProgress: (value) => { if (active) progress.value = value },
		})
		if (!active) return
		if (!result.file_url) throw new Error("The upload did not return a file URL.")
		emit("update:modelValue", result.file_url)
	} catch (reason) {
		if (active && reason.name !== "AbortError") error.value = reason?.message || "Unable to upload attachment."
	} finally {
		if (active) {
			uploading.value = false
			emit("uploading-change", false)
		}
	}
}

onBeforeUnmount(() => {
	active = false
	controller?.abort()
})
</script>

<style scoped>
.inspection-upload { display: grid; min-width: 0; gap: var(--erp-space-3); }
.inspection-upload__actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); }
.inspection-upload :deep(.p-button), .inspection-upload a { min-height: 44px; }
.inspection-upload__preview { display: flex; flex-wrap: wrap; align-items: center; gap: var(--erp-space-2); }
.inspection-upload a { color: var(--erp-accent-ink); overflow-wrap: anywhere; }
.inspection-upload img { display: block; width: 160px; max-width: 100%; max-height: 180px; object-fit: contain; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.inspection-upload progress { width: 100%; accent-color: var(--erp-accent); }
.inspection-upload [role="status"] { color: var(--erp-text-secondary); }
@media (max-width: 640px) { .inspection-upload__actions :deep(.p-button) { width: 100%; } }
</style>

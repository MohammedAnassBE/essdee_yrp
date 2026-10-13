<template>
	<Dialog
		:visible="visible"
		modal
		:header="isBox ? 'Upload Product Box Images' : 'Upload Graphic Designs'"
		class="erp-dialog--lg"
		:closable="!processing"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<div class="product-graphics-bulk">
			<p>Review the Upload Type for each image. Files are uploaded one at a time.</p>
			<div class="product-graphics-bulk__rows">
				<article v-for="row in rows" :key="row.id">
					<div class="product-graphics-bulk__preview"><img :src="row.previewUrl" :alt="row.file.name" /></div>
					<label>
						<span>Upload Type</span>
						<InputText v-model="row.uploadType" fluid :disabled="processing || row.status === 'done'" />
					</label>
					<div class="product-graphics-bulk__status">
						<Tag :value="statusLabel(row.status)" :severity="statusSeverity(row.status)" />
						<span>{{ row.message || row.file.name }}</span>
					</div>
				</article>
			</div>
		</div>
		<template #footer>
			<Button :label="hasFinished ? 'Close' : 'Cancel'" severity="secondary" text :disabled="processing" @click="setVisible(false)" />
			<Button label="Upload images" icon="pi pi-upload" :loading="processing" :disabled="processing || !uploadableRows.length" @click="uploadAll" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Tag from "primevue/tag"
import { computed, onBeforeUnmount, ref, watch } from "vue"

import { uploadGraphic } from "../../../api/pd.js"
import { cleanFileStem } from "../pdViews.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	files: { type: Array, default: () => [] },
	docname: { type: String, default: "" },
	isBox: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "operation-started", "operation-finished"])
const rows = ref([])
const processing = ref(false)
const changedSinceOpen = ref(false)
const uploadableRows = computed(() => rows.value.filter((row) => row.status !== "done"))
const hasFinished = computed(() => rows.value.some((row) => ["done", "error"].includes(row.status)))

watch(() => props.visible, (visible) => {
	if (visible) initialise()
})

function initialise() {
	releasePreviews()
	changedSinceOpen.value = false
	rows.value = props.files.map((file, index) => ({
		id: `${index}-${file.name}-${file.lastModified}`,
		file,
		previewUrl: URL.createObjectURL(file),
		uploadType: cleanFileStem(file.name, `Option ${index + 1}`),
		status: "pending",
		message: "",
	}))
}

function setVisible(value) {
	if (!value && processing.value) return
	if (!value) {
		const changed = changedSinceOpen.value
		releasePreviews()
		changedSinceOpen.value = false
		emit("update:visible", false)
		if (changed) emit("operation-finished", true)
		return
	}
	emit("update:visible", value)
}

async function uploadAll() {
	if (processing.value || !props.docname) return
	processing.value = true
	emit("operation-started")
	for (const row of uploadableRows.value) {
		if (!row.uploadType.trim()) {
			row.status = "error"
			row.message = "Upload Type is required."
			continue
		}
		row.status = "uploading"
		row.message = "Uploading…"
		try {
			await uploadGraphic({
				docname: props.docname,
				uploadType: row.uploadType.trim(),
				file: row.file,
				isBox: props.isBox,
			})
			row.status = "done"
			row.message = "Uploaded."
			changedSinceOpen.value = true
		} catch (reason) {
			row.status = "error"
			row.message = reason?.message || "Upload failed."
		}
	}
	processing.value = false
	emit("operation-finished", false)
}

function statusLabel(status) {
	return ({ pending: "Pending", uploading: "Uploading", done: "Done", error: "Error" })[status]
}

function statusSeverity(status) {
	return ({ pending: "secondary", uploading: "info", done: "success", error: "danger" })[status]
}

function releasePreviews() {
	for (const row of rows.value) {
		if (row.previewUrl) URL.revokeObjectURL(row.previewUrl)
	}
	rows.value = []
}

onBeforeUnmount(releasePreviews)
</script>

<style scoped>
.product-graphics-bulk { display: grid; width: min(48rem, 82vw); gap: var(--erp-space-3); }
.product-graphics-bulk > p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.product-graphics-bulk__rows { display: grid; max-height: 55vh; overflow-y: auto; gap: 9px; padding-right: 3px; }
.product-graphics-bulk__rows article { display: grid; grid-template-columns: 100px minmax(0, 1fr) minmax(120px, auto); align-items: center; gap: 12px; padding: 10px; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-graphics-bulk__preview { display: flex; width: 100px; height: 80px; overflow: hidden; align-items: center; justify-content: center; border-radius: 6px; background: white; }
.product-graphics-bulk__preview img { display: block; width: 100%; height: 100%; object-fit: contain; }
.product-graphics-bulk label { display: grid; gap: 6px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.product-graphics-bulk__status { display: grid; justify-items: start; gap: 5px; }
.product-graphics-bulk__status span { max-width: 180px; overflow-wrap: anywhere; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
@media (max-width: 680px) { .product-graphics-bulk { width: min(32rem, 82vw); } .product-graphics-bulk__rows article { grid-template-columns: 80px minmax(0, 1fr); } .product-graphics-bulk__preview { width: 80px; height: 70px; } .product-graphics-bulk__status { grid-column: 1 / -1; } }
</style>

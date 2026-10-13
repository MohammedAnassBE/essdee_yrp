<template>
	<section class="pd-media-panel erp-card" aria-labelledby="product-silhouette-heading">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">Product media</span>
				<h2 id="product-silhouette-heading">Silhouette</h2>
			</div>
		</div>
		<Message v-if="isNew" severity="info" :closable="false">Save the product to upload images.</Message>
		<div class="product-silhouette" :class="{ 'product-silhouette--set': isSetItem }">
			<article v-for="slot in slots" :key="slot.fieldname" class="product-silhouette__slot">
				<h3>{{ slot.label }}</h3>
				<div class="product-silhouette__preview">
					<img v-if="record[slot.fieldname]" :src="record[slot.fieldname]" :alt="slot.label" />
					<div v-else class="pd-media-empty"><i class="pi pi-image" /><span>No image uploaded</span></div>
				</div>
				<div v-if="canChange" class="product-silhouette__actions">
					<Button
						label="Add/Update Image"
						icon="pi pi-image"
						:loading="busyField === `${slot.fieldname}:image`"
						:disabled="controlsDisabled"
						@click="openFilePicker(slot.fieldname, 'image')"
					/>
					<Button
						label="Upload PDF"
						icon="pi pi-file-pdf"
						severity="secondary"
						:loading="busyField === `${slot.fieldname}:pdf`"
						:disabled="controlsDisabled"
						@click="openFilePicker(slot.fieldname, 'pdf')"
					/>
					<input
						:ref="(element) => registerInput(slot.fieldname, 'image', element)"
						class="pd-visually-hidden"
						type="file"
						accept="image/*"
						:disabled="controlsDisabled"
						@change="uploadImage(slot.fieldname, $event)"
					/>
					<input
						:ref="(element) => registerInput(slot.fieldname, 'pdf', element)"
						class="pd-visually-hidden"
						type="file"
						accept=".pdf,application/pdf"
						:disabled="controlsDisabled"
						@change="uploadPdf(slot.fieldname, $event)"
					/>
				</div>
			</article>
		</div>
		<DocumentErrorDialog
			:message="actionError"
			title="Silhouette could not be updated"
			@dismiss="actionError = ''"
		/>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed, ref } from "vue"

import { replaceAttachment, uploadSinglePagePdf } from "../../../api/pd.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, required: true },
	readonly: { type: Boolean, default: false },
	canUpload: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
	isNew: { type: Boolean, default: false },
})

const emit = defineEmits(["operation-started", "operation-finished"])
const fileInputs = new Map()
const busyField = ref("")
const actionError = ref("")
const isSetItem = computed(() => Boolean(Number(props.record.is_set_item)))
const canChange = computed(() => props.canUpload && !props.readonly)
const controlsDisabled = computed(() => props.busy || Boolean(busyField.value))
const slots = computed(() => isSetItem.value
	? [
		{ fieldname: "top_image", label: "Top Silhouette Image" },
		{ fieldname: "bottom_image", label: "Bottom Silhouette Image" },
	]
	: [{ fieldname: "product_image", label: "Product Silhouette Image" }])

function inputKey(fieldname, type) {
	return `${fieldname}:${type}`
}

function registerInput(fieldname, type, element) {
	const key = inputKey(fieldname, type)
	if (element) fileInputs.set(key, element)
	else fileInputs.delete(key)
}

function openFilePicker(fieldname, type) {
	if (!canChange.value || controlsDisabled.value) return
	fileInputs.get(inputKey(fieldname, type))?.click()
}

async function uploadImage(fieldname, event) {
	await runUpload(fieldname, "image", event, (file) => replaceAttachment({
		doctype: props.doctype,
		docname: props.record.name,
		fieldname,
		oldUrl: props.record[fieldname] || null,
		file,
	}))
}

async function uploadPdf(fieldname, event) {
	await runUpload(fieldname, "pdf", event, (file) => uploadSinglePagePdf({
		doctype: props.doctype,
		docname: props.record.name,
		fieldname,
		file,
	}))
}

async function runUpload(fieldname, type, event, upload) {
	const input = event.target
	const file = input.files?.[0]
	if (!file || !canChange.value || controlsDisabled.value) {
		input.value = ""
		return
	}
	busyField.value = inputKey(fieldname, type)
	actionError.value = ""
	emit("operation-started")
	let changed = false
	try {
		await upload(file)
		changed = true
	} catch (reason) {
		actionError.value = reason?.message || "Unable to upload the silhouette."
	} finally {
		input.value = ""
		busyField.value = ""
		emit("operation-finished", changed)
	}
}
</script>

<style scoped>
.pd-media-panel { display: grid; min-width: 0; gap: var(--erp-space-3); padding: var(--erp-space-4); }
.pd-media-panel__heading { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.pd-media-panel__heading > div { display: grid; min-width: 0; gap: 3px; }
.pd-media-panel__heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 760; }
.pd-media-panel__eyebrow { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.04em; text-transform: uppercase; }
.pd-media-empty { display: grid; align-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.pd-media-empty i { font-size: 1.5rem; }
.pd-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; margin: -1px; padding: 0; border: 0; clip: rect(0 0 0 0); white-space: nowrap; }
.product-silhouette { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--erp-space-3); }
.product-silhouette--set { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.product-silhouette__slot { display: grid; min-width: 0; gap: 10px; }
.product-silhouette__slot h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); font-weight: 720; }
.product-silhouette__preview { display: grid; min-height: 250px; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); place-items: center; }
.product-silhouette__preview img { width: 100%; height: 250px; object-fit: contain; background: white; }
.product-silhouette__actions { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 720px) { .product-silhouette--set { grid-template-columns: 1fr; } }
</style>

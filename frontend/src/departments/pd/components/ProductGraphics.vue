<template>
	<section class="pd-media-panel erp-card" :aria-labelledby="headingId">
		<div class="pd-media-panel__heading">
			<div>
				<span class="pd-media-panel__eyebrow">{{ isBox ? "Packaging media" : "Artwork media" }}</span>
				<h2 :id="headingId">{{ title }}</h2>
			</div>
			<span class="pd-media-panel__count">{{ rows.length }} files</span>
		</div>
		<Message v-if="isNew" severity="info" :closable="false">Save the product to upload images.</Message>

		<div v-if="rows.length" class="product-graphics__grid">
			<article v-for="row in rows" :key="row.name || `${row.upload_name}-${row.graphic_image}`" class="product-graphic-card">
				<div class="product-graphic-card__heading">
					<strong>{{ row.upload_name || "Untitled" }}</strong>
					<Button
						v-if="canChange"
						label="Remove"
						icon="pi pi-trash"
						severity="danger"
						text
						:disabled="controlsDisabled"
						@click="askToRemove(row)"
					/>
				</div>
				<div class="product-graphic-card__preview">
					<img v-if="row.graphic_image" :src="row.graphic_image" :alt="row.upload_name || title" />
					<div v-else class="pd-media-empty"><i class="pi pi-image" /><span>No preview</span></div>
				</div>
			</article>
		</div>
		<div v-else class="pd-media-empty pd-media-empty--panel"><i class="pi pi-images" /><span>No {{ title.toLowerCase() }} uploaded</span></div>

		<div v-if="canChange" class="product-graphics__upload">
			<div class="product-graphics__drop" @dragover.prevent @drop.prevent="queueDroppedFiles">
				<i class="pi pi-cloud-upload" />
				<span>Drop several images here</span>
				<Button label="Upload images" icon="pi pi-upload" :disabled="controlsDisabled" @click="imageInput?.click()" />
				<input ref="imageInput" class="pd-visually-hidden" type="file" accept="image/*" multiple :disabled="controlsDisabled" @change="queueChosenFiles" />
			</div>
			<div class="product-graphics__pdf">
				<Button
					label="Upload PDF"
					icon="pi pi-file-pdf"
					severity="secondary"
					:loading="busyAction === 'pdf'"
					:disabled="controlsDisabled"
					@click="pdfInput?.click()"
				/>
				<input ref="pdfInput" class="pd-visually-hidden" type="file" accept=".pdf,application/pdf" :disabled="controlsDisabled" @change="uploadPdf" />
			</div>
		</div>
		<p v-if="busyMessage" class="product-graphics__busy" role="status"><i class="pi pi-spin pi-spinner" /> {{ busyMessage }}</p>

		<DocumentConfirmationDialog
			v-model:visible="removeVisible"
			title="Remove graphic?"
			:message="`Remove ${removeTarget?.upload_name || 'this graphic'}?`"
			confirm-label="Remove"
			confirm-icon="pi pi-trash"
			:busy="controlsDisabled"
			@confirm="confirmRemove"
		/>
		<ProductGraphicsUploadDialog
			v-model:visible="bulkVisible"
			:files="bulkFiles"
			:docname="docname"
			:is-box="isBox"
			@operation-started="emit('operation-started')"
			@operation-finished="emit('operation-finished', $event)"
		/>
		<DocumentErrorDialog :message="actionError" :title="`${title} could not be updated`" @dismiss="actionError = ''" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed, ref } from "vue"

import { removeGraphic, uploadGraphicsPdf } from "../../../api/pd.js"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ProductGraphicsUploadDialog from "./ProductGraphicsUploadDialog.vue"

const props = defineProps({
	docname: { type: String, default: "" },
	rows: { type: Array, default: () => [] },
	isBox: { type: Boolean, default: false },
	isNew: { type: Boolean, default: false },
	readonly: { type: Boolean, default: false },
	canUpload: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["operation-started", "operation-finished"])
const busyAction = ref("")
const actionError = ref("")
const removeVisible = ref(false)
const removeTarget = ref(null)
const imageInput = ref(null)
const pdfInput = ref(null)
const bulkVisible = ref(false)
const bulkFiles = ref([])
const title = computed(() => props.isBox ? "Product Box Details" : "Product Graphics")
const canChange = computed(() => props.canUpload && !props.readonly)
const controlsDisabled = computed(() => props.busy || Boolean(busyAction.value))
const headingId = `product-graphics-${props.isBox ? "box" : "design"}`
const busyMessage = computed(() => ({
	pdf: "Processing PDF and extracting images…",
	remove: "Removing graphic…",
})[busyAction.value] || "")

function queueChosenFiles(event) {
	queueFiles(event.target.files)
	event.target.value = ""
}

function queueDroppedFiles(event) {
	queueFiles(event.dataTransfer?.files)
}

function queueFiles(fileList) {
	if (!canChange.value || controlsDisabled.value) return
	const files = [...(fileList || [])].filter((file) => file.type.startsWith("image/"))
	if (!files.length) return
	bulkFiles.value = files
	bulkVisible.value = true
}

async function uploadPdf(event) {
	const input = event.target
	const file = input.files?.[0]
	if (!file || !canChange.value || controlsDisabled.value) {
		input.value = ""
		return
	}
	busyAction.value = "pdf"
	actionError.value = ""
	emit("operation-started")
	let changed = false
	try {
		await uploadGraphicsPdf({
			docname: props.docname,
			tableName: props.isBox ? "product_box_details" : "product_designs",
			file,
		})
		changed = true
	} catch (reason) {
		actionError.value = reason?.message || "Unable to process the graphics PDF."
	} finally {
		input.value = ""
		busyAction.value = ""
		emit("operation-finished", changed)
	}
}

function askToRemove(row) {
	if (controlsDisabled.value) return
	removeTarget.value = row
	removeVisible.value = true
}

async function confirmRemove() {
	if (!removeTarget.value?.name || !canChange.value || controlsDisabled.value) return
	busyAction.value = "remove"
	actionError.value = ""
	emit("operation-started")
	let changed = false
	try {
		await removeGraphic(props.docname, removeTarget.value.name)
		removeVisible.value = false
		removeTarget.value = null
		changed = true
	} catch (reason) {
		actionError.value = reason?.message || "Unable to remove the graphic."
	} finally {
		busyAction.value = ""
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
.pd-media-panel__count { flex: 0 0 auto; padding: 4px 9px; color: var(--erp-text-secondary); border: 1px solid var(--erp-border); border-radius: 999px; background: var(--erp-bg); font-size: var(--erp-font-size-min); font-weight: 680; }
.pd-media-empty { display: grid; align-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.pd-media-empty i { font-size: 1.5rem; }
.pd-media-empty--panel { min-height: 120px; border: 1px dashed var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.pd-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; margin: -1px; padding: 0; border: 0; clip: rect(0 0 0 0); white-space: nowrap; }
.product-graphics__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.product-graphic-card { display: grid; min-width: 0; gap: 9px; padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.product-graphic-card__heading { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 8px; }
.product-graphic-card__heading strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-body); text-overflow: ellipsis; white-space: nowrap; }
.product-graphic-card__preview { display: flex; height: 230px; overflow: hidden; align-items: center; justify-content: center; border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-graphic-card__preview img { display: block; width: 100%; height: 100%; background: white; object-fit: contain; }
.product-graphics__upload { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: var(--erp-space-3); padding-top: var(--erp-space-3); border-top: 1px solid var(--erp-border); }
.product-graphics__drop { display: flex; min-height: 84px; align-items: center; justify-content: center; gap: 9px; padding: 12px; color: var(--erp-text-muted); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); background: var(--erp-bg); }
.product-graphics__drop > i { font-size: 1.3rem; }
.product-graphics__busy { display: inline-flex; align-items: center; gap: 7px; margin: 0; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
@media (max-width: 760px) { .product-graphics__grid, .product-graphics__upload { grid-template-columns: 1fr; } .product-graphics__drop { align-items: stretch; flex-direction: column; text-align: center; } }
</style>

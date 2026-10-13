<template>
	<Dialog
		:visible="visible"
		modal
		header="Create Product Image"
		class="erp-dialog--md"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<div class="product-image-create">
			<label class="product-image-create__field">
				<span>Image Title <strong>*</strong></span>
				<InputText v-model="imageTitle" fluid :disabled="busy || readonly || Boolean(createdProduct)" autofocus />
			</label>
			<label class="product-image-create__field">
				<span>Title Header <strong>*</strong></span>
				<InputText v-model="titleHeader" fluid :disabled="busy || readonly || Boolean(createdProduct)" />
			</label>
			<input ref="imageInput" class="pd-visually-hidden" type="file" accept="image/*" @change="uploadImage" />
			<input ref="pdfInput" class="pd-visually-hidden" type="file" accept=".pdf,application/pdf" @change="uploadPdf" />
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button label="Save" :loading="busyAction === 'save'" :disabled="busy || readonly" @click="save" />
			<Button
				label="Save & Upload Image"
				icon="pi pi-image"
				severity="secondary"
				:loading="busyAction === 'image'"
				:disabled="busy || readonly"
				@click="chooseUpload('image')"
			/>
			<Button
				label="Save & Upload PDF"
				icon="pi pi-file-pdf"
				severity="secondary"
				:loading="busyAction === 'pdf'"
				:disabled="busy || readonly"
				@click="chooseUpload('pdf')"
			/>
		</template>
	</Dialog>
	<DocumentErrorDialog
		:message="actionError"
		title="Product Image could not be created"
		@dismiss="actionError = ''"
	/>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import { computed, ref, watch } from "vue"

import { createProductImage, replaceAttachment, uploadSinglePagePdf } from "../../../api/pd.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	readonly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "created"])
const imageTitle = ref("")
const titleHeader = ref("")
const busyAction = ref("")
const actionError = ref("")
const createdProduct = ref(null)
const imageInput = ref(null)
const pdfInput = ref(null)
const busy = computed(() => Boolean(busyAction.value))

watch(() => props.visible, (visible) => {
	if (visible) resetForm()
})

function resetForm() {
	imageTitle.value = ""
	titleHeader.value = ""
	busyAction.value = ""
	actionError.value = ""
	createdProduct.value = null
	if (imageInput.value) imageInput.value.value = ""
	if (pdfInput.value) pdfInput.value.value = ""
}

function setVisible(visible) {
	if (!visible && busy.value) return
	emit("update:visible", visible)
}

function validateFields() {
	if (imageTitle.value.trim() && titleHeader.value.trim()) return true
	actionError.value = "Image Title and Title Header are required."
	return false
}

function chooseUpload(type) {
	if (props.readonly || busy.value || !validateFields()) return
	const input = type === "image" ? imageInput.value : pdfInput.value
	input?.click()
}

async function ensureProductImage() {
	if (createdProduct.value) return createdProduct.value
	const productImage = await createProductImage(imageTitle.value.trim(), titleHeader.value.trim())
	createdProduct.value = productImage
	return productImage
}

async function save() {
	if (props.readonly || busy.value || !validateFields()) return
	busyAction.value = "save"
	actionError.value = ""
	try {
		finish(await ensureProductImage())
	} catch (reason) {
		actionError.value = reason?.message || "Unable to create the Product Image."
	} finally {
		busyAction.value = ""
	}
}

async function uploadImage(event) {
	await createAndUpload(event, "image", (productImage, file) => replaceAttachment({
		doctype: "SD YRP Product Image",
		docname: productImage.name,
		fieldname: "image",
		oldUrl: null,
		file,
	}))
}

async function uploadPdf(event) {
	await createAndUpload(event, "pdf", (productImage, file) => uploadSinglePagePdf({
		doctype: "SD YRP Product Image",
		docname: productImage.name,
		fieldname: "image",
		file,
	}))
}

async function createAndUpload(event, type, upload) {
	const input = event.target
	const file = input.files?.[0]
	if (!file || props.readonly) {
		input.value = ""
		return
	}
	busyAction.value = type
	actionError.value = ""
	try {
		const productImage = await ensureProductImage()
		await upload(productImage, file)
		finish(productImage)
	} catch (reason) {
		actionError.value = reason?.message || "Unable to upload the Product Image."
	} finally {
		input.value = ""
		busyAction.value = ""
	}
}

function finish(productImage) {
	emit("created", productImage.name)
	emit("update:visible", false)
}
</script>

<style scoped>
.pd-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; margin: -1px; padding: 0; border: 0; clip: rect(0 0 0 0); white-space: nowrap; }
.product-image-create { display: grid; min-width: min(30rem, 75vw); gap: var(--erp-space-3); }
.product-image-create__field { display: grid; gap: 7px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.product-image-create__field strong { color: var(--erp-danger); }
@media (max-width: 640px) { .product-image-create { min-width: 0; } }
</style>

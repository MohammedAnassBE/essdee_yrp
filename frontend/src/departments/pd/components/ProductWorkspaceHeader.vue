<template>
	<header class="pd-product-workspace__header">
		<div class="pd-product-workspace__identity">
			<span class="pd-product-workspace__eyebrow">Product · {{ record.name || "New" }}</span>
			<div class="pd-product-workspace__title-row">
				<h1>{{ record.item_name || record.name || "New Product" }}</h1>
				<div class="pd-product-workspace__chips" aria-label="Product details">
					<span class="pd-product-workspace__chip">Tech Pack {{ record.tech_pack_no || 0 }}</span>
					<span class="pd-product-workspace__chip">{{ isSetItem ? "Set item" : "Single item" }}</span>
				</div>
			</div>
		</div>
		<div class="pd-product-workspace__actions">
			<template v-if="mode === 'edit'">
				<div class="pd-product-workspace__edit-actions">
					<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="emit('cancel')" />
					<DocumentSaveButton :loading="saving" :disabled="!canSave" @save="emit('save')" />
				</div>
			</template>
			<template v-else>
				<DocumentActionStrip :actions="actions" />
				<DocumentPrintButton
					v-if="canPrint"
					doctype="SD YRP Product"
					:name="record.name"
					:formats="printFormats"
					:disabled="busy"
				/>
			</template>
		</div>
	</header>
</template>

<script setup>
import Button from "primevue/button"

import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentPrintButton from "../../../components/documents/DocumentPrintButton.vue"
import DocumentSaveButton from "../../../components/documents/DocumentSaveButton.vue"

defineProps({
	record: { type: Object, required: true },
	actions: { type: Array, required: true },
	printFormats: { type: Array, required: true },
	mode: { type: String, required: true },
	isSetItem: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
	saving: { type: Boolean, default: false },
	canSave: { type: Boolean, default: false },
	canPrint: { type: Boolean, default: false },
})
const emit = defineEmits(["cancel", "save"])
</script>

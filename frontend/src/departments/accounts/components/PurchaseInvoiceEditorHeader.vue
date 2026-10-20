<template>
	<header class="purchase-invoice-editor__header erp-editor-header">
		<div class="purchase-invoice-editor__identity">
			<span>{{ currentName || "New document" }}</span>
			<div>
				<h1 class="erp-doc-title">{{ currentName ? "Edit Purchase Invoice" : "New Purchase Invoice" }}</h1>
				<span v-if="billTracking" class="purchase-invoice-editor__fact">
					<i class="pi pi-link" aria-hidden="true" />
					From Bill Tracking <DocumentLink doctype="YRP Bill Tracking" :name="billTracking" :label="billTracking" />
				</span>
			</div>
		</div>
		<div class="erp-editor-actions">
			<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="emit('cancel')" />
			<DocumentSaveButton
				:show-submit="canSubmit"
				:loading="saving"
				:disabled="busy || !canSave"
				@save="emit('save', false)"
				@submit="emit('save', true)"
			/>
		</div>
	</header>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Button from "primevue/button"

import DocumentSaveButton from "../../../components/documents/DocumentSaveButton.vue"

defineProps({
	currentName: { type: String, default: "" },
	billTracking: { type: String, default: "" },
	busy: { type: Boolean, default: false },
	canSubmit: { type: Boolean, default: false },
	canSave: { type: Boolean, default: false },
	saving: { type: Boolean, default: false },
})
const emit = defineEmits(["cancel", "save"])
</script>

<style scoped>
.purchase-invoice-editor__identity {
	display: grid;
	min-width: 0;
	gap: 2px;
}
.purchase-invoice-editor__identity > div {
	display: flex;
	min-width: 0;
	align-items: center;
	gap: 10px;
}
.purchase-invoice-editor__fact {
	display: inline-flex;
	min-height: 25px;
	align-items: center;
	gap: 6px;
	padding: 3px 8px;
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	border: 1px solid var(--erp-accent-border);
	border-radius: 999px;
	background: var(--erp-accent-soft);
	white-space: nowrap;
}
@media (max-width: 700px) {
	.purchase-invoice-editor__identity {
		min-width: 0;
		flex: 1 1 auto;
	}
	.purchase-invoice-editor__fact {
		display: none;
	}
}
</style>

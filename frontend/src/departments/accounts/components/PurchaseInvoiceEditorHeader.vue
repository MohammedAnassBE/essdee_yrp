<template>
	<header class="purchase-invoice-editor__header erp-editor-header">
		<div class="purchase-invoice-editor__identity">
			<span>{{ currentName || "New document" }}</span>
			<div>
				<h1>{{ currentName ? "Edit Purchase Invoice" : "New Purchase Invoice" }}</h1>
				<span v-if="billTracking" class="purchase-invoice-editor__fact">
					<i class="pi pi-link" aria-hidden="true" />
					From Bill Tracking {{ billTracking }}
				</span>
			</div>
		</div>
		<div class="purchase-invoice-editor__actions erp-editor-actions">
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
.purchase-invoice-editor__header { position: sticky; z-index: var(--erp-layer-sticky); top: var(--erp-shell-header-height); display: flex; min-height: 52px; align-items: center; justify-content: space-between; gap: var(--erp-space-4); margin: 0 calc(0px - var(--purchase-invoice-editor-inline)); padding: 7px var(--purchase-invoice-editor-inline); border-top: 3px solid var(--erp-accent); border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface) 96%, var(--erp-accent-soft)); box-shadow: 0 5px 16px rgb(28 61 45 / 5%); }
.purchase-invoice-editor__identity { display: grid; min-width: 0; gap: 2px; }
.purchase-invoice-editor__identity > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
.purchase-invoice-editor__identity > div { display: flex; min-width: 0; align-items: center; gap: 10px; }
.purchase-invoice-editor__identity h1 { margin: 0; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; }
.purchase-invoice-editor__fact { display: inline-flex; min-height: 25px; align-items: center; gap: 6px; padding: 3px 8px; color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 720; border: 1px solid var(--erp-accent-border); border-radius: 999px; background: var(--erp-accent-soft); white-space: nowrap; }
.purchase-invoice-editor__actions { display: flex; justify-content: flex-end; gap: var(--erp-space-2); flex-wrap: wrap; }
@media (max-width: 700px) { .purchase-invoice-editor__header { min-height: 55px; gap: 8px; margin: 0 calc(var(--erp-space-3) * -1); padding: 4px var(--erp-space-3); } .purchase-invoice-editor__identity { min-width: 0; flex: 1 1 auto; } .purchase-invoice-editor__identity > span, .purchase-invoice-editor__fact { display: none; } .purchase-invoice-editor__identity h1 { overflow: hidden; font-size: 16px; text-overflow: ellipsis; white-space: nowrap; } .purchase-invoice-editor__actions { width: auto; flex: 0 0 auto; flex-wrap: nowrap; gap: 4px; } .purchase-invoice-editor__actions :deep(.p-button) { min-width: 0; min-height: 44px; padding-inline: 8px; font-size: 12px; } }
</style>

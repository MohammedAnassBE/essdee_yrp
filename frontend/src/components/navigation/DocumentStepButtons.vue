<template>
	<div class="document-step-buttons" role="group" :aria-label="`${documentLabel} previous and next`">
		<button
			type="button"
			class="document-step-buttons__button"
			:disabled="disabled || !previousName"
			:aria-label="`Previous ${documentLabel}`"
			:title="previousName ? `Previous ${documentLabel}: ${previousName}` : `No previous ${documentLabel}`"
			@click="emit('previous')"
		>
			<i class="pi pi-chevron-left" aria-hidden="true" />
		</button>
		<button
			type="button"
			class="document-step-buttons__button"
			:disabled="disabled || !nextName"
			:aria-label="`Next ${documentLabel}`"
			:title="nextName ? `Next ${documentLabel}: ${nextName}` : `No next ${documentLabel}`"
			@click="emit('next')"
		>
			<i class="pi pi-chevron-right" aria-hidden="true" />
		</button>
	</div>
</template>

<script setup>
defineProps({
	documentLabel: { type: String, default: "" },
	previousName: { type: String, default: "" },
	nextName: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["previous", "next"])
</script>

<style scoped>
.document-step-buttons {
	display: inline-flex;
	flex: 0 0 auto;
	overflow: visible;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.document-step-buttons:has(.document-step-buttons__button:not(:disabled):hover) {
	border-color: var(--erp-accent-border);
}

.document-step-buttons__button {
	display: inline-grid;
	width: 38px;
	height: 36px;
	padding: 0;
	color: var(--erp-text-muted);
	border: 0;
	background: transparent;
	place-items: center;
	cursor: pointer;
	transition: color var(--erp-transition-fast), background var(--erp-transition-fast);
}

.document-step-buttons__button + .document-step-buttons__button { border-left: 1px solid var(--erp-border); }
.document-step-buttons__button:not(:disabled):hover {
	color: var(--erp-text);
	background: var(--erp-surface-hover);
}
.document-step-buttons__button:disabled {
	opacity: .5;
	cursor: not-allowed;
}

@media (max-width: 620px), (pointer: coarse) {
	.document-step-buttons__button { width: 44px; height: 44px; }
}
</style>

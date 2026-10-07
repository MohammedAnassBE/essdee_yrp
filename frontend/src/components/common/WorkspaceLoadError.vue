<template>
	<section class="workspace-load-error" role="alert" aria-live="assertive">
		<span class="workspace-load-error__icon" aria-hidden="true"><i class="pi pi-exclamation-circle" /></span>
		<div class="workspace-load-error__copy">
			<strong>{{ title }}</strong>
			<span>{{ message }}</span>
		</div>
		<Button v-if="retryable" label="Retry" icon="pi pi-refresh" :loading="loading" @click="$emit('retry')" />
	</section>
</template>

<script setup>
import Button from "primevue/button"

defineProps({
	title: { type: String, default: "This workspace could not be loaded" },
	message: { type: String, default: "Check your connection and try again." },
	loading: { type: Boolean, default: false },
	retryable: { type: Boolean, default: true },
})

defineEmits(["retry"])
</script>

<style scoped>
.workspace-load-error {
	display: grid;
	grid-template-columns: 38px minmax(0, 1fr) auto;
	align-items: center;
	gap: var(--erp-space-3);
	width: min(720px, calc(100% - 24px));
	margin: var(--erp-space-4) auto;
	padding: var(--erp-space-3);
	border: 1px solid color-mix(in srgb, var(--erp-danger) 28%, var(--erp-border));
	border-radius: var(--erp-panel-radius);
	background: color-mix(in srgb, var(--erp-danger-soft) 64%, white);
}

.workspace-load-error__icon {
	display: inline-grid;
	place-items: center;
	width: 38px;
	height: 38px;
	border-radius: 10px;
	background: white;
	color: var(--erp-danger);
	font-size: 1rem;
}

.workspace-load-error__copy {
	display: grid;
	gap: 2px;
	min-width: 0;
}

.workspace-load-error__copy strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-body);
}

.workspace-load-error__copy span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-table);
	line-height: 1.45;
}

@media (max-width: 640px) {
	.workspace-load-error {
		grid-template-columns: 38px minmax(0, 1fr);
	}

	.workspace-load-error :deep(.p-button) {
		grid-column: 1 / -1;
		width: 100%;
		min-height: 44px;
	}
}
</style>

<template>
	<Dialog :visible="visible" modal :header="title" :closable="!busy" :dismissable-mask="false" :style="{ width: 'min(440px, calc(100vw - 24px))' }" @update:visible="emit('update:visible', $event)">
		<div class="document-confirmation-dialog"><i :class="icon" /><p>{{ message }}</p></div>
		<template #footer><Button label="Keep Document" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" /><Button :label="confirmLabel" :icon="confirmIcon" :severity="severity" :loading="busy" @click="emit('confirm')" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"

defineProps({
	visible: { type: Boolean, default: false },
	title: { type: String, default: "Confirm action" },
	message: { type: String, default: "Continue with this action?" },
	confirmLabel: { type: String, default: "Continue" },
	confirmIcon: { type: String, default: "pi pi-check" },
	icon: { type: String, default: "pi pi-exclamation-triangle" },
	severity: { type: String, default: "danger" },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])
</script>

<style scoped>
.document-confirmation-dialog { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 14px; padding: 8px 0 4px; }
.document-confirmation-dialog > i { display: grid; width: 40px; height: 40px; place-items: center; color: var(--erp-warning); border: 1px solid color-mix(in srgb, var(--erp-warning) 24%, white); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-warning) 9%, white); }
.document-confirmation-dialog p { margin: 3px 0 0; color: var(--erp-text); font-size: 0.88rem; line-height: 1.55; }
</style>

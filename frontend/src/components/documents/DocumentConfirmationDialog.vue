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
.document-confirmation-dialog { display: grid; grid-template-columns: auto 1fr; align-items: start; gap: 12px; padding: 4px 0; }
.document-confirmation-dialog > i { display: grid; width: 34px; height: 34px; place-items: center; color: #b45309; border-radius: 50%; background: #fff7ed; }
.document-confirmation-dialog p { margin: 4px 0 0; color: var(--erp-text-muted); line-height: 1.5; }
</style>

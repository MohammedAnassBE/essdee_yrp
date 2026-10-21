<template>
	<Button
		v-if="showTrigger && (formats !== null || permissions?.print)"
		type="button"
		class="document-print-button"
		:label="label"
		:aria-label="label"
		icon="pi pi-print"
		severity="secondary"
		outlined
		:disabled="disabled || !name || (formats !== null && !formats.length)"
		@click="openDialog"
	/>
	<DocumentPrintDialog v-model:visible="dialogVisible" :doctype="doctype" :name="name" />
</template>

<script setup>
import Button from "primevue/button"
import { ref } from "vue"
import { useDocumentPermissions } from "../../composables/useDocumentPermissions.js"
import DocumentPrintDialog from "./DocumentPrintDialog.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	formats: { type: Array, default: null },
	docstatus: { type: [Number, String], default: 0 },
	label: { type: String, default: "Print" },
	disabled: { type: Boolean, default: false },
	showTrigger: { type: Boolean, default: true },
})

const permissions = useDocumentPermissions(() => [props.doctype, props.name, props.docstatus], () => props.formats === null)
const dialogVisible = ref(false)

function openDialog() {
	if (!props.disabled && props.name && (props.formats === null ? permissions.value?.print : props.formats.length)) dialogVisible.value = true
}
defineExpose({ open: openDialog })
</script>

<style>
.document-print-button.p-button {
	min-height: var(--erp-control-height);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	border-color: var(--erp-border-strong);
	box-shadow: var(--erp-shadow-xs);
}

.document-print-button.p-button:not(:disabled):hover {
	background: var(--erp-accent-soft);
	border-color: color-mix(in srgb, var(--erp-accent) 28%, var(--erp-border));
}

.document-print-button.p-button:focus-visible {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 16%, transparent);
	outline-offset: 1px;
}

.document-print-button.p-button:not(:disabled):active {
	transform: translateY(1px);
}
</style>

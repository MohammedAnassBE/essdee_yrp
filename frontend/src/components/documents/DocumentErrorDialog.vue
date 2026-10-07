<template>
	<Dialog
		:visible="visible"
		modal
		:header="title"
		class="document-error-dialog"
		:dismissable-mask="false"
		:style="{ width: 'min(520px, calc(100vw - 28px))' }"
		@update:visible="setVisible"
	>
		<div class="document-error-dialog__body" role="alert" aria-live="assertive">
			<span class="document-error-dialog__icon" aria-hidden="true"><i class="pi pi-exclamation-circle" /></span>
			<div><strong>{{ summary }}</strong><p>{{ message }}</p></div>
		</div>
		<template #footer>
			<Button v-if="retryLabel" :label="retryLabel" icon="pi pi-refresh" severity="secondary" outlined @click="retry" />
			<Button label="OK" autofocus @click="close" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"

const props = defineProps({
	message: { type: String, default: "" },
	title: { type: String, default: "Unable to complete this action" },
	summary: { type: String, default: "Please review the message below." },
	retryLabel: { type: String, default: "" },
})
const emit = defineEmits(["dismiss", "retry"])
const visible = ref(Boolean(props.message))

watch(() => props.message, (message) => { visible.value = Boolean(message) })

function setVisible(value) {
	visible.value = value
	if (!value) emit("dismiss")
}
function close() { setVisible(false) }
function retry() { visible.value = false; emit("retry") }
</script>

<style scoped>
.document-error-dialog__body { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 13px; padding: 4px 2px 8px; }
.document-error-dialog__icon { display: grid; width: 38px; height: 38px; border-radius: 50%; color: var(--erp-danger); background: var(--erp-danger-soft); place-items: center; }
.document-error-dialog__icon i { font-size: 18px; }
.document-error-dialog__body > div { display: grid; gap: 5px; min-width: 0; }
.document-error-dialog__body strong { color: var(--erp-text); font-size: 14px; }
.document-error-dialog__body p { margin: 0; color: var(--erp-text-secondary); font-size: 13px; line-height: 1.55; white-space: pre-line; overflow-wrap: anywhere; }
</style>

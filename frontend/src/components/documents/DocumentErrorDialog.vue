<template>
	<Dialog
		:visible="visible"
		modal
		:header="title"
		class="document-error-dialog erp-dialog--sm"
		:dismissable-mask="false"
		@show="focusPrimaryAction"
		@hide="restoreFocus"
		@update:visible="setVisible"
	>
		<div class="document-error-dialog__body" role="alert" aria-live="assertive">
			<span class="document-error-dialog__icon" aria-hidden="true"><i class="pi pi-exclamation-circle" /></span>
			<div><strong>{{ summary }}</strong><p>{{ formatDatesInText(message) }}</p></div>
		</div>
		<template #footer>
			<Button v-if="retryLabel" label="Dismiss" severity="secondary" text @click="close" />
			<Button ref="primaryAction" :label="retryLabel || 'OK'" :icon="retryLabel ? 'pi pi-refresh' : undefined" autofocus @click="retryLabel ? retry() : close()" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { nextTick, ref, watch } from "vue"
import { formatDatesInText } from "../../utils/dateFormat.js"

const props = defineProps({
	message: { type: String, default: "" },
	title: { type: String, default: "Unable to complete this action" },
	summary: { type: String, default: "Please review the message below." },
	retryLabel: { type: String, default: "" },
})
const emit = defineEmits(["dismiss", "retry"])
const visible = ref(Boolean(props.message))
const primaryAction = ref(null)
let focusOrigin = null
let focusOriginId = ""

watch(() => props.message, (message) => {
	if (message && typeof document !== "undefined") {
		focusOrigin = document.activeElement instanceof HTMLElement ? document.activeElement : null
		focusOriginId = focusOrigin?.id || ""
	}
	visible.value = Boolean(message)
})

function focusPrimaryAction() {
	const focus = () => (primaryAction.value?.$el || primaryAction.value)?.focus?.()
	focus()
	nextTick(() => window.requestAnimationFrame(focus))
}

function restoreFocus() {
	const origin = focusOrigin
	const originId = focusOriginId
	const focus = () => (origin?.isConnected ? origin : originId ? document.getElementById(originId) : null)?.focus?.()
	nextTick(() => window.requestAnimationFrame(() => window.requestAnimationFrame(focus)))
	focusOrigin = null
	focusOriginId = ""
}

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

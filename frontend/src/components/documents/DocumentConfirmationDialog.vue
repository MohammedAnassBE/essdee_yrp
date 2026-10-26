<template>
	<Dialog class="document-confirmation-shell erp-dialog--sm" :visible="visible" modal :header="title" :closable="!busy" :dismissable-mask="false" @show="focusSafeAction" @hide="restoreFocus" @update:visible="emit('update:visible', $event)">
		<div class="document-confirmation-dialog"><i :class="icon" /><p>{{ message }}</p></div>
		<slot />
		<template #footer><Button ref="safeAction" :label="cancelLabel" severity="secondary" text autofocus :disabled="busy" @click="emit('update:visible', false)" /><Button :label="confirmLabel" :icon="confirmIcon" :severity="severity" :loading="busy" :disabled="confirmDisabled" @click="emit('confirm')" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { nextTick, ref, watch } from "vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	title: { type: String, default: "Confirm action" },
	message: { type: String, default: "Continue with this action?" },
	confirmLabel: { type: String, default: "Continue" },
	cancelLabel: { type: String, default: "Keep Document" },
	confirmIcon: { type: String, default: "pi pi-check" },
	icon: { type: String, default: "pi pi-exclamation-triangle" },
	severity: { type: String, default: "danger" },
	busy: { type: Boolean, default: false },
	confirmDisabled: { type: Boolean, default: false },
	returnFocusSelector: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "confirm"])
const safeAction = ref(null)
let focusOrigin = null
let focusOriginId = ""
let explicitReturnFocusSelector = ""

watch(() => props.visible, (visible) => {
	if (!visible || typeof document === "undefined") return
	focusOrigin = document.activeElement instanceof HTMLElement ? document.activeElement : null
	focusOriginId = focusOrigin?.id || ""
	explicitReturnFocusSelector = props.returnFocusSelector
}, { immediate: true })

function focusSafeAction() {
	const focus = () => (safeAction.value?.$el || safeAction.value)?.focus?.()
	focus()
	nextTick(() => {
		focus()
		window.requestAnimationFrame(focus)
	})
}

function restoreFocus() {
	const selector = explicitReturnFocusSelector
	const origin = focusOrigin
	const originId = focusOriginId
	const focus = () => {
		const explicitTarget = selector ? document.querySelector(selector) : null
		const target = explicitTarget || (origin?.isConnected ? origin : originId ? document.getElementById(originId) : null)
		target?.focus?.()
	}
	nextTick(() => {
		focus()
		window.requestAnimationFrame(() => window.requestAnimationFrame(focus))
	})
	focusOrigin = null
	focusOriginId = ""
	explicitReturnFocusSelector = ""
}
</script>

<style scoped>
.document-confirmation-dialog { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: start; gap: 14px; padding: 8px 0 4px; }
.document-confirmation-dialog > i { display: grid; width: 40px; height: 40px; place-items: center; color: var(--erp-warning); border: 1px solid color-mix(in srgb, var(--erp-warning) 24%, var(--erp-surface)); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-warning) 9%, var(--erp-surface)); }
.document-confirmation-dialog p { margin: 3px 0 0; color: var(--erp-text); font-size: 0.88rem; line-height: 1.55; }
@media (max-width: 420px) {
	:global(.document-confirmation-shell .p-dialog-footer) { display: flex; align-items: stretch; flex-direction: column-reverse; }
	:global(.document-confirmation-shell .p-dialog-footer .p-button) { width: 100%; justify-content: center; }
}
</style>

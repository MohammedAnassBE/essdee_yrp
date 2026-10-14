<template>
	<DocumentConfirmationDialog
		:visible="visible"
		:title="`${label} Item Price?`"
		:message="message"
		:confirm-label="label"
		:confirm-icon="icon"
		:severity="severity"
		:busy="busy"
		@update:visible="emit('update:visible', $event)"
		@confirm="emit('confirm')"
	/>
</template>

<script setup>
import { computed } from "vue"

import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	action: { type: Object, default: null },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])

const label = computed(() => props.action?.label || props.action?.action || "Continue")
const message = computed(() => props.action?.preview || `${label.value} this Item Price?`)
const icon = computed(() => ({
	Approve: "pi pi-check-circle",
	Reject: "pi pi-times-circle",
	Expire: "pi pi-clock",
	Submit: "pi pi-send",
}[props.action?.action] || "pi pi-check"))
const severity = computed(() => props.action?.action === "Reject" ? "danger" : props.action?.action === "Expire" ? "warn" : "success")
</script>

<template>
	<DocumentConfirmationDialog
		:visible="visible"
		:title="`${label}: ${action?.documentName || 'Item Price'}`"
		:message="itemPriceActionMessage(action || {})"
		:confirm-label="label"
		:confirm-icon="itemPriceActionIcon(action || {})"
		:severity="itemPriceActionSeverity(action || {})"
		:busy="busy"
		@update:visible="emit('update:visible', $event)"
		@confirm="emit('confirm')"
	/>
</template>

<script setup>
import { computed } from "vue"

import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import { itemPriceActionIcon, itemPriceActionMessage, itemPriceActionSeverity } from "./purchaseViews.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	action: { type: Object, default: null },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "confirm"])

const label = computed(() => props.action?.label || props.action?.action || "Continue")
</script>

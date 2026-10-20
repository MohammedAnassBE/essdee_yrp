<template>
	<span class="document-status-badge" :class="`document-status-badge--${tone}`">{{ displayLabel }}</span>
</template>

<script setup>
import { computed } from "vue"

import { documentStatusTone } from "../../utils/statusTone.js"

const props = defineProps({
	docstatus: { type: [Number, String], default: null },
	label: { type: String, default: "" },
	tone: { type: String, default: "" },
})

const defaultLabels = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
const displayLabel = computed(() => props.label || defaultLabels[Number(props.docstatus)] || "Unknown")
const tone = computed(() => props.tone || documentStatusTone(displayLabel.value, props.docstatus))
</script>

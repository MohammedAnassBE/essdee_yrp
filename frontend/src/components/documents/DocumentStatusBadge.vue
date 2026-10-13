<template>
	<span class="document-status-badge" :class="`document-status-badge--${tone}`">{{ displayLabel }}</span>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	docstatus: { type: [Number, String], default: null },
	label: { type: String, default: "" },
})

const defaultLabels = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
const displayLabel = computed(() => props.label || defaultLabels[Number(props.docstatus)] || "Unknown")
const tone = computed(() => {
	const label = displayLabel.value.toLowerCase()
	if (/(cancel|reject|fail|error)/.test(label)) return "danger"
	if (/(pending|partial|hold|to receive|to deliver|overdue|approval)/.test(label)) return "warning"
	if (/(ready|queued|running|planned|in progress)/.test(label)) return "info"
	if (/closed/.test(label)) return "neutral"
	if (/(submit|complete|approve|receive|deliver|active|open)/.test(label)) return "success"
	if (Number(props.docstatus) === 2) return "danger"
	if (Number(props.docstatus) === 1) return "success"
	return "neutral"
})
</script>

<style scoped>
.document-status-badge { display: inline-flex; align-items: center; min-height: 24px; padding: 3px 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-bold); line-height: 1; text-transform: uppercase; white-space: nowrap; background: var(--erp-surface-muted); border: 1px solid transparent; border-radius: var(--erp-pill-radius); }
.document-status-badge--success { color: var(--erp-success-text); background: var(--erp-success-soft); border-color: color-mix(in srgb, var(--erp-success) 18%, transparent); }
.document-status-badge--warning { color: var(--erp-warning); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
.document-status-badge--info { color: var(--erp-info); background: var(--erp-info-soft); border-color: color-mix(in srgb, var(--erp-info) 18%, transparent); }
.document-status-badge--danger { color: var(--erp-danger); background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 18%, transparent); }
</style>

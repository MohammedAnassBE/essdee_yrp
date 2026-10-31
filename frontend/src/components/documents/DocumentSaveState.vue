<template>
	<span v-if="label" class="document-save-state" :class="`document-save-state--${tone}`" role="status" aria-live="polite" :title="title">
		<i :class="icon" aria-hidden="true" />{{ label }}
	</span>
</template>

<script setup>
import { computed } from "vue"

import { useRelativeTime } from "../../composables/live/useRelativeTime.js"
import { formatDisplayDatetime } from "../../utils/dateFormat.js"

const props = defineProps({
	saving: { type: Boolean, default: false },
	dirty: { type: Boolean, default: false },
	/** Time of the last save made on this page; nothing shows for a document that was only opened. */
	savedAt: { type: [Date, Number, String], default: null },
})
const savedRelative = useRelativeTime(() => props.savedAt)
const tone = computed(() => (props.saving ? "saving" : props.dirty ? "dirty" : "saved"))
const label = computed(() => {
	if (props.saving) return "Saving…"
	if (props.dirty) return "Unsaved changes"
	return props.savedAt ? `Saved · ${savedRelative.value}` : ""
})
const icon = computed(() => ({ saving: "pi pi-spin pi-spinner", dirty: "pi pi-circle-fill", saved: "pi pi-check" })[tone.value])
const title = computed(() => (tone.value === "saved" && props.savedAt ? `Saved ${formatDisplayDatetime(new Date(props.savedAt), { seconds: true })}` : ""))
</script>

<style scoped>
.document-save-state {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	white-space: nowrap;
}

.document-save-state i { font-size: 10px; }
.document-save-state--saving { color: var(--erp-text-muted); }
.document-save-state--dirty { color: var(--erp-attention-text); }
.document-save-state--dirty i { font-size: 7px; }
.document-save-state--saved { color: var(--erp-success-text); }
</style>

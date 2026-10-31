<template>
	<div v-if="state" class="document-live-bar" :class="`document-live-bar--${state}`" role="status" aria-live="polite">
		<i :class="state === 'deleted' ? 'pi pi-trash' : 'pi pi-sync'" aria-hidden="true" />
		<span v-if="state === 'deleted'" class="document-live-bar__text">This document was deleted. It can no longer be saved.</span>
		<span v-else class="document-live-bar__text">
			Modified by someone else<template v-if="relative">{{ " " }}<time :datetime="modifiedAt" :title="exactTime">{{ relative }}</time></template>.
			<template v-if="dirty">Reload to see their changes; your unsaved edits will be discarded.</template>
		</span>
		<Button v-if="state === 'modified'" class="document-live-bar__reload" label="Reload" icon="pi pi-refresh" size="small" severity="warn" outlined :loading="reloading" @click="requestReload" />
		<DocumentConfirmationDialog
			v-model:visible="confirmVisible"
			title="Discard your changes?"
			message="Reloading shows the latest saved document and discards your unsaved edits."
			confirm-label="Discard and Reload"
			cancel-label="Keep Editing"
			confirm-icon="pi pi-refresh"
			severity="warn"
			@confirm="confirmReload"
		/>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed, ref } from "vue"

import { useRelativeTime } from "../../composables/live/useRelativeTime.js"
import { formatDisplayDatetime } from "../../utils/dateFormat.js"
import DocumentConfirmationDialog from "./DocumentConfirmationDialog.vue"

const props = defineProps({
	state: { type: String, default: "", validator: (value) => ["", "modified", "deleted"].includes(value) },
	modifiedAt: { type: String, default: "" },
	dirty: { type: Boolean, default: false },
	reloading: { type: Boolean, default: false },
})
const emit = defineEmits(["reload"])
const confirmVisible = ref(false)
const relative = useRelativeTime(() => props.modifiedAt)
const exactTime = computed(() => (props.modifiedAt ? formatDisplayDatetime(props.modifiedAt) : ""))

function requestReload() {
	if (props.dirty) confirmVisible.value = true
	else emit("reload")
}

function confirmReload() {
	confirmVisible.value = false
	emit("reload")
}
</script>

<style scoped>
.document-live-bar {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px 10px;
	padding: 8px 12px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	background: var(--erp-warning-soft);
	border: 1px solid color-mix(in srgb, var(--erp-warning) 35%, transparent);
	border-radius: var(--erp-panel-radius);
}

.document-live-bar > i { color: var(--erp-warning); }
.document-live-bar--deleted { background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 35%, transparent); }
.document-live-bar--deleted > i { color: var(--erp-danger); }
.document-live-bar__text { flex: 1 1 260px; min-width: 0; }
.document-live-bar__text time { font-weight: var(--erp-font-weight-semibold); }
</style>

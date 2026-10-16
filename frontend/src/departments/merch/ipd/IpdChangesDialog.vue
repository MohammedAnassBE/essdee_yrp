<template>
	<Dialog :visible="visible" modal class="erp-entity-dialog erp-dialog--lg" :header="source ? `Changes since ${source}` : 'Changes'" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="ipd-changes__state"><i class="pi pi-spin pi-spinner" aria-hidden="true" /><span>Loading changes…</span></div>
		<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-else-if="!changes.length" class="erp-empty-state erp-empty-state--compact"><i class="pi pi-check" aria-hidden="true" /><strong>No changes yet</strong><span>This version still matches its source.</span></div>
		<div v-else class="ipd-changes__scroll">
			<table class="erp-data-table ipd-changes__table">
				<thead><tr><th scope="col">Section</th><th scope="col">Field</th><th scope="col">Source</th><th scope="col">This version</th></tr></thead>
				<tbody>
					<tr v-for="(change, index) in changes" :key="`${change.section}-${change.field}-${index}`">
						<td>{{ tabLabel(change) }}</td>
						<td>{{ change.label || change.field }}</td>
						<td>{{ display(change.source) }}</td>
						<td>{{ display(change.current) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import Message from "primevue/message"

import { tabLabel } from "./ipdTabs.js"

defineProps({
	visible: { type: Boolean, default: false },
	source: { type: String, default: "" },
	changes: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
})
const emit = defineEmits(["update:visible"])

function display(value) {
	if (value === null || value === undefined || value === "") return "—"
	if (Array.isArray(value)) return value.length > 6 || value.some((entry) => entry && typeof entry === "object") ? `${value.length} rows` : value.map(display).join(", ")
	if (typeof value === "object") return Object.keys(value).length ? `${Object.keys(value).length} values` : "—"
	return String(value)
}
</script>

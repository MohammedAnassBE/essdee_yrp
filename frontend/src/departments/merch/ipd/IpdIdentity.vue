<template>
	<div class="ipd-identity">
		<div class="ipd-identity__title">
			<div class="ipd-identity__meta">
				<span>{{ name ? `Item Production Detail · ${name}` : "New Item Production Detail" }}</span>
				<span v-if="editing" class="ipd-identity__editing">· Editing</span>
			</div>
			<div class="ipd-identity__heading">
				<h1 :id="headingId" class="erp-doc-title" :aria-label="[name || 'New IPD', itemName || item].filter(Boolean).join(' · ')">
					<span class="ipd-identity__name">{{ name || "New IPD" }}</span>
					<template v-if="itemName || item"><span class="ipd-identity__separator" aria-hidden="true">·</span><span class="ipd-identity__item">{{ itemName || item }}</span></template>
				</h1>
				<DocumentStatusBadge v-if="name" :label="status || 'Not Approved'" />
			</div>
		</div>
		<dl class="ipd-identity__facts">
			<div v-if="name" class="ipd-identity__fact ipd-identity__fact--version"><dt>Version</dt><dd>{{ version || "—" }}</dd></div>
			<div class="ipd-identity__fact"><dt>Tech Pack</dt><dd>{{ techPack || "—" }}</dd></div>
			<div class="ipd-identity__fact"><dt>Pattern</dt><dd>{{ pattern || "—" }}</dd></div>
			<div v-if="editing && name" class="ipd-identity__fact"><dt>Draft</dt><dd :class="`ipd-identity__draft--${draftState}`">{{ draftLabel }}</dd></div>
		</dl>
	</div>
</template>

<script setup>
import { computed } from "vue"

import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"

const props = defineProps({
	name: { type: String, default: "" },
	item: { type: String, default: "" },
	itemName: { type: String, default: "" },
	status: { type: String, default: "" },
	version: { type: [Number, String], default: "" },
	techPack: { type: String, default: "" },
	pattern: { type: String, default: "" },
	draftState: { type: String, default: "saved" },
	savedAt: { type: Date, default: null },
	headingId: { type: String, required: true },
	editing: { type: Boolean, default: false },
})
const draftLabel = computed(() => {
	if (props.draftState === "saving") return "Saving…"
	if (props.draftState === "dirty") return "Unsaved changes"
	return props.savedAt ? `Saved ${props.savedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })}` : "Saved"
})
</script>

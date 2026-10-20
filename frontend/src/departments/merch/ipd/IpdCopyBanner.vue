<template>
	<div class="ipd-copy-banner" role="note">
		<i class="pi pi-copy" aria-hidden="true" />
		<span v-if="source?.hidden">Copied from an IPD you cannot open.</span>
		<span v-else>
			Started from <strong><DocumentLink doctype="YRP Item Production Detail" :name="source?.name" /></strong> ({{ source?.approval_status || "Not Approved" }}, used by {{ lotLabel }}).
			<template v-if="changes !== null"><strong>{{ changes.length }} {{ changes.length === 1 ? "change" : "changes" }}</strong> so far<template v-if="changes.length">: {{ changeSummary }}</template>.</template>
		</span>
		<Button v-if="!source?.hidden" label="Show changes" icon="pi pi-eye" size="small" outlined severity="secondary" @click="emit('show-changes')" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"

import DocumentLink from "../../../components/common/DocumentLink.vue"

import { tabLabel } from "./ipdTabs.js"

const props = defineProps({
	source: { type: Object, default: null },
	changes: { type: Array, default: null },
})
const emit = defineEmits(["show-changes"])
const lotLabel = computed(() => {
	const count = Number(props.source?.lot_count || 0)
	return `${count} ${count === 1 ? "lot" : "lots"}`
})
const changeSummary = computed(() => {
	const sections = [...new Set((props.changes || []).map((change) => tabLabel(change)))]
	return sections.slice(0, 3).join(", ") + (sections.length > 3 ? ` and ${sections.length - 3} more` : "")
})
</script>

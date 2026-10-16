<template>
	<p v-if="drift.error" class="ipd-grid-notice ipd-grid-notice--error" role="status">
		<i class="pi pi-exclamation-circle" aria-hidden="true" />{{ drift.error }}
	</p>
	<p v-else-if="drift.differs && !editor.readonly" class="ipd-grid-notice" role="status">
		<i class="pi pi-info-circle" aria-hidden="true" />
		<span>{{ empty ? "Rows are not built yet." : "Rows differ from the current values." }}</span>
		<Button :label="empty ? 'Build rows' : 'Update rows'" icon="pi pi-refresh" size="small" text @click="editor.applyGrid(gridKey)" />
	</p>
	<p v-if="problems.length" class="ipd-grid-notice ipd-grid-notice--error" role="alert">
		<i class="pi pi-exclamation-circle" aria-hidden="true" />
		<span>{{ problems[0].message }}<template v-if="problems.length > 1"> · +{{ problems.length - 1 }} more in Checks</template></span>
	</p>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject } from "vue"

import { IPD_EDITOR_KEY } from "../useIpdEditor.js"

const props = defineProps({
	gridKey: { type: String, default: "" },
	section: { type: String, default: "" },
	field: { type: String, default: "" },
	empty: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const drift = computed(() => editor.gridDrift?.[props.gridKey] || {})
const problems = computed(() => props.field ? (editor.problemsFor?.(props.section) || []).filter((problem) => problem.field === props.field) : [])
</script>

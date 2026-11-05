<template>
	<Dialog v-model:visible="visible" modal :header="outcome?.title || 'Bulk Action Result'" class="erp-dialog--md">
		<div v-if="outcome" class="list-bulk-result" role="alert">
			<p>{{ outcome.summary }}</p>
			<ul class="list-bulk-result__failures">
				<li v-for="failure in outcome.failed" :key="failure.name"><strong>{{ failure.name }}</strong> — {{ formatDatesInText(failure.error) }}</li>
			</ul>
		</div>
		<template #footer><Button label="OK" autofocus @click="visible = false" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"

import { formatDatesInText } from "../../utils/dateFormat.js"

/** Lists every document a bulk list action could not process, with its server error. */
defineProps({ outcome: { type: Object, default: null } })
const visible = defineModel("visible", { type: Boolean, default: false })
</script>

<style scoped>
.list-bulk-result p { margin: 0 0 var(--erp-space-3); }
.list-bulk-result__failures { display: grid; gap: var(--erp-space-2); max-height: 50vh; margin: 0; padding-left: var(--erp-space-4); overflow-y: auto; overflow-wrap: anywhere; }
</style>

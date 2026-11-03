<template>
	<small v-if="name" :id="id || undefined" class="name-exists-hint" role="status">
		<i class="pi pi-exclamation-circle" aria-hidden="true" />
		Already exists
		<a v-if="target && canReadDoctype(doctype)" :href="target.href" target="_blank" rel="noopener">Open {{ name }}</a>
	</small>
</template>

<script setup>
import { computed } from "vue"

import { canReadDoctype, documentLinkTarget } from "../../utils/linkTarget.js"

/** Non-blocking "Already exists" hint under a name field; the link opens the existing document in a new tab so the draft stays. */
const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	id: { type: String, default: "" },
})
const target = computed(() => documentLinkTarget(props.doctype, props.name))
</script>

<style scoped>
.name-exists-hint {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 5px;
	color: var(--erp-warning);
	font-size: var(--erp-font-size-caption);
	line-height: 1.35;
}

.name-exists-hint a {
	color: var(--erp-accent-ink);
	text-decoration: none;
}

.name-exists-hint a:hover,
.name-exists-hint a:focus-visible {
	text-decoration: underline;
	text-underline-offset: 2px;
}
</style>

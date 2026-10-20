<template>
	<a v-if="target && canReadDoctype(doctype)" :href="target.href" class="document-link" @click="navigate"><slot>{{ label ?? name }}</slot></a>
	<span v-else><slot>{{ label ?? name }}</slot></span>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"

import { canReadDoctype, documentLinkTarget } from "../../utils/linkTarget.js"

const props = defineProps({
	doctype: { type: String, default: "" },
	name: { type: [String, Number], default: "" },
	label: { type: [String, Number], default: undefined },
	currentPath: { type: String, default: undefined },
})

const router = useRouter()
const target = computed(() => documentLinkTarget(props.doctype, props.name, props.currentPath))

function navigate(event) {
	if (!router || !target.value?.route || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
	event.preventDefault()
	router.push(target.value.route)
}
</script>

<style scoped>
.document-link {
	color: var(--erp-accent-ink);
	text-decoration: none;
}

.document-link:hover,
.document-link:focus-visible {
	color: var(--erp-accent-hover);
	text-decoration: underline;
	text-underline-offset: 2px;
}
</style>

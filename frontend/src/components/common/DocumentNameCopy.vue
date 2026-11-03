<template>
	<span
		v-if="copyable"
		class="document-name-copy"
		role="button"
		tabindex="0"
		title="Click to copy"
		:aria-label="`Copy ${name}`"
		@click.stop.prevent="copy"
		@keydown.enter.prevent="copy"
		@keydown.space.prevent="copy"
	>{{ name }}</span>
	<span v-else-if="fallback">{{ fallback }}</span>
</template>

<script setup>
import { computed } from "vue"
import { useCopyFeedback } from "../../composables/useCopyFeedback.js"
import { copyDocumentName, isCopyableDocumentName } from "./documentNameCopy.js"

const props = defineProps({
	name: { type: [String, Number], default: "" },
	fallback: { type: String, default: "" },
})
const copyable = computed(() => isCopyableDocumentName(props.name))
const { runCopy } = useCopyFeedback({ success: "Copied" })

function copy() {
	return runCopy(() => copyDocumentName(props.name))
}
</script>

<style scoped>
.document-name-copy {
	cursor: pointer;
	border-radius: 4px;
}

.document-name-copy:hover {
	text-decoration: underline dotted;
	text-underline-offset: 3px;
}

.document-name-copy:focus-visible {
	outline: 2px solid var(--erp-accent);
	outline-offset: 2px;
}
</style>

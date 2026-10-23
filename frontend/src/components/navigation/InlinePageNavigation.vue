<template>
	<nav v-if="inline" class="inline-page-navigation" :aria-label="hasContext ? `${documentLabel} navigation` : `Back to ${backLabel}`">
		<BackLink :to="resolvedBackTo" :label="backLabel" :aria-controls="titleTarget || undefined" />
		<DocumentStepButtons
			v-if="showDocumentNavigation && hasContext"
			:document-label="documentLabel"
			:previous-name="previousName || ''"
			:next-name="nextName || ''"
			:disabled="navigationDisabled"
			@previous="move(goPrevious)"
			@next="move(goNext)"
		/>
		<span v-if="showDocumentNavigation && changed" class="inline-page-navigation__status" role="status">List changed — return to list</span>
		<span v-else-if="showDocumentNavigation && error" class="inline-page-navigation__status" role="status">Navigation unavailable</span>
	</nav>
</template>

<script setup>
import { computed, nextTick, toRef } from "vue"
import BackLink from "./BackLink.vue"
import DocumentStepButtons from "./DocumentStepButtons.vue"
import { useDocumentListNavigation } from "../../composables/useDocumentListNavigation.js"
import { usePageNavigation } from "./pageNavigationContext.js"

const props = defineProps({
	showDocumentNavigation: { type: Boolean, default: false },
	navigationDisabled: { type: Boolean, default: false },
	titleTarget: { type: String, default: "" },
	currentName: { type: String, default: "" },
	documentLabel: { type: String, default: "" },
})

const context = usePageNavigation()
const inline = computed(() => Boolean(context?.inline?.value))
const backTo = computed(() => context?.backTo?.value || "/")
const backLabel = computed(() => context?.backLabel?.value || "Workspaces")
const resolvedDocumentLabel = computed(() => props.documentLabel || backLabel.value.replace(/s$/, ""))
const {
	previousName,
	nextName,
	changed,
	error,
	hasContext,
	sourceFullPath,
	navigationDisabled,
	goPrevious,
	goNext,
} = useDocumentListNavigation({
	currentName: toRef(props, "currentName"),
	disabled: computed(() => props.navigationDisabled || !props.showDocumentNavigation),
})
const resolvedBackTo = computed(() => sourceFullPath.value || backTo.value)
const documentLabel = resolvedDocumentLabel

async function move(action) {
	if (!await action()) return
	await nextTick()
	await new Promise((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)))
	const target = props.titleTarget ? document.getElementById(props.titleTarget) : null
	if (!target) return
	target.setAttribute("tabindex", "-1")
	target.focus({ preventScroll: true })
}
</script>

<style scoped>
.inline-page-navigation {
	display: inline-flex;
	flex: 0 0 auto;
	align-items: center;
	gap: 6px;
}

.inline-page-navigation__status {
	max-width: 190px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: var(--erp-font-weight-medium);
	line-height: 1.2;
}

@media (max-width: 620px), (pointer: coarse) {
	.inline-page-navigation__status { position: absolute; overflow: hidden; width: 1px; height: 1px; padding: 0; white-space: nowrap; clip: rect(0, 0, 0, 0); clip-path: inset(50%); }
}
</style>

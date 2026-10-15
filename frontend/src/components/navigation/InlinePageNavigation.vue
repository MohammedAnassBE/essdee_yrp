<template>
	<nav v-if="inline" class="inline-page-navigation" :aria-label="hasContext ? `${documentLabel} navigation` : `Back to ${backLabel}`">
		<RouterLink
			v-if="!isLockedExit(resolvedBackTo)"
			class="inline-page-navigation__back"
			:to="resolvedBackTo"
			:aria-label="`Back to ${backLabel}`"
			:title="`Back to ${backLabel}`"
			:aria-controls="titleTarget || undefined"
		>
			<i class="pi pi-arrow-left" aria-hidden="true" />
		</RouterLink>
		<div v-if="showDocumentNavigation && hasContext" class="inline-page-navigation__documents" role="group" :aria-label="`${documentLabel} previous and next`">
			<button
				type="button"
				class="inline-page-navigation__document"
				:disabled="navigationDisabled || !previousName"
				:aria-label="`Previous ${documentLabel}`"
				:title="previousName ? `Previous ${documentLabel}: ${previousName}` : `No previous ${documentLabel}`"
				@click="move(goPrevious)"
			>
				<i class="pi pi-chevron-left" aria-hidden="true" />
			</button>
			<button
				type="button"
				class="inline-page-navigation__document"
				:disabled="navigationDisabled || !nextName"
				:aria-label="`Next ${documentLabel}`"
				:title="nextName ? `Next ${documentLabel}: ${nextName}` : `No next ${documentLabel}`"
				@click="move(goNext)"
			>
				<i class="pi pi-chevron-right" aria-hidden="true" />
			</button>
		</div>
		<span v-if="showDocumentNavigation && changed" class="inline-page-navigation__status" role="status">List changed — return to list</span>
		<span v-else-if="showDocumentNavigation && error" class="inline-page-navigation__status" role="status">Navigation unavailable</span>
	</nav>
</template>

<script setup>
import { computed, nextTick, toRef } from "vue"
import { RouterLink } from "vue-router"

import { useDocumentListNavigation } from "../../composables/useDocumentListNavigation.js"
import { usePageNavigation } from "./pageNavigationContext.js"
import { isLockedExit } from "../../router/departmentLock.js"

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

.inline-page-navigation__back {
	display: inline-grid;
	width: 38px;
	height: 38px;
	color: var(--erp-text-muted);
	text-decoration: none;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	place-items: center;
	transition: color var(--erp-transition-fast), border-color var(--erp-transition-fast), background var(--erp-transition-fast);
}

.inline-page-navigation__back:hover {
	color: var(--erp-accent-dark);
	border-color: color-mix(in srgb, var(--erp-accent) 36%, var(--erp-border));
	background: var(--erp-accent-soft);
}

.inline-page-navigation__back:focus-visible {
	outline: 3px solid color-mix(in srgb, var(--erp-accent) 24%, transparent);
	outline-offset: 2px;
}

.inline-page-navigation__documents {
	display: inline-flex;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.inline-page-navigation__document {
	display: inline-grid;
	width: 34px;
	height: 36px;
	padding: 0;
	color: var(--erp-text-muted);
	border: 0;
	background: transparent;
	place-items: center;
	cursor: pointer;
}

.inline-page-navigation__document + .inline-page-navigation__document { border-left: 1px solid var(--erp-border); }
.inline-page-navigation__document:not(:disabled):hover { color: var(--erp-accent-dark); background: var(--erp-accent-soft); }
.inline-page-navigation__document:disabled { color: color-mix(in srgb, var(--erp-text-muted) 45%, transparent); cursor: not-allowed; }
.inline-page-navigation__document:focus-visible { position: relative; z-index: 1; outline: 3px solid color-mix(in srgb, var(--erp-accent) 24%, transparent); outline-offset: -3px; }
.inline-page-navigation__status { max-width: 190px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 650; line-height: 1.2; }

@media (max-width: 620px), (pointer: coarse) {
	.inline-page-navigation__back { width: 44px; height: 44px; }
	.inline-page-navigation__document { width: 44px; height: 44px; }
	.inline-page-navigation__status { position: absolute; overflow: hidden; width: 1px; height: 1px; padding: 0; white-space: nowrap; clip: rect(0, 0, 0, 0); clip-path: inset(50%); }
}
</style>

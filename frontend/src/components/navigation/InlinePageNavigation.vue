<template>
	<nav v-if="inline" class="inline-page-navigation" :aria-label="`Back to ${backLabel}`">
		<RouterLink
			class="inline-page-navigation__back"
			:to="backTo"
			:aria-label="`Back to ${backLabel}`"
			:title="`Back to ${backLabel}`"
			:aria-controls="titleTarget || undefined"
		>
			<i class="pi pi-arrow-left" aria-hidden="true" />
		</RouterLink>
	</nav>
</template>

<script setup>
import { computed } from "vue"
import { RouterLink } from "vue-router"

import { usePageNavigation } from "./pageNavigationContext.js"

defineProps({
	showDocumentNavigation: { type: Boolean, default: false },
	navigationDisabled: { type: Boolean, default: false },
	titleTarget: { type: String, default: "" },
})

const context = usePageNavigation()
const inline = computed(() => Boolean(context?.inline?.value))
const backTo = computed(() => context?.backTo?.value || "/")
const backLabel = computed(() => context?.backLabel?.value || "Workspaces")
</script>

<style scoped>
.inline-page-navigation {
	display: inline-flex;
	flex: 0 0 auto;
	align-items: center;
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

@media (max-width: 620px), (pointer: coarse) {
	.inline-page-navigation__back { width: 44px; height: 44px; }
}
</style>

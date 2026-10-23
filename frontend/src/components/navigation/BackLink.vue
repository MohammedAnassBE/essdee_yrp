<template>
	<RouterLink v-if="!isLockedExit(to)" class="back-link-button" :to="to" :aria-label="`Back to ${label}`" :title="`Back to ${label}`">
		<i class="pi pi-arrow-left" aria-hidden="true" />
	</RouterLink>
</template>

<script setup>
import { RouterLink } from "vue-router"

import { isLockedExit } from "../../router/departmentLock.js"

defineProps({
	to: { type: [String, Object], required: true },
	label: { type: String, required: true },
})
</script>

<style scoped>
.back-link-button {
	display: inline-grid;
	width: 38px;
	height: 38px;
	flex: 0 0 auto;
	color: var(--erp-accent-ink);
	text-decoration: none;
	background: var(--erp-accent-soft);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-control-radius);
	place-items: center;
	transition: color var(--erp-transition-fast), border-color var(--erp-transition-fast), background var(--erp-transition-fast);
}

.back-link-button .pi { font-size: 15px; font-weight: 700; }

.back-link-button:hover {
	color: var(--erp-accent-strong);
	background: var(--erp-accent-100);
	border-color: var(--erp-accent);
}

.back-link-button:focus-visible {
	outline: none;
	box-shadow: var(--erp-focus-ring);
}

@media (max-width: 620px), (pointer: coarse) {
	.back-link-button { width: 44px; height: 44px; }
}
</style>

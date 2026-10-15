<template>
	<RouterLink v-if="!isLockedExit(to)" class="sewing-back-link" :to="to" :aria-label="`Back to ${label}`" :title="`Back to ${label}`">
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
.sewing-back-link {
	display: inline-grid;
	width: 38px;
	height: 38px;
	flex: 0 0 auto;
	color: var(--erp-text-muted);
	text-decoration: none;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	place-items: center;
	transition: color var(--erp-transition-fast), border-color var(--erp-transition-fast), background var(--erp-transition-fast);
}
.sewing-back-link:hover { color: var(--erp-accent-dark); background: var(--erp-accent-soft); border-color: var(--erp-accent-border); }
.sewing-back-link:focus-visible { outline: 3px solid color-mix(in srgb, var(--erp-accent) 24%, transparent); outline-offset: 2px; }
@media (max-width: 760px), (pointer: coarse) { .sewing-back-link { width: 44px; height: 44px; } }
</style>

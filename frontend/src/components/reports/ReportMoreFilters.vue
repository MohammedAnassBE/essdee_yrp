<template>
	<div class="report-more-filters" :class="{ 'is-open': open }">
		<button type="button" class="report-more-filters__toggle" :aria-expanded="open" :aria-controls="panelId" @click="open = !open">
			<span>More filters</span><small>{{ activeCount ? `${activeCount} active` : "Optional" }}</small><i class="pi pi-chevron-down" aria-hidden="true" />
		</button>
		<div :id="panelId" class="report-more-filters__fields"><slot /></div>
	</div>
</template>

<script setup>
import { ref } from "vue"

/** Optional report filters: on wide screens they flow into the shared filter grid; on narrow screens they fold behind a toggle. */
defineProps({ activeCount: { type: Number, default: 0 } })
const panelId = `report-more-filters-${Math.random().toString(36).slice(2, 8)}`
const open = ref(typeof window === "undefined" || !window.matchMedia?.("(max-width: 430px)").matches)
</script>

<style scoped>
.report-more-filters,
.report-more-filters__fields {
	display: contents;
}

.report-more-filters__toggle {
	display: none;
}

@media (max-width: 800px) {
	.report-more-filters {
		display: block;
		grid-column: 1 / -1;
		border: 1px solid var(--erp-border);
		border-radius: var(--erp-control-radius);
		background: var(--erp-surface);
	}

	.report-more-filters__toggle {
		display: flex;
		width: 100%;
		min-height: 44px;
		align-items: center;
		gap: 8px;
		padding: 0 10px;
		border: 0;
		background: transparent;
		color: var(--erp-text);
		font: inherit;
		font-size: var(--erp-font-size-caption);
		font-weight: 750;
		cursor: pointer;
	}

	.report-more-filters__toggle:focus-visible {
		outline: none;
		box-shadow: var(--erp-focus-ring);
	}

	.report-more-filters__toggle small {
		margin-left: auto;
		color: var(--erp-text-muted);
		font-size: var(--erp-font-size-min);
		font-weight: 650;
	}

	.report-more-filters__toggle i {
		color: var(--erp-text-muted);
		font-size: 11px;
		transition: transform var(--erp-transition-fast);
	}

	.is-open .report-more-filters__toggle i {
		transform: rotate(180deg);
	}

	.report-more-filters__fields {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: var(--erp-space-2) var(--erp-space-3);
		padding: 0 10px 10px;
	}

	.report-more-filters:not(.is-open) .report-more-filters__fields {
		display: none;
	}
}

@media (max-width: 520px) {
	.report-more-filters__fields {
		grid-template-columns: minmax(0, 1fr);
	}
}
</style>

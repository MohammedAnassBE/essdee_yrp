<template>
	<section class="planner-plan-workspace">
		<section class="planner-plan-workspace__strategies" aria-labelledby="planner-strategies-title">
			<header>
				<h2 id="planner-strategies-title">Strategies</h2>
				<strong>{{ successful.length }} plans</strong>
			</header>
			<PlannerStrategies
				compact
				:successful="successful"
				:failed="failed"
				:selected="selected"
				:can-select="canSelect"
				:selecting="selecting"
				@select="$emit('select', $event)"
			/>
		</section>
		<main class="planner-plan-workspace__result"><PlannerLayPlan :result="result" :tolerance="tolerance" /></main>
	</section>
</template>

<script setup>
import PlannerLayPlan from "./PlannerLayPlan.vue"
import PlannerStrategies from "./PlannerStrategies.vue"

defineProps({
	successful: { type: Array, default: () => [] },
	failed: { type: Array, default: () => [] },
	selected: { type: String, default: "" },
	result: { type: Object, default: null },
	tolerance: { type: Number, default: 3 },
	canSelect: Boolean,
	selecting: { type: String, default: "" },
})

defineEmits(["select"])
</script>

<style scoped>
.planner-plan-workspace { display: grid; height: 100%; min-height: 0; overflow: hidden; grid-template-columns: minmax(248px, 286px) minmax(0, 1fr); align-items: stretch; background: var(--erp-surface); }
.planner-plan-workspace__strategies { min-width: 0; min-height: 0; overflow-y: auto; overscroll-behavior: contain; background: var(--erp-surface-soft); border-right: 1px solid var(--erp-border); scrollbar-gutter: stable; }
.planner-plan-workspace__strategies > header { display: flex; min-height: 48px; padding: 8px 12px; align-items: center; justify-content: space-between; gap: 12px; background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border); }
.planner-plan-workspace__strategies h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); letter-spacing: -.01em; }
.planner-plan-workspace__strategies header strong { flex: 0 0 auto; color: var(--erp-accent-dark); font-size: var(--erp-font-size-caption); font-variant-numeric: tabular-nums; }
.planner-plan-workspace__strategies :deep(.planner-strategies) { padding: 10px; }
.planner-plan-workspace__result { min-width: 0; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; }

@media (max-width: 700px) {
	.planner-plan-workspace { height: auto; min-height: 100%; overflow: visible; grid-template-columns: 1fr; }
	.planner-plan-workspace__result { min-height: auto; overflow: visible; }
	.planner-plan-workspace__strategies { min-height: 260px; max-height: min(46dvh, 420px); overflow-y: auto; border-right: 0; border-bottom: 1px solid var(--erp-border); }
}
</style>

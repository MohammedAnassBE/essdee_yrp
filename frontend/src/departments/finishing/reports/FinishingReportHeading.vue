<template>
	<header class="finishing-report-heading">
		<div class="finishing-report-heading__title">
			<h2>{{ title }}</h2>
			<span v-if="period">{{ period }}</span>
		</div>
		<div v-if="$slots.default" class="finishing-report-heading__actions"><slot /></div>
	</header>
</template>

<script setup>
defineProps({
	title: { type: String, required: true },
	period: { type: String, default: "" },
})
</script>

<style scoped>
.finishing-report-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--erp-space-2); }
.finishing-report-heading__title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
.finishing-report-heading h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 700; }
.finishing-report-heading span { color: var(--erp-text-secondary); font-size: var(--erp-font-size-table); font-weight: 600; font-variant-numeric: tabular-nums; }
.finishing-report-heading__actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); }
</style>

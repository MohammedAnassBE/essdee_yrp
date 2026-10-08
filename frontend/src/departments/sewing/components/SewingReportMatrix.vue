<template>
	<div class="sewing-report-matrix erp-table-wrap" role="region" :aria-label="label" tabindex="0">
		<table class="erp-table">
			<caption>{{ label }}</caption>
			<thead><tr><th v-for="column in columns" :key="column.key" scope="col" :class="{ numeric: column.numeric }">{{ column.label }}</th></tr></thead>
			<tbody><tr v-for="(row, index) in rows" :key="index"><td v-for="column in columns" :key="column.key" :class="{ numeric: column.numeric }">{{ format(row[column.key]) }}</td></tr></tbody>
			<tfoot v-if="totals"><tr><th v-for="(column, index) in columns" :key="column.key" :class="{ numeric: column.numeric }" :scope="index === 0 ? 'row' : undefined">{{ index === 0 ? totalLabel : format(totals[column.key]) }}</th></tr></tfoot>
		</table>
	</div>
</template>

<script setup>
defineProps({
	label: { type: String, required: true },
	columns: { type: Array, required: true },
	rows: { type: Array, default: () => [] },
	totals: { type: Object, default: null },
	totalLabel: { type: String, default: "Total" },
})
function format(value) {
	return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : value ?? "—"
}
</script>

<style scoped>
.sewing-report-matrix { width: 100%; max-width: 100%; min-width: 0; max-height: 62vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: var(--erp-font-size-caption); }
caption { text-align: left; padding: 10px 12px; color: var(--erp-text-muted); background: var(--erp-surface); }
th, td { padding: 9px 12px; white-space: nowrap; border-bottom: 1px solid var(--erp-border); text-align: left; }
thead th { position: sticky; top: 0; z-index: 1; color: var(--erp-text-secondary); background: var(--erp-surface-soft); }
tfoot th { background: var(--erp-surface-soft); font-weight: 700; }
.numeric { text-align: right; font-variant-numeric: tabular-nums; }
.sewing-report-matrix:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
</style>

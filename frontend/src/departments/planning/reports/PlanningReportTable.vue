<template>
	<div class="finishing-scroll planning-report-scroll" role="region" tabindex="0" :aria-label="title + ' results'">
		<table class="finishing-table">
			<colgroup><col v-for="column in columns" :key="column.key" :style="{ width: column.width + 'px' }" /></colgroup>
			<thead><tr><th v-for="column in columns" :key="column.key" :class="cellAlign(column)">{{ column.label }}</th></tr></thead>
			<tbody><tr v-for="(row, index) in rows" :key="index" :class="{ 'report-total-row': row.is_total_row }"><td v-for="column in columns" :key="column.key" :class="[cellAlign(column), cellTone(column, row) ? 'planning-tone--' + cellTone(column, row) : '']" :title="cellTone(column, row) || undefined"><RouterLink v-if="cellLink(column, row)" :to="cellLink(column, row)">{{ formattedCell(column, row) }}</RouterLink><template v-else>{{ formattedCell(column, row) }}</template><slot name="annotation" :column="column" :row="row" /></td></tr></tbody>
		</table>
	</div>
</template>

<script setup>
import { RouterLink } from "vue-router"

defineProps({
	title: { type: String, required: true },
	columns: { type: Array, required: true },
	rows: { type: Array, required: true },
	cellAlign: { type: Function, required: true },
	formattedCell: { type: Function, required: true },
	cellTone: { type: Function, default: () => "" },
	cellLink: { type: Function, default: () => "" },
})
</script>

<style scoped>
.planning-report-scroll { max-height: 70vh; }
.planning-tone--pass { background: var(--erp-success-soft); color: var(--erp-success-text); }
.planning-tone--fail { background: var(--erp-danger-soft); color: var(--erp-danger); }
.planning-tone--hold { background: var(--erp-warning-soft); color: var(--erp-warning); }
@media (min-width: 701px) {
	th:first-child, td:first-child { position: sticky; left: 0; background: var(--erp-surface); z-index: 2; }
	thead th:first-child { z-index: 3; }
}
</style>

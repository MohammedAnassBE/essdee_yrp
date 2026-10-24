<template>
	<div class="finishing-scroll planning-report-scroll" role="region" tabindex="0" :aria-label="title + ' results'">
		<table class="finishing-table">
			<colgroup><col v-for="column in columns" :key="column.key" :style="{ width: column.width + 'px' }" /></colgroup>
			<thead><tr><th v-for="column in columns" :key="column.key" :class="cellAlign(column)">{{ column.label }}</th></tr><ReportFilterRow v-if="inlineFilters" :columns="columns" :filter="inlineFilter" /></thead>
			<tbody><tr v-for="(row, index) in renderedRows" :key="index" :class="{ 'report-total-row': row.is_total_row }"><template v-for="(column, columnIndex) in columns" :key="column.key"><td v-if="spanOf(column, row, index)" :rowspan="spanOf(column, row, index) > 1 ? spanOf(column, row, index) : undefined" :class="[cellAlign(column), cellTone(column, row) ? 'planning-tone--' + cellTone(column, row) : '', { 'planning-report-first': columnIndex === 0 }]" :title="cellTone(column, row) || undefined"><RouterLink v-if="cellLink(column, row)" :to="cellLink(column, row)">{{ formattedCell(column, row) }}</RouterLink><template v-else>{{ formattedCell(column, row) }}</template><slot name="annotation" :column="column" :row="row" /></td></template></tr><tr v-if="unrenderedCount" ref="moreRowsSentinel" class="planning-report-more" data-export-ignore><td :colspan="columns.length"><div class="planning-report-more__inner"><span>Showing {{ renderedRows.length.toLocaleString() }} of {{ visibleRows.length.toLocaleString() }} rows</span><Button label="Show more rows" size="small" severity="secondary" text @click="renderMoreRows" /></div></td></tr></tbody>
		</table>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"
import { RouterLink } from "vue-router"

import ReportFilterRow from "../../../components/reports/ReportFilterRow.vue"
import { ROW_RENDER_STEP, useIncrementalRows } from "../../../composables/useIncrementalRows.js"
import { useInlineFilters } from "../../../composables/useInlineFilters.js"

const props = defineProps({
	title: { type: String, required: true },
	columns: { type: Array, required: true },
	rows: { type: Array, required: true },
	cellAlign: { type: Function, required: true },
	formattedCell: { type: Function, required: true },
	cellTone: { type: Function, default: () => "" },
	cellLink: { type: Function, default: () => "" },
	/** Block layouts with rowspans mount every row so no block is cut at the step boundary. */
	cellSpan: { type: Function, default: null },
	cellValue: { type: Function, default: (row, column) => row?.[column.fieldname] },
	/** Off for block layouts whose rowspans or subtotal rows need every row of a block. */
	inlineFilters: { type: Boolean, default: false },
})

const inlineFilter = useInlineFilters(() => props.rows, () => props.columns, {
	cellValue: (row, column) => props.cellValue(row, column),
	cellText: (row, column) => props.formattedCell(column, row),
})
const visibleRows = computed(() => props.inlineFilters ? inlineFilter.filteredRows.value : props.rows)
const spanOf = (column, row, index) => props.cellSpan ? props.cellSpan(column, row, index) : 1
// ReportShell mounts every row before Copy Report or a rendered export reads the table.
const { renderedRows, unrenderedCount, sentinel: moreRowsSentinel, renderMoreRows } = useIncrementalRows(visibleRows, {
	step: props.cellSpan ? Infinity : ROW_RENDER_STEP, resetOn: [() => props.rows, inlineFilter.keywords],
})
</script>

<style scoped>
.planning-report-scroll { max-height: 70vh; }
td[rowspan] { vertical-align: middle; }
.planning-report-more__inner { position: sticky; left: 0; display: inline-flex; align-items: center; gap: var(--erp-space-3); color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.planning-tone--pass { background: var(--erp-success-soft); color: var(--erp-success-text); }
.planning-tone--fail { background: var(--erp-danger-soft); color: var(--erp-danger); }
.planning-tone--hold { background: var(--erp-warning-soft); color: var(--erp-warning); }
@media (min-width: 701px) {
	th:first-child, td.planning-report-first, :deep(.report-filter-row > th:first-child) { position: sticky; left: 0; background: var(--erp-surface); z-index: 2; }
	thead th:first-child { z-index: 3; }
}
</style>

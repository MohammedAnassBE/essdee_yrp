<template>
	<div class="sewing-report-matrix erp-table-wrap" role="region" :aria-label="label" tabindex="0">
		<table class="erp-table report-table" :data-column-layout="layoutKey || label" data-column-order>
			<caption>{{ label }}</caption>
			<thead><tr><th v-for="(column, index) in orderedColumns" :key="column.key" scope="col" :class="[cellClass(column, index), { nowrap: !String(column.label).includes(' ') }]" :style="cellStyle(index)">{{ column.label }}</th></tr><ReportFilterRow v-if="inlineFilters" :columns="orderedColumns" :filter="inlineFilter" :cell-class="cellClass" :cell-style="(column, index) => cellStyle(index)" /></thead>
			<tbody><tr v-for="(row, rowIndex) in visibleRows" :key="row.key ?? rowIndex"><td v-for="(column, index) in orderedColumns" :key="column.key" :class="[cellClass(column, index), cellTone?.(row, column)]" :style="cellStyle(index)" :title="column.width ? format(row[column.key], column) : undefined"><slot :name="`cell-${column.key}`" :row="row">{{ format(row[column.key], column) }}</slot></td></tr></tbody>
			<tfoot v-if="footerTotals"><tr class="report-total-row"><th v-for="(column, index) in orderedColumns" :key="column.key" :class="cellClass(column, index)" :style="cellStyle(index)" :scope="index === totalLabelIndex ? 'row' : undefined">{{ index === totalLabelIndex ? totalLabel : format(footerTotals[column.key]) }}</th></tr></tfoot>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { columnTotal } from "../../../components/reports/inlineFilters.js"
import ReportFilterRow from "../../../components/reports/ReportFilterRow.vue"
import { cellTypeClass } from "../../../composables/reportColumns.js"
import { useInlineFilters } from "../../../composables/useInlineFilters.js"
import { useOrderedColumns } from "../../../composables/useReportColumnLayout.js"
import { formatDisplayByFieldtype } from "../../../utils/dateFormat.js"

const props = defineProps({
	label: { type: String, required: true },
	columns: { type: Array, required: true },
	rows: { type: Array, default: () => [] },
	totals: { type: Object, default: null },
	totalLabel: { type: String, default: "Total" },
	cellTone: { type: Function, default: null },
	/** Off for reports that render one matrix per group. */
	inlineFilters: { type: Boolean, default: false },
	/** Tables sharing a key share column widths and order, e.g. one DPR table per lot. */
	layoutKey: { type: String, default: "" },
})
const orderedColumns = useOrderedColumns(() => props.layoutKey || props.label, () => props.columns, { isPinned: column => Boolean(column.frozen) })
// A moved numeric column keeps its total; the label goes to the first text column.
const totalLabelIndex = computed(() => Math.max(0, orderedColumns.value.findIndex(column => !column.numeric)))
const inlineFilter = useInlineFilters(() => props.rows, () => props.columns, { cellValue: (row, column) => row[column.key], cellText: (row, column) => format(row[column.key], column) })
const visibleRows = computed(() => props.inlineFilters ? inlineFilter.filteredRows.value : props.rows)
// Footer totals are sums of the shown rows, so a column filter recomputes them like Desk's total row.
const footerTotals = computed(() => {
	if (!props.totals || !props.inlineFilters || !inlineFilter.isFiltered.value) return props.totals
	return Object.fromEntries(Object.keys(props.totals).map(key => [key, columnTotal(visibleRows.value.map(row => row[key]), { fieldtype: "Float" }) ?? 0]))
})
// Frozen columns must be a leading run with explicit pixel widths so each sticky left offset is known.
const frozenOffsets = computed(() => {
	const offsets = []
	let left = 0
	for (const column of orderedColumns.value) {
		if (!column.frozen) break
		if (!column.width) throw new Error(`Frozen column "${column.label}" needs a width.`)
		offsets.push(left)
		left += column.width
	}
	return offsets
})
function cellClass(column, index) {
	const frozenCount = frozenOffsets.value.length
	// Short identifiers (Lot, Line, Type) stay on one line; only columns marked wrap may break.
	const typeClass = column.numeric ? "report-cell--num" : (column.fieldtype || column.wrap) ? cellTypeClass(column) : undefined
	return [typeClass, { numeric: column.numeric, sized: column.width, frozen: index < frozenCount, "frozen-last": index === frozenCount - 1, "report-cell--last-column": index === orderedColumns.value.length - 1 }]
}
function cellStyle(index) {
	const column = orderedColumns.value[index]
	if (!column.width) return undefined
	const width = `${column.width}px`
	return { width, minWidth: width, maxWidth: width, left: index < frozenOffsets.value.length ? `${frozenOffsets.value[index]}px` : undefined }
}
function format(value, column) {
	if (typeof value === "number") return value.toLocaleString(undefined, { maximumFractionDigits: 3 })
	return formatDisplayByFieldtype(value, column?.fieldtype) ?? "—"
}
</script>

<style scoped>
.sewing-report-matrix { width: 100%; max-width: 100%; min-width: 0; max-height: 62vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
/* Borders, header, padding and wrapping come from .report-table in reportTables.css. */
table { line-height: var(--erp-line-height-tight); }
caption { text-align: left; padding: 10px 12px; color: var(--erp-text-muted); background: var(--erp-surface); }
th, td { box-sizing: border-box; }
td { background: var(--erp-surface); }
thead th { z-index: 2; border-bottom-color: var(--erp-border-strong); }
/* Header labels wrap at spaces, not at the hyphen in sizes like 8-10. */
.report-table thead th { white-space: normal; }
.report-table thead th.nowrap { white-space: nowrap; }
td.sized { overflow: hidden; text-overflow: ellipsis; }
tfoot th { border-top: 1px solid var(--erp-border-strong); }
.frozen { position: sticky; z-index: 1; }
thead th.frozen, :deep(.report-filter-row > th.frozen) { z-index: 3; }
.frozen-last { border-right: 1px solid var(--erp-border-strong); box-shadow: 4px 0 6px -4px rgb(16 24 40 / 18%); }
@media (max-width: 1100px) {
	td.frozen, tfoot th.frozen { position: static; }
	thead th.frozen, :deep(.report-filter-row > th.frozen) { left: auto !important; z-index: 2; }
	.frozen-last { box-shadow: none; }
}
.numeric { text-align: right; font-variant-numeric: tabular-nums; }
td.negative { color: var(--erp-danger); font-weight: var(--erp-font-weight-semibold); }
.sewing-report-matrix:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
</style>

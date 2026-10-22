<template>
	<div class="sewing-report-matrix erp-table-wrap" role="region" :aria-label="label" tabindex="0">
		<table class="erp-table">
			<caption>{{ label }}</caption>
			<thead><tr><th v-for="(column, index) in columns" :key="column.key" scope="col" :class="cellClass(column, index)" :style="cellStyle(index)">{{ column.label }}</th></tr></thead>
			<tbody><tr v-for="(row, rowIndex) in rows" :key="row.key ?? rowIndex"><td v-for="(column, index) in columns" :key="column.key" :class="[cellClass(column, index), cellTone?.(row, column)]" :style="cellStyle(index)" :title="column.width ? format(row[column.key]) : undefined"><slot :name="`cell-${column.key}`" :row="row">{{ format(row[column.key]) }}</slot></td></tr></tbody>
			<tfoot v-if="totals"><tr><th v-for="(column, index) in columns" :key="column.key" :class="cellClass(column, index)" :style="cellStyle(index)" :scope="index === 0 ? 'row' : undefined">{{ index === 0 ? totalLabel : format(totals[column.key]) }}</th></tr></tfoot>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	label: { type: String, required: true },
	columns: { type: Array, required: true },
	rows: { type: Array, default: () => [] },
	totals: { type: Object, default: null },
	totalLabel: { type: String, default: "Total" },
	cellTone: { type: Function, default: null },
})
// Frozen columns must be a leading run with explicit pixel widths so each sticky left offset is known.
const frozenOffsets = computed(() => {
	const offsets = []
	let left = 0
	for (const column of props.columns) {
		if (!column.frozen) break
		if (!column.width) throw new Error(`Frozen column "${column.label}" needs a width.`)
		offsets.push(left)
		left += column.width
	}
	return offsets
})
function cellClass(column, index) {
	return { numeric: column.numeric, sized: column.width, frozen: index < frozenOffsets.value.length, "frozen-last": index === frozenOffsets.value.length - 1 }
}
function cellStyle(index) {
	const column = props.columns[index]
	if (!column.width) return undefined
	const width = `${column.width}px`
	return { width, minWidth: width, maxWidth: width, left: index < frozenOffsets.value.length ? `${frozenOffsets.value[index]}px` : undefined }
}
function format(value) {
	return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : value ?? "—"
}
</script>

<style scoped>
.sewing-report-matrix { width: 100%; max-width: 100%; min-width: 0; max-height: 62vh; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
table { width: 100%; border-collapse: separate; border-spacing: 0; color: var(--erp-text); font-size: var(--erp-font-size-table); line-height: var(--erp-line-height-tight); }
caption { text-align: left; padding: 10px 12px; color: var(--erp-text-muted); background: var(--erp-surface); }
th, td { box-sizing: border-box; padding: 9px 12px; white-space: nowrap; border-bottom: 1px solid var(--erp-border); text-align: left; }
td { background: var(--erp-surface); }
thead th { position: sticky; top: 0; z-index: 2; color: var(--erp-text); font-weight: var(--erp-font-weight-semibold); vertical-align: bottom; background: var(--erp-surface-muted); border-bottom-color: var(--erp-border-strong); }
thead th.sized { white-space: normal; }
td.sized { overflow: hidden; text-overflow: ellipsis; }
tfoot th { color: var(--erp-text); background: var(--erp-surface-muted); font-weight: var(--erp-font-weight-bold); }
.frozen { position: sticky; z-index: 1; }
thead th.frozen { z-index: 3; }
.frozen-last { border-right: 1px solid var(--erp-border-strong); box-shadow: 4px 0 6px -4px rgb(16 24 40 / 18%); }
@media (max-width: 1100px) {
	td.frozen, tfoot th.frozen { position: static; }
	thead th.frozen { left: auto !important; z-index: 2; }
	.frozen-last { box-shadow: none; }
}
.numeric { text-align: right; font-variant-numeric: tabular-nums; }
td.negative { color: var(--erp-danger); font-weight: var(--erp-font-weight-semibold); }
.sewing-report-matrix:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
</style>

<template>
	<tr ref="filterRow" class="report-filter-row" data-export-ignore :style="{ '--report-filter-top': `${stickyTop}px` }">
		<th v-for="(column, index) in columns" :key="filter.columnKey(column)" :class="['report-filter-row__cell', cellClass(column, index)]" :style="cellStyle(column, index)">
			<input
				v-if="column.filterable !== false"
				class="report-filter-row__input"
				type="search"
				autocomplete="off"
				spellcheck="false"
				:value="filter.inputs[filter.columnKey(column)] ?? ''"
				:aria-label="`Filter ${column.label || column.fieldname}`"
				@input="filter.setFilter(filter.columnKey(column), $event.target.value)"
				@keydown.enter.prevent="filter.applyKeywords()"
				@keydown.esc="clearColumn(column, $event)"
			/>
		</th>
	</tr>
	<tr v-if="filter.isFiltered.value && !filter.matchingCount.value" class="report-filter-row__empty" data-export-ignore>
		<td :colspan="columns.length">
			<div class="report-filter-row__empty-inner">
				<span>No rows match the column filters.</span>
				<button type="button" class="report-filter-row__clear" @click="filter.clearFilters()">Clear filters</button>
			</div>
		</td>
	</tr>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"

const props = defineProps({
	columns: { type: Array, required: true },
	/** The object returned by useInlineFilters. */
	filter: { type: Object, required: true },
	cellClass: { type: Function, default: () => "" },
	cellStyle: { type: Function, default: () => undefined },
})

const filterRow = ref(null)
const stickyTop = ref(0)
let observer = null

function clearColumn(column, event) {
	if (!event.target.value) return
	event.target.value = ""
	props.filter.setFilter(props.filter.columnKey(column), "")
}

// Header cells are sticky at top 0, so this row sticks just below every header row above it.
function measureStickyTop() {
	stickyTop.value = filterRow.value?.offsetTop || 0
}

onMounted(() => {
	const head = filterRow.value?.parentElement
	if (!head || typeof ResizeObserver === "undefined") return
	observer = new ResizeObserver(measureStickyTop)
	observer.observe(head)
	measureStickyTop()
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<style>
tr.report-filter-row > th.report-filter-row__cell {
	position: sticky;
	z-index: 2;
	top: var(--report-filter-top, 0);
	background: var(--erp-surface);
	padding: 4px 6px;
	text-transform: none;
	letter-spacing: 0;
}

.report-filter-row__input {
	box-sizing: border-box;
	width: 100%;
	min-width: 48px;
	height: 28px;
	padding: 0 7px;
	color: var(--erp-text);
	font: inherit;
	font-size: var(--erp-font-size-caption);
	font-weight: 400;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	outline: none;
}


.report-filter-row__input:focus-visible {
	border-color: var(--erp-accent);
	box-shadow: 0 0 0 2px color-mix(in srgb, var(--erp-accent) 22%, transparent);
}

.report-filter-row__empty td {
	padding: var(--erp-space-4);
}

.report-filter-row__empty-inner {
	position: sticky;
	left: var(--erp-space-4);
	display: inline-flex;
	align-items: center;
	gap: var(--erp-space-3);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-filter-row__clear {
	padding: 0;
	color: var(--erp-accent);
	font: inherit;
	font-weight: var(--erp-font-weight-semibold);
	background: none;
	border: 0;
	cursor: pointer;
}
</style>

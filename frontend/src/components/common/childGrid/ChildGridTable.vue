<template>
	<div ref="root" v-entry-table="{ add: canAdd ? add : null, isRowBlank: rowIsBlank, fixed: false }" class="child-grid-table" :style="widthVariables">
		<DataTable
			:value="rows"
			size="small"
			scrollable
			class="erp-data-table child-grid-table__table"
			:table-style="{ tableLayout: 'fixed', width: `${tableWidth}px` }"
			:pt="{ tableContainer: { role: 'region', 'aria-label': `${title} rows` } }"
		>
			<Column v-if="showIndex" column-key="__index" header="#" :style="widthStyle(`${INDEX_WIDTH}px`)" class="child-grid-table__index">
				<template #body="{ index }">{{ index + 1 }}</template>
			</Column>
			<Column v-for="(column, index) in visibleColumns" :key="column.key" :column-key="column.key" :style="widthStyle(`var(--child-grid-column-${index})`)">
				<template #header><span class="child-grid-table__label" :title="column.label">{{ column.label }}<span v-if="column.reqd" class="erp-required-mark" aria-hidden="true">*</span></span></template>
				<template #body="slotProps"><slot :name="`cell-${column.key}`" v-bind="slotProps" :column="column">{{ slotProps.data[column.key] }}</slot></template>
			</Column>
			<Column v-if="hasTrailingColumn" column-key="__settings" :style="widthStyle(`${trailingWidth}px`)" class="child-grid-table__trailing">
				<template #header><ChildGridSettings v-if="grid.canConfigure.value" :title="title" :columns="columns" :visible-columns="visibleColumns" :save="grid.save" :reset="grid.reset" /></template>
				<template #body="slotProps"><slot name="row-actions" v-bind="slotProps" /></template>
			</Column>
			<template #empty><slot name="empty">No rows.</slot></template>
		</DataTable>
	</div>
</template>

<script setup>
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import { computed, ref, useSlots } from "vue"

import ChildGridSettings from "./ChildGridSettings.vue"
import { isRowBlank, layoutWidths } from "./childGridColumns.js"
import { vEntryTable } from "./entryTable.js"
import { useContainerWidth, useGridColumns } from "./useGridColumns.js"

const INDEX_WIDTH = 48

const props = defineProps({
	rows: { type: Array, default: () => [] },
	columns: { type: Array, required: true },
	title: { type: String, default: "Table" },
	parentDoctype: { type: String, default: "" },
	childDoctype: { type: String, default: "" },
	canAdd: { type: Boolean, default: false },
	add: { type: Function, default: null },
	showIndex: { type: Boolean, default: false },
	actionsWidth: { type: Number, default: 52 },
})

const slots = useSlots()
const grid = useGridColumns(() => props.columns, { parentDoctype: () => props.parentDoctype, childDoctype: () => props.childDoctype })
const visibleColumns = grid.visibleColumns
const hasTrailingColumn = computed(() => Boolean(slots["row-actions"]) || grid.canConfigure.value)
const trailingWidth = computed(() => Math.max(slots["row-actions"] ? props.actionsWidth : 0, grid.canConfigure.value ? 44 : 0))
const root = ref(null)
const containerWidth = useContainerWidth(root)
const reservedWidth = computed(() => (props.showIndex ? INDEX_WIDTH : 0) + (hasTrailingColumn.value ? trailingWidth.value : 0))
const columnWidths = computed(() => layoutWidths(visibleColumns.value, Math.max(containerWidth.value - 2, 0), reservedWidth.value))
const tableWidth = computed(() => columnWidths.value.reduce((sum, width) => sum + width, 0) + reservedWidth.value)

// Columns read widths through CSS variables: DataTable remounts every cell when its column list re-renders.
const widthVariables = computed(() => Object.fromEntries(columnWidths.value.map((width, index) => [`--child-grid-column-${index}`, `${width}px`])))

function widthStyle(width) {
	return { width, minWidth: width, maxWidth: width }
}

function rowIsBlank(index) {
	return isRowBlank(props.rows[index], visibleColumns.value)
}
</script>

<style scoped>
.child-grid-table { min-width: 0; }
.child-grid-table__table :deep(.p-datatable-table-container) { max-width: 100%; }
.child-grid-table__table :deep(th), .child-grid-table__table :deep(td) { overflow: hidden; }
.child-grid-table__table :deep(td) :is(.p-inputnumber, .p-inputtext, .p-autocomplete, .p-select, .common-field, .link-field__control) { width: 100%; min-width: 0; max-width: 100%; }
.child-grid-table__table :deep(td .p-inputnumber-input) { width: 100%; min-width: 0; }
.child-grid-table__label { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.child-grid-table__table :deep(.child-grid-table__trailing) { padding-inline: 2px; text-align: center; }
.child-grid-table__table :deep(.child-grid-table__index) { color: var(--erp-text-muted); text-align: right; }
</style>

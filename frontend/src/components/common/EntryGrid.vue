<template>
	<section ref="gridRoot" tabindex="-1" class="entry-grid" :class="{ 'entry-grid--readonly': readonly }" :aria-label="ariaLabel || title">
		<header v-if="hasToolbar" class="entry-grid__toolbar">
			<strong v-if="title">{{ title }}</strong>
			<span v-if="unitHint" class="entry-grid__unit">{{ unitHint }}</span>
			<template v-if="!readonly && tools.length">
				<span class="entry-grid__separator" aria-hidden="true" />
				<Button v-for="tool in tools" :key="tool" :label="TOOL_LABELS[tool]" :icon="TOOL_ICONS[tool]" text severity="secondary" size="small" @mousedown.prevent @click="runTool(tool)" />
			</template>
			<slot name="toolbar" />
			<span class="entry-grid__meta" role="status">{{ metaText }}</span>
		</header>
		<div ref="scroller" class="entry-grid__scroll">
			<table
				ref="table"
				class="entry-grid__table"
				role="grid"
				:aria-label="ariaLabel || title"
				:aria-rowcount="rows.length + 1"
				:aria-colcount="columns.length + 1"
				:aria-readonly="readonly || undefined"
				:style="{ minWidth: tableMinWidth }"
				@keydown="onKeydown"
				@copy="onCopy"
				@paste="onPaste"
				@entry-grid-finish-edit="finishCellEdit"
			>
				<thead>
					<tr role="row" aria-rowindex="1">
						<th scope="col" class="entry-grid__corner" role="columnheader">{{ rowHeaderLabel }}</th>
						<th v-for="column in columns" :key="column.key" scope="col" role="columnheader" :class="alignClass(column)" :style="{ minWidth: `${columnMinWidth(column)}px` }">{{ column.label }}</th>
						<th v-if="hasRowTotals" scope="col" class="entry-grid__number">{{ totalLabel }}</th>
						<th v-if="removableRows && !readonly" scope="col"><span class="entry-grid__sr">Remove</span></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, rowIndex) in rows" :key="row.key" role="row" :aria-rowindex="rowIndex + 2">
						<th scope="row" role="rowheader" class="entry-grid__row-header">{{ row.label }}</th>
						<td
							v-for="(column, colIndex) in columns"
							:key="column.key"
							role="gridcell"
							:class="['entry-grid__cell', alignClass(column)]"
							:data-row="rowIndex"
							:data-col="colIndex"
							:tabindex="isActive(rowIndex, colIndex) ? 0 : -1"
							:aria-selected="isSelected(rowIndex, colIndex) || undefined"
							:aria-readonly="!isEditable(rowIndex, colIndex) || undefined"
							:aria-invalid="Boolean(cellError(rowIndex, colIndex)) || undefined"
							:title="cellError(rowIndex, colIndex) || undefined"
							@mousedown="onCellMousedown($event, rowIndex, colIndex)"
							@mouseenter="onCellMouseenter(rowIndex, colIndex)"
							@dblclick="startEdit('edit')"
						>
							<template v-if="isEditing(rowIndex, colIndex)">
								<LinkField v-if="column.type === 'link'" ref="editor" class="entry-grid__link" :model-value="editText" :doctype="column.doctype || ''" :filters="column.filters || {}" :show-open-button="false" :aria-label="cellLabel(row, column)" :invalid="Boolean(cellError(rowIndex, colIndex))" :aria-describedby="cellError(rowIndex, colIndex) ? `${gridId}-error` : undefined" :show-validation-message="false" @validation="linkValidation" @select="commitLink($event.name)" />
								<select v-else-if="usesNativeSelect(column)" ref="editor" v-model="editText" class="entry-grid__box entry-grid__input" :aria-label="cellLabel(row, column)" @keydown="onEditorKeydown" @blur="commitEdit()">
									<option value="" />
									<option v-for="option in normalizedOptions(column)" :key="option.value" :value="option.value">{{ option.label }}</option>
								</select>
								<template v-else>
									<input ref="editor" v-model="editText" class="entry-grid__box entry-grid__input" :class="alignClass(column)" :inputmode="column.type === 'number' ? 'decimal' : undefined" :list="usesDatalist(column) ? datalistId(colIndex) : undefined" :aria-label="cellLabel(row, column)" @keydown="onEditorKeydown" @blur="commitEdit()">
									<datalist v-if="usesDatalist(column)" :id="datalistId(colIndex)"><option v-for="option in normalizedOptions(column)" :key="option.value" :value="option.value">{{ option.label }}</option></datalist>
								</template>
							</template>
							<div v-else class="entry-grid__box" :class="boxClasses(rowIndex, colIndex)" :title="cellError(rowIndex, colIndex) || derivedTitle(rowIndex, colIndex)">{{ cellText(rowIndex, colIndex) }}</div>
						</td>
						<td v-if="hasRowTotals" class="entry-grid__total entry-grid__number">{{ formatTotal(rowTotal(modelValue, row, columns)) }}</td>
						<td v-if="removableRows && !readonly" class="entry-grid__remove">
							<Button icon="pi pi-times" text rounded severity="secondary" size="small" :aria-label="`Remove ${row.label}`" @click="emit('remove-row', row.key)" />
						</td>
					</tr>
				</tbody>
				<tfoot v-if="hasColumnTotals">
					<tr role="row">
						<th scope="row" class="entry-grid__row-header">{{ totalLabel }}</th>
						<td v-for="column in columns" :key="column.key" class="entry-grid__footer-total" :class="alignClass(column)">{{ column.type === "number" ? formatTotal(totals_[column.key]) : "" }}</td>
						<td v-if="hasRowTotals" class="entry-grid__footer-total entry-grid__number">{{ formatTotal(grandTotal) }}</td>
						<td v-if="removableRows && !readonly" />
					</tr>
				</tfoot>
			</table>
		</div>
		<p :id="`${gridId}-error`" class="entry-grid__error" role="status" aria-live="polite">{{ activeError }}</p>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, nextTick, onBeforeUnmount, ref, useId, watch } from "vue"

import LinkField from "./LinkField.vue"
import {
	ENTRY_GRID_INVALID_KEY,
	applyBlock,
	cellValue,
	clearRange,
	coerceCell,
	columnMinWidth,
	columnTotals,
	displayCell,
	fillDown,
	fillRight,
	isCellEditable,
	isPrintableKey,
	moveCell,
	normalizeRange,
	parsePastedBlock,
	pasteReportText,
	rangeMatrix,
	rangeSize,
	rowTotal,
	sameForAll,
	setCells,
	toTsv,
} from "./entryGrid.js"

const TOOL_LABELS = { fillRight: "Fill right", fillDown: "Fill down", sameForAll: "Same for all colours", paste: "Paste", clear: "Clear" }
const TOOL_ICONS = { fillRight: "pi pi-arrow-right", fillDown: "pi pi-arrow-down", sameForAll: "pi pi-clone", paste: "pi pi-clipboard", clear: "pi pi-eraser" }
const ARROWS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" }
const ROW_HEADER_WIDTH = 140

const props = defineProps({
	rows: { type: Array, default: () => [] },
	columns: { type: Array, default: () => [] },
	modelValue: { type: Object, default: () => ({}) },
	readonly: { type: Boolean, default: false },
	title: { type: String, default: "" },
	unitHint: { type: String, default: "" },
	meta: { type: String, default: "" },
	ariaLabel: { type: String, default: "" },
	rowHeaderLabel: { type: String, default: "" },
	errors: { type: Object, default: () => ({}) },
	derived: { type: Object, default: () => ({}) },
	totals: { type: String, default: "", validator: (value) => ["", "row", "column", "both"].includes(value) },
	totalLabel: { type: String, default: "Total" },
	toolbar: { type: Array, default: () => ["fillRight", "fillDown", "paste", "clear"] },
	removableRows: { type: Boolean, default: false },
	validationField: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue", "change", "paste-report", "remove-row"])

const gridId = `entry-grid-${useId()}`
const gridRoot = ref(null)
const table = ref(null)
const scroller = ref(null)
const editor = ref(null)
const active = ref({ row: 0, col: 0 })
const anchor = ref({ row: 0, col: 0 })
const editing = ref("")
const editText = ref("")
const report = ref("")
const invalidCells = ref({})
let dragging = false

const activeError = computed(() => cellError(active.value.row, active.value.col))
const tools = computed(() => props.toolbar)
const hasToolbar = computed(() => Boolean(props.title || props.meta || tools.value.length))
const range = computed(() => normalizeRange(anchor.value, active.value))
const selectedCount = computed(() => { const size = rangeSize(range.value); return size.rows * size.cols })
const metaText = computed(() => selectedCount.value > 1 ? `${selectedCount.value} cells selected` : report.value || props.meta)
const hasRowTotals = computed(() => ["column", "both"].includes(props.totals))
const hasColumnTotals = computed(() => ["row", "both"].includes(props.totals))
const totals_ = computed(() => columnTotals(props.modelValue, props.rows, props.columns))
const grandTotal = computed(() => Object.values(totals_.value).reduce((sum, value) => sum + value, 0))
const tableMinWidth = computed(() => `max(100%, ${ROW_HEADER_WIDTH + props.columns.reduce((sum, column) => sum + columnMinWidth(column), 0)}px)`)

watch(() => [props.rows.length, props.columns.length], clampActive)

const invalidRegistry = inject(ENTRY_GRID_INVALID_KEY, null)
const liveInvalidCells = computed(() => {
	const rowKeys = new Set(props.rows.map((row) => row.key))
	const colKeys = new Set(props.columns.map((column) => column.key))
	return Object.values(invalidCells.value).filter((cell) => rowKeys.has(cell.rowKey) && colKeys.has(cell.colKey))
})
if (invalidRegistry) watch(liveInvalidCells, (cells) => invalidRegistry.report(gridId, cells.length, {
	field: props.validationField, cells, focusCell,
}), { immediate: true })

function clampActive() {
	const row = Math.min(active.value.row, Math.max(props.rows.length - 1, 0))
	const col = Math.min(active.value.col, Math.max(props.columns.length - 1, 0))
	active.value = { row, col }
	anchor.value = { row, col }
}
function cellKey(row, col) { return `${props.rows[row]?.key}\u001f${props.columns[col]?.key}` }
function isEditable(row, col) { return !props.readonly && isCellEditable(props.rows, props.columns, row, col) }
function isActive(row, col) { return active.value.row === row && active.value.col === col }
function isEditing(row, col) { return Boolean(editing.value) && isActive(row, col) }
function isSelected(row, col) {
	const { top, bottom, left, right } = range.value
	return selectedCount.value > 1 && row >= top && row <= bottom && col >= left && col <= right
}
function alignClass(column) { return column.align === "right" || (column.type === "number" && column.align !== "left") ? "entry-grid__number" : "" }
function normalizedOptions(column) { return (column.options || []).map((option) => typeof option === "object" ? option : { value: option, label: option }) }
function usesNativeSelect(column) { return ["select", "value"].includes(column.type) && normalizedOptions(column).length <= 30 }
function usesDatalist(column) { return ["select", "value"].includes(column.type) && normalizedOptions(column).length > 30 }
function datalistId(col) { return `${gridId}-options-${col}` }
function cellLabel(row, column) { return `${row.label} ${column.label}` }
function rawValue(row, col) { return cellValue(props.modelValue, props.rows[row].key, props.columns[col].key) }
function cellError(row, col) {
	return invalidCells.value[cellKey(row, col)]?.message || props.errors?.[props.rows[row]?.key]?.[props.columns[col]?.key] || ""
}
function derivedTitle(row, col) {
	const value = props.derived?.[props.rows[row].key]?.[props.columns[col].key]
	return typeof value === "string" ? value : ""
}
function cellText(row, col) {
	const invalid = invalidCells.value[cellKey(row, col)]
	return invalid ? invalid.value : displayCell(props.columns[col], rawValue(row, col))
}
function boxClasses(row, col) {
	return {
		"is-active": isActive(row, col),
		"is-selected": isSelected(row, col),
		"is-error": Boolean(cellError(row, col)),
		"is-derived": Boolean(props.derived?.[props.rows[row].key]?.[props.columns[col].key]),
		"is-readonly": !isEditable(row, col),
	}
}
function formatTotal(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 4 }) }

function focusActive() {
	nextTick(() => {
		const cell = table.value?.querySelector(`td[data-row="${active.value.row}"][data-col="${active.value.col}"]`)
		cell?.focus({ preventScroll: true })
		cell?.scrollIntoView?.({ block: "nearest", inline: "nearest" })
	})
}
function select(position, extend = false) {
	active.value = position
	if (!extend) anchor.value = position
	focusActive()
}
function focusCell(rowKey, colKey) {
	const row = rowKey == null ? 0 : props.rows.findIndex((candidate) => candidate.key === rowKey)
	const col = colKey == null || colKey === '' ? 0 : props.columns.findIndex((candidate) => candidate.key === colKey)
	if (row < 0 || col < 0 || !props.rows.length || !props.columns.length) return false
	select({ row, col })
	return true
}

function emitChanges(model, changes) {
	if (!changes.length) return
	for (const change of changes) delete invalidCells.value[`${change.rowKey}\u001f${change.colKey}`]
	emit("update:modelValue", model)
	emit("change", changes)
}
function markInvalid(cells) {
	invalidCells.value = { ...invalidCells.value, ...Object.fromEntries(cells.map((cell) => [`${cell.rowKey}\u001f${cell.colKey}`, cell])) }
}

function startEdit(mode, initial = null) {
	const { row, col } = active.value
	if (!isEditable(row, col)) return
	const column = props.columns[col]
	if (column.type === "check") { toggleCheck(); return }
	editing.value = mode
	const current = rawValue(row, col)
	editText.value = initial ?? (current === null ? "" : String(current))
	nextTick(() => {
		const element = Array.isArray(editor.value) ? editor.value[0] : editor.value
		element?.focus()
		if (mode === "edit" && element?.select) element.select()
	})
}
function stopEdit() {
	editing.value = ""
	focusActive()
}
function finishCellEdit() {
	if (!editing.value) return
	const { row, col } = active.value
	if (props.columns[col].type !== "link") { commitEdit(); return }
	const element = Array.isArray(editor.value) ? editor.value[0] : editor.value
	const value = element?.finishEdit()
	delete invalidCells.value[cellKey(row, col)]
	if (value != null) {
		editText.value = value
		commitEdit(null, { picked: true, focus: false })
	} else editing.value = ""
}
function commitEdit(direction = null, { picked = false, focus = true } = {}) {
	if (!editing.value) return
	const { row, col } = active.value
	const column = props.columns[col]
	if (column.type === "link" && !picked) { stopEdit(); return }
	const { value, error } = coerceCell(column, editText.value)
	const cell = { rowKey: props.rows[row].key, colKey: column.key }
	if (error) markInvalid([{ ...cell, value: editText.value, message: error }])
	else if (value !== rawValue(row, col) || invalidCells.value[cellKey(row, col)]) emitChanges(setCells(props.modelValue, [{ ...cell, value }]), [{ ...cell, value }])
	editing.value = ""
	if (direction) move(direction)
	else if (focus) focusActive()
}
function linkValidation({ message, query }) {
	const { row, col } = active.value
	if (!editing.value || !props.rows[row] || !props.columns[col]) return
	if (message) markInvalid([{ rowKey: props.rows[row].key, colKey: props.columns[col].key, value: query, message }])
	else delete invalidCells.value[cellKey(row, col)]
}
function commitLink(value) {
	editText.value = value || ""
	commitEdit(null, { picked: true })
}
function toggleCheck() {
	const { row, col } = active.value
	const cell = { rowKey: props.rows[row].key, colKey: props.columns[col].key, value: Number(rawValue(row, col)) ? 0 : 1 }
	emitChanges(setCells(props.modelValue, [cell]), [cell])
}

function move(direction, extend = false) {
	const bounds = { rows: props.rows.length, cols: props.columns.length }
	select(moveCell(active.value, direction, bounds, isEditable), extend)
}
function tabTarget(backwards) {
	const bounds = { rows: props.rows.length, cols: props.columns.length }
	const next = moveCell(active.value, backwards ? "previous" : "next", bounds, isEditable)
	const index = (cell) => cell.row * bounds.cols + cell.col
	const wrapped = backwards ? index(next) >= index(active.value) : index(next) <= index(active.value)
	return wrapped ? null : next
}

function onEditorKeydown(event) {
	if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); stopEdit(); return }
	if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); commitEdit(event.shiftKey ? "up" : "down"); return }
	if (event.key === "Tab") {
		const target = tabTarget(event.shiftKey)
		event.stopPropagation()
		if (!target) { commitEdit(); return }
		event.preventDefault()
		commitEdit()
		select(target)
		return
	}
	if (editing.value === "replace" && ARROWS[event.key] && !event.altKey) {
		event.preventDefault(); event.stopPropagation(); commitEdit(ARROWS[event.key])
	}
}

function onKeydown(event) {
	if (editing.value || !props.rows.length || !props.columns.length) {
		if (editing.value && event.key === "Escape") { event.preventDefault(); stopEdit() }
		return
	}
	if (event.altKey || event.defaultPrevented) return
	if (handleShortcut(event)) return
	if (ARROWS[event.key]) { event.preventDefault(); move(ARROWS[event.key], event.shiftKey); return }
	if (event.key === "Tab") { onTab(event); return }
	if (event.key === "Enter") { event.preventDefault(); move(event.shiftKey ? "up" : "down"); return }
	if (props.readonly) return
	if (event.key === "F2") { event.preventDefault(); startEdit("edit"); return }
	if (event.key === " " && props.columns[active.value.col]?.type === "check") { event.preventDefault(); toggleCheck(); return }
	if (["Delete", "Backspace"].includes(event.key)) { event.preventDefault(); runTool("clear"); return }
	if (isPrintableKey(event)) { event.preventDefault(); startEdit("replace", event.key) }
}
function onTab(event) {
	const target = tabTarget(event.shiftKey)
	if (!target) return
	event.preventDefault()
	select(target)
}
function handleShortcut(event) {
	if (!(event.ctrlKey || event.metaKey) || props.readonly) return false
	const key = event.key.toLowerCase()
	if (key === "d") { event.preventDefault(); runTool("fillDown"); return true }
	if (key === "r") { event.preventDefault(); runTool("fillRight"); return true }
	return false
}

function runTool(tool) {
	if (props.readonly || !props.rows.length) return
	if (tool === "paste") { pasteFromClipboard(); return }
	const handlers = { fillRight, fillDown, sameForAll, clear: clearRange }
	const result = handlers[tool](props.modelValue, props.rows, props.columns, range.value)
	emitChanges(result.model, result.changes)
	focusActive()
}
async function pasteFromClipboard() {
	if (!navigator.clipboard?.readText) { report.value = "Press Ctrl+V to paste"; return }
	try { pasteText(await navigator.clipboard.readText()) } catch { report.value = "Press Ctrl+V to paste" }
}
function pasteText(text) {
	const block = parsePastedBlock(text)
	if (!block.length) return
	const result = applyBlock(props.modelValue, props.rows, props.columns, { row: range.value.top, col: range.value.left }, block)
	const summary = { rows: block.length, cols: Math.max(...block.map((line) => line.length)), applied: result.applied, skipped: result.skipped, readonly: result.readonly, invalid: result.invalid }
	markInvalid(result.invalid)
	emitChanges(result.model, result.changes)
	report.value = pasteReportText(summary)
	emit("paste-report", summary)
	focusActive()
}
function onPaste(event) {
	if (editing.value || props.readonly) return
	event.preventDefault()
	pasteText(event.clipboardData?.getData("text/plain") || "")
}
function onCopy(event) {
	if (editing.value) return
	event.preventDefault()
	event.clipboardData?.setData("text/plain", toTsv(rangeMatrix(props.modelValue, props.rows, props.columns, range.value)))
}

function onCellMousedown(event, row, col) {
	if (isEditing(row, col)) return
	if (editing.value) commitEdit()
	if (event.button !== 0) return
	event.preventDefault()
	dragging = true
	select({ row, col }, event.shiftKey)
	window.addEventListener("mouseup", stopDragging, { once: true })
}
function onCellMouseenter(row, col) {
	if (dragging) { active.value = { row, col } }
}
function stopDragging() { dragging = false }

onBeforeUnmount(() => {
	window.removeEventListener("mouseup", stopDragging)
	invalidRegistry?.report(gridId, 0)
})
defineExpose({ focusCell })
</script>

<style scoped>
.entry-grid { position: relative; min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.entry-grid + .entry-grid { margin-top: var(--erp-space-3); }
.entry-grid__toolbar { display: flex; min-height: 42px; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 10px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); font-size: var(--erp-font-size-caption); }
.entry-grid__toolbar > strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.entry-grid__unit, .entry-grid__meta { color: var(--erp-text-muted); }
.entry-grid__meta { margin-left: auto; }
.entry-grid__separator { width: 1px; height: 18px; background: var(--erp-border); }
.entry-grid__scroll { overflow-x: auto; }
.entry-grid__table { width: 100%; border-collapse: collapse; font-size: var(--erp-font-size-table); font-variant-numeric: tabular-nums; }
.entry-grid__error { margin: 0; padding: 0 12px; color: var(--erp-danger); font-size: var(--erp-font-size-caption); }
.entry-grid__error:not(:empty) { padding-block: 8px; }
.entry-grid__table:focus { outline: none; }
.entry-grid__table thead th { height: 34px; padding: 6px 10px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 600; letter-spacing: .04em; text-align: left; text-transform: uppercase; white-space: nowrap; border: 1px solid var(--erp-border); background: var(--erp-surface-muted); }
.entry-grid__table thead th.entry-grid__number { text-align: right; }
.entry-grid__corner, .entry-grid__row-header { position: sticky; left: 0; z-index: var(--erp-layer-content); min-width: 140px; }
.entry-grid__row-header { padding: 0 10px; color: var(--erp-text); font-weight: 600; text-align: left; white-space: nowrap; border: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 72%, white); }
.entry-grid__table td { padding: 3px; border: 1px solid var(--erp-border); }
.entry-grid__cell:focus { outline: none; }
.entry-grid__box { display: flex; width: 100%; min-width: 0; height: var(--erp-control-height-compact); align-items: center; padding: 0 7px; overflow: hidden; color: var(--erp-text); white-space: nowrap; text-overflow: ellipsis; border: 1px solid var(--erp-border-strong); border-radius: 5px; background: var(--erp-surface); font: inherit; }
.entry-grid__number .entry-grid__box { justify-content: flex-end; text-align: right; }
.entry-grid__input { outline: none; border-color: var(--erp-accent); box-shadow: var(--erp-focus-ring); }
.entry-grid__box.is-selected { border-color: var(--erp-accent-border); background: var(--erp-accent-soft); }
.entry-grid__box.is-derived { color: var(--erp-text-muted); border-style: dashed; background: var(--erp-surface-soft); }
.entry-grid__box.is-readonly { padding-inline: 0; color: var(--erp-text-secondary); border-color: transparent; background: transparent; }
.entry-grid__box.is-error { border-color: var(--erp-danger); background: var(--erp-danger-soft); }
.entry-grid__cell:focus .entry-grid__box.is-active { border-color: var(--erp-accent); box-shadow: var(--erp-focus-ring); }
.entry-grid__cell:focus .entry-grid__box.is-active.is-readonly { padding-inline: 7px; }
.entry-grid__total, .entry-grid__footer-total { padding: 0 10px !important; color: var(--erp-text); font-weight: 700; white-space: nowrap; background: var(--erp-surface-soft); }
.entry-grid__number { text-align: right; }
.entry-grid tfoot td, .entry-grid tfoot th { height: 34px; border-top: 1px solid var(--erp-border-strong); background: var(--erp-surface-muted); }
.entry-grid__remove { width: 40px; text-align: center; }
.entry-grid__link { min-width: 180px; }
.entry-grid__sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.entry-grid--readonly .entry-grid__box { padding-inline: 0; color: var(--erp-text-secondary); border-color: transparent; background: transparent; }
@media (max-width: 620px) {
	.entry-grid__scroll { mask-image: linear-gradient(to right, var(--erp-text) 0, var(--erp-text) calc(100% - 18px), transparent 100%); }
}
</style>

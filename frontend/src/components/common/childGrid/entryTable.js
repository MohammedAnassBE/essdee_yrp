import { nextTick } from "vue"

import { enterTarget } from "./childGridColumns.js"

const CONTROL_SELECTOR = [
	"input:not([type=hidden]):not(:disabled):not([readonly]):not([data-row-select])",
	"textarea:not(:disabled):not([readonly])",
	"[role=combobox]:not(input):not([aria-disabled=true])",
	"input[role=combobox][data-pc-section=hiddeninput]:not(:disabled)",
].join(",")
const state = new WeakMap()

function rowControls(row) {
	return [...row.querySelectorAll(CONTROL_SELECTOR)].filter((control) => control.closest("tr") === row && control.getClientRects().length)
}

function bodyRows(table) {
	return [...(table?.tBodies || [])].flatMap((body) => [...body.rows]).filter((row) => rowControls(row).length || row.cells.length > 1)
}

function controlValueBlank(control) {
	if (control.type === "checkbox" || control.type === "radio") return true
	if ("value" in control && control.tagName !== "SPAN") return !String(control.value ?? "").trim() || control.inputMode === "decimal" && Number(control.value) === 0
	return Boolean(control.querySelector?.(".p-placeholder")) || control.classList.contains("p-placeholder")
}

/** A DOM row is blank when every text control is empty; zero numbers and checks do not count as data. */
export function isDomRowBlank(controls) {
	const text = controls.filter((control) => control.type !== "checkbox" && control.inputMode !== "decimal" && control.inputMode !== "numeric")
	return (text.length ? text : controls).every(controlValueBlank)
}

function focusControl(table, rowIndex, colIndex) {
	const control = rowControls(bodyRows(table)[rowIndex] || document.createElement("tr"))[colIndex]
	control?.focus()
	control?.select?.()
	return Boolean(control)
}

async function focusNewRow(table, rowCount) {
	for (let attempt = 0; attempt < 5; attempt += 1) {
		await nextTick()
		await new Promise((resolve) => requestAnimationFrame(resolve))
		const rows = bodyRows(table)
		if (rows.length > rowCount && focusControl(table, rows.length - 1, 0)) return
	}
}

function tableOf(element) {
	return element.tagName === "TABLE" ? element : element.querySelector("table")
}

function locate(table, target) {
	const rows = bodyRows(table)
	const controls = rows.map(rowControls)
	const row = rows.findIndex((candidate) => candidate.contains(target))
	const col = row < 0 ? -1 : controls[row].findIndex((control) => control === target || control.contains(target))
	return { rows, controls, row, col }
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

async function overlayClosed(target) {
	for (let attempt = 0; attempt < 15; attempt += 1) {
		if (target.getAttribute("aria-expanded") !== "true") return true
		await wait(20)
	}
	return false
}

async function advance(element, target, wasExpanded) {
	await nextTick()
	await wait(0)
	if (wasExpanded && !(await overlayClosed(target))) return
	const options = state.get(element)?.options || {}
	const table = tableOf(element)
	const { rows, controls, row, col } = locate(table, target)
	if (row < 0 || col < 0) return
	const bounds = { rows: rows.length, cols: Math.max(...controls.map((cells) => cells.length)) }
	const canAdd = typeof options.add === "function" && options.canAdd !== false
	const rowBlank = options.isRowBlank ? options.isRowBlank(row) : isDomRowBlank(controls[row])
	const next = enterTarget({ row, col }, bounds, (r, c) => Boolean(controls[r]?.[c]), { canAdd, rowBlank })
	if (next.action === "move") focusControl(table, next.cell.row, next.cell.col)
	if (next.action === "add") {
		await options.add()
		await focusNewRow(table, rows.length)
	}
}

function cellControl(target) {
	if (target.tagName === "TEXTAREA" || target.tagName === "BUTTON" || !target.closest?.("tbody tr")) return null
	if (!target.matches(CONTROL_SELECTOR) && !target.closest("[role=combobox]")) return null
	return target.getAttribute("aria-expanded") === "true" ? null : target
}

/** A Select or MultiSelect cell (no typed text) would open its overlay on Enter; Alt+Down, Space and typing still open it. */
function isClosedPicker(target) {
	return target.getAttribute("role") === "combobox" && (target.tagName !== "INPUT" || target.readOnly)
}

function onEnter(event) {
	if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return
	const target = event.target
	if (target.tagName === "TEXTAREA" || target.tagName === "BUTTON" || !target.closest?.("tbody tr")) return
	if (!target.matches(CONTROL_SELECTOR) && !target.closest("[role=combobox]")) return
	const wasExpanded = target.getAttribute("aria-expanded") === "true"
	if (!wasExpanded && isClosedPicker(target)) blockKey(event)
	else if (!wasExpanded && target.tagName === "INPUT" && target.type !== "checkbox") event.preventDefault()
	advance(event.currentTarget, target, wasExpanded)
}

const ARROW_STEPS = { ArrowUp: -1, ArrowDown: 1, ArrowLeft: -1, ArrowRight: 1 }
const isVertical = (key) => key === "ArrowUp" || key === "ArrowDown"

/** Cell to reach from `position` by an arrow key; `cells[row]` lists each input's column, so up and down keep the column. */
export function arrowTarget(cells, position, key) {
	const step = ARROW_STEPS[key]
	if (!isVertical(key)) {
		const col = position.col + step
		return col >= 0 && col < cells[position.row].length ? { row: position.row, col } : null
	}
	let row = position.row + step
	while (cells[row] && !cells[row].length) row += step
	if (!cells[row]) return null
	const col = cells[row].indexOf(cells[position.row][position.col])
	return { row, col: col >= 0 ? col : Math.min(position.col, cells[row].length - 1) }
}

/** Left and right leave an input only from the caret's edge or with all its text selected, like a Desk grid cell. */
export function isCaretAtEdge(control, key) {
	if (isVertical(key)) return true
	let start, end
	try { [start, end] = [control.selectionStart, control.selectionEnd] } catch { return true }
	if (start == null) return true
	const length = String(control.value ?? "").length
	if (start === 0 && end === length) return true
	if (start !== end) return false
	return key === "ArrowLeft" ? start === 0 : end === length
}

export function isNumberInput(element) {
	return element?.tagName === "INPUT" && (element.type === "number" || Boolean(element.classList?.contains("p-inputnumber-input")))
}

function blockKey(event) {
	event.preventDefault()
	event.stopPropagation()
}

function onArrow(event) {
	const target = event.target
	if (isVertical(event.key) && isNumberInput(target)) blockKey(event)
	if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey || !cellControl(target) || !isCaretAtEdge(target, event.key)) return
	const table = tableOf(event.currentTarget)
	const { controls, row, col } = locate(table, target)
	if (row < 0 || col < 0) return
	blockKey(event)
	const columns = controls.map((cells) => cells.map((control) => control.closest("td, th")?.cellIndex))
	const next = arrowTarget(columns, { row, col }, event.key)
	if (next) focusControl(table, next.row, next.col)
}

function onTab(event) {
	if (event.ctrlKey || event.metaKey || event.altKey || !cellControl(event.target)) return
	const table = tableOf(event.currentTarget)
	const { controls, row, col } = locate(table, event.target)
	const cells = controls.flatMap((rowControls, rowIndex) => rowControls.map((_, colIndex) => ({ row: rowIndex, col: colIndex })))
	const next = cells[cells.findIndex((cell) => cell.row === row && cell.col === col) + (event.shiftKey ? -1 : 1)]
	if (row < 0 || col < 0 || !next) return
	event.preventDefault()
	focusControl(table, next.row, next.col)
}

function onKeydown(event) {
	if (event.isComposing) return
	if (event.key === "Enter") onEnter(event)
	else if (event.key === "Tab") onTab(event)
	else if (ARROW_STEPS[event.key]) onArrow(event)
}

/** Document-level keydown guard: ArrowUp/ArrowDown never step a number input; v-entry-table handles its own. */
export function guardNumberArrows(event) {
	if (!isVertical(event.key) || !isNumberInput(event.target)) return
	for (let node = event.target; node; node = node.parentElement) if (state.has(node)) return
	blockKey(event)
}

function freezeWidths(element) {
	const table = tableOf(element)
	const headers = [...(table?.tHead?.rows?.[0]?.cells || [])]
	const current = state.get(element)
	const signature = `${headers.length}:${headers.map((cell) => cell.textContent.trim()).join("|")}`
	if (!current || !headers.length || current.signature === signature || !table.tBodies[0]?.rows.length || !table.offsetWidth) return
	table.style.tableLayout = "auto"
	table.style.width = ""
	for (const cell of headers) cell.style.width = ""
	const widths = headers.map((cell) => Math.ceil(cell.getBoundingClientRect().width))
	headers.forEach((cell, index) => { cell.style.width = `${widths[index]}px` })
	table.style.tableLayout = "fixed"
	table.style.width = `${widths.reduce((sum, width) => sum + width, 0)}px`
	table.classList.add("entry-table--fixed")
	current.signature = signature
}

/**
 * v-entry-table on a bespoke editable table (or its wrapper): Desk-grid keys like the IPD Item BOM. Arrows move between
 * inputs and never step a number, Tab moves to the next input, and Enter moves on and adds a row from the last input
 * of the last row; widths are measured once and fixed so focus or validation never shifts columns.
 * Value: { add?: () => void, canAdd?: boolean, isRowBlank?: (rowIndex) => boolean, fixed?: boolean }.
 */
export const vEntryTable = {
	mounted(element, binding) {
		state.set(element, { options: binding.value || {}, signature: "" })
		element.addEventListener("keydown", onKeydown, true)
		if (binding.value?.fixed !== false) requestAnimationFrame(() => freezeWidths(element))
	},
	updated(element, binding) {
		state.get(element).options = binding.value || {}
		if (binding.value?.fixed !== false) requestAnimationFrame(() => freezeWidths(element))
	},
	beforeUnmount(element) {
		element.removeEventListener("keydown", onKeydown, true)
		state.delete(element)
	},
}

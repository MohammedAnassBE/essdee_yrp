import { nextTick } from "vue"

import { enterTarget } from "./childGridColumns.js"

const CONTROL_SELECTOR = [
	"input:not([type=hidden]):not(:disabled):not([readonly]):not([data-row-select])",
	"textarea:not(:disabled):not([readonly])",
	"[role=combobox]:not(input):not([aria-disabled=true])",
].join(",")
const state = new WeakMap()

function rowControls(row) {
	return [...row.querySelectorAll(CONTROL_SELECTOR)].filter((control) => control.closest("tr") === row && control.getClientRects().length)
}

function bodyRows(table) {
	return [...(table?.tBodies?.[0]?.rows || [])].filter((row) => rowControls(row).length || row.cells.length > 1)
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

function onKeydown(event) {
	if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
	const target = event.target
	if (target.tagName === "TEXTAREA" || target.tagName === "BUTTON" || !target.closest?.("tbody tr")) return
	if (!target.matches(CONTROL_SELECTOR) && !target.closest("[role=combobox]")) return
	const wasExpanded = target.getAttribute("aria-expanded") === "true"
	if (!wasExpanded && target.tagName === "INPUT" && target.type !== "checkbox") event.preventDefault()
	advance(event.currentTarget, target, wasExpanded)
}

function freezeWidths(element) {
	const table = tableOf(element)
	const headers = [...(table?.tHead?.rows?.[0]?.cells || [])]
	const current = state.get(element)
	const signature = `${headers.length}:${headers.map((cell) => cell.textContent.trim()).join("|")}`
	if (!headers.length || current.signature === signature || !table.tBodies[0]?.rows.length || !table.offsetWidth) return
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
 * v-entry-table on a bespoke editable table (or its wrapper): Enter moves to the next input and adds a row from
 * the last input of the last row; widths are measured once and fixed so focus or validation never shifts columns.
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

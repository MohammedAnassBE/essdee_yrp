import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"

import { isRowToggleClick, isRowToggleKey } from "../src/utils/rowToggle.js"

const tableSource = fs.readFileSync(path.resolve(import.meta.dirname, "../src/departments/finishing/components/FinishingSeriesTable.vue"), "utf8")
const shellSource = fs.readFileSync(path.resolve(import.meta.dirname, "../src/components/reports/ReportShell.vue"), "utf8")

function target(interactive) {
	return { closest: (selector) => (interactive && selector.split(",").map((part) => part.trim()).includes(interactive) ? {} : null) }
}
const noSelection = { getSelection: () => ({ isCollapsed: true, toString: () => "" }) }

test("a plain click on a row toggles it", () => {
	assert.equal(isRowToggleClick({ target: target(null) }, noSelection), true)
})

test("clicks on links, buttons, inputs and checkboxes inside the row are ignored", () => {
	for (const control of ["a", "button", "input", "textarea", "select", ".p-checkbox"]) {
		assert.equal(isRowToggleClick({ target: target(control) }, noSelection), false, control)
	}
})

test("finishing a text selection does not toggle the row", () => {
	const selecting = { getSelection: () => ({ isCollapsed: false, toString: () => "LOT-001" }) }
	assert.equal(isRowToggleClick({ target: target(null) }, selecting), false)
})

test("Enter and Space toggle only when the row itself has focus", () => {
	const row = {}
	assert.equal(isRowToggleKey({ key: "Enter", target: row, currentTarget: row }), true)
	assert.equal(isRowToggleKey({ key: " ", target: row, currentTarget: row }), true)
	assert.equal(isRowToggleKey({ key: "Enter", target: {}, currentTarget: row }), false)
	assert.equal(isRowToggleKey({ key: "a", target: row, currentTarget: row }), false)
})

test("series rows toggle on click and keyboard, and the arrow still toggles", () => {
	assert.match(tableSource, /<tr class="series-table__row"[^>]*@click="rowClicked\(\$event, row\)"[^>]*@keydown="rowKeydown\(\$event, row\)"/)
	assert.match(tableSource, /:tabindex="expandAll \? undefined : 0"/)
	assert.match(tableSource, /class="series-table__expand"[^>]*@click="emit\('toggle', row\.series\)"/)
})

test("series table scrolls in its own viewport-height frame with a sticky header and first columns", () => {
	assert.match(tableSource, /class="finishing-scroll report-table-frame series-table__frame"/)
	assert.match(shellSource, /\.report-table-frame\)\s*{\s*max-height:[^;]*100dvh/)
	assert.match(tableSource, /\.series-table__sticky\s*{[^}]*position:\s*sticky;[^}]*left:\s*0/)
	assert.match(tableSource, /<th class="series-table__sticky" :class="seriesStickyClass">Series No<\/th>/)
})

test("mounted series table emits toggle for row clicks but not for clicks on its links and buttons", async () => {
	const { findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const rowToggle = await import("../src/utils/rowToggle.js")
	globalThis.getSelection ??= () => ({ isCollapsed: true, toString: () => "" })
	const table = loadComponent(path.resolve(import.meta.dirname, "../src/departments/finishing/components/FinishingSeriesTable.vue"), {
		"../../../components/reports/reportUtils.js": { formatDate: (value) => value },
		"../finishingViews.js": { formatQuantity: (value) => String(value) },
		"../../../utils/rowToggle.js": rowToggle,
	})
	const toggled = []
	const rows = [{ series: "S-1", colour: "Red", total: 1, values: {}, detail: { grn_number: "GRN", lot: "L", item: "I", date: "2026-10-23" } }]
	const root = mountComponent(table, { rows, types: [], printable: true, onToggle: (series) => toggled.push(series) })
	const row = findNodes(root, (node) => node.type === "tr" && String(node.props.class || "").includes("series-table__row"))[0]
	row.props.onClick({ target: target(null) })
	row.props.onClick({ target: target("button") })
	row.props.onClick({ target: target("a") })
	assert.deepEqual(toggled, ["S-1"])
	row.props.onKeydown({ key: "Enter", target: row, currentTarget: row, preventDefault() {} })
	assert.deepEqual(toggled, ["S-1", "S-1"])
	assert.equal(row.props.tabindex, 0)
})

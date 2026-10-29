import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { registerHooks } from "node:module"
import test from "node:test"

const vueUrl = import.meta.resolve("vue")
registerHooks({ resolve: (specifier, context, next) => specifier === "vue" ? { url: vueUrl, shortCircuit: true } : next(specifier, context) })

const { vEntryTable } = await import("../src/components/common/childGrid/entryTable.js")
const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const entryTableSource = read("components/common/childGrid/entryTable.js")
const entryGridSource = read("components/common/EntryGrid.vue")

function mountTable() {
	const listeners = []
	const table = { tagName: "TABLE", tBodies: [], addEventListener: (type, listener) => listeners.push(listener), removeEventListener() {} }
	globalThis.requestAnimationFrame = () => {}
	vEntryTable.mounted(table, { value: { fixed: false } })
	return (target, extra = {}) => {
		const event = { key: "Enter", target, currentTarget: table, prevented: false, stopped: false, preventDefault() { this.prevented = true }, stopPropagation() { this.stopped = true }, ...extra }
		listeners.forEach((listener) => listener(event))
		return event
	}
}

function combobox({ tagName = "SPAN", expanded = "false", readOnly = false } = {}) {
	return {
		tagName, type: tagName === "INPUT" ? "text" : undefined, readOnly,
		getAttribute: (name) => ({ "aria-expanded": expanded, role: "combobox" })[name] ?? null,
		matches: () => true,
		closest: (selector) => selector === "tbody tr" || selector === "[role=combobox]" ? {} : null,
	}
}

test("P1: Enter on a closed Select cell only moves on; the Select never sees it", () => {
	const press = mountTable()
	const closed = press(combobox())
	assert.equal(closed.prevented, true)
	assert.equal(closed.stopped, true)
	const open = press(combobox({ expanded: "true" }))
	assert.equal(open.prevented || open.stopped, false, "an open overlay still picks the highlighted option")
	const altDown = press(combobox(), { key: "ArrowDown", altKey: true })
	assert.equal(altDown.prevented || altDown.stopped, false, "Alt+Down still opens the overlay")
})

test("P1: Enter in a typed input keeps its own handlers (only the default is prevented)", () => {
	const press = mountTable()
	const event = press(combobox({ tagName: "INPUT" }))
	assert.equal(event.prevented, true)
	assert.equal(event.stopped, false)
})

test("P2: a MultiSelect's hidden readonly combobox input is a navigable cell", () => {
	assert.match(entryTableSource, /"input\[role=combobox\]\[data-pc-section=hiddeninput\]:not\(:disabled\)"/)
	const press = mountTable()
	const event = press(combobox({ tagName: "INPUT", readOnly: true }))
	assert.equal(event.prevented, true)
	assert.equal(event.stopped, true, "Enter on a closed MultiSelect must not open it")
})

test("P2: Cutting Marker panel groups rely on v-entry-table, adding only after a filled last group", () => {
	const dialog = read("departments/cutting/CuttingMarkerDialog.vue")
	assert.doesNotMatch(dialog, /addGroupOnEnter/)
	assert.match(dialog, /v-entry-table="\{ add: canEdit \? addGroup : null, isRowBlank: \(index\) => !form\.group_items\[index\]\?\.selected\?\.length \}"/)
})

function entryGridFunction(name, parameters, ...values) {
	const body = entryGridSource.match(new RegExp(`function ${name}\\(event\\) \\{([\\s\\S]*?)\\n\\}`))[1]
	return new Function(...parameters, `return function(event) {${body}}`)(...values)
}

function keyCalls(name, canAdd, shiftKey) {
	const calls = []
	const record = (label) => (...args) => calls.push([label, ...args])
	const arrows = { ArrowDown: "down", ArrowUp: "up" }
	const handler = name === "handleNavigation"
		? entryGridFunction(name, ["ARROWS", "move", "onTab", "enterNext", "canAddRows"], arrows, record("move"), record("tab"), record("enterNext"), { value: canAdd })
		: entryGridFunction(name, ["ARROWS", "commitEdit", "enterNext", "canAddRows", "stopEdit", "tabTarget", "select", "editing"], arrows, record("commit"), record("enterNext"), { value: canAdd }, record("stop"), () => null, record("select"), { value: "edit" })
	handler({ key: "Enter", shiftKey, preventDefault() {}, stopPropagation() {} })
	return calls
}

test("P3: Enter in an EntryGrid without addRow moves to the next editable cell", () => {
	for (const name of ["handleNavigation", "onEditorKeydown"]) {
		for (const canAdd of [true, false]) assert.ok(keyCalls(name, canAdd, false).some(([label]) => label === "enterNext"), `${name}, canAdd=${canAdd}`)
	}
	assert.match(entryGridSource, /enterTarget\(active\.value, bounds, isEditable, \{ canAdd: canAddRows\.value, rowBlank \}\)/)
})

test("P3: Shift+Enter still moves up", () => {
	assert.deepEqual(keyCalls("handleNavigation", false, true), [["move", "up"]])
	assert.deepEqual(keyCalls("handleNavigation", true, true), [["move", "up"]])
	assert.deepEqual(keyCalls("onEditorKeydown", true, true), [["commit", "up"]])
})

test("P4: date fields take showOnFocus (default true) and grid date cells turn it off", () => {
	const base = read("components/common/TemporalFieldBase.vue")
	assert.match(base, /showOnFocus: \{ type: Boolean, default: true \}/)
	assert.match(base, /:show-on-focus="showOnFocus"/)
	assert.match(read("departments/sewing/plan/SewingFiUpdates.vue"), /<DateField v-model="dates\[fiUpdateKey\(row\)\]"[^>]*:show-on-focus="false"/)
	assert.match(read("departments/fabric-store/InspectionEntryPanel.vue"), /<DateField v-model="split\.received_date"[^>]*:show-on-focus="false"/)
})

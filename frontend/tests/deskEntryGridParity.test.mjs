import assert from "node:assert/strict"
import fs from "node:fs"
import { registerHooks } from "node:module"
import test from "node:test"

const vueUrl = import.meta.resolve("vue")
registerHooks({ resolve: (specifier, context, next) => specifier === "vue" ? { url: vueUrl, shortCircuit: true } : next(specifier, context) })

const { nextTick, ref } = await import("vue")
const deskUrl = new URL("../../../yrp/yrp/public/js/utils/entryGrid.js", import.meta.url)
const desk = await import(deskUrl)
const web = {
	...await import("../src/components/common/childGrid/rowSelection.js"),
	...await import("../src/components/common/childGrid/entryTable.js"),
	...await import("../src/components/common/childGrid/childGridColumns.js"),
}
const webSource = fs.readFileSync(new URL("../src/components/common/childGrid/entryTable.js", import.meta.url), "utf8")
const deskSource = fs.readFileSync(deskUrl, "utf8")
const implementations = { desk, web }
const selectorOf = (source) => source.match(/const CONTROL_SELECTOR = \[[\s\S]*?\]\.join/)[0]

test("Desk and /web share the Enter control selector, which skips the row-select checkbox", () => {
	assert.equal(selectorOf(deskSource), selectorOf(webSource))
	assert.match(selectorOf(deskSource), /:not\(\[data-row-select\]\)/)
})

for (const [name, grid] of Object.entries(implementations)) {
	const bounds = { rows: 2, cols: 3 }
	const editable = () => true

	test(`${name}: Enter moves to the next editable cell in the row, then to the next row`, () => {
		assert.deepEqual(grid.enterTarget({ row: 0, col: 0 }, bounds, editable, { canAdd: true, rowBlank: false }), { action: "move", cell: { row: 0, col: 1 } })
		assert.deepEqual(grid.enterTarget({ row: 0, col: 2 }, bounds, editable, { canAdd: true, rowBlank: false }), { action: "move", cell: { row: 1, col: 0 } })
		assert.deepEqual(grid.enterTarget({ row: 0, col: 0 }, bounds, (row, col) => col !== 1, { canAdd: false }), { action: "move", cell: { row: 0, col: 2 } })
	})

	test(`${name}: Enter in the last editable cell adds a row only when allowed and the row has data`, () => {
		const lastCell = { row: 1, col: 2 }
		assert.deepEqual(grid.enterTarget(lastCell, bounds, editable, { canAdd: true, rowBlank: false }), { action: "add" })
		assert.deepEqual(grid.enterTarget(lastCell, bounds, editable, { canAdd: true, rowBlank: true }), { action: "none" })
		assert.deepEqual(grid.enterTarget(lastCell, bounds, editable, { canAdd: false, rowBlank: false }), { action: "none" })
		assert.deepEqual(grid.enterTarget({ row: 1, col: 1 }, bounds, (row, col) => col < 2, { canAdd: true, rowBlank: false }), { action: "add" })
	})

	test(`${name}: a DOM row with only zero numbers and checks is blank`, () => {
		const input = (value, extra = {}) => ({ tagName: "INPUT", type: "text", value, inputMode: "", classList: { contains: () => false }, ...extra })
		assert.equal(grid.isDomRowBlank([input(""), input("0", { inputMode: "decimal" }), input("", { type: "checkbox" })]), true)
		assert.equal(grid.isDomRowBlank([input("Item"), input("0", { inputMode: "decimal" })]), false)
		assert.equal(grid.isDomRowBlank([input("0", { inputMode: "decimal" })]), true)
		assert.equal(grid.isDomRowBlank([input("4", { inputMode: "decimal" })]), false)
	})

	test(`${name}: rows are removed last first so index keys stay valid`, () => {
		assert.deepEqual(grid.removalOrder([0, 1, 2, 3], [1, 3]), [3, 1])
		assert.deepEqual(grid.removalOrder(["a", "b", "c"], ["c", "a", "x"]), ["c", "a"])
	})

	test(`${name}: select all picks only selectable rows and reports partial selection`, () => {
		const keys = ref(["a", "b", "c"])
		const selection = grid.useRowSelection(keys)
		selection.toggle("b")
		assert.deepEqual(selection.selected.value, ["b"])
		assert.equal(selection.isPartlySelected.value, true)
		selection.toggle("locked", true)
		assert.deepEqual(selection.selected.value, ["b"])
		selection.toggleAll(true)
		assert.equal(selection.isAllSelected.value, true)
		keys.value = ["a", "c"]
		assert.deepEqual(selection.selected.value, ["a", "c"])
		selection.toggleAll(false)
		assert.deepEqual(selection.selected.value, [])
		assert.equal(grid.useRowSelection(ref([])).isAllSelected.value, false)
	})

	test(`${name}: delete with all rows selected removes last first and waits a tick between removals`, async () => {
		const rows = ref(["r0", "r1", "r2"])
		const selection = grid.useRowSelection(ref([0, 1, 2]))
		selection.toggleAll(true)
		const seen = []
		await selection.removeSelected(async (index) => {
			seen.push(index)
			rows.value = rows.value.filter((_, at) => at !== index)
			await nextTick()
		})
		assert.deepEqual(seen, [2, 1, 0])
		assert.deepEqual(rows.value, [])
		assert.deepEqual(selection.selected.value, [])
	})

	test(`${name}: delete stops when the table's remove guard turns off`, async () => {
		const tiers = ref(["t0", "t1", "t2"])
		const selection = grid.useRowSelection(ref(["tier-0", "tier-1", "tier-2"]))
		selection.toggleAll(true)
		await selection.removeSelected((key) => { tiers.value = tiers.value.filter((_, index) => `tier-${index}` !== key) }, () => tiers.value.length > 1)
		assert.deepEqual(tiers.value, ["t0"])
	})
}

test("desk: Enter on the form's last input submits, other inputs and modified Enter do not", () => {
	const visible = { getClientRects: () => [1] }
	const first = { tagName: "INPUT", contains: () => false, getAttribute: () => null, ...visible }
	const last = { tagName: "INPUT", contains: () => false, getAttribute: () => null, ...visible }
	const listeners = []
	const form = {
		querySelectorAll: () => [first, last],
		addEventListener: (type, listener) => listeners.push(listener),
		removeEventListener: (type, listener) => listeners.splice(listeners.indexOf(listener), 1),
	}
	let submits = 0
	const cleanup = desk.enterSubmits(form, () => { submits += 1 })
	const press = (target, extra = {}) => {
		const event = { key: "Enter", target, preventDefault() { this.prevented = true }, ...extra }
		listeners.forEach((listener) => listener(event))
		return event
	}
	press(first)
	press(last, { shiftKey: true })
	assert.equal(submits, 0)
	assert.equal(press(last).prevented, true)
	assert.equal(submits, 1)
	cleanup()
	press(last)
	assert.equal(submits, 1)
})

test("essdee_yrp Desk imports of the helper resolve the way Frappe's esbuild nodePaths (apps/<app>) do", () => {
	const appsDir = new URL("../../../", import.meta.url)
	const deskDir = new URL("../../essdee_yrp/public/js/", import.meta.url)
	const importers = fs.readdirSync(deskDir, { recursive: true }).filter((file) => /\.(vue|js)$/.test(file))
		.map((file) => [file, fs.readFileSync(new URL(file, deskDir), "utf8")])
		.filter(([, source]) => source.includes("utils/entryGrid.js"))
	assert.ok(importers.length > 0)
	for (const [file, source] of importers) {
		const specifier = source.match(/from ["']([^"']*utils\/entryGrid\.js)["']/)[1]
		const [app] = specifier.split("/")
		assert.ok(fs.existsSync(new URL(`${app}/${specifier}`, appsDir)), `${file}: ${specifier} does not resolve from apps/${app}`)
	}
})

test("Desk and /web skip width freezing once the table unmounted (state already gone)", () => {
	const guardOf = (source) => source.match(/const current = state\.get\(element\)[\s\S]*?\n\tif \(([^\n]*)\) return/)[1]
	assert.match(guardOf(deskSource), /^!current \|\| /)
	assert.equal(guardOf(deskSource), guardOf(webSource))
})

import assert from "node:assert/strict"
import { registerHooks } from "node:module"
import test from "node:test"

const vueUrl = import.meta.resolve("vue")
registerHooks({ resolve: (specifier, context, next) => specifier === "vue" ? { url: vueUrl, shortCircuit: true } : next(specifier, context) })

const { arrowTarget, isCaretAtEdge, isNumberInput, guardNumberArrows, vEntryTable } = await import("../src/components/common/childGrid/entryTable.js")

const input = (extra = {}) => ({ tagName: "INPUT", type: "text", value: "", classList: { contains: () => false }, parentElement: null, ...extra })
const keyEvent = (key, target, extra = {}) => ({
	key, target, prevented: false, stopped: false,
	preventDefault() { this.prevented = true },
	stopPropagation() { this.stopped = true },
	...extra,
})

test("arrows move to the same column in the row above or below, skipping rows without inputs", () => {
	const cells = [[1, 2, 3], [], [1, 3], [2, 3]]
	assert.deepEqual(arrowTarget(cells, { row: 0, col: 2 }, "ArrowDown"), { row: 2, col: 1 })
	assert.deepEqual(arrowTarget(cells, { row: 2, col: 0 }, "ArrowUp"), { row: 0, col: 0 })
	assert.deepEqual(arrowTarget(cells, { row: 2, col: 0 }, "ArrowDown"), { row: 3, col: 0 })
	assert.equal(arrowTarget(cells, { row: 0, col: 1 }, "ArrowUp"), null)
	assert.equal(arrowTarget(cells, { row: 3, col: 1 }, "ArrowDown"), null)
})

test("left and right move to the previous or next input in the row and stop at its ends", () => {
	const cells = [[1, 2, 3]]
	assert.deepEqual(arrowTarget(cells, { row: 0, col: 1 }, "ArrowRight"), { row: 0, col: 2 })
	assert.deepEqual(arrowTarget(cells, { row: 0, col: 1 }, "ArrowLeft"), { row: 0, col: 0 })
	assert.equal(arrowTarget(cells, { row: 0, col: 2 }, "ArrowRight"), null)
	assert.equal(arrowTarget(cells, { row: 0, col: 0 }, "ArrowLeft"), null)
})

test("left and right leave an input only from the caret's edge or with all text selected", () => {
	const caret = (start, end = start) => input({ value: "12.5", selectionStart: start, selectionEnd: end })
	assert.equal(isCaretAtEdge(caret(0, 4), "ArrowLeft"), true)
	assert.equal(isCaretAtEdge(caret(0, 4), "ArrowRight"), true)
	assert.equal(isCaretAtEdge(caret(0), "ArrowLeft"), true)
	assert.equal(isCaretAtEdge(caret(4), "ArrowRight"), true)
	assert.equal(isCaretAtEdge(caret(2), "ArrowLeft"), false)
	assert.equal(isCaretAtEdge(caret(2), "ArrowRight"), false)
	assert.equal(isCaretAtEdge(caret(1, 3), "ArrowRight"), false)
	assert.equal(isCaretAtEdge({ tagName: "SPAN" }, "ArrowRight"), true)
	assert.equal(isCaretAtEdge(Object.defineProperty(input({ type: "number" }), "selectionStart", { get() { throw new Error("no selection") } }), "ArrowLeft"), true)
})

test("number inputs are native number inputs and PrimeVue InputNumber inputs", () => {
	assert.equal(isNumberInput(input({ type: "number" })), true)
	assert.equal(isNumberInput(input({ classList: { contains: (name) => name === "p-inputnumber-input" } })), true)
	assert.equal(isNumberInput(input({ inputMode: "decimal" })), false)
	assert.equal(isNumberInput({ tagName: "TEXTAREA", classList: { contains: () => false } }), false)
})

test("the global guard stops ArrowUp and ArrowDown from changing a number outside entry tables", () => {
	const number = input({ type: "number" })
	for (const key of ["ArrowUp", "ArrowDown"]) {
		const event = keyEvent(key, number, { shiftKey: key === "ArrowUp" })
		guardNumberArrows(event)
		assert.equal(event.prevented, true)
		assert.equal(event.stopped, true)
	}
	const left = keyEvent("ArrowLeft", number)
	guardNumberArrows(left)
	assert.equal(left.prevented || left.stopped, false)
	const text = keyEvent("ArrowDown", input())
	guardNumberArrows(text)
	assert.equal(text.prevented || text.stopped, false)
})

test("the global guard leaves numbers inside a v-entry-table to the table's own handler", () => {
	globalThis.requestAnimationFrame = () => {}
	const wrapper = { addEventListener() {}, removeEventListener() {}, parentElement: null }
	vEntryTable.mounted(wrapper, { value: { fixed: false } })
	const number = input({ type: "number", parentElement: { parentElement: wrapper } })
	const event = keyEvent("ArrowDown", number)
	guardNumberArrows(event)
	assert.equal(event.stopped, false)
	vEntryTable.beforeUnmount(wrapper)
	const after = keyEvent("ArrowDown", number)
	guardNumberArrows(after)
	assert.equal(after.stopped, true)
	delete globalThis.requestAnimationFrame
})

test("the /web app installs the number arrow guard on the whole document in the capture phase", async () => {
	const { readFile } = await import("node:fs/promises")
	const main = await readFile(new URL("../src/main.js", import.meta.url), "utf8")
	assert.match(main, /document\.addEventListener\("keydown", guardNumberArrows, true\)/)
})

test("navigation walks the rows of every tbody, so grouped tables (one tbody per group) navigate as one grid", async () => {
	const { readFile } = await import("node:fs/promises")
	const source = await readFile(new URL("../src/components/common/childGrid/entryTable.js", import.meta.url), "utf8")
	assert.match(source, /function bodyRows\(table\) \{\n\treturn \[\.\.\.\(table\?\.tBodies \|\| \[\]\)\]\.flatMap\(\(body\) => \[\.\.\.body\.rows\]\)/)
})

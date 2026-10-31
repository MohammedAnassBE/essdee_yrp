import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

const files = [
	"../src/departments/purchase/lot/LotOrderItemsEditor.vue",
]

function handlerFrom(source, addRow) {
	const body = source.match(/function addOnLastEnter\(event\) \{\n([\s\S]*?)\n\}/)[1]
	return new Function("addRow", `return function addOnLastEnter(event) {\n${body}\n}`)(addRow)
}

function keyEvent(target, inputs, extra = {}) {
	return { target, currentTarget: { querySelectorAll: () => inputs }, preventDefault() { this.prevented = true }, ...extra }
}

for (const file of files) {
	const source = fs.readFileSync(new URL(file, import.meta.url), "utf8")

	test(`${file.split("/").slice(-3).join("/")}: the composer listens for Enter`, () => {
		assert.match(source, /aria-label="Add box quantity row"\s*@keydown\.enter="addOnLastEnter"/)
		assert.match(source, /@click="addRow"/)
	})

	test(`${file.split("/").slice(-3).join("/")}: Enter on the last input runs the existing Add`, () => {
		let added = 0
		const handler = handlerFrom(source, () => { added += 1 })
		const inputs = [{ id: "colour" }, { id: "qty" }, { id: "mrp" }]
		const last = keyEvent(inputs[2], inputs)
		handler(last)
		assert.equal(added, 1)
		assert.equal(last.prevented, true)
		handler(keyEvent(inputs[1], inputs))
		handler(keyEvent(inputs[2], inputs, { shiftKey: true }))
		handler(keyEvent(inputs[2], inputs, { isComposing: true }))
		assert.equal(added, 1)
	})
}

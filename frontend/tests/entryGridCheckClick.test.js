import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/common/EntryGrid.vue", import.meta.url), "utf8")

test("single click toggles a check cell without changing text or number click behavior", () => {
	const body = source.match(/function onCellClick\(event, row, col\) \{([\s\S]*?)\n\}/)[1]
	for (const [type, editable, detail, expected] of [["check", true, 1, 1], ["check", true, 2, 0], ["check", false, 1, 0], ["text", true, 1, 0], ["number", true, 1, 0], ["link", true, 1, 1]]) {
		let edits = 0
		const click = new Function("props", "dragged", "isPlainClick", "isEditing", "isEditable", "isChoiceColumn", "select", "startEdit", "toggleCheck", `return function(event, row, col) {${body}}`)(
			{ columns: [{ type }] }, false, () => true, () => false, () => editable,
			column => column.type === "link", () => {}, () => edits++, () => edits++,
		)
		click({ detail }, 0, 0)
		assert.equal(edits, expected, `${type}, editable=${editable}, detail=${detail}`)
	}
})

test("Space still toggles check cells and double click does not toggle them again", () => {
	assert.match(source, /event.key === " "[^\n]*type === "check"[^\n]*toggleCheck\(\)/)
	assert.match(source, /@dblclick="[^"\n]*column.type !== 'check'[^"\n]*startEdit/)
})

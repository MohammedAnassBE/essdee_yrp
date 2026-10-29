import assert from "node:assert/strict"
import { registerHooks } from "node:module"
import test from "node:test"

const vueUrl = import.meta.resolve("vue")
registerHooks({ resolve: (specifier, context, next) => specifier === "vue" ? { url: vueUrl, shortCircuit: true } : next(specifier, context) })

const { vEntryTable } = await import("../src/components/common/childGrid/entryTable.js")

test("a width freeze queued before unmount does nothing once the table is gone", () => {
	const frames = []
	globalThis.requestAnimationFrame = (callback) => frames.push(callback)
	const header = { textContent: "Qty", style: {}, getBoundingClientRect: () => ({ width: 80 }) }
	const table = { tagName: "TABLE", tHead: { rows: [{ cells: [header] }] }, tBodies: [{ rows: [{}] }], offsetWidth: 80, style: {}, classList: { add() {} } }
	const element = { ...table, addEventListener() {}, removeEventListener() {} }
	vEntryTable.mounted(element, { value: {} })
	vEntryTable.beforeUnmount(element)
	assert.doesNotThrow(() => frames.forEach((callback) => callback()))
	delete globalThis.requestAnimationFrame
})

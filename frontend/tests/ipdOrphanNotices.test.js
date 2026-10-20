import assert from "node:assert/strict"
import test from "node:test"
import { orphanProcessNotices } from "../src/departments/merch/ipd/sections/orphanProcessNotices.js"

test("keeps one notice per removed embellishment with a process row", () => {
	const rows = [{ process_name: "Print" }, { process_name: "Wash" }]
	let notices = orphanProcessNotices([], rows, {}, "Print")
	notices = orphanProcessNotices(notices, rows, {}, "Wash")
	notices = orphanProcessNotices(notices, rows, {}, "Print")
	assert.deepEqual(notices, ["Print", "Wash"])
	assert.deepEqual(orphanProcessNotices(notices, rows, {}, "Missing"), notices)
})

test("clears notices for removed process rows and re-added embellishments independently", () => {
	assert.deepEqual(orphanProcessNotices(["Print", "Wash"], [{ process_name: "Wash" }], {}), ["Wash"])
	assert.deepEqual(orphanProcessNotices(["Print", "Wash"], [{ process_name: "Print" }, { process_name: "Wash" }], { Print: [] }), ["Wash"])
	assert.deepEqual(orphanProcessNotices([], [{ process_name: "Print" }], {}), [])
	assert.deepEqual(orphanProcessNotices(["Print"], null, null), [])
	assert.deepEqual(orphanProcessNotices([], [{ process_name: "Print" }], null, "Print"), ["Print"])
})

import assert from "node:assert/strict"
import test from "node:test"

import { availableBulkActions, bulkActionRows, bulkConfirmation, bulkOutcome, runBulkRows } from "../src/components/common/listBulkActions.js"

const draft = { name: "DC-1", docstatus: 0 }
const submitted = { name: "DC-2", docstatus: 1 }
const cancelled = { name: "DC-3", docstatus: 2 }
const all = () => true
const actionNames = (rows, options) => availableBulkActions(rows, options).map(({ action, rows: candidates }) => [action, candidates.map((row) => row.name)])

test("each action applies only to rows whose docstatus allows it, like Desk", () => {
	const rows = [draft, submitted, cancelled]
	assert.deepEqual(bulkActionRows("submit", rows, { isSubmittable: true }), [draft])
	assert.deepEqual(bulkActionRows("cancel", rows, { isSubmittable: true }), [submitted])
	assert.deepEqual(bulkActionRows("delete", rows, { isSubmittable: true }), [draft, cancelled])
	assert.deepEqual(bulkActionRows("submit", rows, { isSubmittable: false }), [])
	assert.deepEqual(bulkActionRows("delete", [{ name: "ITEM-1" }], { isSubmittable: false }), [{ name: "ITEM-1" }])
})

test("an action is offered only when permitted and at least one selected row allows it", () => {
	assert.deepEqual(actionNames([draft, submitted, cancelled], { isSubmittable: true, can: all }), [
		["submit", ["DC-1"]], ["cancel", ["DC-2"]], ["delete", ["DC-1", "DC-3"]],
	])
	assert.deepEqual(actionNames([submitted], { isSubmittable: true, can: all }), [["cancel", ["DC-2"]]])
	assert.deepEqual(actionNames([draft, submitted], { isSubmittable: true, can: (permission) => permission === "cancel" }), [["cancel", ["DC-2"]]])
	assert.deepEqual(actionNames([draft], { isSubmittable: true, can: () => false }), [])
})

test("workflow doctypes keep Delete but never offer direct Submit or Cancel", () => {
	assert.deepEqual(actionNames([draft, submitted], { isSubmittable: true, hasWorkflow: true, can: all }), [["delete", ["DC-1"]]])
	assert.deepEqual(actionNames([{ name: "ITEM-1" }], { isSubmittable: false, can: all }), [["delete", ["ITEM-1"]]])
})

test("confirmation names the count and list, or the single document", () => {
	const rows = Array.from({ length: 6 }, (_, index) => ({ name: `DC-${index}`, docstatus: 1 }))
	assert.deepEqual(bulkConfirmation("cancel", rows, "Delivery Challans"), {
		title: "Cancel Documents", message: "Cancel 6 Delivery Challans?", confirmLabel: "Cancel", severity: "danger",
	})
	assert.equal(bulkConfirmation("submit", [draft], "Delivery Challans").message, "Submit DC-1?")
	assert.equal(bulkConfirmation("delete", [draft, cancelled], "Delivery Challans").message, "Delete 2 Delivery Challans?")
})

test("the runner keeps going after a failure and reports each failed document with its error", async () => {
	const progress = []
	const result = await runBulkRows([draft, submitted, cancelled], async (row) => {
		if (row.name === "DC-2") throw new Error("Insufficient stock for Item X")
	}, (index, total) => progress.push(`${index}/${total}`))
	assert.deepEqual(result, { done: ["DC-1", "DC-3"], failed: [{ name: "DC-2", error: "Insufficient stock for Item X" }] })
	assert.deepEqual(progress, ["1/3", "2/3", "3/3"])
	const outcome = bulkOutcome("cancel", result)
	assert.equal(outcome.title, "Cancel partially completed")
	assert.equal(outcome.summary, "2 documents cancelled; 1 document failed.")
	assert.equal(bulkOutcome("delete", { done: [], failed: result.failed }).title, "Delete failed")
	assert.equal(bulkOutcome("submit", { done: ["DC-1"], failed: [] }).notice, "1 document submitted.")
})

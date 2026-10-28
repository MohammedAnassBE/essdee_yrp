import assert from "node:assert/strict"
import test from "node:test"

import {
	columnDraft,
	defaultColumnWidth,
	distributeEvenly,
	draftPercents,
	layoutWidths,
	percentsFromWeights,
	enterTarget,
	gridViewEntries,
	isRowBlank,
	mergeGridView,
	resolveGridColumns,
	savedEntryWidth,
} from "../src/components/common/childGrid/childGridColumns.js"
import { createGridViewStore } from "../src/components/common/childGrid/gridViewStore.js"

const pick = ({ lastKey, lastPercent, others, error }) => ({ lastKey, lastPercent, others, error })

const schema = [
	{ key: "item", label: "Item", fieldtype: "Link", reqd: 1 },
	{ key: "qty", label: "Qty", fieldtype: "Float" },
	{ key: "done", label: "Done", fieldtype: "Check" },
	{ key: "notes", label: "Notes", fieldtype: "Data" },
	{ key: "actions", label: "", configurable: false },
]

test("default widths follow field type, link and data wider than numbers and checks", () => {
	assert.equal(defaultColumnWidth({ fieldtype: "Link" }), 200)
	assert.equal(defaultColumnWidth({ fieldtype: "Data" }), 160)
	assert.equal(defaultColumnWidth({ fieldtype: "Float" }), 100)
	assert.equal(defaultColumnWidth({ fieldtype: "Check" }), 60)
	assert.equal(defaultColumnWidth({ type: "number" }), 100)
	assert.equal(defaultColumnWidth({ type: "link" }), 200)
	assert.equal(defaultColumnWidth({ fieldtype: "Link", width: 320 }), 320)
	assert.equal(defaultColumnWidth({ fieldtype: "Link", width: 9000 }), 600)
	assert.equal(defaultColumnWidth({}), 140)
	assert.equal(defaultColumnWidth({ fieldtype: "Float", label: "Qty of BOM Item" }), 141)
	assert.equal(defaultColumnWidth({ fieldtype: "Check", label: "A very long check column heading for testing" }), 240)
})

test("saved width reads Frappe px width and legacy 1-12 column units", () => {
	assert.equal(savedEntryWidth({ fieldname: "a", width: 250 }), 250)
	assert.equal(savedEntryWidth({ fieldname: "a", columns: 2 }), 100)
	assert.equal(savedEntryWidth({ fieldname: "a", width: 10 }), 60)
	assert.equal(savedEntryWidth({ fieldname: "a" }), null)
})

const shape = (columns) => columns.map((column) => [column.key, column.percent ?? column.width])

test("without saved settings visible columns share 100% by field-type default width, the last taking the remainder", () => {
	assert.deepEqual(shape(resolveGridColumns(schema, null)), [["item", 38], ["qty", 19], ["done", 11], ["notes", 32], ["actions", 140]])
})

test("percentsFromWeights floors each column and gives the last column the rest", () => {
	assert.deepEqual(percentsFromWeights([1, 1, 1]), [33, 33, 34])
	assert.deepEqual(percentsFromWeights([1000, 1]), [99, 1])
	assert.deepEqual(percentsFromWeights([1, 1000]), [3, 97])
	assert.deepEqual(percentsFromWeights([]), [])
})

test("saved width_percent wins; fixed columns stay at the end with their px width", () => {
	const saved = [{ fieldname: "qty", width: 360, width_percent: 30 }, { fieldname: "item", width: 840, width_percent: 70 }]
	assert.deepEqual(shape(resolveGridColumns(schema, saved)), [["qty", 30], ["item", 70], ["actions", 140]])
})

test("Desk-only px widths convert to percentages in proportion", () => {
	const saved = [{ fieldname: "notes", width: 300, sticky: 0 }, { fieldname: "item", width: 220 }]
	assert.deepEqual(shape(resolveGridColumns(schema, saved)), [["notes", 57], ["item", 43], ["actions", 140]])
})

test("saved settings merge with schema changes: unknown fields drop, missing mandatory fields come back", () => {
	assert.deepEqual(shape(resolveGridColumns(schema, [{ fieldname: "removed_field", width: 100 }, { fieldname: "qty", columns: 3 }])), [["qty", 41], ["item", 59], ["actions", 140]])
	assert.deepEqual(shape(resolveGridColumns(schema, [{ fieldname: "qty", width: 960, width_percent: 80 }])), [["qty", 82], ["item", 18], ["actions", 140]])
})

test("saved settings with no known field fall back to defaults", () => {
	const columns = resolveGridColumns(schema, [{ fieldname: "gone", width: 100 }])
	assert.deepEqual(columns.map((column) => column.key), ["item", "qty", "done", "notes", "actions"])
})

test("columns hidden by default stay hidden until the user picks them", () => {
	const withOptional = [...schema.slice(0, 2), { key: "extra", label: "Extra", fieldtype: "Data", hidden: true }]
	assert.deepEqual(resolveGridColumns(withOptional, null).map((column) => column.key), ["item", "qty"])
	assert.deepEqual(resolveGridColumns(withOptional, [{ fieldname: "extra", width: 120 }, { fieldname: "item" }]).map((column) => column.key), ["extra", "item"])
})

test("layout widths fill the table by percentage and keep a minimum px width on narrow screens", () => {
	const columns = [
		{ key: "a", fieldtype: "Link", width: 200, percent: 50 },
		{ key: "b", fieldtype: "Check", width: 60, percent: 50 },
		{ key: "c", configurable: false, width: 52 },
	]
	assert.deepEqual(layoutWidths(columns, 1052), [500, 500, 52])
	assert.deepEqual(layoutWidths(columns, 1100, 48), [500, 500, 52])
	assert.deepEqual(layoutWidths(columns, 150), [120, 60, 52])
})

test("layout widths take a raised minimum back from wider columns so the table still fits", () => {
	const columns = [
		{ key: "item", fieldtype: "Link", width: 200, percent: 95 },
		{ key: "based_on", fieldtype: "Data", width: 160, percent: 5 },
	]
	const widths = layoutWidths(columns, 1000)
	assert.deepEqual(widths, [904, 96])
	assert.ok(widths.reduce((sum, width) => sum + width, 0) <= 1000)
})

test("the last shown column gets 100% minus the others and moves with reorder or hide", () => {
	const draft = columnDraft(schema, resolveGridColumns(schema, [{ fieldname: "qty", width_percent: 30 }, { fieldname: "item", width_percent: 70 }]))
	assert.deepEqual(draft.map((column) => [column.key, column.visible, column.percent, column.locked]), [
		["qty", true, 30, false], ["item", true, 70, true], ["done", false, 5, false], ["notes", false, 13, false],
	])
	assert.deepEqual(pick(draftPercents(draft)), { lastKey: "item", lastPercent: 70, others: 30, error: "" })
	draft[2].visible = true
	assert.deepEqual(pick(draftPercents(draft)), { lastKey: "done", lastPercent: 0, others: 100, error: "Other columns use 100%; reduce them to leave room for Done." })
	assert.throws(() => gridViewEntries(draft), /reduce them to leave room for Done/)
	draft[1].percent = 50
	assert.deepEqual(gridViewEntries(draft), [
		{ fieldname: "qty", width: 360, width_percent: 30, sticky: 0 },
		{ fieldname: "item", width: 600, width_percent: 50, sticky: 0 },
		{ fieldname: "done", width: 240, width_percent: 20, sticky: 0 },
	])
	draft[2].visible = false
	assert.equal(draftPercents(draft).lastKey, "item")
})

test("others may not leave the last column under the 3% minimum", () => {
	const draft = [{ key: "a", label: "A", visible: true, percent: 98 }, { key: "b", label: "B", visible: true, percent: 0 }]
	assert.match(draftPercents(draft).error, /Other columns use 98%; reduce them to leave room for B/)
	draft[0].percent = 97
	assert.equal(draftPercents(draft).error, "")
	assert.deepEqual(gridViewEntries(draft).map((entry) => entry.width_percent), [97, 3])
})

test("distribute evenly splits shown columns and the last takes the remainder on save", () => {
	const draft = distributeEvenly([{ key: "a", visible: true, percent: 80 }, { key: "b", visible: true, percent: 1 }, { key: "c", visible: true, percent: 1 }, { key: "d", visible: false, percent: 9 }])
	assert.deepEqual(draft.map((column) => column.percent), [33, 33, 33, 9])
	assert.deepEqual(gridViewEntries(draft).map((entry) => entry.width_percent), [33, 33, 34])
})

test("mandatory columns stay in the saved list even if the draft hides them", () => {
	const draft = columnDraft(schema, resolveGridColumns(schema, null)).map((column) => ({ ...column, visible: column.key === "qty" }))
	assert.deepEqual(gridViewEntries(draft).map((entry) => entry.fieldname), ["item", "qty"])
})

test("mergeGridView keeps other child tables and removes only this table on reset", () => {
	const settings = { GridView: { "Child A": [{ fieldname: "x", width: 100 }], "Child B": [{ fieldname: "y" }] }, last_view: "List" }
	assert.deepEqual(mergeGridView(settings, "Child A", [{ fieldname: "z", width: 90, sticky: 0 }]), {
		"Child A": [{ fieldname: "z", width: 90, sticky: 0 }], "Child B": [{ fieldname: "y" }],
	})
	assert.deepEqual(mergeGridView(settings, "Child A", null), { "Child B": [{ fieldname: "y" }] })
	assert.deepEqual(mergeGridView({}, "Child A", null), {})
})

test("row blank check ignores defaulted numbers and checks when a text or link column exists", () => {
	const columns = schema.slice(0, 4)
	assert.equal(isRowBlank({ item: null, qty: 1, done: 0, notes: "" }, columns), true)
	assert.equal(isRowBlank({ item: "ITEM-1", qty: 1 }, columns), false)
	assert.equal(isRowBlank({ notes: " x " }, columns), false)
	const numbers = [{ key: "a", fieldtype: "Float" }, { key: "b", type: "number" }]
	assert.equal(isRowBlank({ a: 0, b: null }, numbers), true)
	assert.equal(isRowBlank({ a: 0, b: 4 }, numbers), false)
	assert.equal(isRowBlank({ item: "X" }, [{ key: "item", fieldtype: "Link", readonly: true }, { key: "qty", fieldtype: "Float" }]), true)
})

const bounds = { rows: 2, cols: 3 }
const editable = () => true

test("Enter moves to the next editable cell in the row, then to the next row", () => {
	assert.deepEqual(enterTarget({ row: 0, col: 0 }, bounds, editable, { canAdd: true, rowBlank: false }), { action: "move", cell: { row: 0, col: 1 } })
	assert.deepEqual(enterTarget({ row: 0, col: 2 }, bounds, editable, { canAdd: true, rowBlank: false }), { action: "move", cell: { row: 1, col: 0 } })
	assert.deepEqual(enterTarget({ row: 0, col: 0 }, bounds, (row, col) => col !== 1, { canAdd: false }), { action: "move", cell: { row: 0, col: 2 } })
})

test("Enter in the last editable cell of the last row adds a row only when allowed and the row has data", () => {
	const lastCell = { row: 1, col: 2 }
	assert.deepEqual(enterTarget(lastCell, bounds, editable, { canAdd: true, rowBlank: false }), { action: "add" })
	assert.deepEqual(enterTarget(lastCell, bounds, editable, { canAdd: true, rowBlank: true }), { action: "none" })
	assert.deepEqual(enterTarget(lastCell, bounds, editable, { canAdd: false, rowBlank: false }), { action: "none" })
	assert.deepEqual(enterTarget({ row: 1, col: 1 }, bounds, (row, col) => col < 2, { canAdd: true, rowBlank: false }), { action: "add" })
})

test("grid view store reads Frappe user settings and writes only the GridView key", async () => {
	const calls = []
	let stored = { GridView: { Other: [{ fieldname: "a", width: 100 }] }, last_view: "Report" }
	const store = createGridViewStore({
		read: async (method, args) => { calls.push([method, args]); return JSON.stringify(stored) },
		write: async (method, args) => {
			calls.push([method, args])
			stored = { ...stored, ...JSON.parse(args.user_settings) }
			return stored
		},
	})
	assert.equal(await store.get("Item", "Child"), null)
	assert.deepEqual(await store.get("Item", "Other"), [{ fieldname: "a", width: 100 }])
	await store.save("Item", "Child", [{ fieldname: "x", width: 90, sticky: 0 }])
	const saveCall = calls.find(([method]) => method === "frappe.model.utils.user_settings.save")
	assert.equal(saveCall[1].doctype, "Item")
	assert.deepEqual(Object.keys(JSON.parse(saveCall[1].user_settings)), ["GridView"])
	assert.deepEqual(stored.GridView, { Other: [{ fieldname: "a", width: 100 }], Child: [{ fieldname: "x", width: 90, sticky: 0 }] })
	assert.equal(stored.last_view, "Report")
	assert.deepEqual(await store.get("Item", "Child"), [{ fieldname: "x", width: 90, sticky: 0 }])
	await store.save("Item", "Child", null)
	assert.deepEqual(stored.GridView, { Other: [{ fieldname: "a", width: 100 }] })
	assert.equal(await store.get("Item", "Child"), null)
})

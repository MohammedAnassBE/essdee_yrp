import assert from "node:assert/strict"
import test from "node:test"
import { nextTick, ref } from "vue"

import { removalOrder, useRowSelection } from "../src/components/common/childGrid/rowSelection.js"

test("rows are removed last first so index keys stay valid", () => {
	assert.deepEqual(removalOrder([0, 1, 2, 3], [1, 3]), [3, 1])
	assert.deepEqual(removalOrder(["a", "b", "c"], ["c", "a", "x"]), ["c", "a"])
})

test("select all picks only selectable rows and reports partial selection", () => {
	const keys = ref(["a", "b", "c"])
	const selection = useRowSelection(keys)
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
	assert.equal(useRowSelection(ref([])).isAllSelected.value, false)
})

test("delete removes one selected row through the table's remove path", async () => {
	const rows = ref(["r0", "r1", "r2"])
	const keys = ref([0, 1, 2])
	const selection = useRowSelection(keys)
	selection.toggle(1)
	await selection.removeSelected((index) => { rows.value = rows.value.filter((_, at) => at !== index) })
	assert.deepEqual(rows.value, ["r0", "r2"])
	assert.deepEqual(selection.selected.value, [])
})

test("delete with all rows selected clears index-keyed rows and waits a tick between removals", async () => {
	const rows = ref(["r0", "r1", "r2"])
	const selection = useRowSelection(ref([0, 1, 2]))
	selection.toggleAll(true)
	const seen = []
	await selection.removeSelected(async (index) => {
		seen.push(index)
		rows.value = rows.value.filter((_, at) => at !== index)
		await nextTick()
	})
	assert.deepEqual(seen, [2, 1, 0])
	assert.deepEqual(rows.value, [])
})

test("delete stops when the table's remove guard turns off", async () => {
	const tiers = ref(["t0", "t1", "t2"])
	const selection = useRowSelection(ref(["tier-0", "tier-1", "tier-2"]))
	selection.toggleAll(true)
	await selection.removeSelected((key) => { tiers.value = tiers.value.filter((_, index) => `tier-${index}` !== key) }, () => tiers.value.length > 1)
	assert.deepEqual(tiers.value, ["t0"])
})

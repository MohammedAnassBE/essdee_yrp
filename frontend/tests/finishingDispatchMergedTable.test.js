import assert from "node:assert/strict"
import test from "node:test"
import { loadComponent, mountComponent, findNodes } from "../../scripts/helpers/vue_renderer.mjs"
import { colourDetails, dispatchBySize, dispatchEntrySource, dispatchInitialState, packingMode, packingRatio } from "../src/departments/finishing/finishingEntries.js"
import { formatQuantity } from "../src/departments/finishing/finishingViews.js"

const component = loadComponent(new URL("../src/departments/finishing/components/FinishingDispatchEntry.vue", import.meta.url).pathname, {
	"../finishingEntries.js": { dispatchBySize, packingMode, packingRatio, colourDetails }, "../finishingViews.js": { formatQuantity },
})
const row = {
	sizes: ["S", "M", "L"],
	values: { L: { qty: 3, dispatch_qty: 1 }, M: { qty: 2, dispatch_qty: 0 }, S: { qty: 5, dispatch_qty: 2 } },
	total: { total_qty: 10 },
}
const textOf = (node) => [node.text, ...node.children.map(textOf)].filter(Boolean).join(" ").replace(/\s+/g, " ").trim()
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const cells = (tableRow) => tableRow.children.filter((node) => ["td", "th"].includes(node.type))

function mountDispatch(props = {}) {
	const source = dispatchEntrySource(row)
	return mountComponent(component, { label: "FP-1", sizes: source.sizes, packed: source.packed, config: {}, initial: dispatchInitialState(row), showPacked: false, ...props })
}

test("dispatch screen shows Balance and Dispatch as two rows of one size table", () => {
	const root = mountDispatch()
	const tables = nodes(root, "table")
	assert.equal(tables.length, 1)
	assert.deepEqual(cells(nodes(tables[0], "thead")[0].children[0]).map(textOf), ["Size", "S", "M", "L", "Total"])
	const bodyRows = nodes(nodes(tables[0], "tbody")[0], "tr")
	assert.deepEqual(bodyRows.map((tableRow) => textOf(cells(tableRow)[0])), ["Balance", "Dispatch"])
	assert.deepEqual(cells(bodyRows[0]).slice(1).map(textOf), ["5", "2", "3", "10"])
	assert.equal(nodes(bodyRows[0], "input").length, 0)
	assert.deepEqual(nodes(bodyRows[1], "input").map((input) => input.props["aria-label"]), ["FP-1 S dispatch boxes", "FP-1 M dispatch boxes", "FP-1 L dispatch boxes"])
	assert.equal(textOf(cells(bodyRows[1]).at(-1)), "3")
})

test("submitted dispatch keeps the merged table with disabled inputs", () => {
	const root = mountDispatch({ readonly: true, disabled: true })
	assert.equal(nodes(root, "table").length, 1)
	assert.ok(nodes(root, "input").every((input) => input.props.disabled === true))
})

test("Finishing Plan dialog adds Packed above Balance in the same table", () => {
	const root = mountDispatch({ showPacked: true })
	assert.equal(nodes(root, "table").length, 1)
	assert.deepEqual(nodes(nodes(root, "tbody")[0], "tr").map((tableRow) => textOf(cells(tableRow)[0])), ["Packed", "Balance", "Dispatch"])
})

test("colour packing modes put Balance into the dispatch table; dynamic batches keep a separate balance table", () => {
	const config = { based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing", colours: ["Red"] }
	const sizeWise = mountDispatch({ config, initial: {} })
	assert.equal(nodes(sizeWise, "table").length, 1)
	assert.deepEqual(nodes(sizeWise, "tr").slice(1).map((tableRow) => textOf(cells(tableRow)[0])), ["Balance", "Red", "Dispatch"])
	const dynamic = mountDispatch({ packed: { ...dispatchEntrySource(row).packed, dynamic_ratio_packing: true } })
	assert.equal(nodes(dynamic, "table").length, 2)
})

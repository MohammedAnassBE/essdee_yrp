import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"

import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as rowSelection from "../src/components/common/childGrid/rowSelection.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const LinkField = (props) => Vue.h("link-field", props)
const Message = (props, { slots }) => Vue.h("message", props, slots.default?.())
const schema = { item: "Fabric A", primary_attribute: "Dia", primary_attribute_values: ["58 Dia"], attributes: ["Colour", "Dia"], attribute_values: { Colour: ["Cream", "Red"] }, default_uom: "Kg" }
const editor = { dimensions: [{ fieldname: "lot", label: "Lot", options: "SD YRP Lot", mandatory: 1 }], permissions: {} }

function mountComposer(extra = {}) {
	const component = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
		"primevue/button": Button, "primevue/message": Message, "../../components/common/LinkField.vue": LinkField,
		"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
		"../common/childGrid/rowSelection.js": rowSelection, "../../api/frappe.js": { callMethod: async () => [] },
	})
	const props = Vue.reactive({ operation: "stock_update", editor, modelValue: [], schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value }, ...extra })
	return { root: mountComponent(component, props), props }
}
const link = (root, label) => findNodes(root, (node) => node.type === "link-field" && node.props.label === label)[0]
const button = (root, label) => findNodes(root, (node) => node.type === "button" && node.props.label === label)[0]
const quantityInput = (root) => findNodes(root, (node) => node.type === "input" && node.props.type === "number")[0]
const isSelectAll = (node) => node.props["aria-label"]?.startsWith("Select all")
const rowChecks = (root) => findNodes(root, (node) => node.type === "input" && "data-row-select" in node.props && !isSelectAll(node))
const headerChecks = (root) => findNodes(root, (node) => node.type === "input" && "data-row-select" in node.props && isSelectAll(node))
const setLink = async (root, label, value) => { link(root, label).props["onUpdate:modelValue"](value); await tick() }
const colours = (props) => props.modelValue.flatMap((group) => group.items.map((row) => row.attributes.Colour))

async function composerWithLines() {
	const state = mountComposer()
	await setLink(state.root, "Lot *", "LOT-1")
	await setLink(state.root, "Item *", "Fabric A")
	button(state.root, "Get Item").props.onClick()
	await tick()
	for (const [colour, qty] of [["Cream", 5], ["Red", 7], ["Cream", 3]]) {
		await setLink(state.root, "Colour *", colour)
		typeInto(quantityInput(state.root), qty)
		await tick()
		const grid = findNodes(state.root, (node) => node.props.class === "stock-composer__quantity-grid")[0]
		const inputs = findNodes(grid, (node) => node.type === "input")
		grid.props.onKeydown({ key: "Enter", target: inputs.at(-1), currentTarget: { querySelectorAll: () => inputs }, preventDefault() {} })
		await tick()
	}
	return state
}

test("Enter on the composer's last quantity input stages the row like Add", async () => {
	const { props } = await composerWithLines()
	assert.deepEqual(colours(props), ["Cream", "Red", "Cream"])
})

test("staged items delete one selected row, then all rows via select all", async () => {
	const { root, props } = await composerWithLines()
	assert.equal(findNodes(root, (node) => node.props.title === "Delete item").length, 0)
	assert.ok(rowChecks(root).every((node) => node.props.tabindex === "-1"))
	assert.equal(button(root, "Delete"), undefined)
	rowChecks(root)[1].props.onChange({ target: { checked: true } })
	await tick()
	assert.ok(findNodes(root, (node) => node.text === "1 selected").length)
	await button(root, "Delete").props.onClick()
	await tick()
	assert.deepEqual(colours(props), ["Cream", "Cream"])
	headerChecks(root)[0].props.onChange({ target: { checked: true } })
	await tick()
	await button(root, "Delete").props.onClick()
	await tick()
	assert.deepEqual(props.modelValue, [])
})

test("read-only composer shows no row checkboxes", () => {
	const { root } = mountComposer({ readOnly: true, modelValue: [{ primary_attribute: "", attributes: [], items: [{ name: "Fabric A", values: { default: { qty: 1 } } }] }] })
	assert.equal(rowChecks(root).length, 0)
})

test("lay sheet cloth and accessory groups select rows and delete them in one confirmed batch", () => {
	const groups = read("departments/cutting/shared/MaterialRequirementGroups.vue")
	assert.doesNotMatch(groups, /emit\('delete', entry\.sourceIndex\)/)
	assert.match(groups, /<td v-if="editable" class="material-requirement-table__select"><input type="checkbox"[^>]*data-row-select tabindex="-1"/)
	assert.match(groups, /emit\("delete", indexes\)/)
	assert.match(groups, /removalOrder\(selectableKeys\.value, rowSelection\.selected\.value\)/)
	const dialog = read("departments/cutting/CuttingLaySheetDialog.vue")
	assert.match(dialog, /for \(const index of indexes\) rows\.splice\(index, 1\)/)
	assert.match(dialog, /accept: \(\) => deleteClothConfirmed\(indexes\)/)
	assert.match(dialog, /accept: \(\) => deleteAccessoryConfirmed\(indexes\)/)
})

test("bulk active lay sheet tables delete selected rows through removeCloth and removeAccessory", () => {
	const source = read("departments/cutting/bulk/BulkActiveLaySheet.vue")
	assert.doesNotMatch(source, /pi-trash" severity="danger" text rounded/)
	assert.match(source, /clothSelection\.removeSelected\(removeCloth, \(\) => !editorLocked\)/)
	assert.match(source, /accessorySelection\.removeSelected\(removeAccessory, \(\) => !editorLocked\)/)
	assert.equal(source.match(/data-row-select tabindex="-1"/g).length, 2)
	assert.equal(source.match(/data-row-select :checked="\w+Selection\.isAllSelected/g).length, 2)
	assert.match(source, /baseCanEdit\.value \? clothRows\.value\.map/)
})

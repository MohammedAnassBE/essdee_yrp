import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"

import {
	disableRows, enableRows, fillColumn, freshGrid, gridFromValues, mappingCardLines, mappingColumns, mappingOutput, setRowIncluded,
} from "../frontend/src/departments/merch/ipd/sections/bomMapping.js"
import { Vue, createTestRenderer, findNodes, loadComponent } from "./helpers/vue_renderer.mjs"
import * as garmentGrids from "../frontend/src/departments/merch/ipd/sections/garmentGrids.js"
import * as attributeValues from "../frontend/src/departments/merch/ipd/sections/attributeValues.js"

const attribute = (name, same = 0) => ({ attribute: name, same_attribute: same })
const itemTables = [attribute("Colour"), attribute("Size")]
const bomTables = [attribute("Size")]
const columns = mappingColumns(itemTables, bomTables)
assert.deepEqual(columns, { item: ["Colour", "Size"], bom: ["Size"], same: [], all_same: false })
assert.deepEqual(mappingColumns([attribute("Colour"), attribute("Size", 1)], [attribute("Size", 1), attribute("Colour")]), {
	item: ["Colour"], bom: ["Colour"], same: ["Size"], all_same: false,
})
const allSame = mappingColumns([attribute("Size", 1)], [attribute("Size", 1)])
assert.deepEqual(allSame, { item: [], bom: [], same: ["Size"], all_same: true })
assert.deepEqual(mappingColumns([], []).item, [])
assert.deepEqual(mappingColumns([attribute("Size")], [attribute("Size", 1)]).bom, ["Size"])

const sizes = ["XS", "S", "M", "L", "XL", "2XL"]
const combinations = sizes.map((Size) => ({ Colour: "Andhra Melange", Size }))
const quantities = [0.58, 0.6, 0.63, 0.65, 0.68, 0.71]
const saved = combinations.flatMap((combo, index) => [
	...columns.item.map((attr) => ({ index, type: "item", attribute: attr, attribute_value: combo[attr], quantity: quantities[index] })),
	{ index, type: "bom", attribute: "Size", attribute_value: "30 mm", quantity: quantities[index] },
])
const loaded = gridFromValues(combinations, columns, saved)
assert.equal(loaded.dropped, 0)
assert.deepEqual(loaded.rows.map((row) => row.included), sizes.map(() => true))
assert.deepEqual(loaded.rows.map((row) => row.bom.Size), sizes.map(() => "30 mm"))
assert.deepEqual(loaded.rows.map((row) => row.quantity), quantities)
assert.deepEqual(mappingOutput(loaded.rows, columns), { values: saved, problems: {}, error: "" })
{
	const partial = saved.filter((row) => row.index === 1 || row.index === 3)
	partial.push(...saved.filter((row) => row.index === 0).map((row) => ({ ...row, index: 17, attribute_value: row.type === "item" && row.attribute === "Size" ? "absent" : row.attribute_value })))
	const grid = gridFromValues(combinations.slice(0, 4), columns, partial)
	assert.deepEqual(grid.rows.map((row) => row.included), [false, true, false, true])
	assert.equal(grid.rows[0].quantity, 0, "a row without a saved line starts excluded with zero quantity")
	assert.equal(grid.dropped, 1)
	const mismatched = saved.filter((row) => row.index === 2).map((row) => ({ ...row, index: 90 }))
	assert.deepEqual(gridFromValues(combinations, columns, mismatched).rows.map((row) => row.included), [false, false, true, false, false, false])
	assert.equal(mappingOutput(grid.rows, columns).values[0].index, 1)
}
{
	let rows = loaded.rows.map((row, index) => index === 0 ? setRowIncluded(row, false) : row)
	rows = fillColumn(rows, "quantity", 0.7)
	rows = fillColumn(rows, "Size", "35 mm")
	assert.equal(rows[0].quantity, quantities[0], "excluding and filling other rows preserves the excluded quantity")
	assert.equal(rows[0].bom.Size, null)
	assert.equal(setRowIncluded(rows[0], true).quantity, quantities[0], "including the row restores its quantity")
	assert.equal(loaded.rows[0].bom.Size, "30 mm", "excluding a row preserves the input row")
	assert.equal(mappingOutput(rows, columns).values.length, 15)
	assert.deepEqual([...new Set(mappingOutput(rows, columns).values.map((row) => row.index))], [1, 2, 3, 4, 5])
	rows[1] = { ...rows[1], bom: { Size: "" } }
	assert.equal(mappingOutput(rows, columns).problems["1"]["bom:Size"], "Choose a value")
	assert.equal(mappingOutput(rows, columns).error, "Row 2: choose Size.")
	rows[1] = { ...rows[1], bom: { Size: "35 mm" }, quantity: 0 }
	assert.equal(mappingOutput(rows, columns).problems["1"].quantity, "Quantity cannot be zero")
	assert.equal(mappingOutput(rows, columns).error, "Row 2: Quantity cannot be zero.")
	assert.equal(mappingOutput(rows.map((row) => setRowIncluded(row, false)), columns).error, "Add Items to continue")
	assert.deepEqual(mappingOutput([], allSame), { values: [], problems: {}, error: "" })
	assert.equal(mappingOutput([{ ...rows[1], quantity: 0 }], { ...columns, bom: [] }).error, "Row 1: Quantity cannot be zero.")
	const invalid = freshGrid(combinations, columns)
	const output = mappingOutput(invalid, columns)
	assert.equal(output.error, "Row 1: choose Size.")
	assert.equal(Object.keys(output.problems).length, 6)
	assert.ok(Object.values(output.problems).every((cells) => cells["bom:Size"] && cells.quantity))
	assert.equal(mappingOutput([{ ...invalid[0], key: "9" }, { ...invalid[1], key: "1" }], columns).error, "Row 1: choose Size.", "report row order, independent of keys")
}
{
	const fresh = freshGrid(combinations, columns)
	assert.ok(fresh.every((row) => row.included && !row.bom.Size && row.quantity === 0))
	assert.ok(disableRows(fresh, columns).every((row) => !row.included && row.quantity === 0))
	const filled = fillColumn(fresh, "Size", "30 mm")
	assert.ok(disableRows(filled, columns).every((row) => row.included))
	assert.ok(disableRows(filled, { ...columns, bom: [] }).every((row) => !row.included && row.bom.Size === null))
	assert.ok(enableRows(disableRows(fresh, columns)).every((row) => row.included && row.bom.Size === null))
	const withQuantities = fillColumn(fresh, "quantity", 0.75)
	const disabled = disableRows(withQuantities, columns)
	assert.ok(disabled.every((row) => !row.included && row.quantity === 0.75 && row.bom.Size === null))
	assert.ok(enableRows(disabled).every((row) => row.included && row.quantity === 0.75), "Disable then Enable keeps quantities")
	assert.ok(fresh.every((row) => row.included), "helpers preserve their inputs")
}
assert.deepEqual(mappingCardLines({ rows: [...saved].reverse() }).total, 6)
assert.deepEqual(mappingCardLines({ rows: saved }), {
	lines: sizes.slice(0, 5).map((size) => `Andhra Melange, ${size} -> 30 mm`), total: 6,
})
assert.deepEqual(mappingCardLines(null), { lines: [], total: 0 })
assert.equal(mappingCardLines({ rows: saved.filter((row) => row.index === 3 || row.index === 1) }).total, 2)
assert.equal(mappingCardLines({ rows: saved.slice(0, 15) }).lines.length, 5)

const key = Symbol("editor")
const Button = {
	props: ["label", "icon", "severity", "disabled", "loading"],
	render() { return Vue.h("button", { disabled: this.disabled, "data-icon": this.icon, "data-severity": this.severity }, this.label) },
}
const Select = {
	props: ["modelValue", "options", "disabled", "invalid"], emits: ["update:modelValue"],
	render() { return Vue.h("select", { disabled: this.disabled, value: this.modelValue, onChange: (event) => this.$emit("update:modelValue", event.target.value) }, (this.options || []).map((value) => Vue.h("option", { value }, value))) },
}
const InputNumber = {
	props: ["modelValue", "disabled", "invalid"], emits: ["update:modelValue"],
	render() { return Vue.h("input", { disabled: this.disabled, value: this.modelValue, onInput: (event) => this.$emit("update:modelValue", Number(event.target.value)) }) },
}
const Checkbox = {
	props: ["modelValue", "disabled"], emits: ["update:modelValue"],
	render() { return Vue.h("input", { type: "checkbox", disabled: this.disabled, checked: this.modelValue }) },
}
const Dialog = {
	props: ["visible", "header"],
	render() { return this.visible ? Vue.h("div", [Vue.h("h2", this.header), this.$slots.default?.(), this.$slots.footer?.()]) : null },
}
const detail = {
	mapping: "map1", mapping_modified: "2026-01-01", item: "Flame Thermal Pyjama Mens I.E", bom_item: "Inner Elastic", bom_uom: "Meter",
	item_attributes: itemTables, bom_item_attributes: bomTables, item_attribute_options: ["Colour", "Size"], bom_attribute_options: ["Size"],
	columns, combinations, bom_values: { Size: ["30 mm", "35 mm"] }, values: saved, is_shared: false,
}
let calls = [], saves = [], nextDetail = detail, failedLoad = false
const Component = loadComponent(fileURLToPath(new URL("../frontend/src/departments/merch/ipd/sections/BomMappingDialog.vue", import.meta.url)), {
	"primevue/button": Button, "primevue/select": Select, "primevue/checkbox": Checkbox, "primevue/dialog": Dialog, "primevue/inputnumber": InputNumber,
	"../useIpdEditor.js": { IPD_EDITOR_KEY: key },
	"./bomMapping.js": { disableRows, enableRows, fillColumn, freshGrid, gridFromValues, mappingOutput, setRowIncluded },
	"../../../../api/merch.js": {
		async getIpdBomMapping(...args) {
			calls.push(args)
			if (failedLoad) throw Error("Load failed")
			return structuredClone(nextDetail)
		},
	},
})
let currentRoot = null
const flush = async () => {
	for (let i = 0; i < 5; i++) await Vue.nextTick()
	for (const node of findNodes(currentRoot, () => true)) {
		node.querySelector = () => null
	}
}
const nodes = (view, predicate) => findNodes(view.root, predicate)
const text = (view, value) => nodes(view, (node) => node.text === value)
const labelled = (view, label) => nodes(view, (node) => node.props["aria-label"] === label)
const button = (view, label) => nodes(view, (node) => node.type === "button" && node.text === label)[0]
function mount(readonly = false, approved = false) {
	calls = []; saves = []
	const root = { type: "root", text: "", props: {}, children: [] }
	currentRoot = root
	const visible = Vue.ref(true)
	const app = createTestRenderer().createApp({
		setup() {
			Vue.provide(key, { record: { name: "ZZ TEST bom" }, context: { bom_mappings: { row1: { mapping_modified: "2025-12-01" } } }, readonly, async saveBomMapping(...args) { saves.push(JSON.parse(JSON.stringify(args))) } })
			return () => Vue.h(Component, { visible: visible.value, bomRow: "row1", itemName: "Inner Elastic", readonly: readonly && !approved, "onUpdate:visible": (value) => { visible.value = value } })
		},
	})
	app.mount(root)
	return { root, app, visible }
}
{
	const view = mount()
	assert.equal(text(view, "Loading mapping…").length, 1)
	await flush()
	assert.deepEqual(calls, [["ZZ TEST bom", "row1", null]])
	assert.equal(text(view, "Inner Elastic Mapping").length, 1)
	assert.equal(text(view, "Flame Thermal Pyjama Mens I.E").length, 1)
	assert.equal(text(view, "Meter").length, 1)
	assert.equal(labelled(view, "Exclude row").length, 6)
	assert.equal(labelled(view, "Exclude row")[0].props["data-icon"], "pi pi-minus-circle")
	assert.equal(labelled(view, "Exclude row")[0].props["data-severity"], "danger")
	assert.equal(labelled(view, "Exclude row")[0].props["aria-pressed"], true)
	labelled(view, "Fill Quantity")[0].props.onInput({ target: { value: "0.7" } })
	await flush()
	labelled(view, "Fill Quantity column")[0].props.onClick()
	labelled(view, "Exclude row")[5].props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.disabled, true)
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.value, 0.7)
	assert.equal(labelled(view, "Row 6 BOM Size")[0].props.value, null)
	assert.equal(labelled(view, "Row 6 BOM Size")[0].props.placeholder, "")
	assert.equal(labelled(view, "Include row")[0].props["data-icon"], "pi pi-plus-circle")
	assert.equal(labelled(view, "Include row")[0].props["aria-pressed"], false)
	labelled(view, "Include row")[0].props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.disabled, false)
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.value, 0.7)
	assert.equal(labelled(view, "Row 6 BOM Size")[0].props.value, null)
	labelled(view, "Exclude row")[5].props.onClick()
	await flush()
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(view.visible.value, false)
	assert.equal(saves[0][0], "row1")
	assert.equal(saves[0][1].length, 15)
	assert.ok(saves[0][1].every((row) => row.quantity === 0.7))
	assert.deepEqual(saves[0][2], { item_attributes: itemTables, bom_item_attributes: bomTables })
	assert.equal(saves[0][3], detail.mapping_modified, "save uses the token loaded by the dialog")
	nextDetail = { ...detail, mapping_modified: "2026-01-02", values: saved.map((row) => ({ ...row, quantity: 0.8 })) }
	view.visible.value = true
	await flush()
	assert.equal(calls.length, 2)
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.value, 0.8)
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(saves[1][3], nextDetail.mapping_modified, "reopening saves with the newly loaded token")
	assert.ok(saves[1][1].every((row) => row.quantity === 0.8))
	view.app.unmount()
	nextDetail = detail
}
{
	nextDetail = { ...detail, values: saved.filter((row) => row.index !== 5) }
	const view = mount()
	await flush()
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.value, null, "an excluded row without a saved line displays a blank quantity")
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.disabled, true)
	labelled(view, "Row 1 BOM Size")[0].props.onChange({ target: { value: "" } })
	await flush()
	button(view, "Disable").props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.value, quantities[0])
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.disabled, true)
	button(view, "Enable").props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.value, quantities[0])
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.disabled, false)
	assert.equal(labelled(view, "Row 6 Quantity")[0].props.value, 0, "including an initially excluded row keeps its stored zero quantity")
	view.app.unmount()
	nextDetail = detail
}
{
	const view = mount()
	await flush()
	labelled(view, "Row 1 BOM Size")[0].props.onChange({ target: { value: "" } })
	await flush()
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 1 BOM Size")[0].props["aria-invalid"], true)
	assert.equal(text(view, "Choose a value").length, 1)
	assert.equal(text(view, "Row 1: choose Size.").length, 1)
	assert.equal(saves.length, 0)
	labelled(view, "Row 1 BOM Size")[0].props.onChange({ target: { value: "30 mm" } })
	labelled(view, "Row 1 Quantity")[0].props.onInput({ target: { value: "0" } })
	await flush()
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(labelled(view, "Row 1 Quantity")[0].props["aria-invalid"], true)
	assert.equal(text(view, "Row 1: Quantity cannot be zero.").length, 1)
	assert.equal(saves.length, 0)
	view.app.unmount()
}
{
	const view = mount()
	await flush()
	labelled(view, "Item Attributes row 2 Attribute")[0].props.onChange({ target: { value: "Colour" } })
	await flush()
	button(view, "Get Combination").props.onClick()
	await flush()
	assert.equal(calls.length, 1, "invalid table edits must not send a request")
	assert.equal(text(view, "Item Attributes: duplicate attribute.").length, 1)
	labelled(view, "Item Attributes row 2 Attribute")[0].props.onChange({ target: { value: "Size" } })
	await flush()
	button(view, "Get Combination").props.onClick()
	await flush()
	assert.deepEqual(calls[1][2], { item_attributes: itemTables, bom_item_attributes: bomTables })
	assert.equal(labelled(view, "Exclude row").length, 6)
	assert.equal(labelled(view, "Row 1 BOM Size")[0].props.value, null)
	assert.equal(labelled(view, "Row 1 Quantity")[0].props.value, 0)
	view.app.unmount()
}
for (const mode of ["record", "approved"]) {
	nextDetail = { ...detail, values: saved.filter((row) => row.index !== 5) }
	const view = mount(true, mode === "approved")
	await flush()
	for (const label of ["Add row", "Save mapping", "Get Combination", "Disable", "Enable", "Fill"]) assert.equal(button(view, label), undefined)
	assert.equal(nodes(view, (node) => node.type === "input" || node.type === "select").length, 0, mode)
	assert.deepEqual(nodes(view, (node) => node.type === "button").map((node) => node.text), ["Cancel"], mode)
	assert.equal(labelled(view, "Included").length, 5)
	assert.equal(labelled(view, "Excluded").length, 1)
	assert.ok([...labelled(view, "Included"), ...labelled(view, "Excluded")].every((node) => node.type === "span" && node.props.role === "img"))
	assert.ok(text(view, "Colour").length)
	assert.ok(text(view, "No").length)
	assert.equal(text(view, "30 mm").length, 5)
	assert.equal(text(view, "0.58").length, 1)
	const excluded = nodes(view, (node) => node.type === "tr" && node.props.class?.includes("is-excluded"))[0]
	const cells = excluded.children.filter((node) => node.type === "td")
	assert.ok(cells.slice(-2).every((cell) => cell.children.length === 2 && cell.children[0].type === "span" && cell.children[0].text === ""), "excluded BOM and quantity text cells are blank")
	view.app.unmount()
	nextDetail = detail
}
{
	const polyTables = [attribute("Colour")]
	const polyColumns = mappingColumns(polyTables, bomTables)
	nextDetail = { ...detail, bom_item: "Plain Poly Bag Big", item_attributes: polyTables, columns: polyColumns, combinations: [{ Colour: "Andhra Melange" }], values: saved.filter((row) => row.index === 0 && !(row.type === "item" && row.attribute === "Size")) }
	const view = mount()
	await flush()
	labelled(view, "Add Item Attributes row")[0].props.onClick()
	await flush()
	labelled(view, "Item Attributes row 2 Attribute")[0].props.onChange({ target: { value: "Size" } })
	await flush()
	nextDetail = { ...detail, bom_item: "Plain Poly Bag Big", bom_values: { Size: ["8.5 x 11 + 2"] } }
	button(view, "Get Combination").props.onClick()
	await flush()
	assert.deepEqual(calls[1][2], { item_attributes: itemTables, bom_item_attributes: bomTables })
	assert.equal(labelled(view, "Exclude row").length, 6)
	assert.ok(nodes(view, (node) => node.type === "select" && String(node.props["aria-label"]).includes("BOM Size")).every((node) => !node.props.value))
	labelled(view, "Fill BOM Size")[0].props.onChange({ target: { value: "8.5 x 11 + 2" } })
	labelled(view, "Fill Quantity")[0].props.onInput({ target: { value: "1" } })
	await flush()
	labelled(view, "Fill BOM Size column")[0].props.onClick()
	labelled(view, "Fill Quantity column")[0].props.onClick()
	await flush()
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(saves[0][1].length, 18)
	assert.deepEqual(saves[0][2].item_attributes, itemTables)
	assert.equal(view.visible.value, false)
	view.app.unmount()
	nextDetail = detail
}
{
	nextDetail = { ...detail, bom_item: "Inner Box", columns: mappingColumns([attribute("Colour")], []), item_attributes: [attribute("Colour")], bom_item_attributes: [], combinations: [{ Colour: "Andhra Melange" }], values: [] }
	const view = mount()
	await flush()
	assert.equal(labelled(view, "Include row").length, 1)
	button(view, "Save mapping").props.onClick()
	await flush()
	assert.equal(text(view, "Add Items to continue").length, 1)
	assert.equal(saves.length, 0)
	view.app.unmount()
	nextDetail = detail
}
{
	failedLoad = true
	const view = mount()
	await flush()
	assert.equal(text(view, "Load failed").length, 1)
	assert.equal(button(view, "Save mapping").props.disabled, true)
	view.app.unmount()
	failedLoad = false
}
{
	const blank = { render: () => null }
	const Accessories = loadComponent(fileURLToPath(new URL("../frontend/src/departments/merch/ipd/sections/IpdAccessoriesSection.vue", import.meta.url)), {
		"primevue/button": Button, "primevue/select": Select, "primevue/inputtext": blank,
		"../../../../components/common/EntryGrid.vue": blank,
		"../IpdSection.vue": { props: ["sectionKey"], render() { return this.$slots.default?.() } },
		"../useIpdEditor.js": { IPD_EDITOR_KEY: key }, "./attributeValues.js": attributeValues,
		"./garmentGrids.js": garmentGrids, "./bomMapping.js": { mappingCardLines },
		"./IpdChoiceChips.vue": blank, "./IpdGridNotice.vue": blank,
		"./sectionFocus.js": { useSectionFocus() {} },
		"./BomMappingDialog.vue": { props: ["visible", "bomRow", "readonly"], render() { return this.visible ? Vue.h("output", `${this.bomRow}:${this.readonly}`) : null } },
	})
	for (const readonly of [false, true]) {
		const root = { type: "root", text: "", props: {}, children: [] }
		const app = createTestRenderer().createApp({
			setup() {
				Vue.provide(key, {
					readonly, isNew: true, gridErrors: () => ({}),
					draft: { item_bom: [{ name: "elastic", item: "Inner Elastic", based_on_attribute_mapping: 1 }, { item: "New BOM", based_on_attribute_mapping: 1 }] },
					context: { bom_mappings: { elastic: { rows: saved, is_shared: false } } },
				})
				return () => Vue.h(Accessories, { part: "bom", sectionKey: "accessories" })
			},
		})
		app.mount(root)
		currentRoot = root
		const view = { root }
		await flush()
		assert.equal(text(view, "Inner Elastic Mapping").length, 1)
		assert.equal(text(view, "+1 more").length, 1)
		assert.equal(text(view, "Andhra Melange, XS -> 30 mm").length, 1)
		assert.equal(text(view, "Save the IPD to create this mapping").length, 1)
		assert.equal(nodes(view, (node) => node.type === "button").length, 1)
		button(view, readonly ? "View" : "Edit").props.onClick()
		await flush()
		assert.equal(text(view, `elastic:${readonly}`).length, 1)
		app.unmount()
	}
}
for (const name of ["IpdAccessoriesSection", "IpdProcessesSection", "IpdStitchingSection", "IpdSetItemSection", "IpdPackingSection", "IpdCuttingSection", "IpdPanelWiseGrids"]) {
	const source = readFileSync(new URL(`../frontend/src/departments/merch/ipd/sections/${name}.vue`, import.meta.url), "utf8")
	const toolbars = [...source.matchAll(/:toolbar="([^"]*)"/g)].map((match) => match[1])
	assert.ok(toolbars.length)
	assert.ok(toolbars.every((toolbar) => !toolbar.includes("paste") && !toolbar.includes("clear")), name)
	if (["IpdProcessesSection", "IpdStitchingSection", "IpdSetItemSection", "IpdPackingSection"].includes(name)) assert.ok(toolbars.every((toolbar) => toolbar === "[]"), name)
}
console.log("ipd BOM mapping helper and dialog tests passed")

#!/usr/bin/env node
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import { Vue, createTestRenderer, findNodes, loadComponent } from "./helpers/vue_renderer.mjs"
import { applyBlock, clearRange, coerceCell, displayCell, fillDown, fillRight, isCellEditable } from "../frontend/src/components/common/entryGrid.js"
import { stableStringify } from "../frontend/src/departments/merch/ipd/ipdEditor.js"
import * as attributes from "../frontend/src/departments/merch/ipd/sections/attributeValues.js"
import * as bomMapping from "../frontend/src/departments/merch/ipd/sections/bomMapping.js"
import { clothDetailChanges, duplicateClothNames } from "../frontend/src/departments/merch/ipd/sections/clothRename.js"
import * as grids from "../frontend/src/departments/merch/ipd/sections/garmentGrids.js"
import {
	COLUMN_SEPARATOR,
	addEmbellishment,
	applyDefaultRadio,
	assortmentFromModel,
	assortmentGrid,
	bundleGroupProblems,
	combinationFromModel,
	combinationGrid,
	embellishmentFromModel,
	embellishmentGrid,
	groupPanels,
	itemsFromModel,
	itemsGrid,
	markerFromModel,
	markerGrid,
	missingCellErrors,
	panelClothFromModel,
	panelClothGrid,
	panelGroupErrors,
	panelGroupFromModel,
	panelGroupGrid,
	processRowsFromModel,
	hasStageMismatch,
	syncProcessStages,
	removeEmbellishment,
	removeTableRow,
	splitWeight,
	stitchingAccessoryFromModel,
	stitchingAccessoryGrid,
	stitchingAccessoryKey,
	tableFromModel,
	tableGrid,
	toggleChoice,
	toggleValueRow,
	ungroupPanel,
} from "../frontend/src/departments/merch/ipd/sections/garmentGrids.js"
import { isComboDerived, packingChanges } from "../frontend/src/departments/merch/ipd/sections/packingSection.js"
import { reviewSummary } from "../frontend/src/departments/merch/ipd/sections/reviewSummary.js"

const samples = JSON.parse(readFileSync(new URL("./fixtures/ipd_samples.json", import.meta.url), "utf8"))
const same = (left, right, message) => assert.equal(stableStringify(left), stableStringify(right), message)

const TABLES = {
	packing_attribute_details: [["quantity"], "attribute_value"],
	packing_size_details: [["quantity"], "attribute_value"],
	stiching_item_details: [["set_item_attribute_value", "quantity", "category", "is_default"], "stiching_attribute_value"],
	cloth_detail: [["name1", "cloth", "required_gsm", "is_bom_item"], ""],
	item_bom: [["item", "process_name", "dependent_attribute_value", "qty_of_product", "qty_of_bom_item", "based_on_attribute_mapping", "wastage_pct"], ""],
	ipd_processes: [["process_name", "process_item", "in_stage", "out_stage"], ""],
}
const ITEM_GRIDS = { cutting_items_json: ["Dia", "Weight", "Required GSM"], cutting_cloths_json: ["Cloth"], cloth_accessory_json: ["Dia", "Weight"] }

function roundTrips(name, values) {
	for (const [table, [fields, keyField]] of Object.entries(TABLES)) {
		const rows = values[table] || []
		const grid = tableGrid(rows, fields, { keyField })
		const back = tableFromModel(rows, grid.model, fields, { keyField })
		assert.ok(back.every((row, index) => row === rows[index]), `${name} ${table} keeps row identity`)
	}
	for (const key of ["set_item_detail", "stiching_item_detail"]) {
		const value = values[key]
		if (!value?.values?.length) continue
		const back = combinationFromModel(value, combinationGrid(value).model)
		same(back, value, `${name} ${key} round trip`)
		assert.ok(back.values.every((row, index) => row === value.values[index]), `${name} ${key} keeps rows`)
	}
	for (const [key, carry] of Object.entries(ITEM_GRIDS)) {
		const value = values[key]
		if (!value?.items?.length) continue
		const back = itemsFromModel(value, itemsGrid(value, carry).model, carry)
		same(back, value, `${name} ${key} round trip`)
		assert.ok(back.items.every((row, index) => row === value.items[index]), `${name} ${key} keeps items`)
	}
	const accessory = values.stiching_accessory_json
	if (accessory?.items?.length) same(stitchingAccessoryFromModel(accessory, stitchingAccessoryGrid(accessory).model), accessory, `${name} stitching accessory`)
	const embellishment = values.emblishment_details_json || {}
	same(embellishmentFromModel(embellishment, embellishmentGrid(embellishment, []).model, []), embellishment, `${name} embellishment`)
	const groups = values.marker_groups || []
	const panels = (values.stiching_item_details || []).map((row) => row.stiching_attribute_value)
	same(markerFromModel(groups, markerGrid(groups, panels).model, panels), groups, `${name} marker groups`)
	const matrix = values.panel_wise_consumption_matrix_json
	for (const panel of matrix?.panels || []) {
		same(panelGroupFromModel(matrix, panel.group_id, panelGroupGrid(matrix, panel).model), matrix, `${name} panel ${panel.group_id}`)
	}
	const cloth = values.panel_wise_cloth_mapping_json
	for (const panel of cloth?.panels || []) {
		const grid = panelClothGrid(cloth, panel)
		assert.ok(grid.columns.every((column) => column.fill === true))
		same(panelClothFromModel(cloth, panel.group_id, grid.model), cloth, `${name} cloth ${panel.group_id}`)
	}

}

for (const [name, sample] of Object.entries(samples)) roundTrips(name, { ...sample.values, bom_mappings: sample.bom_mappings })

const standard = samples.standard.values
{
	const attributes = ["Dia", "Weight", "Required GSM", "Cloth"]
	for (const diaOptions of [[], ["32 Dia"]]) {
		const grid = itemsGrid({ attributes, items: [{}] }, attributes, { diaOptions, clothOptions: ["Main"] })
		assert.ok(grid.columns.every((column) => column.fill === true))
	}
}
{
	const value = standard.cutting_items_json
	const grid = itemsGrid(value, ITEM_GRIDS.cutting_items_json)
	assert.equal(grid.rowHeaderLabel, "Panel")
	assert.deepEqual(grid.columns.map((column) => column.key), ["Dia", "Weight"])
	const first = grid.rows[0].key
	const edited = itemsFromModel(value, { ...grid.model, [first]: { ...grid.model[first], Weight: 0.5 } }, ITEM_GRIDS.cutting_items_json)
	assert.equal(edited.items[0].Weight, 0.5)
	assert.equal(edited.items[1], value.items[1])
	assert.equal(edited.select_list, value.select_list)
}
{
	const blank = { attributes: ["Panel", "Dia", "Weight"], items: [{ Panel: "Front" }] }
	same(itemsFromModel(blank, itemsGrid(blank, ["Dia", "Weight"]).model, ["Dia", "Weight"]), blank, "missing carry keys stay missing")
}

{
	const value = {
		attributes: ["Panel", "Size", "Dia", "Weight"],
		items: [
			{ Panel: "Front", Size: "80 cm", Dia: "44 Dia", Weight: 0.009 },
			{ Panel: "Back", Size: "90 cm", Dia: "42 Dia", Weight: 0.01 },
		],
	}
	const carry = ITEM_GRIDS.cutting_items_json
	const diaOptions = ["42 Dia", "44 Dia", "44.5 Dia", ...Array.from({ length: 25 }, (_, index) => `${144 + index} Dia`)]
	const original = itemsGrid(value, carry)
	const grid = itemsGrid(value, carry, { attributeColumns: true, diaOptions })
	assert.equal(grid.rowHeaderLabel, "Panel")
	assert.equal(grid.rows[0].label, "Front")
	assert.deepEqual(grid.columns.map((column) => column.key), ["Size", "Dia", "Weight"])
	assert.deepEqual(grid.columns[0], { key: "Size", label: "Size", type: "text", readonly: true })
	assert.equal(grid.model[grid.rows[0].key].Size, "80 cm")
	assert.deepEqual(grid.rows.map((row) => row.key), original.rows.map((row) => row.key))
	assert.equal(original.rowHeaderLabel, "Panel · Size")
	assert.equal(original.rows[0].label, "Front · 80 cm")
	assert.deepEqual(original.columns.map((column) => column.key), ["Dia", "Weight"])
	const back = itemsFromModel(value, grid.model, carry)
	same(back, value, "attribute columns round trip")
	assert.ok(back.items.every((item, index) => item === value.items[index]))
	const changed = structuredClone(grid.model)
	changed[grid.rows[0].key].Size = "100 cm"
	assert.equal(itemsFromModel(value, changed, carry).items[0], value.items[0], "readonly attributes are ignored")
	for (const Panel of ["", null, undefined]) {
		assert.equal(itemsGrid({ ...value, items: [{ Panel, Size: "80 cm" }] }, carry, { attributeColumns: true }).rows[0].label, "—")
	}
	const dia = grid.columns[1]
	assert.equal(dia.fill, true)
	assert.equal(grid.columns[2].fill, true)
	assert.equal(original.columns[0].fill, true, "free text Dia supports Fill")
	assert.equal(dia.type, "link")
	assert.equal(dia.doctype, "Item Attribute Value")
	assert.equal(dia.field, "dia")
	assert.equal(dia.width, 140)
	assert.deepEqual(dia.options, diaOptions.map((value) => ({ value, label: value })))
	assert.deepEqual(dia.searchHandler("44"), ["44 Dia", "44.5 Dia", "144 Dia"].map((value) => ({ name: value, label: value })))
	assert.deepEqual(dia.searchHandler("dIA"), diaOptions.slice(0, 20).map((value) => ({ name: value, label: value })))
	assert.deepEqual(dia.searchHandler(""), diaOptions.slice(0, 20).map((value) => ({ name: value, label: value })))
	assert.deepEqual(dia.searchHandler("zzz"), [])
	const rankedOptions = ["15.25 Dia", "15.5 Dia", "115 Dia", "15 Dia", "150 Dia"]
	const rankedDia = itemsGrid(value, carry, { diaOptions: rankedOptions }).columns[0]
	assert.deepEqual(rankedDia.searchHandler("15").map(({ name }) => name), ["15 Dia", "150 Dia", "15.5 Dia", "15.25 Dia", "115 Dia"])
	assert.deepEqual(rankedDia.searchHandler("15 dia").map(({ name }) => name), ["15 Dia", "115 Dia"])
	assert.deepEqual(rankedDia.searchHandler("1").map(({ name }) => name), ["15 Dia", "115 Dia", "150 Dia", "15.5 Dia", "15.25 Dia"])
	assert.deepEqual(rankedDia.searchHandler("").map(({ name }) => name), rankedOptions)
	assert.deepEqual(coerceCell(dia, "44 dia"), { value: "44 Dia", error: "" })
	assert.deepEqual(coerceCell(dia, "99 Foo"), { value: null, error: "99 Foo is not one of the allowed values." })
	assert.equal(displayCell(dia, "Legacy Dia"), "Legacy Dia")
	assert.deepEqual(original.columns[1], grid.columns[2], "Weight stays unchanged")
	const accessoryDia = original.columns[0]
	assert.equal(accessoryDia.type, "text", "Dia without configured values stays free text")
	assert.deepEqual(coerceCell(accessoryDia, "Legacy Dia"), { value: "Legacy Dia", error: "" })
	assert.equal(isCellEditable(grid.rows, grid.columns, 0, 0), false)
	const range = { top: 0, bottom: 1, left: 0, right: 2 }
	const pasted = applyBlock(grid.model, grid.rows, grid.columns, { row: 0, col: 0 }, [["100 cm", "44 dia", "0.0123"]])
	assert.equal(pasted.readonly, 1)
	assert.equal(pasted.model[grid.rows[0].key].Size, "80 cm")
	for (const operation of [fillRight, fillDown, clearRange]) {
		assert.equal(operation(grid.model, grid.rows, grid.columns, range).model[grid.rows[1].key].Size, "90 cm")
	}
}

const setSample = samples.set_item.values
{
	const value = setSample.stiching_item_detail
	const grid = combinationGrid(value, { readonlyColumn: setSample.stiching_major_attribute_value })
	assert.ok(grid.columns.find((column) => column.key === setSample.stiching_major_attribute_value).readonly)
	const major = grid.rows[0].key
	const part = value.attributes[1]
	const edited = combinationFromModel(value, { ...grid.model, [major]: { ...grid.model[major], [part]: "Bright Red" } })
	assert.equal(edited.values[0].val[part], "Bright Red")
	assert.deepEqual(Object.keys(edited.values[0].val), Object.keys(value.values[0].val))
}
{
	const accessory = setSample.stiching_accessory_json
	const grid = stitchingAccessoryGrid(accessory, { colourOptions: ["Bright Red"], clothOptions: ["MAIN FABRIC"] })
	assert.equal(grid.rows[0].key, ["FOLDING", "Top", "Pink Stripes Bow AO"].join("\u001f"))
	assert.equal(grid.rowHeaderLabel, "Accessory")
	assert.equal(grid.rows[0].label, "FOLDING")
	assert.deepEqual(grid.columns.map((column) => column.key), ["set_part", "major_colour", "accessory_colour", "cloth_type"])
	assert.deepEqual(grid.columns.slice(0, 2), [
		{ key: "set_part", label: accessory.set_attr, type: "text", readonly: true },
		{ key: "major_colour", label: "Major colour", type: "text", readonly: true },
	])
	assert.equal(grid.model[grid.rows[0].key].set_part, "Top")
	assert.equal(grid.model[grid.rows[0].key].major_colour, "Pink Stripes Bow AO")
	assert.ok(grid.columns.slice(2).every((column) => column.fill === true && !column.readonly))
	assert.deepEqual(grid.columns[2].options, [{ value: "Bright Red", label: "Bright Red" }])
	assert.deepEqual(grid.columns[3].options, [{ value: "MAIN FABRIC", label: "MAIN FABRIC" }])
	const readonlyEdit = structuredClone(grid.model)
	Object.assign(readonlyEdit[grid.rows[0].key], { set_part: "Bottom", major_colour: "Black" })
	same(stitchingAccessoryFromModel(accessory, readonlyEdit), accessory, "readonly stitching attributes are ignored")
	const edited = stitchingAccessoryFromModel(accessory, { ...grid.model, [grid.rows[0].key]: { accessory_colour: "White", cloth_type: "MAIN FABRIC" } })
	assert.equal(edited.items[0].accessory_colour, "White")
	assert.equal(edited.items[0].cloth_type, "MAIN FABRIC")
	assert.deepEqual(Object.keys(edited.items[0]), Object.keys(accessory.items[0]))
	assert.equal(edited.items[2].major_attr_value, "Pink Stripes Bow AO")
	const withoutSet = stitchingAccessoryGrid({ items: [{ accessory: "Tape", major_colour: "Red" }] })
	assert.deepEqual(withoutSet.columns.map((column) => column.key), ["major_colour", "accessory_colour", "cloth_type"])
	assert.equal(withoutSet.rows[0].key, stitchingAccessoryKey({ accessory: "Tape", major_colour: "Red" }, ""))
	const duplicates = stitchingAccessoryGrid({ ...accessory, items: [accessory.items[0], accessory.items[0]] })
	assert.equal(duplicates.rows[1].key, `${duplicates.rows[0].key}\u001f#1`)
	const colliding = stitchingAccessoryGrid({ set_attr: "accessory_colour", items: [{ accessory: "Tape", accessory_colour: "White", major_colour: "Red" }] })
	assert.equal(new Set(colliding.columns.map((column) => column.key)).size, 4)
}

{
	const value = { attributes: ["Accessory", "Part", "Dia", "Weight"], items: [
		{ Accessory: "Folding", Part: "Top", Dia: null, Weight: " \t" },
		{ Accessory: "Tape", Part: "Bottom", Dia: "", Weight: undefined },
	] }
	const carry = ["Dia", "Weight"]
	const grid = itemsGrid(value, carry, { attributeColumns: true, diaOptions: ["32 Dia"] })
	assert.equal(grid.rowHeaderLabel, "Accessory")
	assert.equal(grid.rows[0].label, "Folding")
	assert.deepEqual(grid.columns.map((column) => [column.key, column.readonly, column.fill]), [["Part", true, undefined], ["Dia", undefined, true], ["Weight", undefined, true]])
	assert.equal(grid.columns[1].type, "link")
	assert.deepEqual(grid.columns[1].searchHandler("32"), [{ name: "32 Dia", label: "32 Dia" }])
	const unchecked = {}
	assert.equal(missingCellErrors(grid, unchecked).errors, unchecked, "no errors before checks")
	assert.equal(missingCellErrors(grid, unchecked).summary, "")
	const [first, second] = grid.rows.map((row) => row.key)
	const serverErrors = { [first]: { Dia: "Fill all the combinations" } }
	const before = structuredClone(grid.model)
	const result = missingCellErrors(grid, serverErrors)
	assert.deepEqual(result.errors, {
		[first]: { Dia: "Dia is required", Weight: "Weight (kg) is required" },
		[second]: { Dia: "Dia is required", Weight: "Weight (kg) is required" },
	})
	assert.equal(result.summary, "2 rows have empty or invalid cells: Folding · Top (Dia, Weight (kg)); Tape · Bottom (Dia, Weight (kg))")
	assert.deepEqual(grid.model, before, "validation is pure")
	assert.deepEqual(serverErrors, { [first]: { Dia: "Fill all the combinations" } })
	grid.model[first].Dia = "32 Dia"
	assert.equal(missingCellErrors(grid, serverErrors).errors[first].Dia, undefined, "filled server cell is dropped")
	assert.equal(missingCellErrors(grid, { [first]: { Weight: "Use the garment weight" } }).errors[first].Weight, "Use the garment weight")
	Object.assign(grid.model[first], { Part: "Changed", Weight: 0 })
	const saved = itemsFromModel(value, grid.model, carry)
	assert.equal(saved.items[0].Part, "Top")
	assert.equal(saved.items[0].Dia, "32 Dia")
	assert.equal(saved.items[0].Weight, 0)
	Object.assign(grid.model[second], { Dia: "32 Dia", Weight: 0.01 })
	assert.deepEqual(missingCellErrors(grid, serverErrors), { errors: {}, summary: "" })
}

{
	const value = { set_attr: "Part", items: Array.from({ length: 6 }, (_, index) => ({ accessory: `Folding ${index}`, Part: "Top", major_colour: "Red", accessory_colour: null, cloth_type: "Gone" })) }
	const grid = stitchingAccessoryGrid(value)
	const first = grid.rows[0].key
	const serverErrors = { [first]: { accessory_colour: "Fill all the combinations" } }
	const isMissing = (value, column) => column.key === "cloth_type" && !["Main"].includes(value) ? "Choose a cloth from Cloth Details" : false
	const result = missingCellErrors(grid, serverErrors, isMissing)
	assert.equal(Object.keys(result.errors).length, 6)
	assert.deepEqual(result.errors[first], { accessory_colour: "Accessory colour is required", cloth_type: "Choose a cloth from Cloth Details" })
	assert.match(result.summary, /^6 rows have empty or invalid cells: Folding 0 · Top · Red \(Accessory colour, Cloth\)/)
	assert.match(result.summary, /; \+2 more$/)
	assert.doesNotMatch(result.summary, /Folding 4|Folding 5/)
	assert.equal(missingCellErrors(grid, { [first]: { cloth_type: "Server cloth problem" } }, isMissing).errors[first].cloth_type, "Server cloth problem")
	grid.model[first].cloth_type = " "
	assert.equal(missingCellErrors(grid, serverErrors, isMissing).errors[first].cloth_type, "Cloth is required")
	assert.equal(missingCellErrors(grid, { [first]: { cloth_type: "Server cloth problem" } }, isMissing).errors[first].cloth_type, "Server cloth problem")
	Object.assign(grid.model[first], { accessory_colour: "White", cloth_type: "Main" })
	assert.equal(missingCellErrors(grid, serverErrors, isMissing).errors[first], undefined)
}

async function testAccessoryValidation() {
	const editorKey = Symbol("editor")
	const blank = { render: () => null }
	const section = loadComponent("frontend/src/departments/merch/ipd/sections/IpdAccessoriesSection.vue", {
		"primevue/button": blank, "primevue/inputtext": blank, "primevue/select": blank,
		"../../../../components/common/EntryGrid.vue": { render() { return Vue.h("grid", this.$attrs) } },
		"../IpdSection.vue": { render() { return Vue.h("section", this.$slots.default?.()) } },
		"../useIpdEditor.js": { IPD_EDITOR_KEY: editorKey },
		"./attributeValues.js": attributes, "./bomMapping.js": bomMapping, "./garmentGrids.js": grids,
		"./BomMappingDialog.vue": blank, "./IpdChoiceChips.vue": blank,
		"./sectionFocus.js": { useSectionFocus() {} },
	})
	const serverErrors = Vue.reactive({})
	const editor = Vue.reactive({
		draft: {
			cloth_detail: [{ name1: "Main" }],
			cloth_accessory_json: { attributes: ["Accessory", "Part", "Dia", "Weight"], items: [{ Accessory: "Folding", Part: "Top", Dia: "", Weight: null }] },
			stiching_accessory_json: { set_attr: "Part", items: [{ accessory: "Folding", Part: "Top", major_colour: "Red", accessory_colour: "", cloth_type: "Gone" }] },
		},
		context: { cutting: { dia_values: ["32 Dia"] } }, readonly: false,
		gridErrors(field) { return serverErrors[field] || {} },
		problemsFor: () => Object.keys(serverErrors).map((field) => ({ field, message: "Fill all the combinations" })),
		gridDrift: {},
		setValue(field, value) { this.draft[field] = value },
	})
	const root = { type: "root", props: {}, children: [] }
	const app = createTestRenderer().createApp({ setup() {
		Vue.provide(editorKey, editor)
		return () => Vue.h("div", ["accessories", "stitching"].map((part) => Vue.h(section, { part, sectionKey: "accessories" })))
	} })
	app.mount(root)
	const notices = () => findNodes(root, (node) => node.props.role === "alert")
	const gridFor = (field) => findNodes(root, (node) => node.type === "grid" && node.props["validation-field"] === field)[0].props
	try {
		assert.equal(notices().length, 0, "no notices before checks")
		for (const [field, cells] of [
			["cloth_accessory_json", { Dia: "32 Dia", Weight: 0.01 }],
			["stiching_accessory_json", { accessory_colour: "White", cloth_type: "Main" }],
		]) {
			const grid = gridFor(field)
			const rowKey = grid.rows[0].key
			const [first, second] = Object.keys(cells)
			serverErrors[field] = { [rowKey]: { [first]: "Fill all the combinations" } }
			await Vue.nextTick()
			assert.deepEqual(Object.keys(gridFor(field).errors[rowKey]), [first, second])
			assert.equal(notices().length, 1, "only the detailed notice is shown")
			const noticeText = findNodes(notices()[0], () => true).map((node) => node.text).join(" ")
			assert.match(noticeText, /Folding · Top/)
			assert.doesNotMatch(noticeText, /more in Checks/)
			if (field === "stiching_accessory_json") assert.equal(gridFor(field).errors[rowKey][second], "Choose a cloth from Cloth Details")
			grid["onUpdate:modelValue"]({ [rowKey]: { ...grid["model-value"][rowKey], [first]: cells[first] } })
			await Vue.nextTick()
			assert.deepEqual(Object.keys(gridFor(field).errors[rowKey]), [second], "filled server error clears live")
			gridFor(field)["onUpdate:modelValue"]({ [rowKey]: { ...grid["model-value"][rowKey], ...cells } })
			await Vue.nextTick()
			assert.deepEqual(gridFor(field).errors, {})
			delete serverErrors[field]
			await Vue.nextTick()
			assert.equal(notices().length, 0, "notice clears when the checks rerun")
		}
		const consumption = gridFor("cloth_accessory_json")
		assert.deepEqual(consumption.columns.map((column) => column.key), ["Part", "Dia", "Weight"])
		assert.deepEqual(consumption.columns[1].options, [{ value: "32 Dia", label: "32 Dia" }])
	} finally { app.unmount() }
}

await testAccessoryValidation()

{
	const rows = [{ stiching_attribute_value: "A", set_item_attribute_value: "Top", is_default: 1 }, { stiching_attribute_value: "B", set_item_attribute_value: "Top", is_default: 0 }, { stiching_attribute_value: "C", set_item_attribute_value: "Bottom", is_default: 1 }]
	const after = applyDefaultRadio(rows, [rows[0], { ...rows[1], is_default: 1 }, rows[2]])
	assert.deepEqual(after.map((row) => row.is_default), [0, 1, 1])
	assert.equal(applyDefaultRadio(rows, rows), rows)
}
{
	const rows = [{ name: "a", attribute_value: "Black", quantity: 0 }]
	assert.equal(toggleValueRow(rows, "attribute_value", "Black", true, () => ({})), rows)
	assert.deepEqual(toggleValueRow(rows, "attribute_value", "Navy", true, (value) => ({ attribute_value: value, quantity: 0 })).map((row) => row.attribute_value), ["Black", "Navy"])
	assert.deepEqual(toggleValueRow(rows, "attribute_value", "Black", false), [])
	assert.deepEqual(removeTableRow([{ name: "x" }, {}, {}], "new:1"), [{ name: "x" }, {}])
}
{
	const saved = [{ name: "a", stiching_attribute_value: "Front", set_item_attribute_value: "Top", quantity: 2, category: "Rib", is_default: 1 }, { name: "b", stiching_attribute_value: "Back", set_item_attribute_value: "Top", quantity: 1, category: "Body", is_default: 0 }]
	const memory = new Map()
	const make = (value) => ({ stiching_attribute_value: value, set_item_attribute_value: null, quantity: 1, category: "Body", is_default: 0 })
	const toggle = (rows, value, on, savedRows = saved) => grids.toggleRememberedRow(rows, "stiching_attribute_value", value, on, make, { memory, savedRows })
	const cleared = toggle(toggle(saved, "Front", false), "Back", false)
	assert.deepEqual(cleared, [])
	const restored = toggle(toggle(cleared, "Front", true), "Back", true)
	assert.deepEqual(restored, saved, "Clear all then Select all keeps every row value and saved row name")
	assert.deepEqual(toggle([], "Sleeve", true), [make("Sleeve")], "a never-ticked panel gets a fresh row")
	assert.deepEqual(toggle([], "Front", true, []), [{ ...saved[0], name: undefined }].map(({ name: _name, ...row }) => row), "a row deleted by a save drops its stale name")
}

{
	assert.deepEqual(splitWeight(0.127, 2), [0.0635, 0.0635])
	assert.deepEqual(splitWeight(0.1, 3), [0.033333, 0.033333, 0.033334])
	assert.deepEqual(splitWeight(null, 2), [null, null])
	const matrix = {
		attributes: { primary: "Size" },
		panel_values: ["Front", "Back", "Sleeve"],
		packing_values: ["Black"],
		panels: ["Front", "Back", "Sleeve"].map((panel) => ({ group_id: panel, panel_value: panel, panel_values: [panel], packing_values: ["Black"], rows: [{ primary_value: "S", values: { Black: { dia: "32 Dia", weight: 0.05 } } }] })),
	}
	const grouped = groupPanels(matrix, ["Back", "Front"])
	assert.equal(grouped.groupId, "Front\u001fBack")
	assert.equal(grouped.matrix.panels.length, 2)
	assert.equal(grouped.matrix.panels[0].panel_value, "Front + Back")
	assert.equal(grouped.matrix.panels[0].rows[0].values.Black.weight, 0.1)
	assert.throws(() => groupPanels(grouped.matrix, ["Front", "Sleeve"]), /Ungroup an existing group/)
	const split = ungroupPanel(grouped.matrix, grouped.groupId)
	assert.equal(split.matrix.panels.length, 3)
	assert.deepEqual(split.matrix.panels.map((panel) => panel.rows[0].values.Black.weight), [0.05, 0.05, 0.05])
	const mixed = structuredClone(matrix)
	mixed.panels[1].rows[0].values.Black.dia = "30 Dia"
	assert.throws(() => groupPanels(mixed, ["Front", "Back"]), /different Dia values/)
	const half = structuredClone(matrix)
	half.panels[1].rows[0].values.Black = { dia: "32 Dia", weight: null }
	assert.throws(() => groupPanels(half, ["Front", "Back"]), /Complete or clear/)

	const panel = matrix.panels[0]
	const grid = panelGroupGrid(matrix, panel, { diaOptions: ["32 Dia"] })
	assert.deepEqual(grid.columns.map((column) => column.field), ["dia", "weight"])
	assert.ok(grid.columns.every((column) => column.fill === true))
	assert.equal(grid.columns[0].type, "link")
	assert.equal(grid.columns[0].doctype, "Item Attribute Value")
	assert.deepEqual(grid.columns[0].options, [{ value: "32 Dia", label: "32 Dia" }])
	assert.deepEqual(grid.columns[0].searchHandler("32"), [{ name: "32 Dia", label: "32 Dia" }])
	const weightKey = `Black${COLUMN_SEPARATOR}weight`
	const edited = panelGroupFromModel(matrix, "Front", { S: { ...grid.model.S, [weightKey]: 0.07 } })
	assert.equal(edited.panels[0].rows[0].values.Black.weight, 0.07)
	assert.equal(edited.panels[1], matrix.panels[1])
	assert.deepEqual(panelGroupErrors({ "Front\u001fS": { Black: "bad" } }, panel), { S: { [weightKey]: "bad" } })
}

{
	const value = { Printing: ["Front"], Fusing: ["Back", "Front"] }
	const grid = embellishmentGrid(value, ["Front", "Back", "Sleeve"])
	const edited = embellishmentFromModel(value, { ...grid.model, Printing: { ...grid.model.Printing, Sleeve: 1 } }, ["Front", "Back", "Sleeve"])
	assert.deepEqual(edited.Printing, ["Front", "Sleeve"])
	assert.equal(edited.Fusing, value.Fusing)
	assert.deepEqual(addEmbellishment(value, "Embroidery", ["Front", "Back"]).Embroidery, ["Front", "Back"])
	assert.throws(() => addEmbellishment(value, "", []), /Enter the process/)
	assert.deepEqual(Object.keys(removeEmbellishment(value, "Printing")), ["Fusing"])
	assert.deepEqual(embellishmentGrid({ Old: ["Gone"] }, ["Front"]).columns.map((column) => column.key), ["Front", "Gone"])
}

{
	const panels = ["Front", "Back", "Sleeve"]
	const groups = [["Front", "Back"], ["Sleeve"]]
	const grid = markerGrid(groups, panels)
	assert.equal(grid.model["group-0"].Front, 1)
	const edited = markerFromModel(groups, { ...grid.model, "group-1": { Front: 0, Back: 0, Sleeve: 0 } }, panels)
	assert.deepEqual(edited, [["Front", "Back"], []])
	assert.deepEqual(bundleGroupProblems(edited, panels), [{ panel: "", message: "Select All the Panels" }])
	assert.deepEqual(bundleGroupProblems([["Front"], ["Front", "Back", "Sleeve"]], panels)[0].message, "Panel Front is grouped multiple times")
	assert.deepEqual(bundleGroupProblems([], panels), [])
}

{
	const value = { assortment_attributes: ["Colour"], separator_attribute: "Size", boxes: [{ box: "7-8", separator_value: "7-8", rows: [{ Colour: "White", qty: 0 }, { Colour: "Red", qty: 2 }] }] }
	const grid = assortmentGrid(value)
	assert.equal(grid.rows[0].label, "7-8 · White")
	same(assortmentFromModel(value, grid.model), value, "assortment round trip")
	const edited = assortmentFromModel(value, { ...grid.model, [grid.rows[0].key]: { qty: 3 } })
	assert.equal(edited.boxes[0].rows[0].qty, 3)
	assert.equal(edited.boxes[0].rows[1], value.boxes[0].rows[1])
}

{
	const draft = {
		cloth_detail: [{ name: "c1", name1: "Main" }],
		cutting_cloths_json: { attributes: ["Panel", "Cloth"], items: [{ Panel: "Front", Cloth: "Main" }], select_list: ["Main"] },
		stiching_accessory_json: { items: [{ accessory: "Tape", cloth_type: "Main" }], select_list: ["Main"] },
	}
	const patch = clothDetailChanges(draft, [{ name: "c1", name1: "Body" }])
	assert.equal(patch.cutting_cloths_json.items[0].Cloth, "Body")
	assert.deepEqual(patch.stiching_accessory_json.select_list, ["Body"])
	assert.deepEqual(Object.keys(clothDetailChanges(draft, [{ name: "c1", name1: "Main" }])), ["cloth_detail"])
	assert.deepEqual(duplicateClothNames([{ name1: "A" }, { name1: "A" }, { name1: "B" }]), ["A"])
}

{
	const draft = { based_on_other_attribute_mapping: 0, auto_calculate: 1, packing_combo: 5, packing_attribute_no: 2, packing_attribute_details: [{ attribute_value: "A", quantity: 0 }, { attribute_value: "B", quantity: 0 }] }
	assert.deepEqual(packingChanges(draft, { packing_attribute_details: draft.packing_attribute_details.slice(0, 1) }), { packing_attribute_details: [{ attribute_value: "A", quantity: 0 }], packing_attribute_no: 1 })
	const wise = packingChanges(draft, { based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing" })
	assert.equal(wise.packing_combo, 1)
	assert.equal(wise.packing_mode, "Size Wise Packing")
	const manual = { ...draft, auto_calculate: 0, packing_combo: 0 }
	assert.equal(packingChanges(manual, { packing_attribute_details: [{ attribute_value: "A", quantity: 3 }, { attribute_value: "B", quantity: 2 }] }).packing_combo, 5)
	assert.equal(isComboDerived(draft), false)
	assert.equal(isComboDerived(manual), true)
	assert.deepEqual(packingChanges(draft, {}), {})
}

{
	assert.deepEqual(toggleChoice(["Size", "Colour", "Panel"], ["Panel"], "Size", true), ["Size", "Panel"])
	assert.deepEqual(toggleChoice(["Size"], ["Legacy", "Size"], "Size", false), ["Legacy"])
	const summary = reviewSummary(
		[{ key: "item", number: 1, label: "Item & versions" }, { key: "stitching", number: 5, label: "Stitching" }, { key: "review", number: 9, label: "Review" }],
		{ item: { state: "done", hint: "done" }, stitching: { state: "attention", hint: "1 issue" } },
	)
	assert.deepEqual(summary.map((entry) => entry.text), ["Complete", "1 issue"])
}

{
	const rows = [
		{ name: "a", process_name: "Ironing", in_stage: "Cut", out_stage: "Piece" },
		{ name: "b", process_name: "Washing", in_stage: "Cut", out_stage: "Cut" },
		{ process_name: "Printing", in_stage: null, out_stage: null },
	]
	const fields = ["process_name", "process_item", "in_stage"]
	const grid = tableGrid(rows, fields)
	assert.deepEqual(grid.rows.map((row) => row.key), ["a", "b", "new:2"])
	const model = structuredClone(grid.model)
	model.b.in_stage = "Pack"
	model["new:2"].in_stage = "Piece"
	model.a.process_item = "X"
	const next = processRowsFromModel(rows, model, fields)
	assert.deepEqual([next[0].in_stage, next[0].out_stage], ["Cut", "Piece"], "legacy row kept unless its stage is edited")
	assert.deepEqual([next[1].in_stage, next[1].out_stage], ["Pack", "Pack"])
	assert.deepEqual([next[2].in_stage, next[2].out_stage], ["Piece", "Piece"])
	model.a.in_stage = "Piece"
	assert.deepEqual(processRowsFromModel(rows, model, fields)[0].out_stage, "Piece")
	assert.deepEqual(rows.map(hasStageMismatch), [true, false, false])
	const synced = syncProcessStages(rows)
	assert.deepEqual(synced.map((row) => row.out_stage), ["Cut", "Cut", null])
	assert.equal(synced[1], rows[1], "rows already in step are kept as they are")
}

console.log("ipd garment grid tests passed")

{
	const draft = { based_on_other_attribute_mapping: 0, auto_calculate: 1, packing_combo: 12, packing_attribute_no: 2,
		packing_attribute_details: [{ attribute_value: "Red", quantity: 2 }, { attribute_value: "Blue", quantity: 4 }] }
	assert.deepEqual(packingChanges(draft, { auto_calculate: 0 }), { auto_calculate: 0, packing_combo: 6 })
	console.log("packing auto calculate off re-derives combo")
}

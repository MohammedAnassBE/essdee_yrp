#!/usr/bin/env node
import assert from "node:assert/strict"
import { readFileSync, readdirSync } from "node:fs"
import { createRequire } from "node:module"
import { FIELD_TAB, IPD_TABS, TAB_FIELDS, problemTab, resolveTab, visibleTabs } from "../frontend/src/departments/merch/ipd/ipdTabs.js"
import { createFocusRegistry, gridRowKey } from "../frontend/src/departments/merch/ipd/ipdFocus.js"

import {
	CLOTH_SECTIONS,
	GARMENT_SECTIONS,
	GRID_DEPENDENCIES,
	GRID_FIELDS,
	changedKeys,
	checksBadge,
	copyClosure,
	copyDefaults,
	dirtyPatch,
	editorActions,
	gridDiffers,
	gridErrors,
	gridPhases,
	gridsForChange,
	gridsReadingAttribute,
	isStaleWriteError,
	mergeGrid,
	packingDerived,
	parseValueList,
	problemTitle,
	problemsFor,
	recordActions,
	renameClothLabel,
	renameClothLabels,
	isJsonWriteBlocked,
	invalidCellMessage,
	sectionProgress,
	sectionStates,
	sectionsFor,
	stableStringify,
	toggleCopySection,
	usageMessage,
	valueListMessage,
} from "../frontend/src/departments/merch/ipd/ipdEditor.js"

const garment = sectionsFor(false)
assert.deepEqual(garment.map((section) => section.key), ["item", "attributes", "packing", "set_item", "stitching", "cutting", "accessories", "processes", "review"])
assert.deepEqual(garment.map((section) => section.number), [1, 2, 3, 4, 5, 6, 7, 8, 9])
assert.deepEqual(sectionsFor(true).map((section) => section.key), ["item", "attributes", "yarn_ratio", "fabric_routes", "fabric_processes", "compacting", "review"])
assert.equal(GARMENT_SECTIONS.length, 9)
assert.equal(CLOTH_SECTIONS.length, 7)

const draft = {
	item: "Vest", item_attributes: [{ attribute: "Size" }, { attribute: "Colour" }], packing_attribute: "Colour",
	packing_attribute_details: [{ name: "p1", attribute_value: "Black", quantity: 0 }], packing_combo: 5, auto_calculate: 1,
	is_set_item: 0, stiching_item_details: [{ stiching_attribute_value: "Front" }, { stiching_attribute_value: "Back" }],
	cloth_detail: [], item_bom: [{ item: "Label" }], ipd_processes: [],
}
const states = sectionStates(garment, draft, { problems: [{ section: "stitching" }], section_counts: { stitching: 1 } })
assert.deepEqual(states.item, { state: "done", hint: "done", issues: 0 })
assert.equal(states.attributes.hint, "2")
assert.equal(states.packing.hint, "5 / box")
assert.equal(states.set_item.state, "off")
assert.deepEqual(states.stitching, { state: "attention", hint: "1 issue", issues: 1 })
assert.equal(states.cutting.state, "not_started")
assert.equal(states.accessories.hint, "1 row")
assert.equal(states.review.state, "not_started")
assert.deepEqual(sectionProgress(states), { complete: 4, active: 8 })
const newStates = sectionStates(garment, { item: "Vest" }, null, { isNew: true })
assert.equal(newStates.item.state, "done")
assert.ok(Object.entries(newStates).filter(([key]) => key !== "item").every(([, entry]) => entry.state === "locked"))
assert.equal(sectionStates(garment, draft, { problems: [], section_counts: {} }).review.state, "done")

const setCombo = { attributes: ["Top", "Bottom"], values: [{ major_attribute: "White", val: { Top: "White", Bottom: "White" } }] }
const stitchCombo = { attributes: ["Front"], values: [{ major_attribute: "White", val: { Front: "White" } }] }
const clean = { ...draft, is_set_item: 1, set_item_attribute: "Part", set_item_detail: setCombo, stiching_item_detail: stitchCombo, cutting_items_json: { items: [] } }
assert.deepEqual(dirtyPatch(clean, clean), {})
assert.deepEqual(dirtyPatch({ ...clean, description: "x" }, clean), { description: "x" })
const packingEdit = dirtyPatch({ ...clean, packing_attribute_details: [{ name: "p1", attribute_value: "Black", quantity: 1 }] }, clean)
assert.deepEqual(Object.keys(packingEdit).sort(), ["packing_attribute_details", "set_item_detail", "stiching_item_detail"])
const setOff = dirtyPatch({ ...clean, is_set_item: 0 }, clean)
assert.deepEqual(Object.keys(setOff).sort(), ["is_set_item", "stiching_item_detail"])
const stitchCell = { ...clean, stiching_item_detail: { ...stitchCombo, values: [{ major_attribute: "White", val: { Front: "Black" } }] } }
assert.deepEqual(Object.keys(dirtyPatch(stitchCell, clean)), ["stiching_item_detail"])
const setCell = { ...clean, set_item_detail: { ...setCombo, values: [{ major_attribute: "White", val: { Top: "White", Bottom: "Navy" } }] } }
assert.deepEqual(Object.keys(dirtyPatch(setCell, clean)).sort(), ["set_item_detail", "stiching_item_detail"])
const emptyStitch = { ...clean, stiching_item_detail: { attributes: [], values: [] } }
assert.deepEqual(Object.keys(dirtyPatch({ ...emptyStitch, stiching_item_details: [] }, emptyStitch)), ["stiching_item_details"])
assert.deepEqual(dirtyPatch({ ...clean, version: 9, approval_status: "Approved", item: "Other" }, clean), {})
assert.deepEqual(dirtyPatch({ item: "Vest" }, { item: "" }, { isNew: true }), { item: "Vest" })
const patched = dirtyPatch({ ...clean, cutting_items_json: { items: [{ Panel: "Front" }] } }, clean)
patched.cutting_items_json.items.push({})
assert.equal(clean.cutting_items_json.items.length, 0)
assert.deepEqual(changedKeys({ a: { x: 1, y: 2 } }, { a: { y: 2, x: 1 } }), [])
assert.equal(stableStringify({ b: 1, a: [1, { d: 2, c: 3 }] }), '{"a":[1,{"c":3,"d":2}],"b":1}')

for (const grids of Object.values(GRID_DEPENDENCIES)) {
	for (const grid of grids) assert.ok(GRID_FIELDS[grid] || grid === "cutting_attribute_choices", `unknown grid ${grid}`)
}
assert.deepEqual(gridsForChange(["cutting_attributes"]), ["cutting_items"])
assert.ok(gridsForChange(["packing_attribute_details"]).includes("panel_wise_cloth_mapping"))
for (const field of ["is_set_item", "set_item_attribute", "major_attribute_value", "set_item_detail"]) assert.ok(gridsForChange([field]).includes("cutting_cloths"), field)
assert.ok(gridsForChange(["set_item_detail"]).includes("cloth_accessory"))
assert.deepEqual(gridsForChange(["stiching_in_stage"]), ["cutting_attribute_choices", "cutting_items", "panel_wise_consumption", "panel_wise_cloth_mapping"])
assert.ok(gridsForChange(["set_item_attribute"]).includes("cutting_attribute_choices"))
assert.deepEqual(gridPhases(["cutting_items", "cutting_attribute_choices"]), [["cutting_attribute_choices"], ["cutting_items"]])
assert.deepEqual(gridPhases(["panel_wise_consumption", "cutting_items", "set_combination", "stitching_combination"]), [["set_combination"], ["stitching_combination"], ["cutting_items"], ["panel_wise_consumption"]])
assert.deepEqual(gridsReadingAttribute("Colour", { packing_attribute: "Colour" }).includes("set_combination"), true)
assert.deepEqual(gridsReadingAttribute("Neck", { cloth_attributes: ["Neck"] }), ["cutting_cloths", "panel_wise_cloth_mapping"])

const setSkeleton = { attributes: ["Top", "Bottom"], values: [{ major_attribute: "White", val: { Top: "White", Bottom: null } }, { major_attribute: "Navy", val: { Top: "Navy", Bottom: null } }] }
const mergedSet = mergeGrid("set_combination", setSkeleton, { attributes: ["Bottom", "Top"], values: [{ major_attribute: "White", val: { Bottom: "Grey", Top: "White" } }, { major_attribute: "Red", val: { Top: "Red", Bottom: "Red" } }] })
assert.deepEqual(mergedSet.value.values, [{ major_attribute: "White", val: { Top: "White", Bottom: "Grey" } }, { major_attribute: "Navy", val: { Top: "Navy", Bottom: null } }])
assert.deepEqual(Object.keys(mergedSet.value.values[0].val), ["Top", "Bottom"])
assert.equal(mergedSet.dropped, 2)
const nonPart = mergeGrid("set_combination", { attributes: ["Upper", "Lower"], values: [{ major_attribute: "Black", val: { Upper: "Black", Lower: null } }] }, { attributes: ["Upper", "Lower"], values: [{ major_attribute: "Black", val: { Upper: "Black", Lower: "Grey" } }] })
assert.equal(nonPart.value.values[0].val.Lower, "Grey")

const cutSkeleton = { combination_type: "Cutting", attributes: ["Panel", "Colour", "Dia", "Weight"], items: [{ Panel: "Front", Colour: "Black", Dia: null, Weight: null }, { Panel: "Front", Colour: "Navy", Dia: null, Weight: null }, { Panel: "Back", Colour: "Black", Dia: null, Weight: null }], select_list: {} }
const cutStored = { combination_type: "Cutting", attributes: ["Panel", "Dia", "Weight"], items: [{ Panel: "Front", Dia: "32 Dia", Weight: 0.09 }, { Panel: "Rib", Dia: "30 Dia", Weight: 0.01 }], select_list: [] }
const mergedCut = mergeGrid("cutting_items", cutSkeleton, cutStored)
assert.deepEqual(mergedCut.value.items, [
	{ Panel: "Front", Colour: "Black", Dia: "32 Dia", Weight: 0.09 },
	{ Panel: "Front", Colour: "Navy", Dia: "32 Dia", Weight: 0.09 },
	{ Panel: "Back", Colour: "Black", Dia: null, Weight: null },
])
assert.equal(mergedCut.dropped, 1)
assert.deepEqual(mergedCut.value.select_list, [])
assert.equal(Object.hasOwn(mergeGrid("cutting_items", cutSkeleton, { attributes: [], items: [] }).value, "select_list"), true)
const narrowed = mergeGrid("cutting_items", { attributes: ["Panel", "Dia", "Weight"], items: [{ Panel: "Front", Dia: null, Weight: null }] }, mergedCut.value)
assert.deepEqual(narrowed.value.items, [{ Panel: "Front", Dia: "32 Dia", Weight: 0.09 }])
const disagree = mergeGrid("cutting_items", { attributes: ["Panel", "Dia", "Weight"], items: [{ Panel: "Front", Dia: null, Weight: null }] }, { attributes: ["Panel", "Colour", "Dia", "Weight"], items: [{ Panel: "Front", Colour: "Black", Dia: "32 Dia", Weight: 0.1 }, { Panel: "Front", Colour: "Navy", Dia: "30 Dia", Weight: 0.1 }] })
assert.deepEqual(disagree.value.items, [{ Panel: "Front", Dia: null, Weight: 0.1 }])
assert.equal(mergeGrid("cutting_items", cutSkeleton, {}).value.items.length, 3)

const clothSkeleton = { combination_type: "Cloth", attributes: ["Panel", "Cloth"], items: [{ Panel: "Front", Cloth: null }, { Panel: "Back", Cloth: null }], select_list: ["MAIN", "RIB"] }
const mergedCloth = mergeGrid("cutting_cloths", clothSkeleton, { attributes: ["Panel", "Cloth"], items: [{ Panel: "Back", Cloth: "RIB" }], select_list: ["OLD"] })
assert.deepEqual(mergedCloth.value.items, [{ Panel: "Front", Cloth: null }, { Panel: "Back", Cloth: "RIB" }])
assert.deepEqual(mergedCloth.value.select_list, ["MAIN", "RIB"])
const accessory = mergeGrid("cloth_accessory", { attributes: ["Part", "Accessory", "Dia", "Weight"], items: [{ Part: "Top", Accessory: "TOP PIPING ", Dia: null, Weight: null }] }, { attributes: ["Part", "Accessory", "Dia", "Weight"], items: [{ Part: "Top", Accessory: "TOP PIPING ", Dia: "20 Dia", Weight: 0.01 }, { Part: "Top", Accessory: "TOP PIPING", Dia: "1", Weight: 1 }] })
assert.deepEqual(accessory.value.items, [{ Part: "Top", Accessory: "TOP PIPING ", Dia: "20 Dia", Weight: 0.01 }])
assert.equal(accessory.dropped, 1)

const stitchAccessory = mergeGrid("stiching_accessory",
	{ select_list: ["MAIN"], attributes: ["Accessory", "Part", "Major Colour", "Accessory Colour", "Cloth"], set_attr: "Part", is_set_item: 1, items: [{ accessory: "PIPING ", Part: "Bottom", major_colour: "White", accessory_colour: null, cloth_type: null, major_attr_value: "White" }, { accessory: "PIPING ", Part: "Top", major_colour: "White", accessory_colour: null, cloth_type: null }] },
	{ set_attr: "Part", items: [{ accessory: "PIPING ", Part: "Bottom", major_colour: "White", accessory_colour: "Navy", cloth_type: "MAIN" }] })
assert.deepEqual(stitchAccessory.value.items[0], { accessory: "PIPING ", Part: "Bottom", major_colour: "White", accessory_colour: "Navy", cloth_type: "MAIN", major_attr_value: "White" })
assert.equal(stitchAccessory.value.items[1].accessory_colour, null)

const assortment = mergeGrid("packing_assortment",
	{ assortment_attributes: ["Colour", "Fit"], separator_attribute: "Size", boxes: [{ box: "S", separator_value: "S", rows: [{ Fit: "Slim", Colour: "Black", qty: 0 }, { Colour: "Navy", Fit: "Slim", qty: 0 }] }] },
	{ assortment_attributes: ["Fit", "Colour"], separator_attribute: "Size", boxes: [{ box: "S", separator_value: "S", rows: [{ Colour: "Black", Fit: "Slim", qty: 4 }] }, { box: "M", separator_value: "M", rows: [{ Colour: "Black", Fit: "Slim", qty: 2 }] }] })
assert.deepEqual(assortment.value.boxes[0].rows.map((row) => row.qty), [4, 0])
assert.equal(assortment.dropped, 1)

const sizes = mergeGrid("packing_sizes", ["S", "M"], [{ name: "r1", attribute_value: "M", quantity: 2 }, { name: "r2", attribute_value: "XL", quantity: 1 }])
assert.deepEqual(sizes.value, [{ attribute_value: "S", quantity: 0 }, { name: "r1", attribute_value: "M", quantity: 2 }])
assert.equal(sizes.dropped, 1)
assert.deepEqual(mergeGrid("panel_wise_consumption", { matrix: { schema_version: 4 }, dia_values: [] }, null).value, { schema_version: 4 })
assert.throws(() => mergeGrid("nope", {}, {}), /Unknown IPD grid/)

assert.equal(gridDiffers("cutting_items", mergedCut.value, cutStored), true)
assert.equal(gridDiffers("cutting_items", { attributes: ["Panel"], items: [{ Panel: "A" }], select_list: [] }, { select_list: {}, items: [{ Panel: "A" }], attributes: ["Panel"] }), false)
assert.equal(gridDiffers("packing_sizes", [{ attribute_value: "S", quantity: 2 }], [{ name: "x", attribute_value: "S", quantity: 2 }]), false)

assert.deepEqual(packingDerived({ packing_attribute_details: [{ quantity: 2 }, { quantity: 3 }], auto_calculate: 0 }), { packing_attribute_no: 2, packing_combo: 5 })
assert.deepEqual(packingDerived({ packing_attribute_details: [{ quantity: 0 }], auto_calculate: 1, packing_combo: 5 }), { packing_attribute_no: 1 })
assert.deepEqual(packingDerived({ packing_attribute_details: [], based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing" }), { packing_attribute_no: 0, packing_combo: 1 })
assert.deepEqual(packingDerived({ packing_attribute_details: [{}], based_on_other_attribute_mapping: 1, packing_mode: "Size Ratio Packing", packing_size_details: [{ quantity: 2 }, { quantity: 2 }] }), { packing_attribute_no: 1, packing_combo: 4 })

const parsed = parseValueList("Black, navy\nRed\tblack\n\n Grey ", ["Navy"])
assert.deepEqual(parsed, { values: ["Black", "Red", "Grey"], added: 3, duplicates: 2 })
assert.equal(valueListMessage({ added: 4, duplicates: 1 }), "4 added · 1 already present")
assert.equal(usageMessage([{ section: "Stitching", label: "Sleeve Cuff row", count: 1 }, { section: "Cloth by panel and colour", label: "cells", count: 4 }]), "Stitching: Sleeve Cuff row · Cloth by panel and colour: cells (4)")

const capabilities = { run_checks: { allowed: true }, approve: { allowed: true, label: "Approve" }, new_version: { allowed: true }, save: { allowed: true } }
const fresh = editorActions({ isNew: true, capabilities, hasItem: false })
assert.equal(fresh[0].label, "Create IPD")
assert.equal(fresh[0].disabled, true)
assert.deepEqual(fresh.map((entry) => entry.key), ["save", "copy_from", "cancel"])
assert.equal(editorActions({ isNew: true, capabilities, hasItem: true })[0].disabled, false)
const editing = editorActions({ isNew: false, capabilities, dirty: true, problemCount: 0, copiedFrom: "Src-1" })
assert.deepEqual(editing.map((entry) => entry.key), ["save", "run_checks", "approve", "new_version", "show_changes", "cancel"])
assert.equal(editing.find((entry) => entry.key === "approve").disabledReason, "Save changes before approving")
assert.equal(editorActions({ isNew: false, capabilities, problemCount: 2 }).find((entry) => entry.key === "approve").disabledReason, "Fix 2 problems before approving")
assert.equal(editorActions({ isNew: false, capabilities, problemCount: 0 }).find((entry) => entry.key === "approve").disabled, false)
assert.equal(editorActions({ isNew: false, capabilities: { ...capabilities, approve: { allowed: false } } }).some((entry) => entry.key === "approve"), false)
assert.equal(editorActions({ isNew: false, capabilities, dirty: false })[0].disabled, true)

const recordCaps = { edit: { allowed: true, label: "Edit" }, approve: { allowed: true }, run_checks: { allowed: true }, new_version: { allowed: true }, revert_approval: { allowed: true, label: "Revert Approval" }, regenerate_process_matrix: { allowed: false } }
assert.deepEqual(recordActions({ capabilities: recordCaps }).map((entry) => entry.key), ["edit", "approve", "run_checks", "new_version"])
assert.deepEqual(recordActions({ approved: true, capabilities: { ...recordCaps, regenerate_process_matrix: { allowed: true } } }).map((entry) => entry.key), ["new_version", "revert_approval", "regenerate_process_matrix"])
assert.equal(recordActions({ approved: true, capabilities: recordCaps })[1].severity, "warn")
assert.deepEqual(recordActions({ capabilities: { edit: { allowed: false }, approve: { allowed: false } } }), [])

const copySections = [
	{ key: "attributes", locked: true }, { key: "packing", locked: true }, { key: "set_item", locked: true }, { key: "stitching", locked: true },
	{ key: "cutting", default: true }, { key: "accessories", default: true, requires: ["cutting"] }, { key: "processes", default: false },
]
assert.deepEqual(copyDefaults(copySections), ["attributes", "packing", "set_item", "stitching", "cutting", "accessories"])
assert.deepEqual(copyClosure(["accessories"], copySections), ["attributes", "packing", "set_item", "stitching"])
assert.deepEqual(toggleCopySection(copyDefaults(copySections), "cutting", false, copySections), ["attributes", "packing", "set_item", "stitching"])
assert.deepEqual(toggleCopySection(["attributes"], "accessories", true, copySections), ["attributes", "packing", "set_item", "stitching", "cutting", "accessories"])
assert.deepEqual(toggleCopySection(copyDefaults(copySections), "packing", false, copySections), copyDefaults(copySections))

const renameDraft = {
	cutting_cloths_json: { attributes: ["Panel", "Cloth"], items: [{ Panel: "Front", Cloth: "MAIN" }, { Panel: "Rib", Cloth: "RIB" }], select_list: ["MAIN", "RIB"] },
	stiching_accessory_json: { select_list: ["MAIN"], items: [{ accessory: "F", cloth_type: "MAIN" }] },
	panel_wise_cloth_mapping_json: { cloth_options: ["MAIN"], panels: [{ rows: [{ values: { Black: { cloth: "MAIN" }, __single__: { cloth: "RIB" } } }] }] },
}
const renamed = renameClothLabel(renameDraft, "MAIN", "BODY")
assert.deepEqual(renamed.cutting_cloths_json.items.map((row) => row.Cloth), ["BODY", "RIB"])
assert.deepEqual(renamed.cutting_cloths_json.select_list, ["BODY", "RIB"])
assert.equal(renamed.stiching_accessory_json.items[0].cloth_type, "BODY")
assert.deepEqual(renamed.panel_wise_cloth_mapping_json.panels[0].rows[0].values, { Black: { cloth: "BODY" }, __single__: { cloth: "RIB" } })
assert.equal(renameDraft.cutting_cloths_json.items[0].Cloth, "MAIN")
assert.deepEqual(renameClothLabel(renameDraft, "NONE", "X"), {})
assert.deepEqual(renameClothLabel({ cutting_cloths_json: {} }, "MAIN", "X"), {})
const swapped = renameClothLabels(renameDraft, new Map([["MAIN", "RIB"], ["RIB", "MAIN"]]))
assert.deepEqual(swapped.cutting_cloths_json.items.map((row) => row.Cloth), ["RIB", "MAIN"])
assert.deepEqual(swapped.cutting_cloths_json.select_list, ["RIB", "MAIN"])
assert.deepEqual(swapped.panel_wise_cloth_mapping_json.panels[0].rows[0].values, { Black: { cloth: "RIB" }, __single__: { cloth: "MAIN" } })
const cycled = renameClothLabels({ cutting_cloths_json: { items: [{ Cloth: "A" }, { Cloth: "B" }, { Cloth: "C" }], select_list: ["A", "B", "C"] } }, new Map([["A", "B"], ["B", "C"], ["C", "A"]]))
assert.deepEqual(cycled.cutting_cloths_json.items.map((row) => row.Cloth), ["B", "C", "A"])

assert.equal(isJsonWriteBlocked({ enable_panel_wise_consumption_matrix: 1 }, "cutting_cloths_json"), true)
assert.equal(isJsonWriteBlocked({}, "panel_wise_consumption_matrix_json"), true)
assert.equal(isJsonWriteBlocked({ based_on_other_attribute_mapping: 1, packing_mode: "Size Wise" }, "packing_assortment_json"), true)
assert.equal(isJsonWriteBlocked({ based_on_other_attribute_mapping: 1, packing_mode: "" }, "packing_assortment_json"), false)
const modeClean = { based_on_other_attribute_mapping: 1, packing_mode: "", packing_assortment_json: { boxes: [] }, cutting_items_json: { items: [] } }
const modeDraft = { ...modeClean, packing_mode: "Size Wise", packing_assortment_json: { boxes: [{ qty: 2 }] }, enable_panel_wise_consumption_matrix: 1, cutting_items_json: { items: [{ Dia: "30" }] } }
const modePatch = dirtyPatch(modeDraft, modeClean)
assert.equal("packing_assortment_json" in modePatch, false)
assert.equal("cutting_items_json" in modePatch, false)
assert.equal(modePatch.packing_mode, "Size Wise")

const checks = { problems: [
	{ key: "a", section: "stitching", field: "stiching_item_details", row_key: "Sleeve Cuff", column: "quantity", message: "Quantity is 0." },
	{ key: "b", section: "packing", field: "packing_combo", row_key: null, column: null, message: "Combo" },
], section_counts: { stitching: 1, packing: 1 } }
assert.equal(problemsFor(checks, "stitching").length, 1)
assert.deepEqual(gridErrors(checks, "stiching_item_details"), { "Sleeve Cuff": { quantity: "Quantity is 0." } })
assert.equal(problemTitle(checks.problems[0], garment), "Stiching · Sleeve Cuff")
assert.equal(problemTitle({ section: "accessories", row_key: "FOLDING\u001fTop\u001fWhite" }, garment), "Cloth Accessory · FOLDING · Top · White")
assert.equal(problemTitle({ section: "accessories", row_key: "new:13" }, garment), "Cloth Accessory · New row 14")
assert.deepEqual(checksBadge(null), { tone: "idle", label: "Not run" })
assert.deepEqual(checksBadge(checks), { tone: "danger", label: "2 problems" })
assert.deepEqual(checksBadge({ problems: [] }), { tone: "success", label: "All clear" })
assert.deepEqual(checksBadge({ problems: [], warnings: [{ rule: "process_stages" }] }), { tone: "warning", label: "1 warning" })
assert.deepEqual(checksBadge(checks, true), { tone: "running", label: "Checking…" })
assert.equal(isStaleWriteError("IPD-1 changed after you opened it. Refresh and try again."), true)

console.log("ipd editor tests passed")
assert.equal(invalidCellMessage(1), "1 grid cell holds a value that was not accepted. Correct or clear the highlighted cell before saving.")
assert.match(invalidCellMessage(3), /^3 grid cells hold values/)

const deskTabs = [
	['item_details_tab', 'Item Details'], ['packing_tab', 'Packing'], ['set_item_tab', 'Set Item'],
	['stiching_tab', 'Stiching'], ['emblishment_tab', 'Emblishment'], ['cutting_tab', 'Cutting'],
	['cloth_accessory_tab', 'Cloth Accessory'], ['advance_settings_tab', 'Advance Settings'],
	['fabric_processes_tab', 'Fabric Processes'], ['compacting_reference_tab', 'Compacting Details'],
]
assert.deepEqual(IPD_TABS.map(({ fieldname, label }) => [fieldname, label]), deskTabs)
const tabKeys = (doc, isNew = false) => visibleTabs(IPD_TABS, doc, { isNew }).map((tab) => tab.fieldname)
const garmentTabKeys = deskTabs.slice(0, 8).map(([key]) => key)
assert.deepEqual(tabKeys({ packing_attribute: 'Colour' }), garmentTabKeys)
assert.deepEqual(tabKeys({ packing_attribute: 'Colour', is_set_item: 1 }), garmentTabKeys)
assert.deepEqual(tabKeys({}), garmentTabKeys.filter((key) => key !== 'set_item_tab'))
assert.deepEqual(tabKeys({ is_cloth_item: 1 }), ['item_details_tab', 'fabric_processes_tab', 'compacting_reference_tab'])
assert.deepEqual(tabKeys({}, true), ['item_details_tab', 'emblishment_tab', 'advance_settings_tab'])
for (const doc of [{ packing_attribute: 'Colour' }, {}, { is_cloth_item: 1 }]) assert.deepEqual(tabKeys({ ...doc, approval_status: 'Approved' }), tabKeys(doc))
assert.deepEqual(tabKeys({ is_cloth_item: '0', packing_attribute: 'Colour' }), garmentTabKeys)
const registrySource = readFileSync(new URL('../essdee_yrp/merch/ipd/fields.py', import.meta.url), 'utf8')
const writableBlock = registrySource.split('WRITABLE = {')[1].split('\n}')[0]
const writable = [...writableBlock.matchAll(/^\t"([^"]+)":/gm)].map((match) => match[1])
assert.deepEqual(Object.values(TAB_FIELDS).flat().sort(), writable.sort(), 'each writable field is assigned once')
assert.deepEqual(Object.keys(FIELD_TAB).sort(), writable.sort(), 'every writable key has exactly one tab')
for (const [field, tab] of Object.entries(FIELD_TAB)) {
	assert.ok(IPD_TABS.some((entry) => entry.fieldname === tab), field)
	assert.equal(problemTab({ field, section: 'review' }), tab, 'field wins over server section')
}
for (const [field, tab] of [['packing_attribute', 'advance_settings_tab'], ['additional_cloth', 'item_details_tab'], ['ipd_processes', 'item_details_tab'], ['emblishment_details_json', 'emblishment_tab']]) assert.equal(problemTab({ field, section: 'packing' }), tab)
assert.equal(problemTab({ section: 'stitching' }), 'stiching_tab')
assert.equal(problemTab({ section: 'fabric_routes' }), 'fabric_processes_tab')
assert.equal(problemTab({ section: 'unknown' }), 'item_details_tab')
const clothTabs = visibleTabs(IPD_TABS, { is_cloth_item: 1 })
for (const key of ['set_item_tab', 'unknown', 'packing', 'review', '']) assert.equal(resolveTab(clothTabs, key), 'item_details_tab')
assert.equal(resolveTab(clothTabs, 'fabric_processes_tab'), 'fabric_processes_tab')
const itemSections = (doc) => IPD_TABS[0].sections.filter((section) => section.visible(doc)).map((section) => section.heading)
assert.deepEqual(itemSections({}), ['', 'Item Attributes', 'Bill of Materials'])
assert.deepEqual(itemSections({ is_cloth_item: 1 }), ['', 'Item Attributes', 'Processes'])
const fabricSections = IPD_TABS.find((tab) => tab.fieldname === 'fabric_processes_tab').sections
assert.equal(fabricSections.at(-1).heading, 'Fabric Routes')
assert.ok(IPD_TABS.every((tab) => tab.sections.every((section) => section.parts.every((part) => part.component !== 'review'))))
const stitchingDetails = IPD_TABS.find((tab) => tab.fieldname === 'stiching_tab').sections[0]
assert.equal(stitchingDetails.visible({}), false)
assert.equal(stitchingDetails.visible({ stiching_attribute: 'Panel' }), true)

const focus = createFocusRegistry()
const focused = []
const removeEmpty = focus.registerFocus('item_bom', () => false)
const removeBom = focus.registerFocus('item_bom', async (problem) => { focused.push(problem.row_key); return true })
focus.registerFocus('accessories', () => { throw new Error('field handler should win') })
assert.equal(await focus.focusProblem({ field: 'item_bom', section: 'accessories', row_key: 'row-3' }), true)
assert.deepEqual(focused, ['row-3'])
removeEmpty()
removeBom()
focus.registerFocus('processes', () => true)
assert.equal(await focus.focusProblem({ field: 'ipd_processes', section: 'processes' }), true)

// Compile IPD SFCs without building or running a bundle.
const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
const componentRoot = new URL('../frontend/src/departments/merch/ipd/', import.meta.url)
for (const folder of ['', 'sections/', 'cloth/']) {
	for (const filename of readdirSync(new URL(folder, componentRoot)).filter((name) => name.endsWith('.vue'))) {
		const source = readFileSync(new URL(folder + filename, componentRoot), 'utf8')
		const { descriptor, errors } = parse(source, { filename })
		assert.deepEqual(errors, [], filename)
		const script = compileScript(descriptor, { id: filename })
		const compiled = compileTemplate({ source: descriptor.template.content, filename, id: filename, compilerOptions: { bindingMetadata: script.bindings } })
		assert.deepEqual(compiled.errors, [], filename)
	}
}
console.log('ipd Desk tabs, field coverage, focus registry and SFC checks passed')

assert.equal(gridRowKey({ stiching_item_details: [{ name: 'row-2', stiching_attribute_value: 'Back' }] }, 'stiching_item_details', 'row-2'), 'Back')
assert.equal(gridRowKey({ packing_attribute_details: [{ attribute_value: 'Blue' }] }, 'packing_attribute_details', 'new:0'), 'Blue')
assert.equal(gridRowKey({}, 'ipd_processes', 'new:3'), 'new:3')
assert.equal(gridRowKey({}, 'stiching_item_details', 'Sleeve'), 'Sleeve')
const linkField = readFileSync(new URL('../frontend/src/components/common/LinkField.vue', import.meta.url), 'utf8')
assert.match(linkField, /auto-option-focus/)
assert.match(linkField, /focusedOptionIndex = input.value.findFirstOptionIndex\(\)/)
assert.match(linkField, /handleAutocompleteKey\(event, input.value, restoreCommittedValue, searching.value\)/)
const { handleAutocompleteKey } = await import('../frontend/src/components/common/autocompleteKeys.js')
const linkInput = {}
let selectedLink = ''
const autocomplete = { $el: { querySelector: () => linkInput }, overlayVisible: true, focusedOptionIndex: 0, onEnterKey() { selectedLink = ['First', 'Second'][this.focusedOptionIndex] } }
handleAutocompleteKey({ target: linkInput, key: 'Enter', preventDefault() {}, stopPropagation() {} }, autocomplete)
assert.equal(selectedLink, 'First')
for (const file of ['IpdTabs.vue', 'IpdTabPanel.vue']) {
	const source = readFileSync(new URL(file, componentRoot), 'utf8')
	assert.doesNotMatch(source, /merch|item_details_tab|packing_tab|Item Details|useRouter/i, 'generic tabs have no workspace rules')
}

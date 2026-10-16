#!/usr/bin/env node
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { addLotOrderRow, boxOrderView, clearedLotContext, editTabFor, fabricColumnFilters, IPD_DERIVED_FIELDS, lotEditorCleanSignature, lotEditorTabs, lotLinkFilters, lotOrderEntry, lotSavePayload, orderQuantityTotal, orderDetailsView } from "../frontend/src/departments/purchase/lot/lotEditor.js"
import { orderItemRows } from "../frontend/src/departments/purchase/lot/lotViews.js"
import { childTableColumnField } from "../frontend/src/components/common/childTableFields.js"
const details = { item: "Shirt", default_uom: "Box", primary_attribute: "Size", primary_attribute_values: ["S", "L"], final_state_attr: ["Colour"], items: [{ attributes: { Colour: "Blue" }, primary_attribute: "Size", values: { S: { qty: 2, ratio: 1, mrp: 50 }, L: { qty: 1, ratio: 2, mrp: 60 } } }] }
const before = structuredClone(details)
const entry = { attributes: { Colour: "Blue" }, values: { S: { qty: 3, ratio: 4, mrp: 100 }, L: { qty: 0, ratio: 1, mrp: 80 } } }
const merged = addLotOrderRow(details, entry)
assert.deepEqual(details, before)
assert.equal(merged.items.length, 1)
assert.deepEqual(merged.items[0].values.S, { qty: 5, ratio: 4, mrp: 100 })
assert.deepEqual(merged.items[0].values.L, { qty: 1, ratio: 1, mrp: 80 })
assert.equal(addLotOrderRow(details, { ...entry, attributes: { Colour: "Red" } }).items.length, 2)
assert.throws(() => addLotOrderRow(details, { ...entry, attributes: {} }), /Enter value for Colour/)
assert.throws(() => addLotOrderRow(details, lotOrderEntry(details)), /Enter value for Colour/)
assert.throws(() => addLotOrderRow(details, { ...lotOrderEntry(details), attributes: entry.attributes }), /Fill the quantity/)
const plain = { item: "Thread", default_uom: "Kg", primary_attribute: null, final_state_attr: [], items: [{ attributes: {}, values: { qty: 2, ratio: 1, mrp: 5 } }] }
assert.deepEqual(addLotOrderRow(plain, { attributes: {}, values: { qty: 3, ratio: 4, mrp: 7 } }).items[0].values, { qty: 5, ratio: 4, mrp: 7 })
assert.equal(addLotOrderRow({ ...plain, items: [] }, { attributes: {}, values: { qty: 1, ratio: 0, mrp: 0 } }).items.length, 1)
assert.throws(() => addLotOrderRow(plain, lotOrderEntry(plain)), /Fill the quantity/)
const form = { lot_name: "Lot", item: "Shirt", production_detail: "IPD", lot_fabric_details: [], fabric_program_details: ["ignored"], fabric_requirement_details: [] }
const payload = lotSavePayload(form, details, [])
assert.deepEqual(payload.item_details, [details])
assert.deepEqual(payload.order_item_details, [])
assert.ok(!Object.hasOwn(payload, "fabric_program_details"))
assert.ok(!Object.hasOwn(payload, "fabric_requirement_details"))
assert.ok(!Object.hasOwn(payload, "items"))
assert.ok(!Object.hasOwn(payload, "lot_order_details"))
assert.deepEqual(lotSavePayload(form, null, []).item_details, [])
const currentSignature = JSON.stringify({ form, itemDetails: details, orderItemDetails: [] })
assert.notEqual(lotEditorCleanSignature({ item_details_generated: true }, currentSignature), currentSignature)
assert.equal(lotEditorCleanSignature({ item_details_generated: false }, currentSignature), currentSignature)
assert.equal(lotEditorCleanSignature({}, currentSignature), currentSignature)
payload.item_details[0].items.push({})
assert.deepEqual(details, before)
assert.deepEqual(lotLinkFilters("production_order", {}), { docstatus: 1 })
assert.deepEqual(lotLinkFilters("production_order", form), { docstatus: 1, item: "Shirt" })
assert.deepEqual(lotLinkFilters("production_detail", form), { item: "Shirt" })
assert.deepEqual(fabricColumnFilters({ fieldname: "cloth_item" }, {}), { is_cloth_item: 1 })
assert.deepEqual(fabricColumnFilters({ fieldname: "production_detail" }, { cloth_item: "Cloth" }), { item: "Cloth" })
assert.equal(fabricColumnFilters({ fieldname: "plan_status" }, {}), undefined)
for (const field of ["production_order", "production_detail"]) {
 const cleared = clearedLotContext(field, form, { uom: "Box", version: "V2" })
 assert.equal(cleared.itemDetails, null)
 assert.equal(cleared.form[field], "")
 for (const key of IPD_DERIVED_FIELDS) assert.equal(cleared.derived[key], "")
 assert.equal(cleared.derived.version, "V2")
 if (field === "production_order") { assert.equal(cleared.form.item, ""); assert.equal(cleared.form.production_detail, "") }
}
assert.deepEqual(form.item, "Shirt")
for (const tab of ["order-items", "order-details"]) assert.equal(editTabFor(tab), tab)
for (const tab of ["bom", "ocr", "fabric", "details", undefined]) assert.equal(editTabFor(tab), "details")
assert.deepEqual(orderItemRows(details), orderItemRows(boxOrderView(details)))
assert.deepEqual(lotEditorTabs({}, [], true).map((tab) => tab.key), ["details"])
assert.deepEqual(lotEditorTabs(form, [{ items: [{}] }], false).map((tab) => tab.key), ["details", "order-items", "order-details"])
const groups = [{ attributes: ["Colour"], primary_attribute: "Size", primary_attribute_values: ["S"], items: [{ attributes: { Colour: "Blue" }, values: { S: { qty: 3 } } }] }]
assert.equal(orderQuantityTotal(groups[0].items), 3)
assert.equal(orderDetailsView(groups, "V1", "Colour").groups[0].totals.quantity, 3)
const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8")
const child = source("frontend/src/components/common/ChildTableField.vue")
assert.match(child, /columnFilters: \{ type: Function, default: null \}/)
const editor = source("frontend/src/departments/purchase/lot/LotEditor.vue")
assert.match(editor, /:dirty="isDirty"/)
assert.doesNotMatch(editor, /<Dialog|<DataTable/)
const state = source("frontend/src/departments/purchase/lot/useLotEditor.js")
assert.match(state, /cleanSignature.value = lotEditorCleanSignature\(payload, signature.value\)/)
const editorDetails = source("frontend/src/departments/purchase/lot/LotEditorDetails.vue")
assert.doesNotMatch(editorDetails, /<small/)
assert.match(editorDetails, /return \{ \.\.\.field, description, link_filters:/)
const wrapper = source("frontend/src/departments/purchase/lot/LotEditorPage.vue")
assert.match(wrapper, /:key="lotId \|\| 'new'"/)

const productionDetailColumn = { fieldname: "production_detail", link_filters: { enabled: 1 } }
const firstRow = { cloth_item: "First cloth" }
assert.deepEqual(childTableColumnField(productionDetailColumn, fabricColumnFilters, firstRow).link_filters, { item: "First cloth" })
assert.deepEqual(childTableColumnField(productionDetailColumn, fabricColumnFilters, { cloth_item: "Second cloth" }).link_filters, { item: "Second cloth" })
assert.equal(childTableColumnField(productionDetailColumn, null, firstRow), productionDetailColumn)
assert.deepEqual(childTableColumnField(productionDetailColumn, () => null, firstRow).link_filters, { enabled: 1 })
assert.deepEqual(productionDetailColumn.link_filters, { enabled: 1 })
console.log("Lot editor tests passed")

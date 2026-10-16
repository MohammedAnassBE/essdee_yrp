import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { itemCanSave, itemEditorValues, itemSaveValues } from "../frontend/src/departments/purchase/purchaseViews.js"
import {
	additionalParameterWording, duplicateParameterProblems, itemTableProblems,
	itemTableWarnings, stageAttributeProblems, stageConversionProblems, stageVariantNameProblems, stockUomRows, uniqueProblemMessages, uomConversionWording, yarnRatioTotal,
} from "../frontend/src/departments/purchase/item/itemTables.js"

const sourceRows = [{ name: "box-row", uom: "Box", conversion_factor: 10 }]
const piecesRow = { uom: "Pieces", conversion_factor: 1, injectedStockUom: "Pieces" }
assert.deepEqual(stockUomRows(sourceRows, "Pieces"), [piecesRow, ...sourceRows])
assert.equal(sourceRows.length, 1)
assert.equal(stockUomRows(stockUomRows(sourceRows, "Pieces"), "Pieces").length, 2)
assert.deepEqual(stockUomRows([], ""), [])
assert.equal(stockUomRows([{ uom: "Pieces", conversion_factor: 2 }], "Pieces")[0].conversion_factor, 2)
const nosRows = stockUomRows(sourceRows, "Nos")
const switchedRows = stockUomRows(nosRows, "Pieces", "Nos")
assert.deepEqual(switchedRows, [piecesRow, ...sourceRows])
assert.deepEqual(nosRows.map((row) => row.uom), ["Nos", "Box"])
assert.deepEqual(stockUomRows(switchedRows, "Kg", "Pieces").map((row) => row.uom), ["Kg", "Box"])
assert.deepEqual(stockUomRows(switchedRows, "", "Pieces"), sourceRows)
assert.deepEqual(stockUomRows([{ uom: "Nos", conversion_factor: 1 }], "Pieces", "Nos").map((row) => row.uom), ["Pieces", "Nos"])
assert.deepEqual(stockUomRows([{ ...nosRows[0], conversion_factor: 2 }], "Pieces", "Nos").map((row) => row.uom), ["Pieces", "Nos"])
assert.deepEqual(stockUomRows([{ ...nosRows[0], uom: "Unit" }], "Pieces", "Nos").map((row) => row.uom), ["Pieces", "Unit"])
assert.deepEqual(itemSaveValues({ stock_uom: "Pieces", uoms: switchedRows }).uoms, [
	{ name: null, uom: "Pieces", conversion_factor: 1 }, sourceRows[0],
])
assert.deepEqual(stockUomRows([], "Kg").map(({ uom, conversion_factor }) => ({ uom, conversion_factor })), [{ uom: "Kg", conversion_factor: 1 }])

const stageItem = itemEditorValues({
	name: "ZZ TEST Item Master", stock_uom: "Pieces", item_group: "Products",
	uoms: sourceRows, primary_attribute: "Size", dependent_attribute: "Stage",
	attributes: [{ attribute: "Stage", values: ["Cut", "Pack"] }, { attribute: "Size", values: [] }],
	dependent_details: [{ value: "Cut", uom: "Pieces", attributes: ["Size"] }, { value: "Pack", uom: "Box", display_name: "Packed", attributes: ["Size"] }],
	additional_parameters: [{ name: "gsm-row", additional_parameter_key: "GSM", additional_parameter_value: "180" }, { additional_parameter_key: "DIA", additional_parameter_value: "" }],
	secondary_unit_of_measure: "Roll", po_excess_allowed_percentage: 10,
	product_category: "Fabric", hsn_code: "123", categories: ["Cloth"], is_ineligible_for_itc: 1,
	description: '<p title="original">Keep &amp; preserve HTML</p>',
})
assert.deepEqual(itemTableProblems(stageItem), [])
assert.equal(itemCanSave(stageItem), true)
const emptyStage = { ...stageItem, dependent_details: stageItem.dependent_details.map((row) => row.value === "Pack" ? { ...row, attributes: [] } : row) }
assert.deepEqual(stageAttributeProblems(emptyStage), [{ field: "stage_attributes", stage: "Pack", message: "Stage Pack must use at least one attribute." }])
assert.equal(itemCanSave(emptyStage), false)
assert.deepEqual(stageAttributeProblems(stageItem), [])
assert.deepEqual(stageAttributeProblems({ ...emptyStage, dependent_attribute: "" }), [])
assert.equal(itemCanSave(itemEditorValues(emptyStage)), false)
const collisionMessage = "Stages Cut and Pack would create variants with the same name. Give one of them a Display Name or tick different attributes."
for (const [first, second] of [[null, ""], ["", " "], ["Same", " Same "]]) {
	const loaded = itemEditorValues({ ...stageItem, attributes: [...stageItem.attributes, { attribute: "Colour", values: [] }], dependent_details: [
		{ value: "Cut", uom: "Pieces", display_name: first, attributes: ["Size", "Colour"] },
		{ value: "Pack", uom: "Box", display_name: second, attributes: ["Colour", "Size", "Size"] },
	] })
	assert.equal(loaded.dependent_details.length, 2)
	assert.deepEqual(stageVariantNameProblems(loaded), [
		{ field: "dependent_details", stage: "Cut", message: collisionMessage },
		{ field: "dependent_details", stage: "Pack", message: collisionMessage },
	])
	assert.deepEqual(uniqueProblemMessages(itemTableProblems(loaded)), [collisionMessage])
	assert.equal(itemCanSave(loaded), false)
	for (const replacement of [{ display_name: "Different" }, { attributes: ["Size"] }]) {
		const fixed = { ...loaded, dependent_details: [loaded.dependent_details[0], { ...loaded.dependent_details[1], ...replacement }] }
		assert.deepEqual(stageVariantNameProblems(fixed), [])
		assert.equal(itemCanSave(fixed), true)
	}
	assert.deepEqual(stageVariantNameProblems({ ...loaded, dependent_attribute: "" }), [])
}
assert.deepEqual(stageVariantNameProblems({}), [])
const withoutBox = { ...stageItem, uoms: stageItem.uoms.filter((row) => row.uom !== "Box") }
assert.equal(itemCanSave(withoutBox), false)
assert.match(stageConversionProblems(withoutBox)[0].message, /Stage Pack.*Box → Pieces.*Add a Box conversion/)
assert.equal(stageConversionProblems(withoutBox)[0].stage, "Pack")
assert.match(stageConversionProblems({ ...stageItem, dependent_details: [{ value: "Pack", uom: "" }] })[0].message, /valid UOM/)
assert.deepEqual(stageConversionProblems({ ...withoutBox, dependent_attribute: "" }), [])
for (const factor of [0, "", null, -1, NaN, Infinity]) {
	assert.match(itemTableProblems({ ...stageItem, uoms: [{ uom: "Box", conversion_factor: factor }] })[0].message, /greater than 0/)
}
assert.match(itemTableProblems({ ...stageItem, uoms: [{ uom: "Pieces", conversion_factor: 2 }] })[0].message, /default Unit of Measure must be 1 in row 1/)
assert.match(itemTableProblems({ ...stageItem, uoms: [...sourceRows, ...sourceRows] })[0].message, /more than once/)
const duplicateUomProblems = itemTableProblems({ ...stageItem, uoms: [...sourceRows, ...sourceRows] })
assert.equal(duplicateUomProblems.length, 2)
assert.deepEqual(uniqueProblemMessages(duplicateUomProblems), ["Unit of Measure Box has been entered more than once in Conversion Factor Table"])
assert.match(itemTableProblems({ ...stageItem, uoms: [{ uom: "", conversion_factor: 1 }] })[0].message, /valid UOM/)
assert.match(itemTableProblems({ ...stageItem, po_excess_allowed_percentage: -1 })[0].message, /greater than or equal to 0/)
assert.match(itemTableProblems({ ...stageItem, po_excess_allowed_percentage: Infinity })[0].message, /greater than or equal to 0/)
assert.equal(uomConversionWording(sourceRows[0], "Pieces"), "1 Box = 10 Pieces")
for (const factor of [null, undefined, "", "   "]) assert.equal(uomConversionWording({ uom: "Box", conversion_factor: factor }, "Pieces"), "—")
assert.equal(uomConversionWording({ uom: "Box", conversion_factor: 0 }, "Pieces"), "1 Box = 0 Pieces")
assert.equal(additionalParameterWording(stageItem.additional_parameters[1]), "DIA (chosen per PO)")
assert.equal(additionalParameterWording(stageItem.additional_parameters[0]), "GSM 180")
assert.deepEqual(duplicateParameterProblems(stageItem.additional_parameters), [])
assert.equal(duplicateParameterProblems([...stageItem.additional_parameters, stageItem.additional_parameters[0]]).length, 2)
const caseDuplicateRows = [{ additional_parameter_key: "GSM" }, { additional_parameter_key: "gsm" }]
assert.equal(duplicateParameterProblems(caseDuplicateRows).length, 2)
assert.equal(itemCanSave({ ...stageItem, additional_parameters: caseDuplicateRows }), false)
assert.equal(itemCanSave({ ...stageItem, additional_parameters: caseDuplicateRows.slice(1) }), true)
assert.match(duplicateParameterProblems([{}])[0].message, /select an Additional Parameter Key/)

assert.deepEqual(itemTableWarnings(stageItem, { has_item_transactions: true, fg_pcs_per_box: 10 }, stageItem), [])
assert.match(itemTableWarnings(withoutBox, { has_item_transactions: true }, stageItem)[0], /Submitted rows keep their stored factor; open drafts and Lots recalculate/)
const changedFactor = { ...stageItem, uoms: [{ uom: "Box", conversion_factor: 12 }] }
assert.equal(itemTableWarnings(changedFactor, { has_item_transactions: true }, stageItem).length, 1)
assert.deepEqual(itemTableWarnings(changedFactor, { has_item_transactions: false }, stageItem), [])
const changedStage = { ...stageItem, dependent_details: [{ value: "Pack", uom: "Pieces" }] }
assert.equal(itemTableWarnings(changedStage, { has_item_transactions: true }, stageItem).length, 1)
assert.deepEqual(itemTableWarnings(stageItem, { has_item_transactions: true }, { ...stageItem, uoms: [...stageItem.uoms].reverse() }), [])
assert.match(itemTableWarnings(stageItem, { fg_pcs_per_box: 12 })[0], /FG Item Master.*12/)
for (const pieces of [0, "0", "", null, undefined, -1]) assert.deepEqual(itemTableWarnings(stageItem, { fg_pcs_per_box: pieces }), [])
assert.deepEqual(itemTableWarnings(withoutBox, { fg_pcs_per_box: 12 }), [])
assert.deepEqual(itemTableWarnings({ stock_uom: "Box", uoms: [] }, { fg_pcs_per_box: 12 }), [])
assert.match(itemTableWarnings({ stock_uom: "Pieces", uoms: [{ uom: "Carton", conversion_factor: 5 }] }, { fg_uom: "Carton", fg_pcs_per_box: 12 })[0], /Carton conversion factor differs/)
assert.match(itemTableWarnings({ ...stageItem, primary_attribute: "" })[0], /Box Sticker auto-create and size-wise pricing need a Primary Attribute/)
assert.equal(itemCanSave({ ...stageItem, primary_attribute: "", dependent_attribute: "" }), true)

const cloth = { ...stageItem, is_cloth_item: 1, yarn_ratio_details: [{ yarn_item: "Yarn A", ratio: 60 }, { yarn_item: "Yarn B", ratio: 40 }] }
assert.equal(yarnRatioTotal(cloth.yarn_ratio_details), 100)
assert.equal(itemCanSave(cloth), true)
assert.match(itemTableProblems({ ...cloth, yarn_ratio_details: [] })[0].message, /at least one Yarn/)
assert.match(itemTableProblems({ ...cloth, yarn_ratio_details: [{ yarn_item: "Yarn A", ratio: 90 }] })[0].message, /exactly 100/)
assert.match(itemTableProblems({ ...cloth, yarn_ratio_details: [{ yarn_item: "Yarn A", ratio: 50 }, { yarn_item: "Yarn A", ratio: 50 }] })[0].message, /unique Yarn/)
assert.equal(itemCanSave({ ...stageItem, is_cloth_item: 0, yarn_ratio_details: [{ yarn_item: "Yarn", ratio: 90 }] }), true)

const saved = itemSaveValues(cloth)
for (const field of ["secondary_unit_of_measure", "po_excess_allowed_percentage", "product_category", "hsn_code", "categories", "is_ineligible_for_itc", "description", "is_cloth_item"]) assert.deepEqual(saved[field], cloth[field])
assert.deepEqual(saved.uoms, [{ name: null, uom: "Pieces", conversion_factor: 1 }, sourceRows[0]])
assert.deepEqual(saved.additional_parameters[0], stageItem.additional_parameters[0])
assert.equal(saved.yarn_ratio_details.length, 2)
assert.equal(saved.description, stageItem.description)
const reloaded = itemEditorValues(saved)
reloaded.uoms[0].conversion_factor = 3
assert.equal(saved.uoms[0].conversion_factor, 1)

const parameterComponent = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemAdditionalParameters.vue", import.meta.url), "utf8")
assert.match(parameterComponent, /disabled \|\| !data.additional_parameter_key/)
assert.match(parameterComponent, /filters="\{ key: data.additional_parameter_key \}"/)
assert.match(parameterComponent, /row.additional_parameter_value = ""/)
const yarnComponent = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemYarnRatio.vue", import.meta.url), "utf8")
assert.match(yarnComponent, /disabled: 0, is_cloth_item: 0/)
assert.match(yarnComponent, /name: \["!=", props.itemName\]/)
assert.match(yarnComponent, /variant_of: \["is", "not set"\]/)
const uomComponent = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemUomConversions.vue", import.meta.url), "utf8")
assert.match(uomComponent, /uniqueProblemMessages\(problems\)/)
assert.match(uomComponent, /props.editable \? props.values.uoms \|\| \[\] : stockUomRows/)
const stageComponent = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemDependentAttributeTable.vue", import.meta.url), "utf8")
assert.match(stageComponent, /problem.stage === row.value && problem.field === 'dependent_details'/)
assert.match(stageComponent, /problem.stage === row.value && problem.field === 'stage_attributes'/)
const itemPage = readFileSync(new URL("../frontend/src/departments/purchase/ItemPage.vue", import.meta.url), "utf8")
assert.match(itemPage, /stageVariantNameProblems\(values.value\)/)
assert.match(itemPage, /stageAttributeProblems\(values.value\)/)
assert.match(itemPage, /uniqueProblemMessages\(stageProblems.value\)/)
console.log("Item table helpers passed")

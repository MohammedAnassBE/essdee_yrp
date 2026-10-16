#!/usr/bin/env node

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import {
	activePriceTiers,
	addAttributeValueDraft,
	attributeValueLabels,
	attributeValuesSummary,
	captureRecordTarget,
	dependentDetailRows,
	itemCombinationAttributes,
	itemDependentProblem,
	itemDependentValues,
	itemCodeHint,
	itemAttributeCountLabel,
	itemCanSave,
	itemEditorValues,
	itemKindLabel,
	itemListFilters,
	itemSaveValues,
	itemPriceActionIcon,
	itemPriceActionItems,
	itemPriceActionMessage,
	itemPriceActionSeverity,
	itemPriceApprovedBy,
	itemPriceAttributeValues,
	itemPriceCanSave,
	itemPriceEditorRequestKey,
	itemPriceEditorValues,
	itemPriceAttributeHint,
	itemPriceDateLimit,
	itemPriceFieldLabel,
	itemPriceOverviewFields,
	itemPriceTierValue,
	ITEM_PRICE_SECTIONS,
	itemPriceListInitialStatus,
	itemPriceSummaryLabel,
	itemPricePath,
	itemPriceSaveAction,
	itemPriceSaveValues,
	itemPriceTierPrecision,
	itemRoutePath,
	isCurrentRecordRequest,
	isSameAttributeValue,
	matchingAttributeValue,
	purchaseLauncherItems,
	removeAttributeValueDraft,
	resetAttributeRow,
	storedAttributeMappings,
	savedItemPriceIdentity,
} from "../frontend/src/departments/purchase/purchaseViews.js"
import { webDocumentPath } from "../frontend/src/router/webDocumentRoutes.js"

assert.equal(itemCodeHint("Poly Bag", "Essdee"), "Essdee Poly Bag")
assert.equal(itemCodeHint("Essdee Poly Bag", "essdee"), "Essdee Poly Bag")
assert.equal(itemCodeHint(" Poly Bag ", ""), "Poly Bag")
assert.equal(itemKindLabel([]), "Plain item")
assert.equal(itemKindLabel([{ attribute: "Colour" }]), "Item with variants (Colour)")
assert.equal(
	itemKindLabel([{ attribute: "Colour" }, { attribute: "Size" }]),
	"Item with variants (Colour × Size)",
)

const itemDraft = itemEditorValues({
	name: "Poly Bag",
	brand: "Essdee",
	attributes: [{
		attribute: "Colour",
		mapping_modified: "m1",
		values: [{ name: "RED", label: "Red" }],
	}],
})
assert.deepEqual(itemDraft.attributes[0].values, ["Red"])
itemDraft.attributes[0].values.push("Blue")
assert.deepEqual(itemSaveValues(itemDraft).attributes, [{
	attribute: "Colour",
	mapping_modified: "m1",
	values: ["Red", "Blue"],
}])
assert.deepEqual(
	itemSaveValues({ attributes: [{ attribute: "Size", mapping_modified: null, values: [{ name: "S", label: "Small" }] }, { attribute: "Colour", values: [], all_values_allowed: true, new_values: [] }] }).attributes,
	[{ attribute: "Size", mapping_modified: null, values: ["Small"] }, { attribute: "Colour", mapping_modified: null, values: [] }],
)
assert.equal(itemSaveValues(itemDraft).primary_attribute, "Colour")
assert.equal(itemSaveValues(itemDraft, { defaultSinglePrimary: false }).primary_attribute, null)
assert.equal(
	itemSaveValues({ ...itemDraft, attributes: [...itemDraft.attributes, { attribute: "Size", values: [] }] }).primary_attribute,
	null,
)
const plainItem = { name: "Poly Bag", item_group: "Products", stock_uom: "Nos", attributes: [] }
assert.equal(itemCanSave(plainItem), true)
assert.equal(itemCanSave({ ...plainItem, name: "  " }), false)
assert.equal(itemCanSave({ ...plainItem, item_group: "" }), false)
assert.equal(itemCanSave({ ...plainItem, stock_uom: "" }), false)
assert.equal(itemCanSave({ ...plainItem, attributes: [{ attribute: "Colour", values: [] }, { attribute: "Size" }] }), true)
assert.equal(itemCanSave({ ...plainItem, attributes: [{ attribute: "", values: [] }] }), false)
assert.equal(itemCanSave({ ...plainItem, attributes: [{ attribute: "Colour", values: [], all_values_allowed: true }] }), true)
const dependentItem = itemEditorValues({
	name: "Tee",
	item_group: "Products",
	stock_uom: "Nos",
	uoms: [{ uom: "Box", conversion_factor: 10 }],
	primary_attribute: "Size",
	dependent_attribute: "Stage",
	dependent_details: [{ value: "Pack", uom: "Box", display_name: "Packed", attributes: ["Size", "Colour"] }, { value: "Cut", uom: "Nos", display_name: "", attributes: [] }],
	attributes: [
		{ attribute: "Stage", values: [{ name: "S-PACK", label: "Pack" }, { name: "S-LOOSE", label: "Loose" }] },
		{ attribute: "Size", values: [] },
		{ attribute: "Colour", values: [] },
		{ attribute: "Length", values: [] },
	],
})
assert.deepEqual(itemDependentValues(dependentItem), ["Pack", "Loose"])
assert.deepEqual(itemCombinationAttributes(dependentItem, ["Length"]), ["Size", "Colour"])
assert.deepEqual(dependentDetailRows(dependentItem, "Nos"), [
	{ value: "Pack", uom: "Box", display_name: "Packed", attributes: ["Size", "Colour"] },
	{ value: "Loose", uom: "Nos", display_name: "", attributes: ["Size"] },
])
assert.deepEqual(dependentDetailRows({ ...dependentItem, dependent_attribute: "" }, "Nos"), [])
const withoutColour = { ...dependentItem, attributes: dependentItem.attributes.filter((row) => row.attribute !== "Colour") }
assert.deepEqual(dependentDetailRows(withoutColour, "Nos")[0].attributes, ["Size"])
assert.equal(itemSaveValues(itemEditorValues({ ...dependentItem, dependent_mapping_modified: "2026-01-01 00:00:00" })).dependent_mapping_modified, "2026-01-01 00:00:00")
const dependentSave = itemSaveValues({ ...dependentItem, dependent_details: dependentDetailRows(dependentItem, "Nos") })
assert.equal(dependentSave.dependent_attribute, "Stage")
assert.deepEqual(dependentSave.dependent_details.map((row) => [row.value, row.uom, row.attributes]), [["Pack", "Box", ["Size", "Colour"]], ["Loose", "Nos", ["Size"]]])
assert.equal(itemSaveValues({ ...dependentItem, primary_attribute: "Stage" }).dependent_attribute, null)
const replacedColour = { ...dependentItem, dependent_details: dependentDetailRows(dependentItem, "Nos"), attributes: dependentItem.attributes.map((row) => row.attribute === "Colour" ? { attribute: "Panel", values: [] } : row) }
assert.deepEqual(itemSaveValues(replacedColour).dependent_details[0].attributes, ["Size"])
assert.deepEqual(itemSaveValues({ ...dependentItem, dependent_attribute: "Missing" }).dependent_details, [])
assert.equal(itemDependentProblem({ ...dependentItem, dependent_details: dependentDetailRows(dependentItem, "Nos") }), "")
assert.equal(itemCanSave({ ...dependentItem, dependent_details: dependentDetailRows(dependentItem, "Nos") }), true)
const allStageValues = { ...dependentItem, attributes: [{ attribute: "Stage", values: [] }, ...dependentItem.attributes.slice(1)] }
assert.equal(itemDependentProblem(allStageValues), "Please configure values for Dependent Attribute Stage.")
assert.equal(itemCanSave(allStageValues), false)
assert.equal(itemDependentProblem({ ...dependentItem, primary_attribute: "" }), "Please set Primary Attribute for this Item.")
assert.equal(itemDependentProblem({ ...dependentItem, dependent_details: [{ value: "Pack", uom: "", attributes: [] }] }), "Set the UOM for every Stage value.")
assert.deepEqual(attributeValueLabels([{ name: "RED", label: "Red" }, " Blue ", "", null]), ["Red", "Blue"])
const valueDraft = addAttributeValueDraft(["Red"], " Green ")
assert.deepEqual(valueDraft, ["Red", "Green"])
assert.equal(addAttributeValueDraft(valueDraft, "green"), valueDraft)
assert.equal(addAttributeValueDraft(valueDraft, "  "), valueDraft)
assert.deepEqual(removeAttributeValueDraft(valueDraft, "Red"), ["Green"])
assert.equal(isSameAttributeValue("XL ", "xl"), true)
assert.equal(matchingAttributeValue([{ name: "C-RED", label: "Red" }, { name: "C-RD", label: "Dark Red" }], "RED"), "Red")
assert.equal(matchingAttributeValue([{ name: "C-RD", label: "Dark Red" }], "red"), null)
assert.equal(attributeValuesSummary([]), "All")
const loadedMappings = storedAttributeMappings([
	{ attribute: "Colour", mapping: "MAP-C", mapping_modified: "2026-01-01 00:00:00", value_count: 5, values: [{ label: "Red" }] },
	{ attribute: "Size", mapping: null, mapping_modified: null, value_count: 3, values: [] },
	{ attribute: "" },
])
assert.deepEqual(Object.keys(loadedMappings), ["Colour", "Size"])
assert.deepEqual(resetAttributeRow(loadedMappings, "Colour"), { mapping: "MAP-C", mapping_modified: "2026-01-01 00:00:00", value_count: 5, attribute: "Colour", values: [], new_values: [], all_values_allowed: true })
assert.deepEqual(resetAttributeRow(loadedMappings, "Open Size"), { mapping: null, mapping_modified: null, value_count: null, attribute: "Open Size", values: [], new_values: [], all_values_allowed: true })
assert.equal(resetAttributeRow(loadedMappings, "").mapping_modified, null)
assert.equal(attributeValuesSummary(["Red"]), "1 value")
assert.equal(attributeValuesSummary(["Red", "Blue"]), "2 values")
assert.equal(itemAttributeCountLabel(2), "2")
assert.equal(itemAttributeCountLabel(0), "None")
assert.equal(itemAttributeCountLabel(null), "…")
const unrestrictedRow = itemEditorValues({ attributes: [{ attribute: "Colour", all_values_allowed: true, value_count: 506, values: [] }] }).attributes[0]
assert.deepEqual([unrestrictedRow.values, unrestrictedRow.all_values_allowed, unrestrictedRow.value_count], [[], true, 506])

assert.deepEqual(itemListFilters("purchase"), [
	["variant_of", "is", "not set"],
	["is_purchase_item", "=", 1],
	["disabled", "=", 0],
])
assert.deepEqual(itemListFilters("all"), [
	["variant_of", "is", "not set"],
	["disabled", "=", 0],
])
assert.deepEqual(itemListFilters("disabled"), [
	["variant_of", "is", "not set"],
	["disabled", "=", 1],
])

assert.equal(itemRoutePath("ITEM/A"), "/web/purchase/items/ITEM%2FA")
assert.equal(itemPricePath("ITP 1"), "/web/purchase/item-prices/ITP%201")
assert.equal(webDocumentPath("SD YRP Lot", "C1225-03"), "/web/purchase/lots/C1225-03")
assert.equal(webDocumentPath("YRP Item Price", "ITP 1"), "/web/purchase/item-prices/ITP%201")
assert.match(webDocumentPath("Item", "ITEM/A"), /^\/web\/document-unavailable\?/)
assert.deepEqual(purchaseLauncherItems(), [
	{
		key: "lots",
		label: "Lot",
		description: "Order quantities, BOM, OCR and cloth program for each lot.",
		icon: "pi pi-th-large",
		to: "/purchase/lots",
	},
	{
		key: "items",
		label: "Items",
		description: "Create purchase items and their allowed attribute values.",
		icon: "pi pi-box",
		to: "/purchase/items",
	},
	{
		key: "item_prices",
		label: "Item Prices",
		description: "Supplier prices, quantity slabs and approval.",
		icon: "pi pi-indian-rupee",
		to: "/purchase/item-prices",
	},
])
assert.equal(itemPriceListInitialStatus({ can_submit: true }), "Approval Pending")
assert.equal(itemPriceListInitialStatus({ can_submit: false }), "")
assert.equal(itemPriceSummaryLabel(undefined), "…")
assert.equal(itemPriceSummaryLabel({ slab_count: 0, min_price: null, max_price: null }), "—")
assert.equal(itemPriceSummaryLabel({ slab_count: 1, min_price: 25, max_price: 25 }), "25.00")
assert.equal(itemPriceSummaryLabel({ slab_count: 3, min_price: 9, max_price: 12.5 }), "9.00 – 12.50")
const submitTransition = { action: "Submit", label: "Submit", state: "Draft", next_state: "Approval Pending", next_state_doc_status: 0 }
assert.deepEqual(itemPriceSaveAction({ workflow: { save_actions: [submitTransition] } }), submitTransition)
assert.equal(itemPriceSaveAction({ workflow: { save_actions: [] } }), null)
assert.equal(itemPriceSaveAction({ workflow: { save_actions: [submitTransition, { ...submitTransition, action: "Reject" }] } }), null)
assert.equal(itemPriceSaveAction({}), null)
assert.equal(itemPriceApprovedBy({ docstatus: 0, approved_by: "migrated@example.test" }), "")
assert.equal(itemPriceApprovedBy({ docstatus: 1, approved_by: "manager@example.test" }), "manager@example.test")
assert.equal(itemPriceApprovedBy({ docstatus: 2, approved_by: "manager@example.test" }), "manager@example.test")
assert.equal(itemPriceApprovedBy({ docstatus: 1 }), "")

const expiredTransition = { action: "Expired", label: "Expired", state: "Approved", next_state: "Expired", next_state_doc_status: 2, documentName: "ITP-9" }
assert.equal(itemPriceActionIcon(expiredTransition), "pi pi-clock")
assert.equal(itemPriceActionSeverity(expiredTransition), "warn")
assert.equal(itemPriceActionMessage(expiredTransition), "Move ITP-9 from Approved to Expired?")
assert.equal(itemPriceActionIcon({ action: "Approve" }), "pi pi-check-circle")
assert.equal(itemPriceActionSeverity({ action: "Approve", next_state_doc_status: 1 }), "success")
assert.equal(itemPriceActionSeverity({ action: "Reject", next_state_doc_status: 0 }), "danger")
assert.equal(itemPriceActionSeverity(submitTransition), "success")
assert.equal(itemPriceActionMessage({ ...submitTransition, preview: "Ends ITP-1." }), "Ends ITP-1.")
assert.equal(itemPriceActionIcon({ action: "Unknown" }), "pi pi-arrow-right")

const editorValues = itemPriceEditorValues({
	item_name: "ITEM-1",
	depends_on_attribute: 1,
	attribute: "Colour",
	item_price_values: [{ moq: 10, price: 25, lead_time: 2, attribute_value: "IAV-RED" }],
})
assert.deepEqual(editorValues.item_price_values, [
	{ moq: 10, price: 25, lead_time: 2, attribute_value: "IAV-RED" },
])
assert.equal(itemPriceTierPrecision({ moq: { precision: 3 } }, "moq"), 3)
assert.equal(itemPriceTierPrecision({ price: { precision: "3" } }, "price"), 3)
assert.equal(itemPriceTierPrecision({ lead_time: { precision: 0 } }, "lead_time"), 0)
assert.notEqual(
	itemPriceEditorRequestKey({ routeName: "purchase-item-price-new", item: "ITEM-A", supplier: "SUP-A" }),
	itemPriceEditorRequestKey({ routeName: "purchase-item-price-new", item: "ITEM-B", supplier: "SUP-B" }),
)
assert.equal(
	itemPriceEditorRequestKey({ name: "ITP-1", routeName: "purchase-item-price-edit", item: "ITEM-A", supplier: "SUP-A" }),
	itemPriceEditorRequestKey({ name: "ITP-1", routeName: "purchase-item-price-edit", item: "ITEM-B", supplier: "SUP-B" }),
)
editorValues.item_price_values[0].price = 30
assert.equal(itemPriceSaveValues(editorValues).item_price_values[0].price, 30)
assert.equal(itemPriceSaveValues({ ...editorValues, depends_on_attribute: 0 }).attribute, null)
assert.equal(itemPriceSaveValues({ ...editorValues, depends_on_attribute: 0 }).item_price_values[0].attribute_value, null)
assert.deepEqual(savedItemPriceIdentity({ record: { name: "ITP-2", modified: "m2" } }), { name: "ITP-2", modified: "m2" })
assert.deepEqual(captureRecordTarget({ name: "ITP-2", modified: "m2" }, "ITP-fallback"), { name: "ITP-2", modified: "m2" })
assert.deepEqual(captureRecordTarget({}, "ITP-fallback"), { name: "ITP-fallback", modified: "" })
assert.equal(isCurrentRecordRequest("ITP-B", "ITP-B", 2, 2), true)
assert.equal(isCurrentRecordRequest("ITP-A", "ITP-B", 1, 2), false)
assert.deepEqual(itemPriceSaveValues({
	...editorValues,
	item_price_values: [
		{ moq: 10, price: 8, lead_time: 2, attribute_value: "RED" },
		{ moq: 5, price: 9, lead_time: 2, attribute_value: "BLUE" },
		{ moq: 1, price: 10, lead_time: 2, attribute_value: "RED" },
	],
}).item_price_values.map((row) => `${row.attribute_value}:${row.moq}`), ["BLUE:5", "RED:1", "RED:10"])
assert.deepEqual(itemPriceAttributeValues([
	{ attribute: "Colour", values: [{ name: "RED", label: "Red" }] },
	{ attribute: "Size", values: [{ name: "L", label: "Large" }] },
], "Size"), [{ name: "L", label: "Large" }])
assert.equal(itemPriceCanSave({ item_name: "ITEM-1", supplier: "SUP-1", tax: "GST", from_date: "2026-10-13", item_price_values: [{ moq: 1, price: 10, lead_time: 2 }] }), true)
assert.equal(itemPriceCanSave({ item_name: "ITEM-1", supplier: "", tax: "GST", from_date: "2026-10-13", item_price_values: [{ moq: 1, price: 10 }] }), false)
assert.equal(itemPriceCanSave({ item_name: "ITEM-1", supplier: "SUP-1", tax: "GST", from_date: "2026-10-13", depends_on_attribute: 1, attribute: "Colour", item_price_values: [{ moq: 1, price: 10 }] }), false)
assert.equal(itemPriceCanSave({ item_name: "ITEM-1", supplier: "SUP-1", tax: "GST", from_date: "2026-10-13", depends_on_attribute: 1, attribute: "Colour", item_price_values: [{ moq: 1, price: 10, lead_time: 2, attribute_value: "RED" }] }), true)

assert.deepEqual(ITEM_PRICE_SECTIONS.map((section) => section.fields), [
	["item_name", "supplier", "supplier_name"],
	["uom", "from_date", "to_date"],
	["tax", "approved_by"],
])
const priceViewFields = [
	{ fieldname: "from_date", label: "From Date", fieldtype: "Date", value: "2026-09-09" },
	{ fieldname: "approved_by", label: "Approved By", fieldtype: "Link", value: "migrated@example.com" },
]
assert.equal(itemPriceOverviewFields({ record: { docstatus: 0 }, fields: priceViewFields })[1].value, "")
assert.equal(itemPriceOverviewFields({ record: { docstatus: 1, approved_by: "boss@example.com" }, fields: priceViewFields })[1].value, "boss@example.com")
assert.equal(itemPriceOverviewFields({})?.length, 0)
assert.equal(itemPriceFieldLabel(priceViewFields, "from_date", "Valid from"), "From Date")
assert.equal(itemPriceFieldLabel({ moq: { label: "MOQ" } }, "moq", "From qty"), "MOQ")
assert.equal(itemPriceFieldLabel(undefined, "moq", "MOQ"), "MOQ")
assert.equal(itemPriceDateLimit("2026-10-15").getTime(), new Date(2026, 9, 15).getTime())
assert.equal(itemPriceDateLimit(""), undefined)
assert.equal(itemPriceTierValue({ fieldname: "moq", fieldtype: "Float", precision: 2 }, 0), "0")
assert.equal(itemPriceTierValue({ fieldname: "moq", fieldtype: "Float", precision: 2 }, 1500.5), "1,500.5")
assert.equal(itemPriceTierValue({ fieldname: "price", fieldtype: "Currency", precision: 3 }, 1.05), "1.05")
assert.equal(itemPriceTierValue({ fieldname: "price", fieldtype: "Currency", precision: 3 }, 9.125), "9.125")
assert.equal(itemPriceTierValue({ fieldname: "lead_time", fieldtype: "Int", precision: 0 }, 7), "7")
assert.equal(itemPriceTierValue({ fieldname: "price", fieldtype: "Currency" }, null), "—")
assert.equal(itemPriceAttributeHint("", []), "Choose an Item first")
assert.equal(itemPriceAttributeHint("Poly Bag", []), "This Item has no attributes")
assert.equal(itemPriceAttributeHint("Poly Bag", [{ attribute: "Size" }]), "")
assert.deepEqual(
	activePriceTiers({
		tiers: [
			{ attribute_value: "RED", attribute_value_label: "Red", moq: 10, price: 8, lead_time: 4 },
			{ attribute_value: "BLUE", attribute_value_label: "Blue", moq: 1.5, price: 9, lead_time: 2 },
			{ attribute_value: "RED", attribute_value_label: "Red", moq: 1, price: 10, lead_time: 3 },
		],
	}),
	[
		{ attribute_value: "BLUE", attribute_value_label: "Blue", moq: 1.5, price: 9, lead_time: 2 },
		{ attribute_value: "RED", attribute_value_label: "Red", moq: 1, price: 10, lead_time: 3 },
		{ attribute_value: "RED", attribute_value_label: "Red", moq: 10, price: 8, lead_time: 4 },
	],
)

const commands = []
const priceActions = itemPriceActionItems({
	actions: [
		{ action: "Approve", label: "Approve", preview: "Ends ITP-1." },
		{ action: "Reject", label: "Reject", preview: "" },
	],
	can_edit: true,
	can_delete: true,
}, {
	workflow: (action) => commands.push(action.action),
	edit: () => commands.push("edit"),
	delete: () => commands.push("delete"),
})
assert.deepEqual(priceActions.map((action) => action.key), ["workflow-approve", "workflow-reject", "edit", "delete"])
assert.equal(priceActions[0].primary, true)
assert.ok(priceActions.slice(0, 3).every((action) => !action.menuOnly), "Workflow actions and Edit must stay visible")
assert.equal(priceActions[1].severity, "danger")
assert.equal(priceActions[2].primary, false)
assert.equal(priceActions[3].menuOnly, true)
assert.equal(priceActions[3].severity, "danger")
const expiredActions = itemPriceActionItems({ actions: [expiredTransition], can_edit: false, can_delete: false })
assert.deepEqual(expiredActions.map((action) => [action.key, action.icon, action.primary]), [["workflow-expired", "pi pi-clock", true]])
assert.equal(expiredActions[0].severity, "warn", "Expired must keep its warning colour on the primary button")
assert.equal(priceActions[0].severity, undefined, "Approve keeps the default primary colour")
assert.equal(itemPriceActionItems({ actions: [{ action: "Reject", label: "Reject" }] })[0].severity, "danger")
const rejectedActions = itemPriceActionItems({ actions: [], can_edit: true, can_delete: true })
assert.deepEqual(rejectedActions.map((action) => [action.key, Boolean(action.primary), Boolean(action.menuOnly)]), [["edit", true, false], ["delete", false, true]])
assert.deepEqual(itemPriceActionItems({ actions: [], can_edit: false, can_delete: false }), [])
priceActions[0].command()
priceActions[2].command()
assert.deepEqual(commands, ["Approve", "edit"])

const requests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	requests.push({ url, body: JSON.parse(options.body) })
	return { ok: true, status: 200, json: async () => ({ message: {} }) }
}
const {
	createItem,
	deleteItemPrice,
	executeItemPriceAction,
	getItemAttributeCounts,
	getItemEditor,
	getItemPriceEditor,
	getLotWorkspace,
	getPurchaseCapabilities,
	saveItemPrice,
	updateItem,
} = await import("../frontend/src/api/purchase.js")

await getPurchaseCapabilities()
await getItemEditor("ITEM-1")
await getItemAttributeCounts(["ITEM-1"])
await createItem({ name: "Item" })
await updateItem("ITEM-1", { name: "Item" }, "2026-10-13 10:00:00.000000")
await getItemPriceEditor(null, "ITEM-1")
await saveItemPrice({ item_name: "ITEM-1" }, { name: "ITP-1", expectedModified: "m1" })
await executeItemPriceAction("ITP-1", "Submit", "m2")
await deleteItemPrice("ITP-1", "m3")
await getLotWorkspace("C1225-03")

assert.match(requests[0].url, /purchase\.web_capabilities\.get_capabilities$/)
assert.equal(requests[1].body.name, "ITEM-1")
assert.deepEqual(requests[2].body.items, ["ITEM-1"])
assert.deepEqual(requests[3].body.values, { name: "Item" })
assert.equal(requests[4].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(requests[5].body.item, "ITEM-1")
assert.equal(requests[6].body.expected_modified, "m1")
assert.equal(requests[7].body.action, "Submit")
assert.equal(requests[8].body.expected_modified, "m3")
assert.match(requests[9].url, /purchase\.lot_workspace\.get_lot_workspace$/)
assert.equal(requests[9].body.name, "C1225-03")

const itemPricesListSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPricesList.vue", import.meta.url), "utf8")
const itemEditorSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemEditorPage.vue", import.meta.url), "utf8")
const itemsListSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemsList.vue", import.meta.url), "utf8")
const itemPageSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPage.vue", import.meta.url), "utf8")
const itemPriceEditorSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPriceEditor.vue", import.meta.url), "utf8")
const itemPricePageSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPricePage.vue", import.meta.url), "utf8")
const attributeValuesSource = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemAttributeValues.vue", import.meta.url), "utf8")
const attributeValuesDialogSource = readFileSync(new URL("../frontend/src/departments/purchase/item/ItemAttributeValuesDialog.vue", import.meta.url), "utf8")
const multiSelectSource = readFileSync(new URL("../frontend/src/components/common/MultiSelectField.vue", import.meta.url), "utf8")
const priceWorkspaceSource = readFileSync(new URL("../essdee_yrp/purchase/item_price_workspace.py", import.meta.url), "utf8")

assert.ok(itemPricesListSource.indexOf('v-else-if="loading"') < itemPricesListSource.indexOf('!capability'), "Item Price list must finish capability loading before ListView mounts")
assert.match(itemPriceEditorSource, /itemPriceSaveAction\(editor\.value\)/)
assert.match(itemPriceEditorSource, /savedItemPriceIdentity\(workspace\)/)
assert.match(itemPriceEditorSource, /was saved, but \$\{action\.label\} could not be applied/)
assert.match(itemPriceEditorSource, /<DocumentSaveButton v-if="!loading && !loadError" :show-submit="Boolean\(saveAction\)"/)
assert.doesNotMatch(itemPriceEditorSource, /"Submit"|send for approval|Save draft/)
assert.match(itemPriceEditorSource, /<DocumentStatusBadge v-if="editor\.workflow\?\.state"/)
assert.doesNotMatch(itemPriceEditorSource, /<h2>Validity<\/h2>/)
assert.match(priceWorkspaceSource, /"save_actions": get_save_actions\(doc\)/)
assert.doesNotMatch(priceWorkspaceSource, /can_send_for_approval|== "Draft"|!= "Draft"/)
assert.match(itemPricesListSource, /:status-options="capability\.workflow_states \|\| \[\]"/)
assert.doesNotMatch(itemPricePageSource + itemPricesListSource, /workflow_state \|\| 'Draft'/)
assert.match(itemPricePageSource, /itemPriceOverviewFields\(workspace\.value\)/)
assert.match(itemPricePageSource, /<DocumentOverview :fields="overviewFields" :definitions="ITEM_PRICE_SECTIONS" include-empty/)
assert.match(itemPricePageSource, /activePriceTiers\(\{ tiers: workspace\.value\.tiers \}\)/)
assert.doesNotMatch(itemPricePageSource, /\{\{ record\.uom|price-summary|itemPriceGroups|dateRange/)
for (const [source, selector] of [[itemPricePageSource, ".item-price-frame"], [itemPageSource, ".purchase-record-page"], [itemPriceEditorSource, ".price-editor-page"], [itemEditorSource, ".purchase-editor-page"]]) {
	assert.ok(source.includes(`${selector} { width: 100%; min-width: 0; }`), `${selector} must span the page gutter without a max-width cap`)
	assert.doesNotMatch(source, /min-height: 5[68]0px|clamp\(2px, \.7vw, 10px\)/)
}
assert.match(itemPricePageSource, /\.price-timeline__list, \.price-history__list \{[^}]*max-height: 320px; overflow: auto;/)
assert.match(itemEditorSource, /<p class="purchase-code-hint">[^\n]*<\/p>\s*<\/div>/)
assert.match(itemEditorSource, /\.purchase-code-hint \{[^}]*margin: 0;/)
assert.match(attributeValuesSource, /repeat\(auto-fit, minmax\(280px, 1fr\)\)/)
assert.ok(itemsListSource.indexOf('<Select v-model="mode"') > itemsListSource.indexOf("<template #toolbar-actions>"), "Item list modes belong in the ListView toolbar")
assert.match(itemEditorSource, /<LinkField [^\n]*doctype="Item Attribute" :filters="otherAttributeFilter\(row\)" :show-open-button="false"/)
assert.match(itemEditorSource, /<ItemAttributeValues [^>]*@edit="openValues"/)
assert.match(itemEditorSource, /<ItemAttributeValuesDialog [^>]*@apply="applyValues"/)
assert.match(itemEditorSource, /permissions\?\.can_write_item_attribute/)
assert.doesNotMatch(itemEditorSource, /options\?\.attributes|MultiSelectField|addItemAttributeValues|searchItemAttributeValues|router\.push\(\{[^}]*Mapping/)
assert.match(itemPageSource, /<ItemAttributeValues v-if="values\.attributes\?\.length" :attributes="values\.attributes" \/>/)
assert.match(attributeValuesSource, /All \{\{ row\.attribute \}\} values/)
assert.match(attributeValuesSource, /:aria-label="`Edit \$\{row\.attribute\} values`"/)
assert.doesNotMatch(attributeValuesSource + attributeValuesDialogSource, /router|window\.open|href=/)
assert.match(attributeValuesDialogSource, /:show-open-button="false"/)
assert.match(attributeValuesDialogSource, /v-if="canCreate"/)
assert.match(attributeValuesDialogSource, /@keydown\.enter\.prevent="createValue"/)
assert.match(attributeValuesDialogSource, /:disabled="!changed \|\| creating"/)
assert.match(attributeValuesDialogSource, /if \(sequence !== openSequence\) return/)
assert.match(attributeValuesDialogSource, /<div @keydown\.escape="keepDialogOpen">\s*<LinkField/)
assert.match(attributeValuesSource + attributeValuesDialogSource, /small \{ flex-shrink: 0; white-space: nowrap;/)
assert.match(itemEditorSource, /Object\.assign\(row, resetAttributeRow\(storedMappings\.value, attribute \|\| ""\)\)/)
assert.doesNotMatch(attributeValuesDialogSource, /createItem|updateItem/)
assert.match(itemsListSource, /excluded-filter-fields="\['variant_of'\]"/)
assert.match(itemsListSource, /itemAttributeCountLabel\(attributeCounts\[row\.name\]\)/)
assert.match(itemsListSource, /sequence !== attributeCountSequence/)
assert.match(multiSelectSource, /@filter="\$emit\('filter', \$event\)"/)
assert.match(itemPriceEditorSource, /const NUMBER_FIELDS = \["moq", "price", "lead_time"\]/)
assert.match(itemPriceEditorSource, /max-fraction-digits="tierPrecision\(fieldname\)"/)
assert.match(itemPriceEditorSource, /:label="`\$\{fieldLabel\('item_name', 'Item'\)\} \*`"/)
assert.match(itemPriceEditorSource, /:max-date="itemPriceDateLimit\(form\.to_date\)"/)
assert.match(itemPriceEditorSource, /:min-date="itemPriceDateLimit\(form\.from_date\)"/)
assert.match(itemPriceEditorSource, /<DataTable v-if="form\.item_price_values\.length" :value="form\.item_price_values"/)
assert.doesNotMatch(itemPriceEditorSource, /hasSavedRecord \|\| itemLoading|ToggleSwitch|price-tier--attribute/)
assert.doesNotMatch(itemPriceEditorSource, /Validity can begin on any date/)
assert.match(itemPriceEditorSource, /watch\(requestKey, load/)
assert.match(itemPriceEditorSource, /itemSequence \+= 1/)
assert.match(itemPageSource, /isCurrentRecordRequest/)
assert.match(itemPageSource, /captureRecordTarget/)
assert.match(itemPageSource, /<InlinePageNavigation/)
assert.match(itemPageSource, /v-if="values.name && values.name !== itemId"><dt>\{\{ fieldLabel\("name", "Item Name"\) \}\}<\/dt><dd>\{\{ values.name \}\}<\/dd>/)
assert.match(itemPageSource, /await setItemDisabled\(target.name, target.disabled \? 0 : 1, target.modified\)/)
assert.doesNotMatch(itemPageSource, /updateItem|itemSaveValues|target.values/)
assert.match(itemPageSource, /activePriceTiers\(data\)/)
assert.match(itemPageSource, /workspace\.value\.item_prices/)
assert.match(itemPageSource, /<DocumentStatusBadge :label="data\.workflow_state"/)
assert.match(itemPageSource, /key: "edit", label: "Edit", icon: "pi pi-pencil", primary: true/)
assert.match(itemPageSource + itemEditorSource, /<ItemDependentAttributeTable/)
assert.doesNotMatch(itemEditorSource, /Main attribute|>Unit <|>Name <|label="HSN"/)
assert.match(itemEditorSource, /fieldLabel\("primary_attribute", "Primary Attribute"\)/)
assert.match(itemEditorSource, /fieldLabel\("dependent_attribute", "Dependent Attribute"\)/)
assert.match(itemPricePageSource, /isCurrentRecordRequest/)
assert.match(itemPricePageSource, /captureRecordTarget/)
assert.match(itemPricePageSource, /<FabricDocumentWorkspace doctype="YRP Item Price" title="Item Price"/)
assert.match(itemPricePageSource, /workspace\.timeline/)
assert.match(priceWorkspaceSource, /"timeline": _timeline\(doc\)/)

for (const [source, prefix] of [[itemEditorSource, "purchase"], [itemPriceEditorSource, "price"]]) {
	assert.match(source, new RegExp(`<header class="erp-editor-header ${prefix}-editor__header">\\s*<div class="${prefix}-editor__leading">\\s*<InlinePageNavigation`))
	assert.match(source, new RegExp(`</div>\\s*</div>\\s*<div class="erp-editor-actions">`))
	assert.match(source, /<Button label="Cancel" icon="pi pi-times"/)
	assert.match(source, new RegExp(`\\.${prefix}-editor__header > \\.${prefix}-editor__leading \\{ display: flex; min-width: 0;`))
}

assert.doesNotMatch(itemPriceEditorSource, /\.price-editor__header \{ flex-wrap: wrap;|\.price-editor__header \.erp-editor-actions \{/)

const actionStripSource = readFileSync(new URL("../frontend/src/components/documents/DocumentActionStrip.vue", import.meta.url), "utf8")
const listViewSource = readFileSync(new URL("../frontend/src/components/common/ListView.vue", import.meta.url), "utf8")
assert.match(actionStripSource, /:severity="action\.severity \|\| 'secondary'"/)
assert.match(actionStripSource, /:severity="primaryAction\.severity"/)
assert.match(actionStripSource, /document-action-menu__item--danger/)
assert.match(listViewSource, /field\.inStandardFilter && !field\.hidden && !excluded\.has\(field\.fieldname\)/)

console.log("purchase views OK")

const unorderedTiers = itemPriceEditorValues({ item_price_values: [
	{ attribute_value: "IAV-2", attribute_value_label: "50 cm", moq: 0 },
	{ attribute_value: "IAV-7", attribute_value_label: "45 cm", moq: 0 },
] }).item_price_values
assert.deepEqual(unorderedTiers.map((row) => row.attribute_value_label), ["45 cm", "50 cm"])
console.log("item price editor order OK")
const labelOrdered = itemPriceSaveValues({ depends_on_attribute: 1, attribute: "Size", item_price_values: [
	{ attribute_value: "IAV-2", moq: 0 }, { attribute_value: "IAV-7", moq: 0 },
] }, [{ name: "IAV-2", label: "50 cm" }, { name: "IAV-7", label: "45 cm" }]).item_price_values
assert.deepEqual(labelOrdered.map((row) => row.attribute_value), ["IAV-7", "IAV-2"])
console.log("item price save order OK")

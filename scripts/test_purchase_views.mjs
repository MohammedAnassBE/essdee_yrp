#!/usr/bin/env node

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import {
	PURCHASE_ITEM_PRICE_STATUS_OPTIONS,
	activePriceTiers,
	canSendItemPriceForApproval,
	captureRecordTarget,
	itemCodeHint,
	itemAttributeSearchScope,
	itemAttributeCountLabel,
	itemEditorValues,
	itemKindLabel,
	itemListFilters,
	itemSaveValues,
	itemPriceActionItems,
	itemPriceAttributeValues,
	itemPriceCanSave,
	itemPriceEditorRequestKey,
	itemPriceEditorValues,
	itemPriceGroups,
	itemPriceListInitialStatus,
	itemPricePath,
	itemPriceSaveValues,
	itemPriceTierPrecision,
	itemRoutePath,
	isCurrentRecordRequest,
	purchaseLauncherItems,
	savedItemPriceIdentity,
	stageItemAttributeValue,
	withSelectedAttributeValues,
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
itemDraft.attributes[0].values.push({ name: "BLUE", label: "Blue" })
assert.deepEqual(itemSaveValues(itemDraft).attributes, [{
	attribute: "Colour",
	mapping_modified: "m1",
	values: [{ name: "RED", label: "Red" }, { name: "BLUE", label: "Blue" }],
}])
assert.equal(itemSaveValues(itemDraft).primary_attribute, "Colour")
assert.equal(itemSaveValues(itemDraft, { defaultSinglePrimary: false }).primary_attribute, null)
assert.equal(
	itemSaveValues({ ...itemDraft, attributes: [...itemDraft.attributes, { attribute: "Size", values: [] }] }).primary_attribute,
	null,
)
assert.equal(itemAttributeSearchScope(false, "ITEM-1"), null)
assert.equal(itemAttributeSearchScope(true, "ITEM-1"), "ITEM-1")
assert.deepEqual(
	withSelectedAttributeValues(
		[{ name: "RED", label: "Red" }],
		[{ name: "BLUE", label: "Blue" }, { name: "RED", label: "Red" }],
	),
	[{ name: "BLUE", label: "Blue" }, { name: "RED", label: "Red" }],
)
const stagedAttribute = stageItemAttributeValue(
	["Red"],
	[{ name: "Red", label: "Red" }, { name: "Blue", label: "Blue" }],
	"Green",
)
assert.deepEqual(stagedAttribute.values, ["Red", "Green"])
assert.deepEqual(stagedAttribute.availableValues.map((option) => option.label), ["Red", "Blue", "Green"])
assert.equal(itemAttributeCountLabel(2), "2")
assert.equal(itemAttributeCountLabel(0), "None")
assert.equal(itemAttributeCountLabel(null), "…")
assert.equal(itemEditorValues({ attributes: [{ attribute: "Colour", all_values_allowed: true, values: [{ label: "Red" }] }] }).attributes[0].all_values_allowed, true)

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
assert.equal(webDocumentPath("YRP Item Price", "ITP 1"), "/web/purchase/item-prices/ITP%201")
assert.match(webDocumentPath("Item", "ITEM/A"), /^\/web\/document-unavailable\?/)
assert.deepEqual(purchaseLauncherItems(), [
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
assert.equal(canSendItemPriceForApproval({ workflow: { can_send_for_approval: true }, permissions: { can_submit: false } }), true)
assert.equal(canSendItemPriceForApproval({ workflow: { can_send_for_approval: false }, permissions: { can_submit: true } }), false)
assert.deepEqual(PURCHASE_ITEM_PRICE_STATUS_OPTIONS, [
	"Approval Pending",
	"Draft",
	"Approved",
	"Rejected",
	"Expired",
])

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

assert.deepEqual(
	itemPriceGroups([
		{ moq: 10, price: 8, attribute_value: "BLUE", attribute_value_label: "Blue" },
		{ moq: 1, price: 10, attribute_value: "RED", attribute_value_label: "Red" },
		{ moq: 5, price: 9, attribute_value: "RED", attribute_value_label: "Red" },
	]),
	[
		{ key: "BLUE", label: "Blue", rows: [{ moq: 10, price: 8, attribute_value: "BLUE", attribute_value_label: "Blue" }] },
		{
			key: "RED",
			label: "Red",
			rows: [
				{ moq: 1, price: 10, attribute_value: "RED", attribute_value_label: "Red" },
				{ moq: 5, price: 9, attribute_value: "RED", attribute_value_label: "Red" },
			],
		},
	],
)
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
assert.equal(priceActions[1].menuOnly, true)
assert.equal(priceActions[2].menuOnly, true)
assert.equal(priceActions[3].menuOnly, true)
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

assert.match(requests[0].url, /purchase\.web_capabilities\.get_capabilities$/)
assert.equal(requests[1].body.name, "ITEM-1")
assert.deepEqual(requests[2].body.items, ["ITEM-1"])
assert.deepEqual(requests[3].body.values, { name: "Item" })
assert.equal(requests[4].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(requests[5].body.item, "ITEM-1")
assert.equal(requests[6].body.expected_modified, "m1")
assert.equal(requests[7].body.action, "Submit")
assert.equal(requests[8].body.expected_modified, "m3")

const itemPricesListSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPricesList.vue", import.meta.url), "utf8")
const itemEditorSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemEditorPage.vue", import.meta.url), "utf8")
const itemsListSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemsList.vue", import.meta.url), "utf8")
const itemPageSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPage.vue", import.meta.url), "utf8")
const itemPriceEditorSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPriceEditor.vue", import.meta.url), "utf8")
const itemPricePageSource = readFileSync(new URL("../frontend/src/departments/purchase/ItemPricePage.vue", import.meta.url), "utf8")
const multiSelectSource = readFileSync(new URL("../frontend/src/components/common/MultiSelectField.vue", import.meta.url), "utf8")
const priceWorkspaceSource = readFileSync(new URL("../essdee_yrp/purchase/item_price_workspace.py", import.meta.url), "utf8")

assert.ok(itemPricesListSource.indexOf('v-else-if="loading"') < itemPricesListSource.indexOf('!capability'), "Item Price list must finish capability loading before ListView mounts")
assert.match(itemPriceEditorSource, /canSendItemPriceForApproval\(editor\.value\)/)
assert.match(itemPriceEditorSource, /savedItemPriceIdentity\(workspace\)/)
assert.match(itemPriceEditorSource, /saved, but it could not be sent for approval/i)
assert.match(priceWorkspaceSource, /"can_send_for_approval"/)
assert.match(itemEditorSource, /@filter="searchAttributeOptions/)
assert.match(itemEditorSource, /itemAttributeSearchScope\(attributesLocked\.value, currentName\.value\)/)
assert.match(itemEditorSource, /const row = form\.attributes\.at\(-1\)/)
assert.match(itemEditorSource, /All values allowed/)
assert.match(itemEditorSource, /permissions\?\.can_write_item_attribute/)
assert.match(itemEditorSource, /stageItemAttributeValue/)
assert.doesNotMatch(itemEditorSource, /addItemAttributeValues/)
assert.match(itemsListSource, /excluded-filter-fields="\['variant_of'\]"/)
assert.match(itemsListSource, /itemAttributeCountLabel\(attributeCounts\[row\.name\]\)/)
assert.match(itemsListSource, /sequence !== attributeCountSequence/)
assert.match(multiSelectSource, /@filter="\$emit\('filter', \$event\)"/)
assert.match(itemPriceEditorSource, /max-fraction-digits="tierPrecision\('moq'\)"/)
assert.match(itemPriceEditorSource, /max-fraction-digits="tierPrecision\('price'\)"/)
assert.match(itemPriceEditorSource, /max-fraction-digits="tierPrecision\('lead_time'\)"/)
assert.match(itemPriceEditorSource, /price-field--required-link/)
assert.doesNotMatch(itemPriceEditorSource, /Validity can begin on any date/)
assert.match(itemPriceEditorSource, /watch\(requestKey, load/)
assert.match(itemPriceEditorSource, /itemSequence \+= 1/)
assert.match(itemPageSource, /isCurrentRecordRequest/)
assert.match(itemPageSource, /captureRecordTarget/)
assert.match(itemPageSource, /<InlinePageNavigation/)
assert.match(itemPageSource, /activePriceTiers\(data\)/)
assert.match(itemPricePageSource, /isCurrentRecordRequest/)
assert.match(itemPricePageSource, /captureRecordTarget/)
assert.match(itemPricePageSource, /<InlinePageNavigation/)
assert.match(itemPricePageSource, /workspace\.timeline/)
assert.match(priceWorkspaceSource, /"timeline": _timeline\(doc\)/)

console.log("purchase views OK")

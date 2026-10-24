import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { conversionPreview, emptySide, inheritDimensions, sideAttributes, sideProblems, sideSaveValues, sideUom, valuationArgs, withAttribute } from "../src/departments/fabric-store/item-conversion/itemConversion.js"
import { ACCESSORY_STORE_WORKSPACE_KEYS, storeWorkspaces } from "../src/departments/fabric-store/storeWorkspaces.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { PURCHASE_STORE_WORKSPACE_KEYS } from "../src/departments/purchase/purchaseViews.js"
import { departments } from "../src/departments/registry.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const SCHEMA = { attributes: ["Colour"], primary_attribute: "Size", primary_attribute_values: ["S", "M"], default_uom: "Nos" }
const COMPLETE = emptySide({ item: "Tee", attributes: { Colour: "Red" }, primary_value: "M", lot: "L1", received_type: "Accepted", qty: 2, rate: 30 })

test("Item Conversions open from Fabric Store, Accessory Store, Purchase and Merch & Purchase", () => {
	const card = storeWorkspaces("/accessory-store").find((item) => item.key === "item_conversions")
	assert.equal(card.to, "/accessory-store/item-conversions")
	assert.ok(ACCESSORY_STORE_WORKSPACE_KEYS.includes("item_conversions"))
	assert.ok(PURCHASE_STORE_WORKSPACE_KEYS.includes("item_conversions"))
	assert.ok(source("../src/departments/FabricStore.vue").includes('"stock_transfers", "item_conversions", "reports"'))
	assert.equal(merchPurchaseLauncherItems().find((item) => item.key === "item_conversions").to, "/purchase/item-conversions")
	for (const key of ["fabric-store", "accessory-store", "purchase"]) {
		assert.equal(departments.find((item) => item.key === key).sections.item_conversions, "item-conversions", key)
	}
	const router = source("../src/router/index.js")
	for (const path of ["/fabric-store/item-conversions", "/accessory-store/item-conversions", "/purchase/item-conversions"]) {
		assert.ok(router.includes(`path: "${path}"`), path)
	}
})

test("each side needs one item, its attributes, one size, lot, received type and a quantity", () => {
	assert.deepEqual(sideProblems(emptySide(), SCHEMA, "from"), ["Select the From Item."])
	assert.deepEqual(sideProblems(COMPLETE, SCHEMA, "to"), [])
	assert.deepEqual(
		sideProblems({ ...COMPLETE, attributes: {}, primary_value: "", qty: 0 }, SCHEMA, "to"),
		["Select the To Colour.", "Select the To Size.", "Enter the To Quantity."],
	)
})

test("the To rate spreads the From value so both sides match", () => {
	const preview = conversionPreview(COMPLETE, { ...COMPLETE, qty: 3 })
	assert.equal(preview.fromValue, 60)
	assert.equal(preview.toRate, 20)
	assert.equal(preview.difference, 0)
	assert.equal(conversionPreview(COMPLETE, { ...COMPLETE, qty: 0 }).toRate, 0)
})

test("the From valuation lookup waits for the variant and location", () => {
	assert.equal(valuationArgs(COMPLETE, SCHEMA, {}), null)
	assert.equal(valuationArgs({ ...COMPLETE, primary_value: "" }, SCHEMA, { warehouse: "S-1" }), null)
	const args = valuationArgs(COMPLETE, SCHEMA, { warehouse: "S-1", posting_date: "2026-10-24", posting_time: "10:00:00" })
	assert.deepEqual(JSON.parse(args.attributes), { Colour: "Red", Size: "M" })
	assert.equal(valuationArgs({ ...COMPLETE, attributes: { Colour: "" } }, SCHEMA, { warehouse: "S-1" }), null)
	assert.equal(args.uom, "Nos")
})

test("save values carry only the server fields and To inherits the From lot", () => {
	assert.deepEqual(Object.keys(sideSaveValues(COMPLETE)).sort(), ["attributes", "item", "lot", "primary_value", "qty", "received_type", "remarks", "secondary_qty"])
	assert.deepEqual(inheritDimensions(COMPLETE, emptySide()).lot, "L1")
	assert.equal(inheritDimensions(COMPLETE, emptySide({ lot: "L2" })).lot, "L2")
})

test("the editor shows From and To as separate consumed and produced cards", () => {
	const dialog = source("../src/departments/fabric-store/item-conversion/ItemConversionDialog.vue")
	const side = source("../src/departments/fabric-store/item-conversion/ItemConversionSide.vue")
	assert.ok(dialog.includes('direction="from"') && dialog.includes('direction="to"'))
	assert.ok(dialog.includes("pi pi-arrow-right"))
	assert.ok(side.includes('"From · consumed"') && side.includes('"To · produced"'))
})

test("a Stage-dependent item asks only for the attributes and UOM of the chosen Stage", () => {
	const schema = {
		attributes: ["Stage", "Panel", "Colour"],
		primary_attribute: "Size",
		primary_attribute_values: ["S", "M"],
		default_uom: "Pieces",
		dependent_attribute: "Stage",
		dependent_attribute_details: { attr_list: { Pack: { attributes: ["Size"], uom: "Box" }, Piece: { attributes: ["Size", "Colour"], uom: "Pieces" } } },
	}
	assert.deepEqual(sideAttributes(schema, emptySide()), ["Stage"])
	const piece = withAttribute(schema, withAttribute(schema, emptySide(), "Stage", "Piece"), "Colour", "Red")
	assert.deepEqual(sideAttributes(schema, piece), ["Stage", "Colour"])
	const pack = withAttribute(schema, piece, "Stage", "Pack")
	assert.deepEqual(pack.attributes, { Stage: "Pack" })
	assert.equal(sideUom(schema, pack), "Box")
	const side = { ...COMPLETE, attributes: pack.attributes }
	assert.deepEqual(sideProblems(side, schema, "from"), [])
	const args = valuationArgs(side, schema, { warehouse: "S-1" })
	assert.equal(args.uom, "Box")
	assert.deepEqual(JSON.parse(args.attributes), { Stage: "Pack", Size: "M" })
})

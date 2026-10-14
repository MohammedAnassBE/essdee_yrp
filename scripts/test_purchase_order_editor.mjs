import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"

import {
	addDaysToIsoDate,
	applyPurchaseOrderPricePreview,
	applyPurchaseOrderPriceSchedule,
	createPurchaseOrderPricePath,
	createPurchaseOrderDraftRevision,
	createPurchaseOrderPreviewController,
	currentPurchaseOrderPreview,
	formatIsoDate,
	loadPurchaseOrderGroups,
	purchaseOrderPriceWarning,
	validatePurchaseOrderItems,
} from "../frontend/src/utils/purchaseOrder.js"
import { mergeStockItemDraft } from "../frontend/src/utils/stockItemComposer.js"

assert.equal(addDaysToIsoDate("2026-10-05", 5), "2026-10-10")
assert.equal(formatIsoDate("2026-09-10"), "10-09-2026")

const validGroups = [{ items: [{ name: "ITEM-1", schedule_date: "2026-10-14" }] }]
assert.equal(validatePurchaseOrderItems({ transaction_date: "2026-10-05" }, validGroups), "")

const invalidGroups = [{ items: [{ name: "Yarn 34's GL-Greige", schedule_date: "2026-09-10" }] }]
assert.equal(
	validatePurchaseOrderItems({ transaction_date: "2026-10-05" }, invalidGroups),
	"Yarn 34's GL-Greige has Required By 10-09-2026, which is before Order Date 05-10-2026. Edit this item and choose a Required By date on or after the Order Date.",
)

const missingGroups = [{ items: [{ name: "ITEM-2", schedule_date: "" }] }]
assert.equal(
	validatePurchaseOrderItems({ transaction_date: "2026-10-05" }, missingGroups),
	"ITEM-2 needs a Required By date. Edit this item and select the date.",
)

assert.equal(
	validatePurchaseOrderItems({ transaction_date: "2026-10-05", schedule_date: "2026-10-14" }, missingGroups),
	"",
)

const draft = [{ items: [
	{ name: "ITEM A", discount_percentage: 10, values: { default: { qty: 6, rate: 999 } } },
	{ name: "ITEM B", discount_percentage: 0, values: { S: { qty: 6 }, M: { qty: 0 } } },
] }]
const preview = { rows: [
	{
		group_index: 0,
		item_index: 0,
		status: "ok",
		tax: "5",
		tax_rate: 5,
		lead_time_days: 7,
		values: { default: { status: "ok", rate: 80, tier: { moq: 10, rate: 80, lead_time_days: 7 } } },
	},
	{
		group_index: 0,
		item_index: 1,
		status: "missing",
		tax: null,
		tax_rate: 0,
		lead_time_days: null,
		values: { S: { status: "missing", rate: null, tier: null } },
	},
] }
const priced = applyPurchaseOrderPricePreview(draft, preview, {
	supplier: "Supplier & Sons",
	canCreateItemPrice: true,
})
assert.equal(priced[0].items[0].values.default.rate, 80)
assert.equal(priced[0].items[0].values.default.amount, 480)
assert.equal(priced[0].items[0].values.default.discount_amount, 48)
assert.equal(priced[0].items[0].values.default.tax_amount, 21.6)
assert.equal(priced[0].items[0].values.default.total_amount, 453.6)
assert.equal(priced[0].items[1].values.S.rate, 0)
assert.equal(priced[0].items[1].price_warning, "No approved price for this supplier")
assert.equal(
	priced[0].items[1].price_create_url,
	"/purchase/item-prices/new?item=ITEM%20B&supplier=Supplier%20%26%20Sons",
)
assert.equal(purchaseOrderPriceWarning("ambiguous"), "Multiple approved prices for this supplier")
assert.equal(purchaseOrderPriceWarning("no_slab"), "No approved price slab for this quantity")
assert.equal(createPurchaseOrderPricePath("ITEM", "SUP-1"), "/purchase/item-prices/new?item=ITEM&supplier=SUP-1")
assert.equal(
	applyPurchaseOrderPricePreview(draft, preview, { supplier: "SUP-1", canCreateItemPrice: false })[0].items[1].price_create_url,
	"",
)

const unresolvedDraft = [{ items: [{
	name: "LEGACY ITEM",
	tax: "12",
	discount_percentage: 10,
	values: { default: { qty: 2, rate: 125, amount: 250, discount_amount: 25, tax_amount: 27, total_amount: 252 } },
}] }]
const unresolvedPreview = { rows: [{
	group_index: 0,
	item_index: 0,
	status: "missing",
	tax: null,
	tax_rate: 0,
	lead_time_days: null,
	values: { default: { status: "missing", rate: null, tier: null } },
}] }
const unresolved = applyPurchaseOrderPricePreview(unresolvedDraft, unresolvedPreview, { supplier: "SUP-2" })
assert.equal(unresolved[0].items[0].tax, "12")
assert.deepEqual(unresolved[0].items[0].values.default, {
	qty: 2,
	rate: 125,
	amount: 250,
	discount_amount: 25,
	tax_amount: 27,
	total_amount: 252,
	price_status: "missing",
	price_tier: null,
	tax: "12",
})

const editedUnresolvedDraft = mergeStockItemDraft(
	{
		name: "LEGACY ITEM",
		tax: "12",
		values: { default: { qty: 2, rate: 125, amount: 250, tax_amount: 30, total_amount: 280 } },
	},
	{ name: "LEGACY ITEM", values: { default: { qty: 3 } } },
)
const editedUnresolved = applyPurchaseOrderPricePreview(
	[{ items: [editedUnresolvedDraft] }],
	unresolvedPreview,
	{ supplier: "SUP-2" },
)
assert.equal(editedUnresolved[0].items[0].tax, "12")
assert.equal(editedUnresolved[0].items[0].values.default.rate, 125)
assert.equal(editedUnresolved[0].items[0].values.default.amount, 375)
assert.equal(editedUnresolved[0].items[0].values.default.tax_amount, 45)

const mixedDraft = [{ items: [{
	name: "PRIMARY ITEM",
	tax: "12",
	discount_percentage: 0,
	values: {
		S: { qty: 2, rate: 125, tax: "12" },
		M: { qty: 3, rate: 150, tax: "12" },
	},
}] }]
const mixedPreview = { rows: [{
	group_index: 0,
	item_index: 0,
	status: "no_slab",
	tax: "5",
	tax_rate: 5,
	values: {
		S: { status: "ok", rate: 100, tax: "5", tax_rate: 5 },
		M: { status: "no_slab", rate: null, tax: "5", tax_rate: 5 },
	},
}] }
const mixed = applyPurchaseOrderPricePreview(mixedDraft, mixedPreview)
assert.equal(mixed[0].items[0].tax, "12")
assert.equal(mixed[0].items[0].values.S.rate, 100)
assert.equal(mixed[0].items[0].values.S.tax, "5")
assert.equal(mixed[0].items[0].values.S.tax_amount, 10)
assert.equal(mixed[0].items[0].values.M.rate, 150)
assert.equal(mixed[0].items[0].values.M.tax, "12")
assert.equal(mixed[0].items[0].values.M.tax_amount, 54)

const mixedUntaxedDraft = structuredClone(mixedDraft)
mixedUntaxedDraft[0].items[0].values.M.tax = ""
const mixedUntaxed = applyPurchaseOrderPricePreview(mixedUntaxedDraft, mixedPreview)
assert.equal(mixedUntaxed[0].items[0].values.M.tax, "")
assert.equal(mixedUntaxed[0].items[0].values.M.tax_amount, 0)
assert.equal(mixedUntaxed[0].items[0].values.M.total_amount, 450)

const legacyLoaded = loadPurchaseOrderGroups([{
	items: [{ name: "LEGACY ITEM", tax: "12", schedule_date: "2026-09-10", values: { default: { qty: 2, rate: 125 } } }],
}])
assert.equal(legacyLoaded[0].items[0].tax, "12")
assert.equal(legacyLoaded[0].items[0].values.default.rate, 125)
assert.match(
	validatePurchaseOrderItems({ transaction_date: "2026-10-05" }, legacyLoaded),
	/before Order Date/,
)

const scheduled = applyPurchaseOrderPriceSchedule([{
	items: [
		{ name: "FETCH", fetch_delivery_date: 1, price_status: "ok", price_lead_time_days: 7, values: {} },
		{ name: "MANUAL", fetch_delivery_date: 0, schedule_date: "2026-10-20", values: {} },
		{ name: "UNRESOLVED", fetch_delivery_date: 1, price_status: "missing", schedule_date: "2026-10-22", values: {} },
	],
}], { transactionDate: "2026-10-05", defaultRequiredBy: "2026-10-14" })
assert.equal(scheduled[0].items[0].schedule_date, "2026-10-12")
assert.equal(scheduled[0].items[1].schedule_date, "2026-10-20")
assert.equal(scheduled[0].items[2].schedule_date, "2026-10-22")

let releaseFirst
let releaseSecond
const pendingStates = []
const previewController = createPurchaseOrderPreviewController((pending) => pendingStates.push(pending))
const first = previewController.run(() => new Promise((resolve) => { releaseFirst = resolve }))
const second = previewController.run(() => new Promise((resolve) => { releaseSecond = resolve }))
releaseFirst("old")
assert.deepEqual(await first, { stale: true, value: "old" })
assert.equal(previewController.pending(), true)
releaseSecond("new")
assert.deepEqual(await second, { stale: false, value: "new" })
assert.equal(previewController.pending(), false)
assert.deepEqual(pendingStates, [true, true, true, false])

let rejectObsolete
let releaseCurrent
const failureController = createPurchaseOrderPreviewController()
const obsoleteFailure = failureController.run(() => new Promise((_resolve, reject) => { rejectObsolete = reject }))
const currentResponse = failureController.run(() => new Promise((resolve) => { releaseCurrent = resolve }))
rejectObsolete(new Error("obsolete preview failed"))
assert.deepEqual(await obsoleteFailure, { stale: true, value: undefined })
releaseCurrent("current")
assert.deepEqual(await currentResponse, { stale: false, value: "current" })
assert.equal(currentPurchaseOrderPreview({ stale: true, value: "obsolete" }), null)
assert.throws(
	() => currentPurchaseOrderPreview({ stale: true, value: "obsolete" }, { required: true }),
	/Purchase Order pricing changed/,
)
assert.equal(currentPurchaseOrderPreview({ stale: false, value: "current" }), "current")

const draftRevision = createPurchaseOrderDraftRevision()
const poARevision = draftRevision.revise()
assert.equal(draftRevision.isCurrent(poARevision), true)
const poBRevision = draftRevision.revise()
assert.equal(draftRevision.isCurrent(poARevision), false)
assert.equal(draftRevision.isCurrent(poBRevision), true)

const routerSource = await readFile(new URL("../frontend/src/router/index.js", import.meta.url), "utf8")
for (const path of [
	"/fabric-store/purchase-orders/new",
	"/accessory-store/purchase-orders/new",
	"/purchase/purchase-orders/new",
]) {
	assert.match(routerSource, new RegExp(`path: ["']${path}["']`))
}
const editorSource = await readFile(new URL("../frontend/src/departments/fabric-store/PurchaseOrderEditor.vue", import.meta.url), "utf8")
for (const filter of ["variant_of", "is_purchase_item", "is_stock_item"]) assert.match(editorSource, new RegExp(filter))
assert.match(editorSource, /:groups-preparer="previewItemPrices"/)
assert.match(editorSource, /:disabled="Boolean\(saving\) \|\| previewPending"/)

console.log("Purchase Order editor utility tests passed")

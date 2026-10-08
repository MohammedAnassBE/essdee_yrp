import assert from "node:assert/strict"

import {
	addDaysToIsoDate,
	formatIsoDate,
	validatePurchaseOrderItems,
} from "../frontend/src/utils/purchaseOrder.js"

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

console.log("Purchase Order editor utility tests passed")

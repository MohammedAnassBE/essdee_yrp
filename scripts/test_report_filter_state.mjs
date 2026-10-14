#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	cutBundleFormFilters,
	finishingPlanFormFilters,
	purchaseOrderFormFilters,
	stockBalanceFormFilters,
} from "../frontend/src/components/reports/reportFilterState.js"
import {
	normalizeReportFilters,
	sameReportFilters,
} from "../frontend/src/composables/webReportState.js"

assert.deepEqual(stockBalanceFormFilters({
	from_date: "2026-09-01",
	to_date: "2026-10-13",
	item: "ITEM-1",
	parent_item: "STYLE-1",
	warehouse: "Stores",
	lot: "LOT-1",
	received_type: "Purchase",
	remove_zero_balance_item: 0,
	show_variant_attributes: 1,
	show_stock_ageing_data: 0,
	show_inward_date_split: 1,
}), {
	fromDate: "2026-09-01",
	toDate: "2026-10-13",
	item: "ITEM-1",
	parentItem: "STYLE-1",
	warehouse: "Stores",
	lot: "LOT-1",
	receivedType: "Purchase",
	removeZero: false,
	showAttributes: true,
	showAgeing: false,
	showInwardSplit: true,
})

assert.deepEqual(purchaseOrderFormFilters({
	purchase_order: "PO-1",
	open_status: "Closed",
	date_based_on: "Delivery Date",
	from_date: "2026-10-01",
}), {
	item: "",
	supplier: "",
	purchaseOrder: "PO-1",
	deliveryLocation: "",
	lot: "",
	status: "",
	openStatus: "Closed",
	docstatus: "",
	dateBasedOn: "Delivery Date",
	fromDate: "2026-10-01",
	toDate: "",
})
assert.equal(purchaseOrderFormFilters({ open_status: "" }).openStatus, "")
assert.deepEqual(normalizeReportFilters({
	status: null,
	open_status: null,
	docstatus: undefined,
}), {
	docstatus: "",
	open_status: "",
	status: "",
})
assert.equal(sameReportFilters(
	{ status: null, open_status: "" },
	{ open_status: null, status: "" },
), true)
assert.deepEqual(finishingPlanFormFilters({ lot: "LOT-2", product_category: "Knits" }), {
	lot: "LOT-2",
	item: "",
	season: "",
	productCategory: "Knits",
})
assert.deepEqual(cutBundleFormFilters({ lot: "LOT-3", supplier: "SUP-1" }), {
	lot: "LOT-3",
	supplier: "SUP-1",
})

console.log("report filter state OK")

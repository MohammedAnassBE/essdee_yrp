import assert from "node:assert/strict"
import test from "node:test"

import { listStandardFilterFields, listStatusFilters } from "../src/components/common/listStatusFilters.js"
import {
	PURCHASE_ORDER_STATUSES,
	purchaseOrderStatusLabel,
	purchaseOrderStatusOptions,
	purchaseOrderStatusTone,
} from "../src/utils/purchaseOrderStatus.js"

const statuses = ["Draft", "Ordered", "Partially Received", "Received", "Partially Cancelled", "Cancelled", "Closed"]
const tones = ["warning", "info", "warning", "success", "neutral", "neutral", "info"]

test("managed Purchase Orders use every Desk fulfillment label ahead of ERPNext status", () => {
	for (const label of statuses) {
		assert.equal(purchaseOrderStatusLabel({
			is_yrp_managed: 1,
			yrp_fulfillment_status: label,
			status: "To Receive and Bill",
			docstatus: 0,
		}), label)
	}
})

test("managed Purchase Orders fall back to ERPNext status when fulfillment is empty or missing", () => {
	for (const fulfillment of [undefined, null, ""]) {
		assert.equal(purchaseOrderStatusLabel({
			is_yrp_managed: 1,
			yrp_fulfillment_status: fulfillment,
			status: "To Receive",
			docstatus: 1,
		}), "To Receive")
	}
})

test("unmanaged submitted Purchase Orders keep ERPNext status", () => {
	for (const managed of [undefined, 0, "0", false]) {
		assert.equal(purchaseOrderStatusLabel({
			is_yrp_managed: managed,
			yrp_fulfillment_status: "Received",
			status: "To Bill",
			docstatus: 1,
		}), "To Bill")
	}
})

test("unmanaged draft and cancelled Purchase Orders use Desk docstatus labels", () => {
	for (const [docstatus, label] of [[0, "Draft"], ["0", "Draft"], [2, "Cancelled"], ["2", "Cancelled"]]) {
		assert.equal(purchaseOrderStatusLabel({
			is_yrp_managed: 0,
			yrp_fulfillment_status: "Ordered",
			status: "To Receive and Bill",
			docstatus,
		}), label)
	}
})

test("string managed flags use fulfillment status and an empty record displays Draft", () => {
	assert.equal(purchaseOrderStatusLabel({ is_yrp_managed: "1", yrp_fulfillment_status: "Ordered", status: "Draft" }), "Ordered")
	assert.equal(purchaseOrderStatusLabel({}), "Draft")
})

test("Purchase Order tones map all Desk colours and default to blue meaning", () => {
	assert.deepEqual(statuses.map(purchaseOrderStatusTone), tones)
	assert.equal(purchaseOrderStatusTone("To Receive and Bill"), "info")
	assert.equal(purchaseOrderStatusTone(""), "info")
})

test("Purchase Order tabs have Desk order, labels and shared tones", () => {
	assert.deepEqual(PURCHASE_ORDER_STATUSES, statuses)
	assert.deepEqual(purchaseOrderStatusOptions.map(({ label, value, tone }) => ({ label, value, tone })),
		statuses.map((value, index) => ({ label: value, value, tone: tones[index] })))
})

test("every Purchase Order tab restricts both rows and counts to managed fulfillment status", () => {
	for (const value of statuses) {
		const expected = [["is_yrp_managed", "=", 1], ["yrp_fulfillment_status", "=", value]]
		assert.deepEqual(purchaseOrderStatusOptions.find((option) => option.value === value).filters, expected)
		assert.deepEqual(listStatusFilters("yrp_fulfillment_status", purchaseOrderStatusOptions, value), expected)
	}
})

test("generic status filters keep supporting string options and objects without custom filters", () => {
	assert.deepEqual(listStatusFilters("status", ["Draft"], "Draft"), [["status", "=", "Draft"]])
	assert.deepEqual(listStatusFilters("docstatus", [{ label: "Submitted", value: "1" }], "1"), [["docstatus", "=", "1"]])
})

test("configured status field replaces the raw status quick filter with its tab options", () => {
	const fields = [
		{ fieldname: "supplier", label: "Supplier", fieldtype: "Link" },
		{ fieldname: "status", label: "Status", fieldtype: "Select", options: "To Receive\nCompleted" },
		{ fieldname: "company", label: "Company", fieldtype: "Link" },
	]
	const result = listStandardFilterFields(fields, { statusField: "yrp_fulfillment_status", statusOptions: purchaseOrderStatusOptions })
	assert.deepEqual(result.map(({ fieldname, label, fieldtype }) => ({ fieldname, label, fieldtype })), [
		{ fieldname: "supplier", label: "Supplier", fieldtype: "Link" },
		{ fieldname: "yrp_fulfillment_status", label: "Status", fieldtype: "Select" },
		{ fieldname: "company", label: "Company", fieldtype: "Link" },
	])
	assert.deepEqual(result[1].choices, statuses.map((value) => ({ label: value, value })))
	assert.deepEqual(listStatusFilters("yrp_fulfillment_status", purchaseOrderStatusOptions, "Ordered"),
		[["is_yrp_managed", "=", 1], ["yrp_fulfillment_status", "=", "Ordered"]])
})

test("status quick filter keeps option labels and leaves lists without a status filter alone", () => {
	const fields = [{ fieldname: "docstatus", label: "Document Status", fieldtype: "Select" }]
	const options = [{ label: "Submitted", value: "1" }]
	assert.deepEqual(listStandardFilterFields(fields, { statusField: "docstatus", statusOptions: options })[0].choices, [{ label: "Submitted", value: "1" }])
	const plain = [{ fieldname: "supplier", label: "Supplier", fieldtype: "Link" }]
	assert.equal(listStandardFilterFields(plain, { statusField: "status", statusOptions: ["Open"] }), plain)
	assert.equal(listStandardFilterFields(fields, { statusField: "", statusOptions: options }), fields)
	assert.equal(listStandardFilterFields(fields, { statusField: "docstatus", statusOptions: [] }), fields)
})

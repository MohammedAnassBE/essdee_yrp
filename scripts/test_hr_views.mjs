#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	BILL_TRACKING_LIST_COLUMNS,
	BILL_TRACKING_STATUS_OPTIONS,
	assignedToMeFilters,
	billTrackingActionItems,
	bulkAssignSummary,
	deliveryPersonLabel,
} from "../frontend/src/departments/hr/hrViews.js"

assert.deepEqual(assignedToMeFilters(["HR"]), [
	["assigned_to", "in", ["HR"]],
	["docstatus", "=", 1],
	["form_status", "!=", "Closed"],
])
assert.equal(assignedToMeFilters([]), null)

assert.equal(
	bulkAssignSummary({
		assigned: ["BT-1", "BT-2"],
		skipped: [{ name: "BT-3", reason: "Closed bill" }],
	}),
	"Assigned 2 bills. Skipped 1: BT-3 (Closed bill).",
)
assert.equal(bulkAssignSummary({ assigned: ["BT-1"], skipped: [] }), "Assigned 1 bill.")

const actions = billTrackingActionItems(
	{
		approve_cancel: { allowed: true, label: "Approve Cancel Request" },
		assign: { allowed: true, label: "Assign" },
		cancel: { allowed: true, label: "Cancel" },
	},
	{ approve_cancel: () => "approved" },
)
assert.equal(actions.find((item) => item.primary).key, "approve_cancel")
assert.equal(actions.find((item) => item.key === "approve_cancel").command(), "approved")
assert.equal(actions.find((item) => item.key === "cancel").menuOnly, true)

assert.equal(BILL_TRACKING_STATUS_OPTIONS.length, 8)
assert.deepEqual(BILL_TRACKING_STATUS_OPTIONS, [
	"Open",
	"Assigned",
	"Closed",
	"Reopen",
	"Cancelled",
	"Amended",
	"Pending Approval",
	"Cancel Request Approved",
])
assert.deepEqual(BILL_TRACKING_LIST_COLUMNS, [
	"supplier",
	"bill_no",
	"bill_date",
	"invoice_value",
	"assigned_to",
	"form_status",
])
const deliveryPerson = { delivery_person: "Ravi", delivery_mob_no: "9876543210" }
assert.equal(deliveryPersonLabel(deliveryPerson), "Ravi · 9876543210")
assert.equal(deliveryPersonLabel({ delivery_mob_no: "9876543210" }), "9876543210")

const hrRequests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	hrRequests.push({ url, body: JSON.parse(options.body) })
	return { ok: true, status: 200, json: async () => ({ message: {} }) }
}
const { executeBillTrackingCommand, saveBillTracking } = await import("../frontend/src/api/hr.js")
await saveBillTracking({}, {
	name: "BT-1",
	expectedModified: "2026-10-13 10:00:00.000000",
})
await executeBillTrackingCommand("BT-1", "submit", "2026-10-13 10:00:00.000000")
await saveBillTracking({})
assert.equal(hrRequests[0].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(hrRequests[1].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(hrRequests[2].body.expected_modified, null)

console.log("hr views OK")

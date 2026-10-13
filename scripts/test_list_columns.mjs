#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	activeCurrencyReferences,
	buildColumnOptions,
	canSaveColumnDraft,
	createListInitialisationGuard,
	currencyReferenceField,
	matchesColumnSearch,
	syncColumnDraft,
} from "../frontend/src/components/common/listColumns.js"

const fields = [
	{ fieldname: "name", fieldtype: "Data", label: "ID" },
	{ fieldname: "supplier", fieldtype: "Link", label: "Supplier", inListView: 1 },
	{ fieldname: "form_status", fieldtype: "Select", label: "Form Status" },
	{ fieldname: "owner", fieldtype: "Link", label: "Created By" },
	{ fieldname: "creation", fieldtype: "Datetime", label: "Created On" },
]

const defaults = buildColumnOptions(fields, null, ["supplier", "form_status"])
assert.deepEqual(defaults.filter((field) => field.enabled).map((field) => field.fieldname), [
	"supplier",
	"form_status",
])
assert.equal(defaults.some((field) => field.fieldname === "name"), false)
assert.equal(defaults.find((field) => field.fieldname === "owner").label, "Created By")

const saved = buildColumnOptions(fields, [
	{ fieldname: "creation", enabled: 1 },
	{ fieldname: "forbidden_field", enabled: 1 },
	{ fieldname: "supplier", enabled: 0 },
], ["supplier"])
assert.deepEqual(saved.slice(0, 2).map((field) => field.fieldname), ["creation", "supplier"])
assert.equal(saved.some((field) => field.fieldname === "forbidden_field"), false)
assert.equal(saved.find((field) => field.fieldname === "form_status").enabled, false)

const migrated = buildColumnOptions(fields, [
	{ fieldname: "creation", enabled: 1 },
	{ fieldname: "supplier", enabled: 0 },
], ["supplier", "form_status"])
assert.deepEqual(migrated.slice(0, 3).map((field) => field.fieldname), [
	"creation",
	"form_status",
	"supplier",
])
assert.equal(migrated.find((field) => field.fieldname === "form_status").enabled, true)
assert.equal(migrated.find((field) => field.fieldname === "supplier").enabled, false)

for (const emptySaved of [[], [{ fieldname: "forbidden_field", enabled: 1 }]]) {
	const restored = buildColumnOptions(fields, emptySaved, ["supplier", "form_status"])
	assert.deepEqual(restored.filter((field) => field.enabled).map((field) => field.fieldname), [
		"supplier",
		"form_status",
	])
}

const displayedStatus = { ...fields[2], label: "Status" }
assert.equal(matchesColumnSearch(displayedStatus, "Status"), true)
assert.equal(matchesColumnSearch(displayedStatus, "Form Status"), false)
assert.equal(matchesColumnSearch(displayedStatus, "form_status"), true)
assert.equal(matchesColumnSearch(displayedStatus, "Select"), false)

const guard = createListInitialisationGuard()
const firstRequest = guard.begin("Purchase Order")
let metadataReady = false
let settingsReady = false
let columnDraft = syncColumnDraft([], [], { visible: true, edited: false })
assert.equal(canSaveColumnDraft(settingsReady, columnDraft), false)

let resolveFirstSettings
const firstSettings = new Promise((resolve) => {
	resolveFirstSettings = resolve
})
const secondRequest = guard.begin("Sales Order")
resolveFirstSettings(buildColumnOptions(fields, null, ["supplier", "form_status"]))
const staleOptions = await firstSettings
assert.equal(guard.isCurrent(firstRequest, "Sales Order"), false)
assert.equal(guard.isCurrent(secondRequest, "Sales Order"), true)
assert.deepEqual(columnDraft, [])

let resolveReload
const reloadRequest = guard.snapshot("Sales Order")
const reloadSettings = new Promise((resolve) => {
	resolveReload = resolve
})
const thirdRequest = guard.begin("Purchase Receipt")
resolveReload(staleOptions)
await reloadSettings
assert.equal(guard.isCurrent(reloadRequest, "Purchase Receipt"), false)
assert.equal(guard.isCurrent(thirdRequest, "Purchase Receipt"), true)

let activeStatus = ""
if (metadataReady) activeStatus = "Submitted"
assert.equal(activeStatus, "")
columnDraft = syncColumnDraft(columnDraft, staleOptions, { visible: true, edited: false })
metadataReady = true
settingsReady = true
if (metadataReady) activeStatus = "Submitted"
assert.equal(activeStatus, "Submitted")
assert.deepEqual(columnDraft.map((field) => field.fieldname), [
	"supplier",
	"form_status",
	"owner",
	"creation",
])
assert.equal(canSaveColumnDraft(settingsReady, columnDraft), true)
const editedDraft = syncColumnDraft(columnDraft, [{ fieldname: "replacement" }], {
	visible: true,
	edited: true,
})
assert.equal(editedDraft, columnDraft)
assert.equal(canSaveColumnDraft(true, []), false)

const currencyColumn = {
	fieldname: "advance_paid",
	fieldtype: "Currency",
	options: "party_account_currency",
}
const currencyFields = { advance_paid: "party_account_currency" }
assert.equal(currencyReferenceField(currencyColumn, currencyFields), "party_account_currency")
assert.deepEqual(activeCurrencyReferences([currencyColumn], currencyFields), ["party_account_currency"])

const requests = []
let responseMessage = {
	fields,
	columns: null,
	currency_fields: { advance_paid: "party_account_currency" },
}
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	requests.push({ url, body: JSON.parse(options.body) })
	return {
		ok: true,
		status: 200,
		json: async () => ({ message: responseMessage }),
	}
}
const { getUserListview, saveUserListview } = await import("../frontend/src/api/frappe.js")
const viewFields = ["supplier", "form_status"]
await getUserListview("YRP Bill Tracking", viewFields)
await saveUserListview("YRP Bill Tracking", [{ fieldname: "form_status", enabled: 1 }], viewFields)
assert.equal(requests[0].url, "/api/method/essdee_yrp.api.list_columns.get_user_listview")
assert.deepEqual(requests[0].body.view_fields, viewFields)
assert.equal(requests[1].url, "/api/method/essdee_yrp.api.list_columns.save_user_listview")
assert.deepEqual(requests[1].body.view_fields, viewFields)

const settings = await getUserListview("YRP Bill Tracking", viewFields)
assert.deepEqual(settings.currency_fields, { advance_paid: "party_account_currency" })

responseMessage = { fields: {}, columns: null }
await assert.rejects(
	getUserListview("YRP Bill Tracking", viewFields),
	/Invalid list column settings returned for YRP Bill Tracking/,
)
responseMessage = { fields, columns: {} }
await assert.rejects(
	getUserListview("YRP Bill Tracking", viewFields),
	/Invalid list column settings returned for YRP Bill Tracking/,
)
responseMessage = { fields, columns: null, currency_fields: [] }
await assert.rejects(
	getUserListview("YRP Bill Tracking", viewFields),
	/Invalid list column settings returned for YRP Bill Tracking/,
)

console.log("list columns OK")

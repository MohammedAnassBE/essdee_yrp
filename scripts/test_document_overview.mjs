#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	buildDocumentOverviewGroups,
	documentOverviewHasValue,
	formatDocumentOverviewValue,
} from "../frontend/src/utils/documentOverview.js"

const fields = [
	{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", value: "Essdee Knitting" },
	{ fieldname: "transaction_date", label: "Order Date", fieldtype: "Date", value: "2026-10-08" },
	{ fieldname: "comments", label: "Comments", fieldtype: "Small Text", value: "Handle carefully" },
	{ fieldname: "is_internal", label: "Internal", fieldtype: "Check", value: 0 },
	{ fieldname: "empty", label: "Empty", fieldtype: "Data", value: "" },
]

const definitions = [
	{ key: "identity", label: "Order identity", fields: ["is_internal"] },
	{ key: "supplier", label: "Supplier & delivery", fields: ["supplier"] },
	{ key: "schedule", label: "Schedule", fields: ["transaction_date"] },
	{ key: "status", label: "Status & notes", fields: ["comments", "empty"] },
]

assert.equal(documentOverviewHasValue("   "), false)

const groups = buildDocumentOverviewGroups(fields, definitions)
assert.deepEqual(groups.map((group) => group.label), [
	"Order identity",
	"Supplier & delivery",
	"Schedule",
	"Status & notes",
])
assert.deepEqual(groups[3].fields.map((field) => field.fieldname), ["comments"])
assert.equal(formatDocumentOverviewValue(fields[1]), "08-10-2026")
assert.equal(formatDocumentOverviewValue(fields[3]), "No")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Currency", value: 12345.5 }), "12,345.5")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Percent", value: 10 }), "10%")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Float", value: 0.0035, precision: 4 }), "0.0035")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Float", value: 0.27, precision: 4 }), "0.2700")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Float", value: null }), "—")
assert.equal(formatDocumentOverviewValue({ fieldtype: "Data", value: null }), "—")

const additional = buildDocumentOverviewGroups(fields, definitions.slice(0, 2), {
	includeUnclaimed: true,
	unclaimedDefinition: { key: "additional", label: "Additional details" },
})
assert.deepEqual(additional.at(-1).fields.map((field) => field.fieldname), ["transaction_date", "comments"])

console.log("Document overview grouping verified.")

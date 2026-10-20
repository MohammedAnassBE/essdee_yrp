import assert from "node:assert/strict"
import test from "node:test"

import { normaliseFrappeTime } from "../src/utils/documentValues.js"

test("Frappe time values with single-digit fractional seconds still display", () => {
	assert.equal(normaliseFrappeTime("22:26:0.947516"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:47:6.80532"), "22:47:06")
	assert.equal(normaliseFrappeTime("9:05:07"), "09:05:07")
	assert.equal(normaliseFrappeTime("22:26:00.947516"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:26"), "22:26:00")
	assert.equal(normaliseFrappeTime("22:26:60"), "")
	assert.equal(normaliseFrappeTime("22:2:00"), "")
})

test("List Time filters parse values with the shared Frappe time normaliser", async () => {
	const { readFileSync } = await import("node:fs")
	const source = readFileSync(new URL("../src/components/common/ListviewFilters.vue", import.meta.url), "utf8")
	assert.match(source, /const match = normaliseFrappeTime\(value\)\.match\(/)
})

test("F-G15 document overview shows Time fields without microseconds", async () => {
	const { formatDocumentOverviewValue } = await import("../src/utils/documentOverview.js")
	assert.equal(formatDocumentOverviewValue({ fieldtype: "Time", value: "23:04:19.619135" }), "23:04:19")
	assert.equal(formatDocumentOverviewValue({ fieldtype: "Time", value: "4:05:09" }), "04:05:09")
})

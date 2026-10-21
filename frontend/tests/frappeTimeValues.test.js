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

test("Dispatch History and the CPM rail show posting times through the shared normaliser", async () => {
	const { readFileSync } = await import("node:fs")
	const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
	assert.match(read("../src/departments/finishing/plan/FinishingDispatchHistoryTab.vue"), /normaliseFrappeTime\(log\.posting_time\)/)
	assert.match(read("../src/departments/cut-panel-store/CutPanelMovementRail.vue"), /normaliseFrappeTime\(row\.posting_time\)\.slice\(0, 5\)/)
	assert.equal(normaliseFrappeTime("6:03:58.712204"), "06:03:58")
})

test("Dispatch Box batch inputs are labelled with the batch id, not the internal row name", async () => {
	const { readFileSync } = await import("node:fs")
	const source = readFileSync(new URL("../src/departments/finishing/components/FinishingDispatchEntry.vue", import.meta.url), "utf8")
	assert.match(source, /\$\{batch\.batch_id \|\| batch\.batch_row\} Dispatch boxes/)
})

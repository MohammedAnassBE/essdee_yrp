import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	getActiveFinishingPlanTab,
	getVisibleFinishingPlanTabs,
	hasAlternativeRows,
	hasRole,
} from "../src/departments/finishing/plan/finishingPlanTabVisibility.js"

const TABS = ["details", "item-details", "grn", "inward", "old-lot", "dispatch-history", "ironing-excess", "pack-return", "ocr", "incomplete-transfer", "alternatives", "rejection"]
	.map((value) => ({ value }))
const values = (tabs) => tabs.map((tab) => tab.value)
const ALTERNATIVES = { "LOT-2": { item: "ALT", details: [{ items: [{ total_qty: 4 }] }] } }

test("System Manager sees Details, Inward and Dispatch History", () => {
	const visible = values(getVisibleFinishingPlanTabs(TABS, { isSystemManager: true }))
	for (const tab of ["details", "inward", "dispatch-history"]) assert.ok(visible.includes(tab), tab)
})

test("other users do not see Details, Inward and Dispatch History", () => {
	assert.deepEqual(values(getVisibleFinishingPlanTabs(TABS, { isSystemManager: false })), [
		"item-details", "grn", "old-lot", "ironing-excess", "pack-return", "ocr", "incomplete-transfer", "rejection",
	])
})

test("Alternatives tab follows alternative rows for every role", () => {
	for (const isSystemManager of [true, false]) {
		assert.ok(values(getVisibleFinishingPlanTabs(TABS, { isSystemManager, hasAlternatives: true })).includes("alternatives"))
		assert.ok(!values(getVisibleFinishingPlanTabs(TABS, { isSystemManager, hasAlternatives: false })).includes("alternatives"))
	}
})

test("alternative rows are detected only when a lot has item rows", () => {
	assert.equal(hasAlternativeRows(ALTERNATIVES), true)
	assert.equal(hasAlternativeRows({}), false)
	assert.equal(hasAlternativeRows(null), false)
	assert.equal(hasAlternativeRows({ "LOT-2": { item: "ALT", details: [{ items: [] }] } }), false)
})

test("hidden or missing active tab falls back to the first visible tab", () => {
	const visible = getVisibleFinishingPlanTabs(TABS, { isSystemManager: false })
	assert.equal(getActiveFinishingPlanTab(visible, "details"), "item-details")
	assert.equal(getActiveFinishingPlanTab(visible, "alternatives"), "item-details")
	assert.equal(getActiveFinishingPlanTab(visible, undefined), "item-details")
	assert.equal(getActiveFinishingPlanTab(visible, "grn"), "grn")
	const manager = getVisibleFinishingPlanTabs(TABS, { isSystemManager: true })
	assert.equal(getActiveFinishingPlanTab(manager, undefined), "details")
})

test("hasRole reads frappe boot user roles", () => {
	assert.equal(hasRole("System Manager", { user: { roles: ["System Manager"] } }), true)
	assert.equal(hasRole("System Manager", { user: { roles: ["Accounts User"] } }), false)
	assert.equal(hasRole("System Manager", undefined), false)
})

test("Finishing Plan tabs use the visibility helpers", () => {
	const source = readFileSync(new URL("../src/departments/finishing/FinishingPlanTabs.vue", import.meta.url), "utf8")
	assert.match(source, /getVisibleFinishingPlanTabs\(allTabs\.value/)
	assert.match(source, /getActiveFinishingPlanTab\(tabs\.value, route\.query\.tab\)/)
	assert.match(source, /hasRole\("System Manager"\)/)
	assert.match(source, /hasAlternativeRows\(/)
})

import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import test from "node:test"

import { LOT_TABS, LOT_VIEW_TABS } from "../src/departments/planning/lot/lotLayout.js"

const folder = new URL("../src/departments/planning/lot/", import.meta.url)
const source = (path) => readFileSync(new URL(path, folder), "utf8")

test("Planning view shows a Summary tab with the process flow; the editor keeps the Lot tab", () => {
	assert.equal(LOT_VIEW_TABS[0].label, "Summary")
	assert.equal(LOT_TABS[0].label, "Lot")
	assert.match(source("LotPage.vue"), /<Tab v-for="tab in LOT_VIEW_TABS"/)
	assert.match(source("LotPage.vue"), /<LotViewMain [^>]*include-empty/)
	const view = source("LotViewMain.vue")
	assert.match(view, /import LotProcessFlow from "\.\/flow\/LotProcessFlow\.vue"/)
	assert.match(view, /:pieces="workspace\.order_pieces"/)
	assert.doesNotMatch(view, /LotOcrTable|#fabric-details|#ipd|#ppo/)
})

test("Planning flow components use Planning APIs, Planning reports and nothing from another workspace", () => {
	const flow = new URL("flow/", folder)
	for (const name of readdirSync(flow)) {
		const text = readFileSync(new URL(name, flow), "utf8")
		assert.doesNotMatch(text, /departments\/merch|\.\.\/\.\.\/\.\.\/merch|api\/merch\.js/, name)
	}
	const container = source("flow/LotProcessFlow.vue")
	assert.match(container, /getPlanningCapabilities/)
	assert.match(container, /visibleProductionReports\(capabilities\?\.sections\?\.reports\?\.production/)
	assert.match(source("flow/LotFlowReports.vue"), /const REPORTS_PATH = "\/web\/planning\/reports"/)
})

test("step cards show the progress ring tile instead of bars", () => {
	assert.match(source("flow/LotItemSteps.vue"), /<LotStepRing :meters="step.meters" :status="step.status" \/>/)
	assert.doesNotMatch(source("flow/LotItemSteps.vue"), /pf-meters/)
})

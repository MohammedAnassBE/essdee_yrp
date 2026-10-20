import assert from "node:assert/strict"
import test from "node:test"
import { lotOcrView } from "../src/departments/sales/lotOcrView.js"

test("Lot OCR view treats a missing payload as an empty table", () => {
	for (const payload of [null, undefined]) {
		const view = lotOcrView(payload)
		assert.deepEqual(view.sizes, [])
		assert.deepEqual(view.processRows, [])
		assert.deepEqual(view.dispatchDetail, {})
		assert.deepEqual(view.finishingPlans, [])
		assert.equal(view.totalDispatch, 0)
	}
})

test("Lot OCR view normalises process rows", () => {
	const view = lotOcrView({ sizes: ["S"], processes: { Cutting: { total_sent: 2 }, Printing: null }, dispatch_detail: { S: 1 }, finishing_plan_list: ["FP-1"], total_dispatch: 1 })
	assert.deepEqual(view.sizes, ["S"])
	assert.deepEqual(view.processRows.map((row) => [row.name, row.wo_list, row.cp_list, row.data]), [["Cutting", [], [], {}], ["Printing", [], [], {}]])
	assert.equal(view.processRows[0].total_sent, 2)
	assert.deepEqual(view.dispatchDetail, { S: 1 })
	assert.deepEqual(view.finishingPlans, ["FP-1"])
	assert.equal(view.totalDispatch, 1)
})

test("LotOcrTable renders the empty state when the Lot has no OCR payload", async () => {
	const { resolve } = await import("node:path")
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const viewModule = await import("../src/departments/sales/lotOcrView.js")
	const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
	const LotOcrTable = loadComponent(resolve("frontend/src/departments/sales/LotOcrTable.vue"), {
		"vue-router": { RouterLink: control },
		"../../router/webDocumentRoutes.js": { webDocumentRoute: () => "" },
		"../../components/common/DocumentLink.vue": control,
		"./lotOcrView.js": viewModule,
	})
	const root = mountComponent(LotOcrTable, { payload: null })
	const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
	const cells = findNodes(root, (node) => node.type === "td").map(text)
	assert.ok(cells.includes("No submitted Work Order movement is available for this Lot."))
})

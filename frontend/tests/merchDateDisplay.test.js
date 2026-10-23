import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { cellText } from "../src/departments/merch/reports/workInProgress.js"

const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")

test("Work In Progress date cells render DD-MM-YYYY", () => {
	assert.equal(cellText({ last_cut_date: "2026-10-23" }, { fieldname: "last_cut_date", fieldtype: "Date" }), "23-10-2026")
	assert.equal(cellText({ sent_on: "2026-10-23 14:05:09" }, { fieldname: "sent_on", fieldtype: "Datetime" }), "23-10-2026 14:05")
	assert.equal(cellText({ last_cut_date: "" }, { fieldname: "last_cut_date", fieldtype: "Date" }), "")
	assert.equal(cellText({ lot: "LOT-2026-10-23" }, { fieldname: "lot", fieldtype: "Link" }), "LOT-2026-10-23")
})

test("Merch Lot PPO panel shows the delivery date as DD-MM-YYYY", () => {
	const panel = loadComponent(resolve("frontend/src/departments/merch/lot/MerchLotPpoPanel.vue"), {
		"vue-router": { RouterLink: control },
		"primevue/button": control, "primevue/dialog": control,
		"../../../components/common/DocumentLink.vue": control,
		"../../../components/common/LinkField.vue": control,
		"../../../components/documents/DocumentActionStrip.vue": control,
		"../merchViews.js": { MERCH_ROUTES: {} },
	})
	const root = mountComponent(panel, { showPanel: true, ppo: { name: "PPO", item: "A", delivery_date: "2026-10-23" } })
	const dates = findNodes(root, (node) => node.type === "dd").map(text)
	assert.ok(dates.includes("23-10-2026"), dates.join(" | "))
})

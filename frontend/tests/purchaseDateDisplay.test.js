import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { planBadge } from "../src/departments/purchase/lot/lotViews.js"

const text = node => node.text + node.children.map(text).join("")
const control = (props, { slots }) => Vue.h("control", props, slots.default?.())

test("purchase plan badge shows the build date as DD-MM-YYYY", () => {
	assert.equal(planBadge({ plan_status: "Built", plan_built_on: "2026-10-23 14:05:09.123456" }).text, "Plan ready 23-10-2026")
	assert.equal(planBadge({ plan_status: "Built" }).text, "Plan ready ")
})

test("purchase LotIdentity shows the delivery date as DD-MM-YYYY", () => {
	const component = loadComponent(resolve("frontend/src/departments/purchase/lot/LotIdentity.vue"), {
		"../../../components/common/DocumentLink.vue": control,
		"../../../components/documents/DocumentStatusBadge.vue": control,
	})
	const root = mountComponent(component, { name: "LOT", deliveryDate: "2026-10-23", headingId: "lot-title" })
	const strong = findNodes(root, node => node.type === "strong")[0]
	assert.equal(text(strong), "23-10-2026")
})

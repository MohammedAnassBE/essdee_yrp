import assert from "node:assert/strict"
import test from "node:test"
import { findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as sewingQuantityTotals from "../src/departments/sewing/sewingQuantityTotals.js"

test("F-G14 closed Work Order GRN quantity inputs use the server receipt limit", () => {
	const component = loadComponent("frontend/src/departments/sewing/components/ClosedWorkOrderGrnEditor.vue", {
		"../../../components/common/FormField.vue": () => null,
		"../sewingQuantityTotals.js": sewingQuantityTotals,
	})
	for (const limit of [0, 3.5, 12]) {
		const root = mountComponent(component, { values: {}, namingField: {}, groups: [{ items: [{ values: { default: { ref_docname: "ROW-1", qty: 0, pending_quantity: 20, max_receivable_quantity: limit } } }] }] })
		const input = findNodes(root, node => node.type === "input")[0]
		assert.equal(input.props.max, limit)
		assert.equal(input.props.min, "0")
	}
})

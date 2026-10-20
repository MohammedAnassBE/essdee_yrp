import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const Container = (_props, { slots }) => Vue.h("section", slots.default?.())
const nodes = (root, type) => findNodes(root, n => n.type === type)
const text = node => node.text + node.children.map(text).join("")
const component = loadComponent(resolve("frontend/src/departments/cutting/CuttingPlanTabs.vue"), {
	...Object.fromEntries(["message", "skeleton", "tab", "tablist", "tabpanel", "tabpanels", "tabs"].map(name => [`primevue/${name}`, Container])),
	"../../components/common/DocumentLink.vue": () => null,
	"../../components/documents/DocumentOverview.vue": () => null,
	"./CuttingPlanCpm.vue": () => null, "./CuttingPlanStockTransfers.vue": () => null, "./shared/MaterialRequirementGroups.vue": () => null,
})
function summary(items) {
	const root = mountComponent(component, { doc: { name: "CP-1" }, data: { completed_items: [{ attributes: ["Colour"], primary_attribute_values: ["S", "M"], items }] } })
	return findNodes(root, node => node.props.class?.includes?.("completed-quantity-section"))[0]
}

test("Cutting Plan Summary includes partial cut quantities, Completed Yes/No, and column totals", () => {
	const root = summary([
		{ attributes: { Colour: "Red" }, values: { S: 120, M: 80 }, completed: false },
		{ attributes: { Colour: "Blue" }, values: { S: "30", M: 20 }, completed: true },
		{ attributes: { Colour: "Zero" }, values: { S: 0, M: "0" }, completed: true },
		{ attributes: { Colour: "Negative" }, values: { S: -2 }, completed: false },
	])
	assert.deepEqual(nodes(root, "th").map(text), ["S.No.", "Colour", "S", "M", "Total", "Completed"])
	const rows = nodes(root, "tbody")[0].children.filter(node => node.type === "tr")
	assert.deepEqual(rows.map(row => nodes(row, "td").map(text)), [["1", "Red", "120", "80", "200", "No"], ["2", "Blue", "30", "20", "50", "Yes"], ["Total", "", "150", "100", "250", ""]])
	assert.ok(!text(root).includes("No completed cut quantities."))
})

test("Cutting Plan Summary retains the empty state when no cut quantity is positive", () => {
	const root = summary([{ values: { S: 0, M: "0" }, completed: true }, { values: { S: -1 }, completed: false }, { values: {} }])
	assert.equal(nodes(root, "table").length, 0)
	assert.ok(text(root).includes("No completed cut quantities."))
})

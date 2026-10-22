import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = (type, props, emits = []) => Vue.defineComponent({ props, emits, setup: (componentProps, { emit }) => () => Vue.h(type, { ...componentProps, emit }) })

function setup(props) {
	const events = []
	const component = loadComponent(resolve("frontend/src/departments/fabric-store/StockDocumentDialog.vue"), {
		"../../components/documents/DocumentTransactionDialog.vue": stub("view", ["visible", "doctype", "name"], ["update:visible", "changed", "edit", "amended"]),
		"./FabricStockOperationDialog.vue": stub("editor", ["visible", "operation", "name", "expectedModified"], ["update:visible", "changed"]),
	})
	const root = mountComponent(component, { visible: true, ...props, "onUpdate:visible": value => events.push(["visible", value]) })
	return { root, events, only: (type) => findNodes(root, node => node.type === type) }
}

test("submitted and cancelled stock entries open read-only, never the draft-only editor", async () => {
	for (const docstatus of [1, 2]) {
		const { only } = setup({ name: "YRP-STE-2026-00063", docstatus })
		await tick()
		assert.equal(only("editor").length, 0)
		assert.equal(only("view")[0].props.name, "YRP-STE-2026-00063")
		assert.equal(only("view")[0].props.doctype, "YRP Stock Entry")
	}
})

test("draft and new stock entries open the editor", async () => {
	for (const [name, docstatus] of [["YRP-STE-DRAFT", 0], ["", 0]]) {
		const { only } = setup({ name, docstatus, expectedModified: "m1" })
		await tick()
		assert.equal(only("view").length, 0)
		assert.equal(only("editor")[0].props.name, name)
		assert.equal(only("editor")[0].props.expectedModified, "m1")
	}
})

test("amending a submitted stock entry switches to the editor without closing", async () => {
	const { only, events } = setup({ name: "STE-1", docstatus: 1 })
	await tick()
	const view = only("view")[0]
	view.props.emit("amended", { record: { name: "STE-1-1", modified: "m2" } })
	view.props.emit("update:visible", false)
	await tick()
	assert.deepEqual(events, [])
	assert.equal(only("editor")[0].props.name, "STE-1-1")
	assert.equal(only("editor")[0].props.expectedModified, "m2")
})

test("CPM rail and Stock Transfers open stock entries through the view-or-edit dialog", () => {
	const movement = read("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(movement, /<StockDocumentDialog v-model:visible="stockDocumentVisible" :name="linkedDocumentName" :docstatus="linkedDocumentDocstatus"/)
	assert.match(movement, /linkedDocumentDocstatus.value = Number\(document.docstatus \|\| 0\)/)
	assert.doesNotMatch(movement, /FabricStockOperationDialog/)
	const transfers = read("departments/fabric-store/FabricStockTransfers.vue")
	assert.match(transfers, /<StockDocumentDialog/)
	assert.doesNotMatch(transfers, /FabricStockOperationDialog|DocumentTransactionDialog/)
})

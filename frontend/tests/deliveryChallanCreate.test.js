import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import { groupItemsForDisplay, setAggregatedCellQuantity } from "../src/engine/stock/groupItemsForDisplay.js"
import { isTableFilled, setTableQuantities } from "../src/engine/stock/deliveryChallanTotals.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

function table() {
	const groups = [{ items: [
		{ name: "RAW", attributes: { Colour: "Red" }, values: { S: { qty: 4, pending_quantity: 4 }, M: { qty: 2, pending_quantity: 6 } } },
		{ name: "RAW", attributes: { Colour: "Red" }, values: { S: { qty: 0, pending_quantity: 1 }, M: { qty: 0, pending_quantity: 2 } } },
		{ name: "RAW", attributes: { Colour: "Blue" }, values: { S: { qty: 0, pending_quantity: 0 }, M: { qty: 0, pending_quantity: 3 } } },
	] }]
	return { groups, rows: () => groupItemsForDisplay(groups)[0].items }
}
const setQuantity = (row, value, qty) => setAggregatedCellQuantity(row, value, qty)

test("ticking a Delivery Challan table fills every row with its pending quantity", () => {
	const { groups, rows } = table()
	assert.equal(isTableFilled(rows(), ["S", "M"]), false)
	setTableQuantities(rows(), ["S", "M"], true, setQuantity)
	assert.deepEqual(groups[0].items.map((row) => [row.values.S.qty, row.values.M.qty]), [[4, 6], [1, 2], [0, 3]])
	assert.equal(isTableFilled(rows(), ["S", "M"]), true)
})

test("unticking a Delivery Challan table sets every row to zero", () => {
	const { groups, rows } = table()
	setTableQuantities(rows(), ["S", "M"], true, setQuantity)
	setTableQuantities(rows(), ["S", "M"], false, setQuantity)
	assert.ok(groups[0].items.every((row) => row.values.S.qty === 0 && row.values.M.qty === 0))
	assert.equal(isTableFilled(rows(), ["S", "M"]), false)
})

test("a table with nothing pending is never shown as filled", () => {
	assert.equal(isTableFilled([{ values: { default: { qty: 0, pending_qty: 0 } } }], ["default"]), false)
	assert.equal(isTableFilled([{ values: { default: { qty: 3, pending_qty: 3 } } }], ["default"]), true)
})

test("each editable Delivery Challan item table offers the fill quantity toggle", () => {
	const workspace = source("../src/departments/fabric-store/DeliveryChallanWorkspace.vue")
	assert.match(workspace, /<label v-if="canEditMatrixBlock\(block\.kind\)" class="delivery-challan-matrix__fill"[^\n]*@update:model-value="fillTable\(section, \$event\)"/)
	assert.match(workspace, /function fillTable\(section, fill\) \{ setTableQuantities\(section\.items, primaryValues\(section\.group\), fill, setDisplayQuantity\) \}/)
})

function documentList(props, pushed) {
	const list = (listProps, { slots }) => Vue.h("list", listProps, slots["toolbar-actions"]?.())
	const component = loadComponent(resolve("frontend/src/departments/cut-panel-store/CutPanelDocuments.vue"), {
		"primevue/button": (buttonProps) => Vue.h("button", buttonProps),
		"vue-router": { useRouter: () => ({ push: (target) => pushed.push(target) }) },
		"../../components/common/ListView.vue": list,
		"../../router/listDocumentNavigation.js": {},
	})
	return mountComponent(component, props)
}

test("department Delivery Challan lists open a new Delivery Challan when the user can create one", () => {
	const pushed = []
	const capability = { doctype: "YRP Delivery Challan", can_read: true, can_create: true }
	const root = documentList({ capability, filters: [], viewRouteName: "merch-delivery-challan", newRouteName: "merch-delivery-challan-new" }, pushed)
	const [button] = findNodes(root, (node) => node.type === "button")
	assert.equal(button.props.label, "New Delivery Challan")
	button.props.onClick()
	assert.deepEqual(pushed, [{ name: "merch-delivery-challan-new" }])
	const readOnly = documentList({ capability: { ...capability, can_create: false }, filters: [], newRouteName: "merch-delivery-challan-new" }, [])
	assert.equal(findNodes(readOnly, (node) => node.type === "button").length, 0)
	const cutPanel = documentList({ capability }, [])
	assert.equal(findNodes(cutPanel, (node) => node.type === "button").length, 0, "Cut Panel Movement DCs are created from their movement")
})

test("editable department document routes hand the Delivery Challan list its new route", () => {
	const router = source("../src/router/index.js")
	assert.match(router, /deliveryChallanNewRouteName: editable \? `\$\{prefix\}-delivery-challan-new` : ""/)
	const section = source("../src/departments/FabricStoreSection.vue")
	assert.match(section, /props\.section === "delivery_challans" \? \{ newRouteName: props\.deliveryChallanNewRouteName \}/)
})

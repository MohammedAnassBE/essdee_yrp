import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as lotLayout from "../src/departments/purchase/lot/lotLayout.js"
import * as lotEditorModule from "../src/departments/purchase/lot/lotEditor.js"
import * as lotViewsModule from "../src/departments/purchase/lot/lotViews.js"

const { editTabFor, lotFabricErrors } = lotEditorModule

const { LOT_TABS, lotEditorTabs, lotSections, resolveLotTab, hasLotOcr, hasLotTransfer, toggleSection } = lotLayout
const source = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")

test("Lot pages and editors show Lot, Cloth Program, Actual Dia Conversions and BOM tabs; a new Lot shows Lot only", () => {
	assert.deepEqual(LOT_TABS.map((tab) => tab.label), ["Lot", "Cloth Program", "Actual Dia Conversions", "BOM"])
	assert.deepEqual(lotEditorTabs(false).map((tab) => tab.key), ["lot", "fabric", "dia-conversions", "bom"])
	assert.deepEqual(lotEditorTabs(true).map((tab) => tab.key), ["lot"])
})

test("legacy ?tab= keys land on the Lot tab and expand the matching section", () => {
	assert.deepEqual(resolveLotTab("details"), { tab: "lot", section: "" })
	assert.deepEqual(resolveLotTab("order-items"), { tab: "lot", section: "" })
	assert.deepEqual(resolveLotTab("order-details"), { tab: "lot", section: "order-details" })
	assert.deepEqual(resolveLotTab("ppo"), { tab: "lot", section: "ppo" })
	assert.deepEqual(resolveLotTab("ocr"), { tab: "lot", section: "ocr" })
	assert.deepEqual(resolveLotTab("fabric"), { tab: "fabric", section: "" })
	assert.deepEqual(resolveLotTab("dia-conversions"), { tab: "dia-conversions", section: "" })
	assert.deepEqual(resolveLotTab("bom"), { tab: "bom", section: "" })
	assert.deepEqual(resolveLotTab(undefined), { tab: "lot", section: "" })
	assert.deepEqual(resolveLotTab("unknown"), { tab: "lot", section: "" })
	assert.deepEqual(resolveLotTab("bom", lotEditorTabs(true)), { tab: "lot", section: "" })
	assert.equal(editTabFor("order-details"), "lot")
	assert.equal(editTabFor("fabric"), "fabric")
	assert.equal(editTabFor("bom"), "bom")
})

test("Lot sections keep Desk order and appear only when relevant", () => {
	const all = Object.fromEntries(lotLayout.LOT_SECTIONS.map((section) => [section.key, true]))
	assert.deepEqual(lotSections(all).map((section) => section.key), ["order-details", "fabric-details", "ipd", "ppo", "transfer", "ocr"])
	assert.deepEqual(lotSections({ ocr: true, ipd: true }, { ocr: 3 }), [
		{ ...lotLayout.LOT_SECTIONS[2], count: null },
		{ ...lotLayout.LOT_SECTIONS[5], count: 3 },
	])
	assert.equal(hasLotOcr(null), false)
	assert.equal(hasLotOcr({ processes: {}, total_dispatch: 0 }), false)
	assert.equal(hasLotOcr({ processes: { Print: {} } }), true)
	assert.equal(hasLotOcr({ total_dispatch: 5 }), true)
	assert.equal(hasLotTransfer({ has_transferred: 0, is_transferred: 0, transferred_lot: "" }), false)
	assert.equal(hasLotTransfer({ transferred_lot: "LOT-2" }), true)
	assert.deepEqual(toggleSection(["ipd"], "ocr"), ["ipd", "ocr"])
	assert.deepEqual(toggleSection(["ipd", "ocr"], "ipd"), ["ocr"])
})

test("editor facts show Yes/No transfer flags and link the transferred Lot", () => {
	const facts = lotLayout.derivedFacts({ is_transferred: 1, has_transferred: 0, transferred_lot: "LOT/2" }, lotLayout.LOT_TRANSFER_FIELDS)
	assert.deepEqual(facts.map((fact) => fact.value), ["No", "Yes", "LOT/2"])
	assert.deepEqual(facts[2].link, { doctype: "SD YRP Lot", name: "LOT/2" })
	assert.equal(lotLayout.derivedFacts({}, ["uom"])[0].value, "—")
	assert.deepEqual(lotFabricErrors([{ cloth_item: "" }, { cloth_item: "C" }], true), { "0.cloth_item": "Cloth Item is required." })
	assert.deepEqual(lotFabricErrors([{ cloth_item: "" }], false), {})
})

test("collapsible sections render their content only when expanded and toggle through update:expanded", () => {
	const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
	const tab = loadComponent(new URL("../src/departments/purchase/lot/LotMainTab.vue", import.meta.url).pathname, {
		"./LotCollapsibleSection.vue": loadComponent(new URL("../src/departments/purchase/lot/LotCollapsibleSection.vue", import.meta.url).pathname, {}),
		"./lotLayout.js": lotLayout,
		"primevue/button": control,
	})
	const updates = []
	const props = Vue.reactive({ sections: lotSections({ "order-details": true, ocr: true }), expanded: ["ocr"], "onUpdate:expanded": (value) => updates.push(value) })
	const slots = {
		header: () => Vue.h("lot-header"),
		quantities: () => Vue.h("lot-quantities"),
		"order-details": () => Vue.h("order-details-grid"),
		ocr: () => Vue.h("ocr-grid"),
	}
	const root = mountComponent({ render: () => Vue.h(tab, props, slots) }, {})
	const types = findNodes(root, (node) => typeof node.type === "string").map((node) => node.type)
	assert.ok(types.indexOf("lot-header") < types.indexOf("lot-quantities"))
	assert.ok(types.includes("ocr-grid"))
	assert.ok(!types.includes("order-details-grid"))
	const toggles = findNodes(root, (node) => node.type === "button")
	assert.deepEqual(toggles.map((button) => button.props["aria-expanded"]), [false, true])
	toggles[0].props.onClick()
	assert.deepEqual(updates, [["ocr", "order-details"]])
})

test("Purchase and Planning Lot page and editor use the shared Lot layout", () => {
	for (const department of ["purchase", "planning"]) {
		const page = source(`${department}/lot/LotPage.vue`)
		assert.match(page, /<LotViewMain /)
		assert.match(page, /v-for="tab in LOT_TABS"/)
		assert.match(page, /<LotBomPanel /)
		assert.match(page, /<TabPanel v-else-if="activeTab === 'dia-conversions'" value="dia-conversions">\s*<LotDiaConversionsTab /)
		const editor = source(`${department}/lot/LotEditor.vue`)
		assert.match(editor, /<LotEditorMain /)
		assert.match(editor, /<template #quantities><LotOrderItemsEditor /)
		assert.doesNotMatch(editor, /order-items/)
	}
	const view = source("purchase/lot/LotViewMain.vue")
	assert.ok(view.indexOf("#header") < view.indexOf("#quantities"))
	assert.ok(view.indexOf("#quantities") < view.indexOf("#order-details"))
})

test("selecting an IPD fills Order Quantities in place without switching tabs", () => {
	for (const path of ["purchase/lot/useLotEditor.js", "planning/lot/useLotEditor.js"]) {
		const text = source(path)
		const update = text.match(/async function updateProductionDetail\(sequence\) \{([\s\S]*?)\n\t\}/)[1]
		assert.match(update, /itemDetails\.value = result\.item_details/)
		assert.doesNotMatch(update, /activeTab/)
		assert.match(text, /itemDetails\.value\?\.items\.length/)
	}
})

function orderEditor() {
	const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
	const dir = new URL("../src/departments/purchase/lot/", import.meta.url).pathname
	return loadComponent(`${dir}LotOrderItemsEditor.vue`, {
		"primevue/button": control, "primevue/message": control, "primevue/inputnumber": (props) => Vue.h("input-number", props),
		"../../../api/frappe.js": { callMethod: async () => [] },
		"../../../components/common/LinkField.vue": control,
		"../../../components/documents/DocumentErrorDialog.vue": control,
		"../../../components/common/childGrid/entryTable.js": { vEntryTable: {} },
		"./LotEmptyState.vue": control,
		"./lotEditor.js": lotEditorModule,
		"./lotViews.js": lotViewsModule,
	})
}
const details = (extra = {}) => ({ item: "TEE", default_uom: "Box", primary_attribute: "Size", primary_attribute_values: ["S", "M"], final_state_attr: [],
	items: [{ attributes: {}, values: { S: { qty: 200, ratio: 2, mrp: 0 }, M: { qty: 100, ratio: 1, mrp: 0 } } }], ...extra })

test("Order Quantities is one editable Qty/Ratio/MRP × size grid bound to the saved box quantities", () => {
	const itemDetails = Vue.reactive(details())
	const root = mountComponent(orderEditor(), { itemDetails })
	const inputs = findNodes(root, (node) => node.type === "input-number")
	assert.deepEqual(inputs.map((input) => input.props["model-value"]), [200, 100, 2, 1, 0, 0])
	assert.equal(findNodes(root, (node) => node.type === "table").length, 1)
	assert.equal(findNodes(root, (node) => node.props?.label === "Add row").length, 0)
	inputs[1].props["onUpdate:modelValue"](150)
	assert.equal(itemDetails.items[0].values.M.qty, 150)
	inputs[0].props["onUpdate:modelValue"](null)
	assert.equal(itemDetails.items[0].values.S.qty, 0)
})

test("Order Quantities locks to plain values and offers the row composer only for non-size attributes", () => {
	const locked = mountComponent(orderEditor(), { itemDetails: details(), isLocked: true })
	assert.equal(findNodes(locked, (node) => node.type === "input-number").length, 0)
	const ppoLocked = mountComponent(orderEditor(), { itemDetails: details(), productionOrder: "PPO-1", hasOrderDetails: true })
	assert.equal(findNodes(ppoLocked, (node) => node.type === "input-number").length, 0)
	const boxLocked = mountComponent(orderEditor(), { itemDetails: details(), boxLocked: true })
	assert.equal(findNodes(boxLocked, (node) => node.type === "input-number").length, 0)
	const coloured = mountComponent(orderEditor(), { itemDetails: details({ final_state_attr: ["Colour"] }) })
	assert.equal(findNodes(coloured, (node) => node.props?.label === "Add row").length, 1)
	const emitted = []
	const empty = mountComponent(orderEditor(), { itemDetails: details({ items: [] }), "onUpdate:itemDetails": (value) => emitted.push(value) })
	findNodes(empty, (node) => node.props?.label === "Add row")[0].props.onClick()
	assert.deepEqual(emitted[0].items, [{ attributes: {}, primary_attribute: "Size", values: { S: { qty: 0, ratio: 0, mrp: 0 }, M: { qty: 0, ratio: 0, mrp: 0 } } }])
})

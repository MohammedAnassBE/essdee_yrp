import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as program from "../src/engine/lotClothProgram.js"
import * as printUrl from "../src/utils/printUrl.js"

const tick = async () => { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = type => (props, { slots }) => Vue.h(type, props, Object.values(slots || {}).map(slot => slot?.()))
const preview = {
	extra_percentage: 4.8,
	cloth_per_kg_yarn: 1,
	tables: [{
		cloth_item: "Cloth", colours: ["Navy"], colour_totals: { Navy: 105 }, total: 105,
		fabric_groups: [{ fabric_type: "Main Fabric", routes: [{ fabric_type: "Main Fabric", dia: "12 Dia", weights: { Navy: 105 }, total: 105 }], colour_totals: { Navy: 105 }, total: 105, additions: { Navy: 5 }, additional_total: 5 }],
	}],
	display_totals: { required_weight: 96, extra_weight: 4, manual_additional_weight: 5, program_weight: 105 },
}

function mountDialog() {
	const calls = []
	const component = loadComponent(new URL("../src/departments/purchase/lot/ClothProgramBuildDialog.vue", import.meta.url).pathname, {
		"primevue/button": stub("button"), "primevue/dialog": stub("dialog"), "primevue/inputnumber": stub("inputnumber"), "primevue/message": stub("message"),
		"../../../api/frappe.js": { callMethod: async (method, args) => { calls.push([method.split(".").pop(), args]); return method.endsWith("preview") ? preview : {} } },
		"../../../engine/lotClothProgram.js": program,
		"../../../utils/printUrl.js": printUrl,
		"./lotViews.js": { formatQuantity: value => String(value) },
	})
	const events = []
	const root = mountComponent(component, { visible: true, lot: "LOT-1", modified: "m1", "onUpdate:visible": value => events.push(["visible", value]), onSaved: () => events.push(["saved"]) })
	const button = label => findNodes(root, node => node.type === "button" && node.props.label === label)[0].props
	const dialog = () => findNodes(root, node => node.type === "dialog")[0].props
	return { calls, events, button, dialog }
}

test("Calculate only previews; nothing is saved", async () => {
	const page = mountDialog()
	page.dialog().onShow()
	await tick()
	page.button("Calculate").onClick()
	await tick()
	assert.deepEqual(page.calls.map(([method]) => method), ["get_cloth_program_preview", "get_cloth_program_preview"])
	assert.deepEqual(page.calls[0][1], { lot: "LOT-1" })
	assert.deepEqual(JSON.parse(page.calls[1][1].additions), [{ cloth_item: "Cloth", fabric_type: "Main Fabric", colour: "Navy", additional_weight: 5 }])
	assert.equal(page.calls[1][1].excess_percentage, 4.8)
	assert.deepEqual(page.events, [])
})

test("Save stores the percentage and Add Weight, then closes", async () => {
	const page = mountDialog()
	page.dialog().onShow()
	await tick()
	page.button("Save").onClick()
	await tick()
	assert.deepEqual(page.calls[1], ["recalculate_cloth_program", { lot: "LOT-1", modified: "m1", excess_percentage: 4.8, additions: page.calls[1][1].additions }])
	assert.deepEqual(page.events, [["saved"], ["visible", false]])
})

test("Print saves first, then opens the saved Lot's cloth program print", async () => {
	const opened = { location: {} }
	globalThis.window = { open: () => opened }
	try {
		const page = mountDialog()
		page.dialog().onShow()
		await tick()
		page.button("Print").onClick()
		await tick()
		assert.deepEqual(page.calls.map(([method]) => method), ["get_cloth_program_preview", "recalculate_cloth_program"])
		assert.deepEqual(page.events, [["saved"]])
		assert.equal(opened.location.href, "/printview?doctype=SD+YRP+Lot&name=LOT-1&trigger_print=1&format=Essdee+Lot+Cloth+Program&no_letterhead=1")
	} finally {
		delete globalThis.window
	}
})

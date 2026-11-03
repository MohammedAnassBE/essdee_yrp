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

const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
const textOf = node => node.text + node.children.map(textOf).join("")
const livePreview = additions => ({
	...preview,
	tables: [{ ...preview.tables[0], colour_totals: { Navy: 100 + additions }, total: 100 + additions,
		fabric_groups: [{ ...preview.tables[0].fabric_groups[0], routes: [{ fabric_type: "Main Fabric", dia: "12 Dia", weights: { Navy: 100 + additions }, total: 100 + additions }], colour_totals: { Navy: 100 + additions }, total: 100 + additions, additions: { Navy: additions }, additional_total: additions }] }],
	display_totals: { required_weight: 96, extra_weight: 4, manual_additional_weight: additions, program_weight: 100 + additions },
})

function mountDialog(respond = args => (args.additions ? livePreview(JSON.parse(args.additions)[0].additional_weight) : preview)) {
	const calls = []
	const component = loadComponent(new URL("../src/departments/purchase/lot/ClothProgramBuildDialog.vue", import.meta.url).pathname, {
		"primevue/button": stub("button"), "primevue/dialog": stub("dialog"), "primevue/inputnumber": stub("inputnumber"), "primevue/message": stub("message"),
		"../../../api/frappe.js": { callMethod: async (method, args) => { calls.push([method.split(".").pop(), args]); return method.endsWith("preview") ? respond(args) : {} } },
		"../../../engine/lotClothProgram.js": program,
		"../../../utils/printUrl.js": printUrl,
		"./lotViews.js": { formatQuantity: value => String(value) },
	})
	const events = []
	const root = mountComponent(component, { visible: true, lot: "LOT-1", modified: "m1", "onUpdate:visible": value => events.push(["visible", value]), onSaved: () => events.push(["saved"]) })
	const button = label => findNodes(root, node => node.type === "button" && node.props.label === label)[0]?.props
	const dialog = () => findNodes(root, node => node.type === "dialog")[0].props
	const input = id => findNodes(root, node => node.type === "inputnumber" && (node.props["input-id"] || node.props.inputId || node.props["aria-label"]) === id)[0].props
	const addWeightTotal = () => textOf(findNodes(root, node => node.type === "tr" && node.props.class === "lot-add-weight")[0].children.at(-1))
	const footer = () => textOf(findNodes(root, node => node.props.class === "cpb-totals")[0])
	return { calls, events, button, dialog, input, addWeightTotal, footer, root }
}

async function opened(respond) {
	const page = mountDialog(respond)
	page.dialog().onShow()
	await tick()
	return page
}

test("Opening previews once and there is no Calculate button", async () => {
	const page = await opened()
	assert.equal(page.input("Add Weight Main Fabric Navy").modelValue, 5)
	assert.deepEqual(page.calls, [["get_cloth_program_preview", { lot: "LOT-1" }]])
	assert.equal(page.button("Calculate"), undefined)
	await wait(450)
	assert.equal(page.calls.length, 1)
})

test("Add Weight updates the row total at once and the preview after a debounce", async () => {
	const page = await opened()
	page.input("Add Weight Main Fabric Navy").onInput({ value: 12 })
	page.input("Add Weight Main Fabric Navy").onInput({ value: 125 })
	await tick()
	assert.equal(page.addWeightTotal(), "+125")
	assert.equal(page.calls.length, 1)
	await wait(450)
	await tick()
	assert.equal(page.calls.length, 2)
	assert.deepEqual(JSON.parse(page.calls[1][1].additions), [{ cloth_item: "Cloth", fabric_type: "Main Fabric", colour: "Navy", additional_weight: 125 }])
	assert.match(page.footer(), /Added Kg: \+125/)
	assert.match(page.footer(), /Total Knitting Program Kg: 225/)
	assert.equal(page.addWeightTotal(), "+125")
	assert.deepEqual(page.events, [])
})

test("Excess percentage changes recompute the preview", async () => {
	const page = await opened()
	page.input("cpb-excess").onInput({ value: 6 })
	await wait(450)
	await tick()
	assert.equal(page.calls.length, 2)
	assert.equal(page.calls[1][1].excess_percentage, 6)
})

test("A stale preview response never overwrites a newer one", async () => {
	const pending = []
	const page = await opened(args => {
		if (!args.additions) return preview
		const weight = JSON.parse(args.additions)[0].additional_weight
		return new Promise(resolve => pending.push(() => resolve(livePreview(weight))))
	})
	page.input("Add Weight Main Fabric Navy").onInput({ value: 10 })
	await wait(450)
	page.input("Add Weight Main Fabric Navy").onInput({ value: 20 })
	await wait(450)
	pending[1]()
	await tick()
	pending[0]()
	await tick()
	assert.match(page.footer(), /Added Kg: \+20/)
})

test("A preview error is shown and blocks Save and Print until fixed", async () => {
	const page = await opened(args => {
		if (args.additions && JSON.parse(args.additions)[0].additional_weight < -200) throw new Error("Dia below zero")
		return args.additions ? livePreview(JSON.parse(args.additions)[0].additional_weight) : preview
	})
	page.input("Add Weight Main Fabric Navy").onInput({ value: -500 })
	await wait(450)
	await tick()
	assert.match(textOf(findNodes(page.root, node => node.type === "message")[0]), /Dia below zero/)
	assert.equal(page.button("Save").disabled, true)
	assert.equal(page.button("Print").disabled, true)
	page.input("Add Weight Main Fabric Navy").onInput({ value: -5 })
	await wait(450)
	await tick()
	assert.equal(page.button("Save").disabled, false)
})

test("Save right after typing waits for the current inputs, then stores them and closes", async () => {
	const page = await opened()
	page.input("Add Weight Main Fabric Navy").onInput({ value: 30 })
	await tick()
	page.button("Save").onClick()
	await wait(50)
	await tick()
	assert.deepEqual(page.calls.map(([method]) => method), ["get_cloth_program_preview", "get_cloth_program_preview", "recalculate_cloth_program"])
	assert.deepEqual(page.calls[2], ["recalculate_cloth_program", { lot: "LOT-1", modified: "m1", excess_percentage: 4.8, additions: page.calls[2][1].additions }])
	assert.equal(JSON.parse(page.calls[2][1].additions)[0].additional_weight, 30)
	assert.deepEqual(page.events, [["saved"], ["visible", false]])
	await wait(450)
	assert.equal(page.calls.length, 3)
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

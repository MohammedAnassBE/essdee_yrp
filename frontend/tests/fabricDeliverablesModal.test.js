import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { compile } from "@vue/compiler-dom"
import { parse } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import * as Vue from "vue"
import { collectManualKnittingContract, createFabricEntries } from "../src/composables/useFabricDeliverableContext.js"

import { fabricColourError, fabricEntryError, fabricEntryLabel, fabricPlanningHint, fabricUnavailableMessage, fabricWarnings, fabricYarnTotals, hydrateFabricRows } from "../src/departments/fabric-store/fabricCalculate.js"

const source = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")
const template = parse(source).descriptor.template.content
const render = new Function("Vue", compile(template, { mode: "function" }).code)(Vue)
const SlotStub = { setup(_, { slots }) { return () => Vue.h("div", [slots.default?.(), slots.footer?.()]) } }

async function renderPanel(row, sourceProcess = {}) {
	const Root = {
		render,
		data: () => ({
			workOrder: {}, closeConfirmVisible: false, confirmClose() {}, busy: false, canSubmit: true, submitLabel: "Apply", visible: true, title: "Calculate Fabric Deliverables", largePanel: true,
			mode: "calculate_fabric", loading: false, acting: "", error: "", draft: {},
			fabricContext: { source_process: sourceProcess, warnings: [], source_process_options: [] },
			fabricRows: hydrateFabricRows({ rows: [row] }), isCloseMode: false, canApply: true, discardVisible: false,
		}),
		computed: {
			fabricUnavailable() { return fabricUnavailableMessage(this.fabricContext) },
			fabricQuantityWarnings() { return fabricWarnings(this.fabricRows) },
		},
		methods: {
			fabricColourError, fabricEntryError, fabricEntryLabel, fabricPlanningHint, fabricYarnTotals,
			discardAction() {}, submit() {}, requestVisibility() {}, refreshFabricSource() {}, apply() {}, discardAndClose() {},
			attributeText: (attrs) => Object.values(attrs || {}).join(" · "),
			number: (value) => String(value || 0), sourcePreview: () => "",
		},
	}
	const app = Vue.createSSRApp(Root)
	app.config.warnHandler = () => {}
	for (const name of ["Dialog", "Button", "Select", "InputNumber", "LinkField", "Message", "DocumentErrorDialog"]) app.component(name, SlotStub)
	return renderToString(app)
}

test("current fabric panel edits physical knitting inputs and outputs with exact route keys", async () => {
	const row = {
		fabric_row: "FABRIC-1", kind: "knitting", cloth_item: "Cloth", manual_io: true,
		reference_routed: true, entries: [],
		qty_rows: [{ key: "opaque-route:1", output_item: "Cloth", out_attrs: { Dia: "26", Colour: "Navy" }, prefill: 7, knitting_inputs: [{ key: "opaque-yarn:1", item: "Yarn", attrs: { Colour: "Navy" }, qty_per_output: 1, prefill: 7 }] }],
	}
	row.manualEntry = createFabricEntries({ rows: [row] })[0]
	row.manualEntry.manualDeliverables[0].qty = 8
	const html = await renderPanel(row)
	assert.match(html, /Enter the yarn quantities to deliver/)
	assert.match(html, /Cloth quantity expected back/)
	const contract = collectManualKnittingContract(row, row.manualEntry)
	assert.equal(contract.routes[0].qr.key, "opaque-route:1")
	assert.deepEqual(contract.routes[0].manualInputs, [{ key: "opaque-yarn:1", qty: 8 }])
})

test("unavailable predecessor stock keeps the blocking explanation", async () => {
	const html = await renderPanel({ fabric_row: "FABRIC-1", entries: [] }, { unavailable: true, label: "Knitting" })
	assert.match(html, /No predecessor stock available/)
	assert.match(html, /Submit an unallocated Knitting GRN/)
})

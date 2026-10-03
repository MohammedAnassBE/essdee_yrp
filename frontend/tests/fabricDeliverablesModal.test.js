import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { compile } from "@vue/compiler-dom"
import { parse } from "@vue/compiler-sfc"
import { renderToString } from "@vue/server-renderer"
import * as Vue from "vue"

const modalPath = fileURLToPath(new URL("../src/views/dynamic/FabricDeliverablesModal.vue", import.meta.url))
const source = fs.readFileSync(modalPath, "utf8")
const deskPath = fileURLToPath(new URL("../../essdee_yrp/public/js/work_order.js", import.meta.url))
const deskSource = fs.readFileSync(deskPath, "utf8")
const template = parse(source).descriptor.template.content
const render = new Function("Vue", compile(template, { mode: "function" }).code)(Vue)

const SlotStub = {
	setup(_, { slots }) {
		return () => Vue.h("div", slots.default?.())
	},
}

async function renderModal(sourceProcess, options = {}) {
	const rows = options.rows || [{
		fabric_row: "fabric-1",
		cloth_item: "Dyd Fabric 36's RL",
		production_detail: "Dyd Fabric 36's RL-15",
		kind: "identity",
		qty_rows: [],
	}]
	const Root = {
		render,
		data: () => ({
			visible: true,
			dialogHeader: "Calculate Fabric Deliverables — Dyeing",
			loading: false,
			applying: false,
			ctx: {
				rows,
				source_process: sourceProcess,
				source_process_options: [],
				warnings: [],
			},
			entries: options.entries || rows.map(() => ({})),
			layouts: options.layouts || [],
			sourcePickerOpen: false,
			fillError: "",
			selectedSource: null,
		}),
		methods: {
			emit() {},
			loadContext() {},
			needsColourPicker() { return false },
			isMultiColour() { return false },
			contractAttributeLabel() { return "" },
			availableOutputLabel(qr) { return `${qr.source_available} kg` },
			availabilityHeading() { return "Available output" },
			sourceReferenceLabel() { return "" },
			searchColourValues() {},
			recomputeYarn() {},
			yarnQuantity() { return 0 },
			openSourcePicker() {},
			onApply() {},
			fillQuantity() {},
		},
	}
	const app = Vue.createSSRApp(Root)
	app.config.warnHandler = () => {}
	for (const name of ["Dialog", "Button", "Select", "InputNumber", "LinkField"]) {
		app.component(name, SlotStub)
	}
	return renderToString(app)
}

test("colour cards show Colour first and one Dia heading above duplicate stock rows", async () => {
	const qtyRows = [
		{ key: "grey-26-a", section: "Grey", row_label: "26 Dia", source_available: 0.993 },
		{ key: "grey-26-b", section: "Grey", row_label: "26 Dia", source_available: 0.988 },
	]
	const items = qtyRows.map((qr, j) => ({ qr, j }))
	const html = await renderModal({ label: "Knitting", available: 10 }, {
		rows: [{
			fabric_row: "fabric-1",
			cloth_item: "Dyd Fabric 36's RL",
			production_detail: "Dyd Fabric 36's RL-15",
			kind: "dyeing",
			qty_rows: qtyRows,
		}],
		entries: [{ qtys: [0.993, 0.988] }],
		layouts: [{
			sections: [{ name: "Grey", items, diaGroups: [{ name: "26 Dia", items }] }],
			asColumns: true,
		}],
	})

	assert.match(html, /class="fc-colour-card"/)
	assert.match(html, /fc-colour-kicker[^>]*>Colour</)
	assert.match(html, /fc-colour-name[^>]*>Grey</)
	assert.match(html, /fc-dia-kicker[^>]*>Dia</)
	assert.equal((html.match(/26 Dia/g) || []).length, 1)
	assert.match(html, /Available output/)
	assert.match(html, /Quantity to receive/)
})

test("Desk popup defines the same labelled Colour and Dia hierarchy", () => {
	assert.match(deskSource, /yrp-fabric-colour-kicker/)
	assert.match(deskSource, /yrp-fabric-colour-name/)
	assert.match(deskSource, /yrp-fabric-dia-kicker/)
	assert.match(deskSource, /yrp-fabric-dia-name/)
	assert.match(deskSource, /yrp-fabric-allocation-row \.control-label \{ display: none; \}/)
})

test("available predecessor stock does not render verbose GRN source details", async () => {
	const html = await renderModal({
		label: "Knitting",
		available: 10,
		sources: [{
			key: "source-1",
			grn: "YRP-GRN-2026-00048",
			supplier: "S-0002",
			warehouse: "YRP Test Factory Warehouse",
			item_variant: "Dyd Fabric 36's RL-26 Dia-Greige",
			available: 0.993,
			received: 0.993,
		}],
	})

	assert.doesNotMatch(html, /fc-source-note/)
	assert.doesNotMatch(html, /Filled from Knitting GRNs/)
	assert.doesNotMatch(html, /YRP-GRN-2026-00048/)
})

test("unavailable predecessor stock keeps the blocking warning", async () => {
	const html = await renderModal({
		unavailable: true,
		label: "Knitting",
	})

	assert.match(html, /No predecessor stock available/)
	assert.match(html, /Submit the predecessor GRN/)
})

test("duplicate physical outputs identify their exact GRN source and cap", () => {
	assert.match(template, /sourceReferenceLabel\(row, it\.qr\)/)
	assert.match(source, /source_stock_available/)
	assert.match(source, /source_stock_per_output/)
	assert.match(source, /source_grn/)
	assert.doesNotMatch(source, /qr\.available/)
	assert.match(deskSource, /source_stock_available/)
	assert.match(deskSource, /source_stock_per_output/)
	assert.match(deskSource, /source_grn/)
})

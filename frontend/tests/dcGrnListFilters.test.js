import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = name => (props) => Vue.h(name, props)
const yrpFile = path => readFileSync(new URL(`../../../yrp/yrp/${path}`, import.meta.url), "utf8")
const doctypeFields = folder => JSON.parse(yrpFile(`yrp/doctype/${folder}/${folder}.json`)).fields
const lotField = { fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot" }

function grnLotOverride() {
	const overrides = yrpFile("stock/dimensions.py").split("OPERATIONAL_DIMENSION_FIELD_OVERRIDES = {")[1].split("\n}")[0]
	const grn = overrides.split('"YRP Goods Received Note": {')[1].split("}")[0]
	return { in_standard_filter: /"in_standard_filter": 1/.test(grn) ? 1 : 0 }
}

async function quickFilterFields(doctype, fields) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const api = {
		getMeta: async () => [{ name: doctype, fields }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async () => [],
		getCount: async () => 0,
	}
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/fabric-store" }) },
		"../../api/frappe.js": api,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./FormField.vue", "./UserListviewColumns.vue"]) modules[path] = stub(path)
	modules["./ListviewFilters.vue"] = stub("advanced-filters")
	modules["./ListviewQuickFilters.vue"] = stub("quick-filters")
	try {
		const component = loadComponent("frontend/src/components/common/ListView.vue", modules)
		const root = mountComponent(component, Vue.reactive({ doctype, navigationEnabled: false }))
		await tick(); await tick()
		const quick = findNodes(root, node => node.type === "quick-filters")[0]
		return quick?.props.fields || []
	} finally {
		globalThis.window = previousWindow
	}
}

test("Delivery Challan list offers a Transfer Complete quick filter", async () => {
	const fields = await quickFilterFields("YRP Delivery Challan", [...doctypeFields("yrp_delivery_challan"), lotField])
	const transfer = fields.find(field => field.fieldname === "transfer_complete")
	assert.equal(transfer?.fieldtype, "Check")
	assert.equal(transfer.label, "Transfer Complete")
	assert.ok(!fields.some(field => field.fieldname === "is_internal_unit"))
})

test("GRN list offers Transfer Complete and Lot quick filters", async () => {
	const fields = await quickFilterFields("YRP Goods Received Note", [...doctypeFields("yrp_goods_received_note"), { ...lotField, ...grnLotOverride() }])
	assert.equal(fields.find(field => field.fieldname === "transfer_complete")?.fieldtype, "Check")
	const lot = fields.find(field => field.fieldname === "lot")
	assert.equal(lot?.fieldtype, "Link")
	assert.equal(lot.options, "SD YRP Lot")
	assert.ok(!fields.some(field => field.fieldname === "is_internal_unit"))
})

test("every department DC and GRN card uses the meta-driven list without hiding these filters", () => {
	const source = readFileSync(new URL("../src/departments/cut-panel-store/CutPanelDocuments.vue", import.meta.url), "utf8")
	assert.match(source, /<ListView :doctype="capability.doctype"/)
	assert.doesNotMatch(source, /excluded-filter-fields/)
})

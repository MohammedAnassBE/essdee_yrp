import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { createRequire } from "node:module"
import test from "node:test"
import { Vue, loadComponent, mountComponent, findNodes } from "../../scripts/helpers/vue_renderer.mjs"
import { getSewingEntries } from "../src/api/sewing.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import { dispatchBySize, packingMode, packingRatio, colourDetails } from "../src/departments/finishing/finishingEntries.js"
import { formatQuantity } from "../src/departments/finishing/finishingViews.js"

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
function script(path, bindings, expose) {
	const source = read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*?from ["'][^"']+["'];?$/gm, "").replace(/^import ["'][^"']+["'];?$/gm, "")
	const { computed, ref, reactive, watch, toRefs, nextTick } = Vue
	const injections = { computed, ref, reactive, watch, toRefs, nextTick, onMounted: () => {}, onUnmounted: () => {}, onBeforeUnmount: () => {}, defineExpose: () => {}, ...bindings }
	return new Function(...Object.keys(injections), `${source}\nreturn { ${expose} }`)(...Object.values(injections))
}
function sewingContext() {
	const supplier = Vue.ref("UNIT-1"), requestGeneration = Vue.ref(0)
	return { supplier, requestGeneration, beginRequest: () => ++requestGeneration.value, isCurrent: value => value === requestGeneration.value }
}

test("F-D09: entries append bounded pages, preserve URL Lot and reset after filter changes", async () => {
	const state = Vue.reactive({ filters: { lot: "LOT-URL", workStation: "", inputType: "" }, busy: false })
	const requests = [], mounted = [], context = sewingContext()
	const page = script("departments/sewing/plan/SewingEntries.vue", {
		defineProps: () => ({ state, mutate() {} }), useSewingContext: () => context,
		onMounted: callback => mounted.push(callback),
		getSewingEntries: async (supplier, filters, start) => {
			requests.push({ supplier, lot: filters.lot, start })
			return { rows: { [`ENTRY-${start}`]: { entry_date: "2026-10-20" } }, has_more: start === 0, next_start: start + 100 }
		},
	}, "load, records, hasMore, nextStart")
	mounted.forEach(callback => callback())
	await tick()
	assert.deepEqual(requests[0], { supplier: "UNIT-1", lot: "LOT-URL", start: 0 })
	await page.load(true)
	assert.deepEqual(Object.keys(page.records.value), ["ENTRY-0", "ENTRY-100"])
	assert.equal(page.hasMore.value, false)
	state.filters.lot = "LOT-OTHER"
	await tick()
	assert.equal(requests.at(-1).start, 0)
	assert.deepEqual(Object.keys(page.records.value), ["ENTRY-0"])
	assert.match(read("departments/sewing/plan/SewingEntries.vue"), /label="Load more"/)
})

test("F-D09: a stale next page cannot append to a changed filter", async () => {
	const context = sewingContext(), state = Vue.reactive({ filters: { lot: "A" } })
	let resolveOld
	const page = script("departments/sewing/plan/SewingEntries.vue", {
		defineProps: () => ({ state }), useSewingContext: () => context,
		getSewingEntries: async (_supplier, filters) => filters.lot === "A" ? await new Promise(resolve => { resolveOld = resolve }) : { rows: { B: {} }, next_start: 1 },
	}, "load, records")
	const old = page.load(true)
	state.filters.lot = "B"
	await page.load()
	resolveOld({ rows: { A: {} }, next_start: 100, has_more: true })
	await old
	assert.deepEqual(Object.keys(page.records.value), ["B"])
})

test("F-D19: zero-first entry, per-colour fill/clear and allowance limit including Remaining zero", async () => {
	const state = Vue.reactive({ response: { data: { LOT: { PLAN: { details: { lot: "LOT" }, colours: {
		Red: { values: { S: { order_detail: "RED-S", order_qty: 100, input_qty: 103, input_qty_remaining: 0 } } },
		Blue: { values: { S: { order_detail: "BLUE-S", order_qty: 0, input_qty_remaining: 0 } } },
		Green: { values: { S: { order_detail: "GREEN-S", order_qty: 50, input_qty_remaining: 30 } } },
	} } } }, diff: { input_qty: "order_qty" }, allowances: { input_qty: 5 } }, entryDrafts: {}, inspectionDrafts: {} })
	const filters = Vue.reactive({ lot: "LOT", plan: "PLAN", inputType: "Input Qty" })
	const page = script("departments/sewing/plan/SewingDataEntry.vue", {
		defineProps: () => ({ state, filters, actions: { entry: { can_create: true } } }), useSewingContext: sewingContext,
	}, "initializeEntry, entryQuantities, entryColours, fillColourQuantities")
	page.initializeEntry()
	assert.deepEqual({ ...page.entryQuantities.value }, { "RED-S": 0, "BLUE-S": 0, "GREEN-S": 0 })
	assert.equal(page.entryColours.value.Red.values.S.allowed_remaining, 2)
	assert.equal(page.entryColours.value.Blue.values.S.allowed_remaining, 0)
	page.fillColourQuantities("Green", true)
	assert.equal(page.entryQuantities.value["GREEN-S"], 30)
	assert.equal(page.entryQuantities.value["RED-S"], 0)
	page.fillColourQuantities("Green", false)
	assert.equal(page.entryQuantities.value["GREEN-S"], 0)
	filters.inputType = "Output Qty"
	await tick()
	assert.ok(Object.values(page.entryQuantities.value).every(value => value === 0))
	assert.match(read("departments/sewing/plan/SewingDataEntry.vue"), /Fill remaining/)
})

test("Sewing data entry Lot filter is a Sewing Unit scoped Link field", async () => {
	const source = read("departments/sewing/plan/SewingDataEntry.vue")
	assert.match(source, /<LinkField v-model="filters.lot" doctype="SD YRP Lot"[^>]*show-clear[^>]*:search-handler="text => search\('SD YRP Lot', text\)"/)
	assert.doesNotMatch(source, /input-id="sewing-lot"/)
	const state = Vue.reactive({ response: { data: { "LOT-A": { "PLAN-A": { details: { lot: "LOT-A" }, colours: {} } }, "LOT-B": { "PLAN-B": { details: { lot: "LOT-B" }, colours: {} } } } }, busy: false, entryDrafts: {}, inspectionDrafts: {} })
	const filters = Vue.reactive({ lot: "", plan: "PLAN-B", inputType: "", inspectionType: "pre_final" })
	const lotSearches = []
	const page = script("departments/sewing/plan/SewingDataEntry.vue", {
		defineProps: () => ({ state, filters }), useSewingContext: sewingContext,
		getSewingSupplierLots: async (supplier, text) => { lotSearches.push({ supplier, text }); return [{ name: "LOT-A", label: "LOT-A" }] },
		searchLink: async () => assert.fail("Lot must use the Sewing Unit lot query"),
	}, "search, plans")
	assert.deepEqual(await page.search("SD YRP Lot", "lot"), [{ name: "LOT-A", label: "LOT-A" }])
	assert.deepEqual(lotSearches, [{ supplier: "UNIT-1", text: "lot" }])
	filters.lot = "LOT-A"
	await tick()
	assert.deepEqual(page.plans.value.map(plan => plan.name), ["PLAN-A"])
	assert.equal(filters.plan, "")
	filters.lot = ""
	await tick()
	assert.deepEqual(page.plans.value.map(plan => plan.name), ["PLAN-A", "PLAN-B"])
})

test("F-C04/C05: Cut Panel document routes, filtered lists, back navigation and GRN movement link", () => {
	for (const [doctype, slug, param] of [["YRP Delivery Challan", "delivery-challans", "deliveryChallanId"], ["YRP Goods Received Note", "goods-received-notes", "goodsReceivedNoteId"]]) {
		assert.equal(webDocumentPath(doctype, "DOC/1", "/web/cut-panel-store/movements"), `/web/cut-panel-store/${slug}/DOC%2F1`)
		assert.ok(read("router/index.js").includes(`path: "/cut-panel-store/${slug}/:${param}"`))
		assert.ok(read("router/index.js").includes(`backTo: "/cut-panel-store/${slug}"`))
	}
	assert.match(read("departments/cut-panel-store/CutPanelDocuments.vue"), /\[\["cut_panel_movement", "is", "set"\]\]/)
	assert.match(read("departments/cut-panel-store/CutPanelMovementDialog.vue"), /router.push\(webDocumentRoute\(document.doctype, document.name, "\/web\/cut-panel-store"\)\)/)
	assert.match(read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue"), /\["Cut Panel Movement", .*"SD YRP Cut Panel Movement"\]/)
	assert.match(read("departments/fabric-store/DeliveryChallanWorkspace.vue"), /\["Cut Panel Movement", .*"SD YRP Cut Panel Movement"\]/)
})

test("F-F14: dispatch inputs identify the Finishing Plan and row", () => {
	const component = loadComponent(new URL("../src/departments/finishing/components/FinishingDispatchEntry.vue", import.meta.url).pathname, {
		"../finishingEntries.js": { dispatchBySize, packingMode, packingRatio, colourDetails }, "../finishingViews.js": { formatQuantity },
	})
	for (const plan of ["FP-1", "FP-2"]) {
		const root = mountComponent(component, { label: plan, sizes: ["S"], packed: {}, config: {} })
		assert.equal(findNodes(root, node => node.type === "input")[0].props["aria-label"], `${plan} S dispatch boxes`)
	}
})

test("F-F14: Dispatch Stock prefills source through the shared Supplier/Warehouse helper", async () => {
	const calls = []
	const page = script("departments/finishing/FinishingDispatch.vue", {
		defineProps: () => ({ basePath: "/finishing", viewRouteName: "finishing-dispatch" }), useRoute: () => ({ params: {} }), useRouter: () => ({}), useToast: () => ({ add() {} }), useActionConfirmation: () => () => {},
		watch: () => {}, setDispatchSupplier: async (stock, side, supplier) => { calls.push([side, supplier]); stock.from_supplier = supplier; stock.from_warehouse = "WH-1" },
	}, "workspace, openDispatch, dispatchOpen, stock")
	page.workspace.value = { dispatch_defaults: { from_supplier: "SUP-1" } }
	page.openDispatch()
	await tick()
	assert.deepEqual(calls, [["from", "SUP-1"]])
	assert.equal(page.stock.from_warehouse, "WH-1")
	assert.equal(page.dispatchOpen.value, true)
	for (const file of ["FinishingDispatch.vue", "FinishingEntryDialog.vue"]) {
		assert.match(read(`departments/finishing/${file}`), /aria-label="Goods Value"/)
		assert.match(read(`departments/finishing/${file}`), /aria-label="Vehicle No"/)
	}
})

test("F-F14: Dispatch Box success toast names and links the created Stock Entry", async () => {
	const notices = []
	const page = script("departments/finishing/FinishingPlan.vue", {
		defineProps: () => ({}), useRoute: () => ({ params: { finishingPlanId: "FP-1" } }), useRouter: () => ({}), useToast: () => ({ add: message => notices.push(message) }), useActionConfirmation: () => () => {}, watch: () => {},
		executeFinishingPlanCommand: async () => ({ record: { name: "FP-1" }, result: { doctype: "YRP Stock Entry", name: "STE-1" } }),
	}, "submitEntry, entryOpen")
	page.entryOpen.value = true
	await page.submitEntry("dispatch_box", {})
	assert.equal(page.entryOpen.value, false)
	assert.equal(notices[0].group, "finishing-stock-entry")
	assert.deepEqual(notices[0].document, { doctype: "YRP Stock Entry", name: "STE-1" })
	assert.match(read("departments/finishing/FinishingPlan.vue"), /DocumentLink :doctype="message.document.doctype" :name="message.document.name"/)
})

test("F-F16: Dispatch Report and Packing DPR size headers explicitly say Pcs", () => {
	for (const file of ["FinishingDispatchReport.vue", "FinishingPackingDpr.vue"]) assert.match(read(`departments/finishing/reports/${file}`), /\{\{ size \}\} \(Pcs\)/)
})

test("F-B31: Save retains the saved CPM, exposes Submit, and defers parent refresh until Close", async () => {
	const props = Vue.reactive({ visible: true, cuttingPlan: "CP-1", movement: "" }), events = []
	const saved = { name: "CPM-1", docstatus: 0, modified: "now", movement_data: {}, permissions: { can_write: true, can_submit: true } }
	const page = script("departments/cutting/CpmMovementDialog.vue", {
		defineProps: () => props, defineEmits: () => (...args) => events.push(args), useActionConfirmation: () => () => {}, saveMovement: async () => saved,
	}, "save, record, canSubmit, hasGenerated")
	await page.save(false)
	assert.equal(page.record.value.name, "CPM-1")
	assert.equal(page.canSubmit.value, true)
	assert.equal(page.hasGenerated.value, true)
	assert.deepEqual(events, [])
	props.visible = false
	await tick()
	assert.equal(events[0][0], "changed")
	assert.equal(events[0][1].name, "CPM-1")
})

test("F-B31: Submit after Save uses the saved name and modified token", async () => {
	const requests = [], events = []
	const page = script("departments/cutting/CpmMovementDialog.vue", {
		defineProps: () => ({ visible: true, cuttingPlan: "CP-1", movement: "" }), defineEmits: () => (...args) => events.push(args), useActionConfirmation: () => () => {},
		saveMovement: async (...args) => { requests.push(args); return { name: "CPM-1", modified: "modified-1", docstatus: args[3] ? 1 : 0, movement_data: {}, permissions: { can_write: true, can_submit: true } } },
	}, "save, movementEditor")
	await page.save(false)
	page.movementEditor.value = { hasSelection: true }
	await page.save(true)
	assert.equal(requests[1][2], "CPM-1")
	assert.equal(requests[1][3], true)
	assert.equal(requests[1][4], "modified-1")
	assert.ok(events.some(([event, value]) => event === "update:visible" && value === false))
})

test("F-B31: an existing draft blocks Generate before a bundle request", async () => {
	let generated = false
	const page = script("departments/cutting/CpmMovementDialog.vue", {
		defineProps: () => ({ visible: true, cuttingPlan: "CP-1" }), defineEmits: () => () => {}, useActionConfirmation: () => () => {}, generateMovementBundles: async () => { generated = true },
	}, "editor, generateBundles, error, canEdit")
	page.editor.create_blocker = "Submit or delete draft Cut Panel Movement CPM-1 for SUP-1 / LOT-1 first."
	page.editor.permissions = { can_create: true }
	await page.generateBundles()
	assert.equal(generated, false)
	assert.equal(page.error.value, page.editor.create_blocker)
	assert.equal(page.canEdit.value, false)
})


test("F-D09: the API forwards bounded offsets without losing Lot and stage filters", async () => {
	const oldWindow = globalThis.window, oldFetch = globalThis.fetch
	const requests = []
	globalThis.window = { csrf_token: "test" }
	globalThis.fetch = async (_url, options) => { requests.push(JSON.parse(options.body)); return { ok: true, status: 200, json: async () => ({ message: { rows: {}, has_more: false } }) } }
	try {
		await getSewingEntries("UNIT-1", { lot: "LOT-URL", workStation: "LINE-1", inputType: "Input Qty" })
		await getSewingEntries("UNIT-1", { lot: "LOT-URL" }, 100)
		assert.deepEqual(requests[0], { supplier: "UNIT-1", lot_name: "LOT-URL", work_station: "LINE-1", input_type: "Input Qty", start: 0, page_length: 100 })
		assert.equal(requests[1].start, 100)
	} finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("the changed operator workflow components compile", () => {
	const require = createRequire(new URL("../package.json", import.meta.url))
	const { parse, compileScript } = require("@vue/compiler-sfc")
	for (const path of [
		"departments/sewing/plan/SewingEntries.vue", "departments/sewing/plan/SewingDataEntry.vue", "departments/sewing/components/SewingQuantityMatrix.vue",
		"departments/CutPanelStore.vue", "departments/CutPanelStoreSection.vue", "departments/cut-panel-store/CutPanelDocuments.vue", "departments/cut-panel-store/CutPanelMovementDialog.vue",
		"departments/fabric-store/GoodsReceivedNoteWorkspace.vue", "departments/cutting/CpmMovementDialog.vue",
		"departments/finishing/FinishingPlan.vue", "departments/finishing/FinishingDispatch.vue", "departments/finishing/FinishingEntryDialog.vue", "departments/finishing/components/FinishingDispatchEntry.vue",
		"departments/finishing/reports/FinishingDispatchReport.vue", "departments/finishing/reports/FinishingPackingDpr.vue",
	]) {
		const { descriptor, errors } = parse(read(path), { filename: path })
		assert.deepEqual(errors, [], path)
		assert.doesNotThrow(() => compileScript(descriptor, { id: path, inlineTemplate: true }), path)
	}
})

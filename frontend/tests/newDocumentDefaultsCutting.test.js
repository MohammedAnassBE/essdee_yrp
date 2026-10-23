import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"
import * as defaults from "../src/utils/newDocumentDefaults.js"

const LIST = "/cutting/plans?from=list"
const read = path => readFileSync(resolve(`frontend/src/${path}`), "utf8")
const script = path => read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
function setup(path, bindings, names) {
	const values = {
		...Vue, watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {}, onBeforeRouteLeave: () => {},
		defineProps: () => ({}), defineEmits: () => () => {}, useDocumentShortcuts: () => {}, useRouter: () => ({ push() {}, replace() {} }),
		takeNewDocumentDefaults: defaults.takeNewDocumentDefaults, withNewDocumentDefaults: defaults.withNewDocumentDefaults, ...bindings,
	}
	return new Function(...Object.keys(values), `${script(path)}\nreturn { ${names} }`)(...Object.values(values))
}
function stage(doctype, values) {
	globalThis.window = { history: { state: { back: LIST, current: "/new" } }, addEventListener() {}, removeEventListener() {} }
	defaults.stageNewDocumentDefaults(doctype, values, LIST)
}

test("new Cutting Plan loads the filtered Lot and keeps server-computed values", async () => {
	stage("SD YRP Cutting Plan", { lot: "LOT-1", cutting_location: "Unit 2", maximum_no_of_plys: 40, item: "ITEM-X" })
	const calls = []
	const plan = setup("departments/cutting/plan/CuttingPlanEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null, initialSource: {}, duplicateFrom: "" }),
		getCuttingPlanEditor: async (...args) => { calls.push(args); return { record: { lot: "LOT-1", item: "ITEM-1", maximum_no_of_plys: 60 }, matrix: { groups: [] } } },
	}, "load, form")
	await plan.load()
	assert.deepEqual(calls, [["", "LOT-1", ""]])
	assert.equal(plan.form.cutting_location, "Unit 2")
	assert.equal(plan.form.maximum_no_of_plys, 60)
	assert.equal(plan.form.item, "ITEM-1")
})

test("duplicated Cutting Plan clears staged defaults without applying them", async () => {
	stage("SD YRP Cutting Plan", { cutting_location: "Unit 2" })
	const plan = setup("departments/cutting/plan/CuttingPlanEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null, initialSource: {}, duplicateFrom: "CP-1" }),
		getCuttingPlanEditor: async () => ({ record: { lot: "LOT-1" }, matrix: { groups: [] } }),
	}, "load, form")
	await plan.load()
	assert.equal(plan.form.cutting_location, "")
	assert.deepEqual(defaults.takeNewDocumentDefaults("SD YRP Cutting Plan"), {})
})

test("new Cutting Order loads the filtered Cutting Order Detail", async () => {
	stage("SD YRP Cutting Order", { cutting_order_detail: "COD-1", cutting_location: "Unit 1", maximum_no_of_plys: 30 })
	const calls = []
	const order = setup("departments/cutting/order/CuttingOrderEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null, duplicateFrom: "" }),
		getCuttingOrderEditor: async (...args) => { calls.push(args); return { record: { maximum_no_of_plys: 50 }, detail: { name: "COD-1", item: "ITEM-1" }, matrix: { groups: [] } } },
		getCuttingOrderDetail: async () => ({ permissions: {} }),
	}, "load, form")
	await order.load()
	assert.deepEqual(calls, [["", "COD-1", ""]])
	assert.equal(order.form.cutting_order_detail, "COD-1")
	assert.equal(order.form.cutting_location, "Unit 1")
	assert.equal(order.form.maximum_no_of_plys, 50)
	assert.equal(order.form.item, "ITEM-1")
})

test("new Bulk LaySheets and LaySheet Planner take the list filters", async () => {
	stage("SD YRP Cutting Bulk Lay Sheets", { main_lot: "LOT-1", cutter: "EMP-1", posting_date: "2026-10-01" })
	const bulk = setup("departments/cutting/bulk/BulkSetupEditor.vue", {
		defineProps: () => ({ name: "", initialPayload: null }),
		getBulkLaySheetsEditor: async () => ({ record: { posting_date: "2026-10-23" } }),
	}, "load, form")
	await bulk.load()
	assert.equal(bulk.form.main_lot, "LOT-1")
	assert.equal(bulk.form.cutter, "EMP-1")
	assert.equal(bulk.form.posting_date, "2026-10-23")

	stage("SD YRP Cutting Laysheet Planner", { lot: "LOT-2", tubular: 1, tolerance_pct: 5 })
	const planner = setup("departments/CuttingLaySheetPlannerEditorPage.vue", {
		getLaySheetPlannerEditor: async () => ({ record: { tolerance_pct: 3, tubular: 0 }, actions: {} }),
	}, "load, payload")
	await planner.load()
	assert.equal(planner.payload.value.record.lot, "LOT-2")
	assert.equal(planner.payload.value.record.tubular, 1)
	assert.equal(planner.payload.value.record.tolerance_pct, 3)
})

test("new Cut Bundle Edit and Cut Panel Movement dialogs take the list filters", async () => {
	stage("SD YRP Cut Bundle Edit", { lot: "LOT-1", warehouse: "WH-1" })
	const previews = []
	const bundle = setup("departments/cut-panel-store/CutBundleEditDialog.vue", {
		defineProps: () => ({ visible: true, documentName: "" }),
		getCutBundleEditor: async () => ({ permissions: { can_create: true }, defaults: { posting_date: "2026-10-23" }, record: null }),
		previewCutBundleSource: async (...args) => { previews.push(args); return { choices: { colours: ["Red"] } } },
	}, "load, form")
	await bundle.load()
	assert.equal(bundle.form.lot, "LOT-1")
	assert.equal(bundle.form.warehouse, "WH-1")
	assert.equal(bundle.form.posting_date, "2026-10-23")
	assert.equal(previews[0]?.[0], "LOT-1")

	stage("SD YRP Cut Panel Movement", { lot: "LOT-3", from_warehouse: "WH-2", posting_date: "2026-01-01" })
	const movement = setup("departments/cut-panel-store/CutPanelMovementDialog.vue", {
		defineProps: () => ({ visible: true, movement: "" }),
		getCutPanelMovementEditor: async () => ({ permissions: { can_create: true }, defaults: { posting_date: "2026-10-23" } }),
	}, "load, form")
	await movement.load()
	assert.equal(movement.form.lot, "LOT-3")
	assert.equal(movement.form.from_warehouse, "WH-2")
	assert.equal(movement.form.posting_date, "2026-10-23")
})

test("new Box and Excel Sticker Print dialogs take the list filters", async () => {
	stage("SD YRP Box Sticker Print", { lot: "LOT-1", fg_item: "FG-1", print_format: "ZPL-1" })
	const sources = []
	const box = setup("departments/cut-panel-store/BoxStickerPrintDialog.vue", {
		defineProps: () => ({ visible: true, documentName: "" }),
		getBoxStickerEditor: async () => ({ permissions: { can_create: true }, defaults: { print_format: "ZPL-DEFAULT" }, record: null }),
		previewBoxStickerSource: async (...args) => { sources.push(args); return { rows: [{ size: "M", quantity: 4 }] } },
	}, "load, form, rows")
	await box.load()
	assert.equal(box.form.lot, "LOT-1")
	assert.equal(box.form.fg_item, "FG-1")
	assert.equal(box.form.print_format, "ZPL-DEFAULT")
	assert.deepEqual(sources[0]?.slice(0, 2), ["LOT-1", "FG-1"])

	stage("YRP Excel Sticker Print", { print_format: "ZPL-2" })
	const excel = setup("departments/cut-panel-store/ExcelStickerPrintDialog.vue", {
		defineProps: () => ({ visible: true, documentName: "" }),
		getExcelStickerEditor: async () => ({ permissions: { can_create: true }, defaults: { temporary_name: "tmp-1" }, record: null }),
	}, "load, form")
	await excel.load()
	assert.equal(excel.form.print_format, "ZPL-2")
	assert.equal(excel.form.temporary_name, "tmp-1")
})

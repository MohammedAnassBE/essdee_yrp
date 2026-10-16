import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8")
const functionSource = (source, name) => {
	const match = source.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))
	assert.ok(match, `Missing ${name}`)
	return match[0]
}

const list = read("frontend/src/components/common/ListView.vue")
for (const [file, statusField, activeLabel] of [
	["CuttingOrders.vue", "co_status", "Submitted"],
	["CuttingPlans.vue", "cp_status", "Planned"],
]) {
	const source = read(`frontend/src/departments/${file}`)
	const options = JSON.parse(source.match(/const statusOptions = (\[[^\n]+\])/)[1])
	assert.ok(options.includes("Cancelled"))
	assert.ok(source.includes(`status-field="${statusField}"`))
	const rows = [activeLabel, "Cutting In Progress", "Cancelled", "Draft"].map((status) => ({ [statusField]: status }))
	const filtered = (filters) => rows.filter((row) => filters.every(([field, operator, value]) => operator === "=" && row[field] === value))
	const context = vm.createContext({
		effectiveStatusField: { value: statusField }, effectiveStatusOptions: { value: options },
		activeStatus: { value: "Cancelled" }, standardFilterFields: { value: [] },
		advancedFilters: { value: [] }, appliedSearch: { value: "" },
		statusCounts: { value: {} }, loadSequence: 1, total: { value: rows.length },
		props: { doctype: "Cutting" }, baseFilters: () => [], quickFilterTuples: () => [],
		listStatusFilters: (await import("../frontend/src/components/common/listStatusFilters.js")).listStatusFilters,
		hasFilterValue: (value) => Boolean(value), getCount: async (_doctype, filters) => filtered(filters).length,
	})
	vm.runInContext(`${functionSource(list, "allFilters")}\n${functionSource(list, "loadStatusCounts")}`, context)
	await context.loadStatusCounts()
	assert.equal(context.statusCounts.value.Cancelled, 1)
	assert.equal(context.statusCounts.value[activeLabel], 1)
	assert.equal(context.statusCounts.value["Cutting In Progress"], 1)
	assert.equal(context.statusCounts.value.__all__, 4)
	assert.equal(filtered(context.allFilters())[0][statusField], "Cancelled")
	context.activeStatus.value = activeLabel
	assert.equal(filtered(context.allFilters()).some((row) => row[statusField] === "Cancelled"), false)
}

const setup = read("frontend/src/departments/cutting/bulk/BulkSetupEditor.vue")
const requests = []
const events = []
const context = vm.createContext({
	form: {
		main_lot: "MAIN", from_location: "CUTTING", posting_date: "2026-10-15", cutter: "NEW-CUTTER", cutting_spreader: "SPREADER",
		lot_details: [
			{ name: "ROW-1", _row_key: "ROW-1", lot: "SPLIT", cutting_plan: "PLAN", cutting_marker: "MARKER", work_order: "WORK-ORDER", cutting_laysheet: "LAY", lot_transfer: "TRANSFER", delivery_challan: "DELIVERY", idx: 1, status: "Setup" },
			{ _row_key: "new-1", lot: "NEW-SPLIT", cutting_plan: "NEW-PLAN", cutting_marker: "NEW-MARKER" },
		],
	},
	saving: { value: false }, actionError: { value: "" }, modified: { value: "token" }, props: { name: "BULK" },
	saveBulkLaySheets: async (values, options) => { requests.push({ values: JSON.parse(JSON.stringify(values)), options }); return { saved: true } },
	emit: (...args) => events.push(args),
})
vm.runInContext(functionSource(setup, "saveSetup"), context)
await context.saveSetup()
assert.equal(context.actionError.value, "")
assert.equal(context.saving.value, false)
assert.equal(requests[0].values.cutter, "NEW-CUTTER")
assert.deepEqual(requests[0].values.lot_details, [
	{ name: "ROW-1", lot: "SPLIT", cutting_plan: "PLAN", cutting_marker: "MARKER" },
	{ lot: "NEW-SPLIT", cutting_plan: "NEW-PLAN", cutting_marker: "NEW-MARKER" },
])
assert.equal(requests[0].options.expectedModified, "token")
assert.equal(events[0][0], "saved")

const detail = read("frontend/src/departments/cutting/order/CuttingOrderDetailDialog.vue")
const detailRequests = []
const detailEvents = []
const detailContext = vm.createContext({
	form: { name: "DETAIL", modified: "detail-token", item: "STYLE", is_set_item: 1, set_item_attribute: "Part", major_attribute_value: "Top", major_panel_value: "Front" },
	attributes: { value: [{ attribute: "Panel", valuesText: "Front, Back" }] },
	colours: { value: [{ attribute_value: "Navy" }, { attribute_value: "Red" }] },
	panels: { value: [{ stiching_attribute_value: "Front" }] },
	clothDetails: { value: [{ name1: "Main", diaText: "30, 32" }] },
	setCombination: { attributes: ["Top"], values: [{ major_attribute: "Navy", val: { Top: "Blue" } }] },
	stitchingCombination: { attributes: ["Front", "Back"], values: [{ major_attribute: "Navy", val: { Front: "Navy", Back: "Blue" } }] },
	saving: { value: false }, error: { value: "" }, actionError: { value: "" },
	saveCuttingOrderDetail: async (values, options) => {
		const request = JSON.parse(JSON.stringify({ values, options }))
		detailRequests.push(request)
		return request
	},
	applyPayload: () => {}, emit: (...args) => detailEvents.push(args),
})
vm.runInContext(`${functionSource(detail, "payloadValues")}\n${detail.match(/^function splitValues.*$/m)[0]}\n${functionSource(detail, "save")}`, detailContext)
// Execute each actual template handler, including the explicit boolean argument.
for (const [label, regenerate] of [["Save Detail", false], ["Generate from Setup", true]]) {
	const handler = detail.match(new RegExp(`label="${label}"[^>]*@click="([^"]+)"`))?.[1]
	assert.ok(handler, `Missing ${label} handler`)
	await vm.runInContext(handler, detailContext)
	const request = detailRequests.at(-1)
	assert.equal(request.values.regenerate_combinations, regenerate)
	assert.deepEqual(request.values.stiching_combination, JSON.parse(JSON.stringify(detailContext.stitchingCombination)))
	assert.deepEqual(request.values.set_item_combination, JSON.parse(JSON.stringify(detailContext.setCombination)))
	assert.deepEqual(request.values.colours, [{ attribute_value: "Navy" }, { attribute_value: "Red" }])
	assert.deepEqual(request.values.panels, [{ stiching_attribute_value: "Front" }])
	assert.deepEqual(request.options, { name: "DETAIL", expectedModified: "detail-token" })
	assert.equal(detailContext.actionError.value, "")
	assert.equal(detailContext.saving.value, false)
	assert.equal(detailEvents.at(-1)[0], "saved")
}
Object.assign(detailContext.setCombination, { attributes: [], values: [] })
Object.assign(detailContext.stitchingCombination, { attributes: [], values: [] })
await vm.runInContext(detail.match(/label="Save Detail"[^>]*@click="([^"]+)"/)[1], detailContext)
assert.deepEqual(detailRequests.at(-1).values.stiching_combination, { attributes: [], values: [] })
assert.deepEqual(detailRequests.at(-1).values.set_item_combination, { attributes: [], values: [] })
assert.equal(detailRequests.at(-1).values.regenerate_combinations, false)
console.log("Cutting P1 regression tests passed")

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

import { listStatusFilters } from "../frontend/src/components/common/listStatusFilters.js"
import { productionOrderItemFilters, productionOrderStatusOptions } from "../frontend/src/departments/sales/productionOrderOptions.js"
import { createListNavigationState, navigationStorageKey, readNavigationState, writeNavigationState } from "../frontend/src/utils/listNavigation.js"

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8")
const listSource = read("frontend/src/components/common/ListView.vue")
const copy = (value) => JSON.parse(JSON.stringify(value))
const rows = [[0, "Draft", 1], [0, null, 4], [0, "PPO Request", 2], [1, "Closed", 52], [1, "Not Processed", 7], [1, "Open", 264], [2, null, 29], [2, "Open", 3]]
	.flatMap(([docstatus, status, count], group) => Array.from({ length: count }, (_, index) => ({ name: `PPO-${group}-${index}`, docstatus, status })))

function matches(row, filters) {
	return filters.every(([fieldname, operator, value]) => {
		const actual = row[fieldname] ?? ""
		if (operator === "in") return value.includes(actual)
		if (operator === "like") return String(actual).includes(value.replaceAll("%", ""))
		return String(actual) === String(value)
	})
}

function listHarness({ options = productionOrderStatusOptions, fieldname = "status", standardStatus = false } = {}) {
	const context = vm.createContext({
		listStatusFilters,
		effectiveStatusField: { value: fieldname },
		effectiveStatusOptions: { value: options },
		activeStatus: { value: "" },
		advancedFilters: { value: [] },
		appliedSearch: { value: "" },
		appliedQuickFilters: { value: {} },
		standardFilterFields: { value: standardStatus ? [{ fieldname }] : [] },
		statusCounts: { value: {} },
		total: { value: rows.length },
		props: { doctype: "YRP Production Order" },
		baseFilters: () => [],
		hasFilterValue: (value) => value !== "" && value !== null && value !== undefined,
		computed: (getter) => ({ get value() { return getter() } }),
		getCount: async (_doctype, filters) => rows.filter((row) => matches(row, filters)).length,
		loadSequence: 1,
	})
	vm.runInContext([
		listSource.slice(listSource.indexOf("function quickFilterTuples("), listSource.indexOf("async function initialise(")),
		listSource.slice(listSource.indexOf("async function loadStatusCounts("), listSource.indexOf("async function loadRows(")),
		listSource.slice(listSource.indexOf("const statusTabs ="), listSource.indexOf("watch(", listSource.indexOf("const statusTabs ="))),
		"globalThis.list = { allFilters, loadStatusCounts, statusTabs, statusSelectOptions }",
	].join("\n"), context)
	return context
}

test("PPO filters offer enabled templates only and Desk keeps its Production Term query", () => {
	assert.deepEqual(productionOrderItemFilters, { has_variants: 1, variant_of: ["is", "not set"], disabled: 0 })
	let handlers
	vm.runInNewContext(read("essdee_yrp/public/js/production_order_workflow.js"), {
		frappe: { ui: { form: { on: (_doctype, value) => { handlers = value } } } },
	})
	const queries = {}
	handlers.setup({ set_query: (fieldname, query) => { queries[fieldname] = query } })
	assert.deepEqual(copy(queries.item().filters), productionOrderItemFilters)
	assert.deepEqual(copy(queries.production_term({}).filters), { docstatus: 1 })
	const editor = read("frontend/src/departments/sales/ProductionOrderEditor.vue")
	assert.match(editor, /v-model="form.item"[^>]+:filters="productionOrderItemFilters"[^>]+:disabled="Boolean\(name\)"/)
})

test("PPO tabs and narrow Status dropdown partition all 362 fixture rows correctly", async () => {
	for (const standardStatus of [false, true]) {
		const harness = listHarness({ standardStatus })
		await harness.list.loadStatusCounts()
		assert.deepEqual(copy(harness.statusCounts.value), { __all__: 362, Draft: 5, "PPO Request": 2, Open: 264, "Pending Request": 0, "Item Changed": 0, "Not Processed": 7, Closed: 52, Cancelled: 32 })
		assert.equal(harness.list.statusTabs.value.reduce((sum, tab) => sum + (tab.value ? tab.count : 0), 0), 362)
		assert.deepEqual(copy(harness.list.statusSelectOptions.value.map(({ value, count }) => ({ value, count }))), copy(harness.list.statusTabs.value.map(({ value, count }) => ({ value, count }))))
		for (const option of productionOrderStatusOptions) {
			harness.activeStatus.value = option.value
			harness.appliedQuickFilters.value = { status: option.value }
			assert.deepEqual(copy(harness.list.allFilters()), option.filters)
			assert.equal(rows.filter((row) => matches(row, harness.list.allFilters())).length, harness.statusCounts.value[option.value])
		}
	}
})

test("search and other filters constrain counts and cancelled rows together", async () => {
	const harness = listHarness()
	harness.activeStatus.value = "Cancelled"
	harness.appliedSearch.value = "PPO-7-"
	harness.advancedFilters.value = [["status", "=", "Open"]]
	await harness.list.loadStatusCounts()
	assert.equal(harness.statusCounts.value.Cancelled, 3)
	assert.equal(harness.statusCounts.value.Open, 0)
	assert.equal(harness.statusCounts.value.__all__, 3)
	assert.deepEqual(copy(harness.list.allFilters()), [["status", "=", "Open"], ["docstatus", "=", 2], ["name", "like", "%PPO-7-%"]])
})

test("string, object and docstatus options preserve the original equality queries", async () => {
	for (const [fieldname, options, value] of [["status", ["Open", "Closed"], "Open"], ["status", [{ label: "Active", value: "Open" }], "Open"], ["docstatus", [{ label: "Cancelled", value: "2" }], "2"]]) {
		const harness = listHarness({ fieldname, options })
		harness.activeStatus.value = value
		assert.deepEqual(copy(harness.list.allFilters()), [[fieldname, "=", value]])
		await harness.list.loadStatusCounts()
		assert.equal(harness.statusCounts.value[value], fieldname === "docstatus" ? 32 : 267)
	}
})

test("restored Cancelled state resolves its option filters after navigation", () => {
	const storage = new Map()
	storage.setItem = storage.set.bind(storage)
	storage.getItem = storage.get.bind(storage)
	const input = { sourceRouteName: "sales-production-orders", doctype: "YRP Production Order", status: "Cancelled", filters: [["docstatus", "=", 2]] }
	writeNavigationState(storage, createListNavigationState(input))
	const state = readNavigationState(storage, navigationStorageKey(input.sourceRouteName, input.doctype))
	for (const standardStatus of [false, true]) {
		const harness = listHarness({ standardStatus })
		harness.activeStatus.value = state.status
		assert.deepEqual(copy(harness.list.allFilters()), state.filters)
	}
})

test("row badge prioritizes cancelled docstatus, and header consumes backend status_label", () => {
	const source = read("frontend/src/departments/sales/ProductionOrders.vue")
	const expression = source.match(/:docstatus="row.docstatus" :label="([^"]+)"/)[1]
	const label = new Function("row", "value", `return ${expression}`)
	const defaults = { 0: "Draft", 1: "Submitted", 2: "Cancelled" }
	for (const [docstatus, stored, expected] of [[2, null, "Cancelled"], [2, "Open", "Cancelled"], [0, null, "Draft"], [0, "PPO Request", "PPO Request"], [1, "Open", "Open"]]) {
		assert.equal(label({ docstatus }, stored) || defaults[docstatus], expected)
	}
	assert.match(read("frontend/src/departments/sales/ProductionOrder.vue"), /:label="record.status_label"/)
})

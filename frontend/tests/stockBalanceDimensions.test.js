import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import * as filterState from "../src/components/reports/reportFilterState.js"
import { FilterService } from "@primevue/core/api"
const reportExportModule = await import(new URL("../src/components/reports/reportExport.js", import.meta.url))

const dimensions = [
	{ fieldname: "lot", label: "Lot", dimension_doctype: "SD YRP Lot" },
	{ fieldname: "received_type", label: "Received Type", dimension_doctype: "YRP Received Type" },
	{ fieldname: "quality", label: "Quality", dimension_doctype: "Quality" },
]

for (const configured of [dimensions, []]) {
	test(`Desk generates ${configured.length} dimension filters in config order after Supplier`, () => {
		const lookups = []
		let request
		const frappe = {
			query_reports: {}, datetime: { get_today: () => "2026-10-20", add_months: () => "2026-09-20" },
			call: (args) => { request = args },
			db: { get_link_options: (...args) => { lookups.push(args); return [] } },
		}
		vm.runInNewContext(readFileSync(new URL("../../../yrp/yrp/yrp_stock/report/yrp_stock_balance/yrp_stock_balance.js", import.meta.url), "utf8"), { frappe, __: (text) => text })
		assert.equal(request?.method, "yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance.get_filter_dimensions")
		request.callback({ message: configured })
		const filters = frappe.query_reports["YRP Stock Balance"].filters
		assert.deepEqual(Array.from(filters, (field) => field.fieldname), ["from_date", "to_date", "item", "parent_item", "warehouse", "supplier", ...configured.map((d) => d.fieldname), "show_stock_ageing_data", "show_variant_attributes", "remove_zero_balance_item", "show_inward_date_split"])
		for (const key of ["item", "parent_item"]) {
			const field = filters.find((field) => field.fieldname === key)
			assert.equal(field.fieldtype, "MultiSelectList")
		}
		for (const dimension of configured) {
			const field = filters.find((field) => field.fieldname === dimension.fieldname)
			assert.equal(field.fieldtype, "MultiSelectList")
			assert.equal(field.label, dimension.label)
			assert.equal(field.options, dimension.dimension_doctype)
			field.get_data("query")
		}
		assert.deepEqual(lookups, configured.map((dimension) => [dimension.dimension_doctype, "query"]))
	})
}

test("web restores only configured dimension arrays, including old scalar requests", () => {
	const request = { lot: ["A", "B"], received_type: "Accepted", quality: '["Q1", "Q2"]' }
	assert.deepEqual(filterState.stockBalanceFormFilters(request, dimensions).dimensions, { lot: ["A", "B"], received_type: ["Accepted"], quality: ["Q1", "Q2"] })
	assert.deepEqual(filterState.stockBalanceFormFilters(request, []).dimensions, {})
})

for (const configured of [dimensions, []]) {
	test(`web renders ${configured.length} config-driven multiselects, sends selections and resets`, async () => {
		const calls = [], requests = [], lookups = [], changes = []
		const activeFilters = Vue.ref(null)
		const shell = (_, { slots, attrs }) => Vue.h("shell", attrs, [slots.filters?.(), slots.default?.()])
		const control = (props) => Vue.h("control", props)
		const ref = Vue.ref
		const component = loadComponent(resolve(import.meta.dirname, "../src/components/reports/StockBalanceReport.vue"), {
			"primevue/button": control,
			"@primevue/core/api": { FilterService },
			"../common/DateField.vue": control,
			"../common/LinkField.vue": control,
			"../common/MultiSelectField.vue": control,
			"./reportExport.js": reportExportModule,
			"./ReportShell.vue": shell,
			"./ReportColumnPicker.vue": control,
			"./ReportRunStatus.vue": control,
			"./reportFilterState.js": filterState,
			"./reportUtils.js": { number: String, oneMonthAgoIso: () => "2026-09-20", todayIso: () => "2026-10-20", stockCellValue: String },
			"../../api/frappe.js": { callMethod: async (method) => { if (method.endsWith("get_item_filter_options")) return [{ value: "EC-11400", description: "Tank Top" }]; calls.push(method); return configured }, searchLink: async (...args) => { lookups.push(args); return [{ name: "A", label: "Alpha", description: "Maze Capri" }] } },
			"../../composables/useIncrementalRows.js": incrementalRows, "../../composables/useInlineFilters.js": inlineFilters,
			"../../composables/useWebReport.js": { useWebReport: () => ({ state: ref("idle"), sourceColumns: ref([]), sourceRows: ref([]), job: ref(null), activeFilters, generate: async (filters) => requests.push(JSON.parse(JSON.stringify(filters))), filtersChanged: (filters) => changes.push(filters), clear() {} }) },
			"../../composables/useReportColumns.js": { useReportColumns: () => ({ columns: ref([]), displayColumns: ref([]), rows: ref([]), linkSources: ref({}), fieldsBySource: ref({}), loadLayout() {} }) },
		})
		const root = mountComponent(component)
		await new Promise(setImmediate); await Vue.nextTick()
		assert.deepEqual(calls, ["yrp.yrp_stock.report.yrp_stock_balance.yrp_stock_balance.get_filter_dimensions"])
		const selectors = () => findNodes(root, (node) => node.type === "control" && node.props["data-dimension"])
		assert.deepEqual(selectors().map((node) => node.props.label), configured.map((d) => d.label))
		for (const selector of selectors()) {
			assert.equal(selector.props["reset-filter-on-hide"], true)
			assert.equal(FilterService.filter([{ label: "LOT-001", value: "LOT-001" }], selector.props["filter-fields"] || ["label"], "associated item", selector.props["filter-match-mode"] || "contains").length, 1, "server matches through Lot.item must stay visible")
			selector.props["onUpdate:modelValue"](["A", "B"])
			await selector.props.onFilter({ value: "Al" })
		}
		await Vue.nextTick()
		for (const selector of selectors()) assert.deepEqual(selector.props.options.find((option) => option.value === "A"), { label: "Alpha", value: "A", description: "Maze Capri" }, "lot options keep the item name line")
		const shellNode = findNodes(root, (node) => node.type === "shell")[0]
		await shellNode.props.onGenerate()
		for (const dimension of configured) assert.deepEqual(requests[0][dimension.fieldname], ["A", "B"])
		const itemSelectors = findNodes(root, (node) => node.type === "control" && node.props["data-item-filter"])
		assert.deepEqual(itemSelectors.map((node) => node.props.label), ["Item", "Item Variant"])
		await itemSelectors[0].props.onBeforeShow()
		await Vue.nextTick()
		const itemSelector = findNodes(root, (node) => node.type === "control" && node.props["data-item-filter"] === "parentItem")[0]
		assert.deepEqual(itemSelector.props.options[0], { label: "EC-11400", value: "EC-11400", description: "Tank Top" }, "item name renders as the second line")
		for (const selector of itemSelectors) selector.props["onUpdate:modelValue"](["I1", "I2"])
		await Vue.nextTick()
		await shellNode.props.onGenerate()
		assert.deepEqual(requests[1].parent_item, ["I1", "I2"])
		assert.deepEqual(requests[1].item, ["I1", "I2"])
		assert.equal(lookups.length, configured.length)
		assert.deepEqual(lookups.map((args) => args[0]), configured.map((d) => d.dimension_doctype))
		for (const args of lookups) assert.equal(args[4], true, "dimension pickers match only visible name and description")
		if (!configured.length) for (const d of dimensions) assert.ok(!(d.fieldname in requests[0]))
		changes.length = 0
		activeFilters.value = { from_date: "2026-10-01", to_date: "2026-10-17", lot: ["RESTORED"], quality: "Q1" }
		await Vue.nextTick()
		assert.equal(changes.length, 0, "restoring a tracked report must not clear its result")
		if (configured.length) assert.deepEqual(selectors()[0].props["model-value"], ["RESTORED"])
		shellNode.props.onReset(); await Vue.nextTick()
		for (const selector of selectors()) assert.deepEqual(selector.props["model-value"], [])
	})
}

test("web restores old scalar and JSON item filters as multiselect arrays", () => {
	assert.deepEqual(filterState.stockBalanceFormFilters({ item: "V1", parent_item: '["T1", "S1"]' }).item, ["V1"])
	assert.deepEqual(filterState.stockBalanceFormFilters({ parent_item: '["T1", "S1"]' }).parentItem, ["T1", "S1"])
})

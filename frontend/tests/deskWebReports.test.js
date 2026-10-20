import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const configUrl = new URL("../src/components/reports/deskReportConfig.js", import.meta.url)
async function config() {
	assert.ok(existsSync(configUrl), "Shared Desk report filter/menu configuration is missing")
	return import(configUrl)
}

const departments = ["cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "purchase"]
const stockReports = [
	["stock-entry-report", "sd_yrp_stock_entry_report", "SD YRP Stock Entry Report", departments],
	["stock-reconciliation-report", "sd_yrp_stock_reconciliation_report", "SD YRP Stock Reconciliation Report", departments],
	["stock-update-report", "sd_yrp_stock_update_report", "SD YRP Stock Update Report", departments],
	["item-conversion-report", "sd_yrp_item_conversion_report", "SD YRP Item Conversion Report", ["purchase", "accessory-store", "fabric-store", "cutting"]],
]

const issuedReports = [
	["dc-report", "sd_yrp_dc_report", "SD YRP DC Report", departments],
	["jobwork-issued-items", "sd_yrp_jobwork_issued_items", "SD YRP Jobwork Issued Items", ["purchase", "accessory-store", "fabric-store", "accounts"]],
]

const placementReports = [
	["purchase-order-itemwise", "sd_yrp_purchase_order_itemwise", "SD YRP Purchase Order Itemwise", ["purchase", "accounts"]],
	["lot-consumption-report", "sd_yrp_lot_consumption_report", "SD YRP Lot Consumption Report", ["purchase", "fabric-store", "accessory-store", "accounts"]],
	["non-jobwork-issued-items", "sd_yrp_non_jobwork_issued_items", "SD YRP Non Jobwork Issued Items", ["purchase", "accessory-store", "fabric-store", "accounts"]],
	["non-grn-received-items", "sd_yrp_non_grn_received_items", "SD YRP Non-GRN Received Items", ["purchase", "accessory-store", "fabric-store", "accounts"]],
	["lot-wise-stock-ageing", "sd_yrp_lot_wise_stock_ageing", "SD YRP Lot Wise Stock Ageing", ["purchase", "accessory-store", "fabric-store", "accounts"]],
	["stock-ageing", "yrp_stock_ageing", "YRP Stock Ageing", ["purchase", "accessory-store", "fabric-store", "accounts"]],
]

for (const [key, , name, visibleDepartments] of [...stockReports, ...issuedReports, ...placementReports]) {
	test(`${name} appears only in its allowed departments with report access`, async () => {
		const { departmentDeskReports } = await config()
		const capabilityKey = key.replaceAll("-", "_")
		const capabilities = { [capabilityKey]: { can_read: true, can_report: true } }
		for (const department of [...departments, "sales", "pd", "hr", "accounts", "planning"]) {
			const tabs = departmentDeskReports(department, capabilities)
			assert.deepEqual(tabs.map(tab => tab.value), visibleDepartments.includes(department) ? [key] : [])
			if (tabs.length) {
				assert.equal(tabs[0].label, name.replace("SD YRP ", ""))
				assert.deepEqual(tabs[0].componentProps, { reportKey: key })
			}
			assert.deepEqual(departmentDeskReports(department, capabilities, false), [])
			assert.deepEqual(departmentDeskReports(department, {}), [])
			assert.deepEqual(departmentDeskReports(department, { [capabilityKey]: { can_read: false } }), [])
		}
	})
}

test("Lot Purchase Summary is available only in an allowed Purchase report area", async () => {
	const { departmentDeskReports } = await config()
	const capabilities = { lot_purchase_summary: { can_read: true, can_report: true } }
	const tabs = departmentDeskReports("purchase", capabilities)
	assert.deepEqual(tabs.map(({ key, value, label, componentProps }) => ({ key, value, label, componentProps })), [{
		key: "lot_purchase_summary", value: "lot-purchase-summary", label: "Lot Purchase Summary",
		componentProps: { reportKey: "lot-purchase-summary" },
	}])
	for (const department of [...departments.filter(value => value !== "purchase"), "sales", "pd", "hr", "accounts", "planning"]) {
		assert.deepEqual(departmentDeskReports(department, capabilities), [])
	}
	assert.deepEqual(departmentDeskReports("purchase", capabilities, false), [])
	assert.deepEqual(departmentDeskReports("purchase", {}), [])
	assert.deepEqual(departmentDeskReports("purchase", { lot_purchase_summary: { can_read: false } }), [])
})

test("GRN menus cover exactly the requested departments and respect report capabilities", async () => {
	const { departmentDeskReports } = await config()
	for (const department of departments) {
		const tabs = departmentDeskReports(department, { grn_report: { can_read: true }, grn_summary: { can_read: true } })
		assert.deepEqual(tabs.map(tab => tab.value), ["grn-report", "grn-summary"])
		assert.deepEqual(departmentDeskReports(department, {}), [])
	}
	for (const department of ["sales", "pd", "hr", "accounts", "planning"]) {
		assert.deepEqual(departmentDeskReports(department, { grn_report: { can_read: true } }), [])
	}
	const capabilities = { purchase_order_log: { can_read: true }, finishing_inward_updates: { can_read: true } }
	assert.deepEqual(departmentDeskReports("purchase", capabilities).map(tab => tab.value), ["purchase-order-log"])
	assert.deepEqual(departmentDeskReports("sewing", capabilities).map(tab => tab.value), ["finishing-inward-updates"])
	assert.deepEqual(departmentDeskReports("cutting", capabilities), [])
})

test("web filters, defaults and select values match the actual Desk report definitions", async () => {
	const { deskReportConfig, deskReportDefaults } = await config()
	for (const [key, slug, name] of [
		["grn-report", "sd_yrp_grn_report", "SD YRP GRN Report"],
		["grn-summary", "sd_yrp_grn_summary", "SD YRP GRN Summary"],
		["purchase-order-log", "sd_yrp_purchase_order_log", "SD YRP Purchase Order Log"],
		["lot-purchase-summary", "sd_yrp_lot_purchase_summary", "SD YRP Lot Purchase Summary"],
		...stockReports, ...issuedReports, ...placementReports,
	]) {
		const frappe = { query_reports: {}, datetime: {
			nowdate: () => "2026-03-31", get_today: () => "2026-03-31",
			month_start: () => "2026-03-01", month_end: () => "2026-03-31",
			add_months: value => value === "2026-03-01" ? "2026-02-01" : "2026-02-28",
			add_days: () => "2026-02-28",
		} }
		const source = key === "stock-ageing"
			? new URL(`../../../yrp/yrp/yrp_stock/report/${slug}/${slug}.js`, import.meta.url)
			: new URL(`../../essdee_yrp/essdee_yrp/report/${slug}/${slug}.js`, import.meta.url)
		vm.runInNewContext(readFileSync(source, "utf8"), { frappe, __: value => value })
		const desk = JSON.parse(JSON.stringify(frappe.query_reports[name].filters))
		const web = deskReportConfig[key].filters
		assert.deepEqual(web.map(({ fieldname, fieldtype, label, options, reqd }) => ({ fieldname, fieldtype, label, options, reqd: Boolean(reqd) })),
			desk.map(({ fieldname, fieldtype, label, options, reqd }) => ({ fieldname, fieldtype, label,
				options: fieldtype === "Link" && options === "Warehouse" ? "Supplier"
					: fieldtype === "Select" && typeof options === "string" ? options.split("\n").map(value => ({ value, label: value || "All" })) : options,
				reqd: Boolean(reqd) })))
		for (const field of frappe.query_reports[name].filters) {
			assert.equal(web.find(webField => webField.fieldname === field.fieldname).depends_on,
				field.depends_on?.replace("eval:doc.", ""))
			if (field.get_query) assert.deepEqual(web.find(webField => webField.fieldname === field.fieldname).filters,
				JSON.parse(JSON.stringify(field.get_query().filters)))
		}
		const defaults = deskReportDefaults(key, "2026-03-31")
		for (const field of desk) assert.equal(defaults[field.fieldname], field.fieldtype === "Int" ? Number(field.default) : field.default ?? (field.fieldtype === "Check" ? 0 : ""))
	}
	// FI Updates uses the Sewing Details page's supplier control rather than a Script Report.
	const page = readFileSync(new URL("../../essdee_yrp/public/js/SewingPlan/SewingPlan.vue", import.meta.url), "utf8")
	let deskSupplier
	vm.runInNewContext(`${page.slice(page.indexOf("function initSupplierField()"), page.indexOf("</script>"))}; initSupplierField()`, {
		supplier_field_wrapper: { value: {} }, sample_doc: { value: {} },
		$: () => ({ find: () => ({ length: 0 }) }),
		frappe: { ui: { form: { make_control: ({ df }) => { deskSupplier = df } } } },
	})
	const supplier = deskReportConfig["finishing-inward-updates"].filters[0]
	assert.equal(supplier.fieldname, deskSupplier.fieldname)
	assert.equal(supplier.fieldtype, deskSupplier.fieldtype)
	assert.equal(supplier.options, deskSupplier.options)
	assert.deepEqual(supplier.filters, JSON.parse(JSON.stringify(deskSupplier.get_query().filters)))
	assert.equal(supplier.reqd, 1)
	assert.deepEqual(deskReportDefaults("finishing-inward-updates", "2026-03-31"), { supplier: "" })
})

test("stock report location lookups use Suppliers and Desk date calculations survive month boundaries", async () => {
	const { deskReportConfig, deskReportDefaults } = await config()
	for (const [key, fields] of [
		["stock-entry-report", ["from_warehouse", "to_warehouse"]],
		["stock-reconciliation-report", ["supplier"]],
		["stock-update-report", ["warehouse"]],
		["dc-report", ["from_location", "supplier"]],
		["jobwork-issued-items", ["from_location", "supplier"]],
		["non-jobwork-issued-items", ["from_location", "supplier"]],
		["non-grn-received-items", ["received_location", "supplier"]],
		["lot-wise-stock-ageing", ["warehouse"]],
		["stock-ageing", ["warehouse"]],
		["purchase-order-itemwise", ["supplier", "delivery_location"]],
	]) {
		for (const fieldname of fields) assert.equal(deskReportConfig[key].filters.find(field => field.fieldname === fieldname).options, "Supplier")
	}
	for (const [today, rollingFrom, monthFrom, monthTo] of [
		["2026-04-15", "2026-03-15", "2026-03-01", "2026-03-30"],
		["2026-01-31", "2025-12-31", "2025-12-01", "2025-12-31"],
		["2024-03-31", "2024-02-29", "2024-02-01", "2024-02-29"],
	]) {
		for (const [key] of [...stockReports, ...issuedReports]) {
			const defaults = deskReportDefaults(key, today)
			const monthly = ["stock-reconciliation-report", "item-conversion-report"].includes(key)
			assert.equal(defaults.from_date, monthly ? monthFrom : rollingFrom)
			assert.equal(defaults.to_date, monthly ? monthTo : today)
		}
	}
})

test("report lot query prefills the lookup and follows navigation within the report", async () => {
	const route = Vue.reactive({ query: { report: "lot-purchase-summary", lot: "LOT-1", unknown: "ignored" } })
	const requests = []
	const empty = () => Vue.ref([])
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"vue-router": { useRoute: () => route },
		"primevue/inputnumber": () => null, "primevue/button": () => null, "primevue/checkbox": () => null, "primevue/select": () => null,
		"../common/DateField.vue": () => null, "../common/LinkField.vue": props => Vue.h("filter-link", props),
		"./ReportShell.vue": Vue.defineComponent({ emits: ["generate", "reset"], setup: (_props, { slots, emit }) => () => Vue.h("report-shell", {
			onGenerate: () => emit("generate"), onReset: () => emit("reset"),
		}, slots.filters?.()) }),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": await config(),
		"./reportUtils.js": { todayIso: () => "2026-03-31", stockCellValue: value => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({ sourceColumns: empty(), sourceRows: empty(), activeFilters: Vue.ref(null),
			filtersChanged() {}, clear() {}, generate: async request => requests.push(request),
		}) },
		"../../composables/useReportColumns.js": { useReportColumns: () => ({ columns: empty(), displayColumns: empty(), rows: empty(), loadLayout() {} }) },
	})
	const root = mountComponent(component, { reportKey: "lot-purchase-summary" })
	try {
		const lotField = () => findNodes(root, node => node.type === "filter-link" && node.props.label === "Lot")[0]
		assert.equal(lotField().props.modelValue, "LOT-1")
		route.query = { report: "lot-purchase-summary", lot: "LOT-2" }
		await Vue.nextTick()
		assert.equal(lotField().props.modelValue, "LOT-2")
		findNodes(root, node => node.type === "report-shell")[0].props.onGenerate()
		await Vue.nextTick()
		assert.deepEqual(requests, [{ lot: "LOT-2", item: "", parent_item: "" }])
		lotField().props["onUpdate:modelValue"]("LOT-3")
		findNodes(root, node => node.type === "report-shell")[0].props.onReset()
		await Vue.nextTick()
		assert.equal(lotField().props.modelValue, "LOT-2")
	} finally { root.__vue_app__.unmount() }
})

test("FI Updates passes the company-location restriction to its supplier lookup", async () => {
	const { deskReportConfig } = await config()
	const empty = () => Vue.ref([])
	const ReportShell = (_props, { slots }) => Vue.h("section", slots.filters?.())
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/inputnumber": () => null, "primevue/button": () => null, "primevue/checkbox": () => null, "primevue/select": () => null,
		"../common/DateField.vue": () => null,
		"../common/LinkField.vue": props => Vue.h("supplier-lookup", props),
		"./ReportShell.vue": ReportShell, "./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": await config(),
		"./reportUtils.js": { todayIso: () => "2026-03-31", stockCellValue: value => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({
			sourceColumns: empty(), sourceRows: empty(), activeFilters: Vue.ref(null), filtersChanged() {},
		}) },
		"../../composables/useReportColumns.js": { useReportColumns: () => ({
			columns: empty(), displayColumns: empty(), rows: empty(), loadLayout() {},
		}) },
	})
	const root = mountComponent(component, { reportKey: "finishing-inward-updates" })
	try {
		const lookup = findNodes(root, node => node.type === "supplier-lookup")[0]
		assert.equal(lookup.props.doctype, "Supplier")
		assert.deepEqual(lookup.props.filters, { is_company_location: 1 })
		assert.deepEqual(lookup.props.filters, deskReportConfig["finishing-inward-updates"].filters[0].filters)
	} finally { root.__vue_app__.unmount() }
})

test("report capability alone cannot open an otherwise unavailable department report area", async () => {
	const { departmentDeskReports } = await config()
	assert.deepEqual(departmentDeskReports("fabric-store", { grn_report: { can_read: true } }, false), [])
	assert.deepEqual(departmentDeskReports("purchase", { purchase_order_log: { can_read: true } }, false), [])
	const tabs = departmentDeskReports("purchase", { purchase_order_log: { can_read: true } })
	assert.deepEqual(tabs[0].componentProps, { reportKey: "purchase-order-log" })
})


test("GRN Summary sends each selected status including Draft as a string", async () => {
	const requests = []
	const empty = () => Vue.ref([])
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/inputnumber": () => null, "primevue/button": () => null, "primevue/checkbox": () => null,
		"primevue/select": props => Vue.h("status-select", props),
		"../common/DateField.vue": () => null, "../common/LinkField.vue": () => null,
		"./ReportShell.vue": Vue.defineComponent({
			emits: ["generate"],
			setup: (_props, { slots, emit }) => () => Vue.h("report-shell", { onGenerate: () => emit("generate") }, slots.filters?.()),
		}),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": await config(),
		"./reportUtils.js": { todayIso: () => "2026-03-31", stockCellValue: value => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({
			sourceColumns: empty(), sourceRows: empty(), activeFilters: Vue.ref(null), filtersChanged() {},
			generate: async request => requests.push(request),
		}) },
		"../../composables/useReportColumns.js": { useReportColumns: () => ({
			columns: empty(), displayColumns: empty(), rows: empty(), loadLayout() {},
		}) },
	})
	const root = mountComponent(component, { reportKey: "grn-summary" })
	try {
		for (const value of ["0", "1", "2", ""]) {
			const select = findNodes(root, node => node.type === "status-select")[0]
			assert.equal(select.props["option-value"], "value")
			select.props["onUpdate:modelValue"](value)
			await Vue.nextTick()
			findNodes(root, node => node.type === "report-shell")[0].props.onGenerate()
			await Vue.nextTick()
		}
		assert.deepEqual(requests.map(request => request.status), ["0", "1", "2", ""])
		assert.ok(requests.every(request => !("grn_status" in request)))
	} finally { root.__vue_app__.unmount() }
})


test("Accounts integrates shared Desk reports and passes the selected report props", async () => {
	const { accountsReportTabs } = await import("../src/departments/accounts/accountsViews.js")
	const capabilities = { jobwork_issued_items: { can_read: true }, dc_report: { can_read: true }, stock_balance: { can_read: true } }
	assert.deepEqual(accountsReportTabs(capabilities).map(tab => tab.value), ["stock-balance", "jobwork-issued-items"])
	assert.deepEqual(accountsReportTabs(capabilities).at(-1).componentProps, { reportKey: "jobwork-issued-items" })
	assert.deepEqual(accountsReportTabs({ jobwork_issued_items: { can_read: false } }), [])
	const source = readFileSync(new URL("../src/departments/accounts/AccountsReports.vue", import.meta.url), "utf8")
	assert.match(source, /import DeskBackedReport from/)
	assert.match(source, /component: REPORT_COMPONENTS\[report.key\] \|\| DeskBackedReport/)
	assert.match(source, /v-bind="currentTab.componentProps"/)
})

test("ageing ranges and warehouse defaults render, reset and reach report generation", async () => {
	const requests = []
	const empty = () => Vue.ref([])
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/button": () => null, "primevue/checkbox": props => Vue.h("warehouse-check", props),
		"primevue/select": () => null, "primevue/inputnumber": props => Vue.h("age-range", props),
		"../common/DateField.vue": () => null, "../common/LinkField.vue": () => null,
		"./ReportShell.vue": Vue.defineComponent({
			emits: ["generate", "reset"],
			setup: (_props, { slots, emit }) => () => Vue.h("report-shell", {
				onGenerate: () => emit("generate"), onReset: () => emit("reset"),
			}, slots.filters?.()),
		}),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": await config(),
		"./reportUtils.js": { todayIso: () => "2026-03-31", stockCellValue: value => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({
			sourceColumns: empty(), sourceRows: empty(), activeFilters: Vue.ref(null), filtersChanged() {}, clear() {},
			generate: async request => requests.push(request),
		}) },
		"../../composables/useReportColumns.js": { useReportColumns: () => ({
			columns: empty(), displayColumns: empty(), rows: empty(), loadLayout() {},
		}) },
	})
	for (const [key, warehouseDefault] of [["lot-wise-stock-ageing", 0], ["stock-ageing", 1]]) {
		const root = mountComponent(component, { reportKey: key })
		try {
			const ranges = () => findNodes(root, node => node.type === "age-range")
			assert.deepEqual(ranges().map(node => Number(node.props.modelValue)), [30, 60, 90])
			assert.equal(findNodes(root, node => node.type === "warehouse-check")[0].props.modelValue, warehouseDefault)
			for (const [i, node] of ranges().entries()) node.props["onUpdate:modelValue"]([12, 24, 48][i])
			await Vue.nextTick()
			findNodes(root, node => node.type === "report-shell")[0].props.onGenerate()
			await Vue.nextTick()
			assert.deepEqual([requests.at(-1).range1, requests.at(-1).range2, requests.at(-1).range3], [12, 24, 48])
			findNodes(root, node => node.type === "report-shell")[0].props.onReset()
			await Vue.nextTick()
			assert.deepEqual(ranges().map(node => Number(node.props.modelValue)), [30, 60, 90])
		} finally { root.__vue_app__.unmount() }
	}
})

test("Purchase uses one shared PO tab and store menus exclude it even if passed its key", async () => {
	const shared = await config()
	const shell = (_props, { slots }) => Vue.h("section", slots.default?.())
	const component = loadComponent(new URL("../src/departments/fabric-store/FabricReports.vue", import.meta.url).pathname, {
		"primevue/message": shell, "primevue/tab": shell, "primevue/tablist": shell,
		"primevue/tabpanel": shell, "primevue/tabpanels": shell, "primevue/tabs": shell,
		"../../components/reports/DeskBackedReport.vue": props => Vue.h("desk-report", props),
		"../../components/reports/deskReportConfig.js": shared,
		"../../components/reports/LotCutQuantityReport.vue": () => null,
		"../../components/reports/StockBalanceReport.vue": () => null,
		"vue-router": { useRoute: () => ({ query: {} }) },
	})
	for (const department of ["purchase", "fabric-store", "accessory-store"]) {
		const root = mountComponent(component, { department, reportKeys: ["purchase_order_itemwise"], capability: {
			reports: { purchase_order_itemwise: { can_read: true } },
		} })
		try {
			assert.deepEqual(findNodes(root, node => node.type === "desk-report").map(node => node.props.reportKey),
				department === "purchase" ? ["purchase-order-itemwise"] : [])
		} finally { root.__vue_app__.unmount() }
	}
	const { accountsReportTabs } = await import("../src/departments/accounts/accountsViews.js")
	assert.deepEqual(accountsReportTabs({ purchase_order_itemwise: { can_read: true }, lot_consumption_report: { can_read: true } })
		.map(tab => [tab.value, tab.componentProps]), [
			["purchase-order-itemwise", { reportKey: "purchase-order-itemwise" }],
			["lot-consumption-report", { reportKey: "lot-consumption-report" }],
		])
})

test("PO conditional dates and all Lot Consumption required filters reach the shared runner", async () => {
	const requests = []
	const empty = () => Vue.ref([])
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/button": () => null, "primevue/checkbox": () => null, "primevue/inputnumber": () => null,
		"primevue/select": props => Vue.h("filter-select", props),
		"../common/DateField.vue": props => Vue.h("filter-date", props),
		"../common/LinkField.vue": props => Vue.h("filter-link", props),
		"./ReportShell.vue": Vue.defineComponent({
			emits: ["generate"], setup: (props, { slots, emit }) => () => Vue.h("report-shell", {
				...props, onGenerate: () => emit("generate"),
			}, slots.filters?.()),
		}),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": await config(),
		"./reportUtils.js": { todayIso: () => "2026-03-31", stockCellValue: value => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({
			sourceColumns: empty(), sourceRows: empty(), activeFilters: Vue.ref(null), filtersChanged() {},
			generate: async request => requests.push(request),
		}) },
		"../../composables/useReportColumns.js": { useReportColumns: () => ({
			columns: empty(), displayColumns: empty(), rows: empty(), loadLayout() {},
		}) },
	})
	const po = mountComponent(component, { reportKey: "purchase-order-itemwise" })
	try {
		assert.equal(findNodes(po, node => node.type === "filter-date").length, 0)
		findNodes(po, node => node.type === "filter-select" && node.props.options.some(option => option.value === "Posting Date"))[0].props["onUpdate:modelValue"]("Delivery Date")
		await Vue.nextTick()
		assert.deepEqual(findNodes(po, node => node.type === "filter-date").map(node => [node.props.label, node.props.required, node.props.modelValue]), [["From Date", false, ""], ["To Date", false, ""]])
		findNodes(po, node => node.type === "filter-select" && node.props.options.some(option => option.value === "0"))[0].props["onUpdate:modelValue"]("0")
		await Vue.nextTick()
		findNodes(po, node => node.type === "report-shell")[0].props.onGenerate()
		await Vue.nextTick()
		assert.equal(requests.at(-1).docstatus, "0")
		assert.equal(requests.at(-1).date_based_on, "Delivery Date")
		const dates = findNodes(po, node => node.type === "filter-date")
		dates[0].props["onUpdate:modelValue"]("2026-09-30")
		dates[1].props["onUpdate:modelValue"]("2026-09-01")
		findNodes(po, node => node.type === "filter-select" && node.props.options.some(option => option.value === "Posting Date"))[0].props["onUpdate:modelValue"]("")
		await Vue.nextTick()
		findNodes(po, node => node.type === "report-shell")[0].props.onGenerate()
		await Vue.nextTick()
		// Desk ignores stale date bounds when the date basis has been cleared.
		assert.equal(requests.length, 2)
	} finally { po.__vue_app__.unmount() }
	requests.length = 0
	const lot = mountComponent(component, { reportKey: "lot-consumption-report" })
	try {
		const generate = () => findNodes(lot, node => node.type === "report-shell")[0].props.onGenerate()
		generate()
		await Vue.nextTick()
		assert.equal(requests.length, 0)
		for (const [label, value] of [["Lot", "C0925-57/1"], ["Item Group", "Purchase"]]) {
			const field = findNodes(lot, node => node.type === "filter-link" && node.props.label === label)[0]
			assert.equal(field.props.required, true)
			field.props["onUpdate:modelValue"](value)
			await Vue.nextTick()
		}
		generate()
		await Vue.nextTick()
		assert.deepEqual(requests, [{ lot: "C0925-57/1", start_date: "2026-02-01", end_date: "2026-02-28", item_group: "Purchase" }])
	} finally { lot.__vue_app__.unmount() }
})

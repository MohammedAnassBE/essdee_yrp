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
	]) {
		const frappe = { query_reports: {}, datetime: { nowdate: () => "2026-03-31", get_today: () => "2026-03-31", add_months: () => "2026-02-28" } }
		const source = new URL(`../../essdee_yrp/essdee_yrp/report/${slug}/${slug}.js`, import.meta.url)
		vm.runInNewContext(readFileSync(source, "utf8"), { frappe, __: value => value })
		const desk = JSON.parse(JSON.stringify(frappe.query_reports[name].filters))
		const web = deskReportConfig[key].filters
		assert.deepEqual(web.map(({ fieldname, fieldtype, label, options, reqd }) => ({ fieldname, fieldtype, label, options, reqd: Boolean(reqd) })),
			desk.map(({ fieldname, fieldtype, label, options, reqd }) => ({ fieldname, fieldtype, label, options, reqd: Boolean(reqd) })))
		const defaults = deskReportDefaults(key, "2026-03-31")
		for (const field of desk) assert.equal(defaults[field.fieldname], field.default ?? (field.fieldtype === "Check" ? 0 : ""))
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

test("FI Updates passes the company-location restriction to its supplier lookup", async () => {
	const { deskReportConfig } = await config()
	const empty = () => Vue.ref([])
	const ReportShell = (_props, { slots }) => Vue.h("section", slots.filters?.())
	const component = loadComponent(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url).pathname, {
		"primevue/button": () => null, "primevue/checkbox": () => null, "primevue/select": () => null,
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
		"primevue/button": () => null, "primevue/checkbox": () => null,
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

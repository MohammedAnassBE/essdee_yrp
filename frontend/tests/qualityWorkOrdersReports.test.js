import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import * as reportConfig from "../src/components/reports/deskReportConfig.js"
import { reconcileReportLayout, reportCellValue, cellAlign } from "../src/composables/reportColumns.js"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import * as views from "../src/departments/quality/qualityViews.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const component = (name, modules) => loadComponent(resolve(`frontend/src/departments/quality/${name}.vue`), modules)
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const container = (props, { slots }) => Vue.h("section", props, [slots.default?.(), slots.footer?.()])
const deferred = () => {
	let resolve
	const promise = new Promise((done) => { resolve = done })
	return { promise, resolve }
}

const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
function workOrderList(basePath, { processes = async () => ["Stitching", "Finishing Inward"], qualityCapability = { can_read: true, can_create: true } } = {}) {
	const requests = [], navigations = []
	const workOrders = loadComponent(resolve("frontend/src/departments/fabric-store/FabricWorkOrders.vue"), {
		"primevue/button": Button, "vue-router": { useRouter: () => ({ push: (to) => navigations.push(to) }) },
		"../../components/common/ListView.vue": (props, { slots }) => Vue.h("list", props, slots["toolbar-actions"]?.()),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": { openListDocument: (_router, row, _snapshot, options) => navigations.push({ name: options.routeName, params: { [options.paramName]: row.name } }) },
	})
	const section = loadComponent(resolve("frontend/src/departments/FabricStoreSection.vue"), {
		"primevue/message": stub("message"),
		"./cut-panel-store/CutPanelDocuments.vue": stub("documents"),
		"../api/fabricStore.js": { getFabricStoreCapabilities: async () => { requests.push("fabric"); return { sections: { work_orders: { can_read: true, can_create: true } } } } },
		"../api/quality.js": { getQualityCapabilities: async () => { requests.push("quality"); return { sections: { work_orders: qualityCapability } } } },
		"../api/sewing.js": { getSewingWorkOrderProcesses: () => { requests.push("processes"); return processes() } },
		"../api/finishing.js": { getFinishingCapabilities: () => assert.fail("Only Finishing uses Finishing capabilities") },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/FabricWorkOrders.vue": workOrders,
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
	})
	const props = Vue.reactive({ section: "work_orders", basePath, storeName: "Quality", workOrderViewRouteName: "quality-work-order" })
	return { root: mountComponent(section, props), props, requests, navigations }
}

test("Quality Work Orders use Quality capabilities, submitted sewing filters and view-only list navigation", async () => {
	const processes = deferred()
	const page = workOrderList("/quality", { processes: () => processes.promise })
	await tick()
	assert.equal(nodes(page.root, "list").length, 0)
	processes.resolve(["Stitching", "Finishing Inward"])
	await tick()
	assert.deepEqual(page.requests, ["quality", "processes"])
	const list = nodes(page.root, "list")[0]
	assert.deepEqual(list.props.filters, [["docstatus", "=", 1], ["process_name", "in", ["Stitching", "Finishing Inward"]]])
	assert.equal(nodes(page.root, "button").length, 0)
	list.props.onRowClick({ name: "WO /1" })
	assert.deepEqual(page.navigations, [{ name: "quality-work-order", params: { workOrderId: "WO /1" } }])
})

test("Quality Work Orders fail closed for denied access, empty settings and failed process lookup", async () => {
	const denied = workOrderList("/quality", { qualityCapability: { can_read: false, can_create: true } })
	const empty = workOrderList("/quality", { processes: async () => [] })
	const failed = workOrderList("/quality", { processes: async () => { throw new Error("No processes") } })
	await tick()
	assert.deepEqual(denied.requests, ["quality"])
	assert.equal(nodes(denied.root, "list").length, 0)
	assert.deepEqual(nodes(empty.root, "list")[0].props.filters, [["docstatus", "=", 1], ["process_name", "in", []]])
	assert.equal(nodes(failed.root, "list").length, 0)
	assert.equal(nodes(failed.root, "error")[0].props.message, "No processes")
})

test("Sewing and Fabric Store retain their original capability source, filters and Create button", async () => {
	for (const basePath of ["/sewing", "/fabric-store"]) {
		const page = workOrderList(basePath)
		await tick()
		assert.deepEqual(page.requests, basePath === "/sewing" ? ["fabric", "processes"] : ["fabric"])
		assert.deepEqual(nodes(page.root, "list")[0].props.filters, basePath === "/sewing" ? [["process_name", "in", ["Stitching", "Finishing Inward"]]] : [])
		assert.equal(nodes(page.root, "button")[0].props.label, "Create Work Order")
	}
})

test("late Quality process results cannot replace Fabric Store filters or create capability", async () => {
	const task = deferred(), page = workOrderList("/quality", { processes: () => task.promise })
	await tick()
	page.props.basePath = "/fabric-store"
	await tick()
	task.resolve(["Stitching"])
	await tick()
	assert.deepEqual(nodes(page.root, "list")[0].props.filters, [])
	assert.equal(nodes(page.root, "button")[0].props.label, "Create Work Order")
})

function inspectionRail({ capability = { can_read: true, can_create: true }, getList = async () => [], getCapabilities } = {}) {
	return component("components/QualityWorkOrderInspections", {
		"../../../api/frappe.js": { getList },
		"../../../api/quality.js": { getQualityCapabilities: getCapabilities || (async () => ({ sections: { inspections: capability } })) },
		"../../../components/common/DocumentLink.vue": stub("document-link"),
		"../../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../../components/reports/reportUtils.js": { formatDate: (value) => value },
		"../qualityViews.js": views,
	})
}

async function workOrderPage({ quality = true, docstatus = 1, canCreate = true, showEditorActions = !quality, list = async () => [] } = {}) {
	const navigations = [], qualityRequests = []
	const route = Vue.reactive({ params: { workOrderId: "WO /#1" } })
	const modules = {
		"vue-router": { useRoute: () => route, useRouter: () => ({ push: (to) => navigations.push(to) }) },
		"../api/fabricStore.js": { getWorkOrderWorkspace: async (name) => ({ record: { name, docstatus }, permissions: { can_create: true }, capabilities: { save: {}, amend: {}, create_delivery_challan: {} } }) },
		"../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"../utils/documentValues.js": { hasDocumentDisplayValue: () => true },
		"../components/DepartmentPage.vue": container,
		"../components/common/DocumentLink.vue": stub("document-link"),
		"../components/common/LinkField.vue": stub("link-field"),
		"../components/documents/DocumentActionStrip.vue": stub("action-strip"),
		"../components/documents/DocumentConfirmationDialog.vue": stub("confirmation"),
		"../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"./fabric-store/FabricDocumentWorkspace.vue": (props, { slots }) => Vue.h("workspace", props, [slots["header-actions"]?.(), slots.rail?.()]),
		"./quality/components/QualityWorkOrderInspections.vue": inspectionRail({ getCapabilities: async () => { qualityRequests.push(true); return { sections: { inspections: { can_read: true, can_create: canCreate } } } }, getList: list }),
	}
	for (const name of ["button", "dialog", "message", "tab", "tablist", "tabpanel", "tabpanels", "tabs"]) modules[`primevue/${name}`] = stub(name)
	for (const name of ["FabricStockOperationDialog", "RelatedDocumentWorkspaceDialog", "WorkOrderActionPanel", "WorkOrderActivityRail", "WorkOrderDetails", "WorkOrderOverview", "WorkOrderSummary"]) modules[`./fabric-store/${name}.vue`] = stub(name)
	const root = mountComponent(loadComponent(resolve("frontend/src/departments/FabricWorkOrder.vue"), modules), { quality, showEditorActions })
	await tick()
	return { root, navigations, qualityRequests, route, actions: () => nodes(root, "action-strip")[0].props.actions }
}

test("Quality WO primary inspection action uses inspection create permission and preserves the WO name", async () => {
	const page = await workOrderPage()
	const action = page.actions().find(({ key }) => key === "new_quality_inspection")
	assert.equal(action.label, "New Quality Inspection")
	assert.equal(action.icon, "pi pi-verified")
	assert.equal(action.primary, true)
	assert.equal(page.actions().filter(({ primary }) => primary).length, 1)
	action.command()
	assert.deepEqual(page.navigations, [{ path: "/quality/inspections/new", query: { against_id: "WO /#1" } }])
	assert.ok(!page.actions().some(({ key }) => ["save", "duplicate", "amend"].includes(key)))
	for (const options of [{ docstatus: 0 }, { docstatus: 2 }, { canCreate: false }]) {
		const restricted = await workOrderPage(options)
		assert.ok(!restricted.actions().some(({ key }) => key === "new_quality_inspection"))
	}
})

test("other departments keep WO editor actions and never load Quality capabilities or inspection links", async () => {
	const page = await workOrderPage({ quality: false })
	assert.deepEqual(page.qualityRequests, [])
	assert.ok(!page.actions().some(({ key }) => key === "new_quality_inspection"))
	assert.ok(["save", "duplicate", "amend"].every((key) => page.actions().some((action) => action.key === key)))
	assert.equal(nodes(page.root, "document-link").length, 0)
})

test("Quality WO inspection rail requests all EQIs against the WO and renders record links and status", async () => {
	const requests = []
	const page = await workOrderPage({ list: async (...args) => { requests.push(args); return [{ name: "EQI /1", inspection_type: "Final", posting_date: "2026-10-21", result: "Pass", docstatus: 1 }] } })
	assert.deepEqual(requests, [[views.INSPECTION_DOCTYPE, {
		filters: [["against_id", "=", "WO /#1"]], fields: ["name", "inspection_type", "posting_date", "result", "docstatus"],
		orderBy: "posting_date desc, creation desc", pageLength: 0,
	}]])
	const link = nodes(page.root, "document-link")[0]
	assert.equal(link.props.doctype, views.INSPECTION_DOCTYPE)
	assert.equal(link.props.name, "EQI /1")
	assert.equal(webDocumentPath(link.props.doctype, link.props.name, link.props.currentPath), "/web/quality/inspections/EQI%20%2F1")
	assert.equal(nodes(page.root, "badge").find(({ props }) => props.label === "Pass").props.tone, "success")
})

test("inspection rail avoids unauthorized reads, ignores stale results and allows error retry", async () => {
	const events = []
	const denied = mountComponent(inspectionRail({ capability: { can_read: false, can_create: false }, getList: () => assert.fail("Unauthorized inspection read") }), { workOrder: "WO", onCanCreate: (value) => events.push(value) })
	await tick()
	assert.equal(nodes(denied, "document-link").length, 0)
	assert.ok(events.every((value) => value === false))
	const pending = deferred()
	const props = Vue.reactive({ workOrder: "WO-1" })
	const rail = mountComponent(inspectionRail({ getList: async (_doctype, options) => options.filters[0][2] === "WO-1" ? pending.promise : [{ name: "EQI-2" }] }), props)
	await tick()
	props.workOrder = "WO-2"
	await tick()
	pending.resolve([{ name: "STALE" }]); await tick()
	assert.deepEqual(nodes(rail, "document-link").map(({ props }) => props.name), ["EQI-2"])
	let fail = true
	const retry = mountComponent(inspectionRail({ getList: async () => { if (fail) throw new Error("Read failed"); return [{ name: "EQI" }] } }), { workOrder: "WO" })
	await tick()
	assert.equal(nodes(retry, "error")[0].props.message, "Read failed")
	fail = false
	nodes(retry, "error")[0].props.onRetry(); await tick()
	assert.equal(nodes(retry, "document-link")[0].props.name, "EQI")
})

async function qualityReports(capabilities, query = {}) {
	const route = Vue.reactive({ query, hash: "#report" }), navigations = []
	const modules = {
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: (to) => navigations.push(to) }) },
		"../../api/quality.js": { getQualityCapabilities: async () => capabilities },
		"../../components/DepartmentPage.vue": container,
		"../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../components/reports/DeskBackedReport.vue": stub("desk-report"),
	}
	for (const name of ["select", "skeleton", "tab", "tablist", "tabpanel", "tabpanels", "tabs"]) modules[`primevue/${name}`] = stub(name)
	const root = mountComponent(component("QualityReports", modules), {})
	await tick()
	return { root, route, navigations }
}

test("Quality report tabs gate the RFT report by its capability and preserve query/hash navigation", async () => {
	for (const capabilities of [{}, { sections: { reports: { can_read: true } } }, { reports: { quality_inspection_rft: { can_read: false } } }]) {
		const denied = await qualityReports(capabilities)
		assert.equal(nodes(denied.root, "desk-report").length, 0)
		assert.equal(nodes(denied.root, "error")[0].props.title, "Reports unavailable")
	}
	const page = await qualityReports({ reports: { quality_inspection_rft: { can_read: true } } }, { report: "unknown", lot: "LOT" })
	assert.equal(nodes(page.root, "desk-report")[0].props["report-key"], "quality-inspection-rft")
	const select = nodes(page.root, "select")[0]
	assert.equal(select.props.modelValue, "quality-inspection-rft")
	assert.deepEqual(select.props.options.map(({ label, value }) => ({ label, value })), [{ label: "Quality Inspection RFT", value: "quality-inspection-rft" }])
	select.props["onUpdate:modelValue"]("quality-inspection-rft")
	assert.deepEqual(page.navigations, [{ query: { report: "quality-inspection-rft", lot: "LOT" }, hash: "#report" }])
	page.route.query = { report: "quality-inspection-rft" }; await tick()
	assert.equal(nodes(page.root, "tabs")[0].props.value, "quality-inspection-rft")
})

test("RFT config matches optional Desk filters, blank All selection and no date defaults", () => {
	const config = reportConfig.deskReportConfig["quality-inspection-rft"]
	assert.equal(config.title, "Quality Inspection RFT")
	assert.equal(config.dateDefaults, "none")
	assert.deepEqual(config.filters.map(({ fieldname }) => fieldname), ["lot", "item", "from_date", "to_date", "supplier", "result"])
	for (const [name, doctype] of [["lot", "SD YRP Lot"], ["item", "Item"], ["supplier", "Supplier"]]) {
		const field = config.filters.find(({ fieldname }) => fieldname === name)
		assert.equal(field.fieldtype, "Link")
		assert.equal(field.options, doctype)
	}
	assert.ok(config.filters.every((field) => !field.reqd))
	for (const field of config.filters.filter(({ fieldtype }) => fieldtype === "Date")) assert.equal(field.reqd, 0)
	assert.deepEqual(config.filters.at(-1).options, [{ value: "", label: "All" }, ...["Pass", "Fail", "Hold"].map((value) => ({ value, label: value }))])
	assert.deepEqual(reportConfig.deskReportDefaults("quality-inspection-rft", "2026-10-21"), { lot: "", item: "", from_date: "", to_date: "", supplier: "", result: "" })
})

test("RFT cell tone is opt-in and applies only to result fieldnames with known results", () => {
	const tone = reportConfig.deskReportConfig["quality-inspection-rft"].cellTone
	for (const field of ["result", "result_1", "result_20", "calculated_result"]) {
		assert.deepEqual(["Pass", "Fail", "Hold", "", null, "Other"].map((value) => tone(field, value)), ["success", "danger", "warning", "", "", ""])
	}
	for (const field of ["posting_date_1", "supplier", undefined]) assert.equal(tone(field, "Pass"), "")
	assert.equal(reportConfig.deskReportConfig["grn-report"].cellTone, undefined)
})

function dynamicRftColumns(count) {
	return ["against_id", "supplier", "lot", "item", "colour", "sizes", "description"].map((fieldname) => ({ fieldname, label: fieldname, fieldtype: "Data" })).concat(
		Array.from({ length: count }, (_, i) => [
			{ fieldname: `posting_date_${i + 1}`, label: `Inspection ${i + 1} Date`, fieldtype: "Date" },
			{ fieldname: `result_${i + 1}`, label: `Result ${i + 1}`, fieldtype: "Data" },
		]).flat(),
	)
}

test("report layout keeps every dynamic RFT date/result pair from 1 through 20 inspections", () => {
	for (let count = 1; count <= 20; count++) {
		const columns = reconcileReportLayout(dynamicRftColumns(count), [{ kind: "base", column_key: "base:against_id", visible: 1 }])
		assert.equal(columns.length, 7 + 2 * count)
		assert.ok(columns.every(({ visible }) => visible))
		assert.equal(columns.at(-1).fieldname, `result_${count}`)
	}
})

test("DeskBackedReport generates RFT with empty filters and renders all dynamic columns with cell tones", async () => {
	const requests = [], sourceColumns = Vue.ref(dynamicRftColumns(1)), sourceRows = Vue.ref([{ result_1: "Pass", supplier: "Pass" }])
	const empty = () => Vue.ref([])
	const report = loadComponent(resolve("frontend/src/components/reports/DeskBackedReport.vue"), {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/button": Button, "primevue/checkbox": () => null, "primevue/inputnumber": () => null, "primevue/select": () => null,
		"../common/DateField.vue": stub("date-field"), "../common/LinkField.vue": stub("link-field"),
		"./ReportShell.vue": (props, { slots }) => Vue.h("report-shell", props, [slots.filters?.(), slots.default?.()]),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": reportConfig,
		"./reportUtils.js": { todayIso: () => "2026-10-21", stockCellValue: (value) => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({ sourceColumns, sourceRows, activeFilters: Vue.ref(null), filtersChanged() {}, generate: async (filters) => requests.push(filters) }) },
		"../../composables/useReportColumns.js": { useReportColumns: () => {
			const columns = Vue.computed(() => reconcileReportLayout(sourceColumns.value, null))
			return { columns, displayColumns: columns, rows: sourceRows, linkSources: empty(), fieldsBySource: empty(), loadLayout() {}, cellValue: reportCellValue, cellAlign }
		} },
	})
	const root = mountComponent(report, { reportKey: "quality-inspection-rft" })
	assert.ok(nodes(root, "date-field").every(({ props }) => !props.required))
	await nodes(root, "report-shell")[0].props.onGenerate()
	assert.deepEqual(requests, [{ lot: "", item: "", from_date: "", to_date: "", supplier: "", result: "" }])
	assert.equal(nodes(root, "th").length, 9)
	assert.ok(nodes(root, "td").find((cell) => cell.text === "Pass" && cell.props.class.includes("desk-report-cell--success")))
	assert.ok(!nodes(root, "td")[1].props.class.includes("desk-report-cell--success"))
	sourceColumns.value = dynamicRftColumns(20)
	sourceRows.value = [{ result_1: "Pass", result_2: "Fail", result_20: "Hold" }]
	await tick()
	assert.equal(nodes(root, "th").length, 47)
	assert.equal(nodes(root, "th").at(-1).text, "Result 20")
	for (const [value, tone] of [["Pass", "success"], ["Fail", "danger"], ["Hold", "warning"]]) assert.ok(nodes(root, "td").find((cell) => cell.text === value).props.class.includes(`desk-report-cell--${tone}`))
	const source = read("components/reports/DeskBackedReport.vue")
	for (const token of ["--erp-success-text", "--erp-danger", "--erp-warning"]) assert.ok(source.includes(`var(${token})`))
})

test("Quality Work Order page hides DC and GRN creation", () => {
	const source = readFileSync(resolve("frontend/src/departments/FabricWorkOrder.vue"), "utf8")
	assert.match(source, /QUALITY_HIDDEN_ACTIONS = \["create_delivery_challan", "create_goods_received_note"\]/)
	assert.match(source, /if \(props\.quality && QUALITY_HIDDEN_ACTIONS\.includes\(key\)\) return/)
	assert.match(source, /\[key, \{ \.\.\.value, can_create: false \}\]/)
})

import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { legacyPlanningReportQuery, planningReports } from "../src/departments/planning/reports/planningReportCatalog.js"

const tick = async () => { for (let index = 0; index < 5; index += 1) { await new Promise(done => setImmediate(done)); await Vue.nextTick() } }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const sewing = {
	sections: { reports: { can_read: true } },
	reports: {
		dpr: { can_read: true, can_report: true },
		scr: { can_read: true, can_report: false },
		lot_cut_quantity: { can_read: true, can_report: true, can_read_cutting_plan: true },
	},
}

test("Planning lists every permitted report of every group in one grouped list", () => {
	const reports = planningReports({
		cutting: { "daily-production": true, "multi-ccr": false },
		sewing,
		finishing: { sections: { reports: { reports: { packing_dpr: { can_read: true }, stock_balance: { can_read: false } } } } },
		production: { work_order: { can_read: true }, ppo_report: { can_read: true, can_export: true }, multi_ccr: { can_read: false } },
	})
	assert.deepEqual(reports.map(report => [report.group, report.value]), [
		["Cutting", "cutting-daily-production"],
		["Sewing", "sewing-dpr"],
		["Sewing", "sewing-lot-cut-quantity"],
		["Finishing", "finishing-packing-dpr"],
		["Production / WIP", "work-order"],
		["Production / WIP", "ppo-report"],
	])
	assert.equal(new Set(reports.map(report => report.value)).size, reports.length)
	assert.ok(reports.every(report => report.component))
	assert.deepEqual(reports.find(report => report.value === "ppo-report").props, { canExport: true })
	assert.deepEqual(reports.find(report => report.value === "sewing-lot-cut-quantity").props, { canReadCuttingPlan: true })
})

test("only Sewing Unit-scoped reports ask for a unit, each with its own kept filters", () => {
	const [dpr, lotCut] = planningReports({ sewing })
	assert.ok(dpr.props.report, "unit-scoped report is wrapped with the unit picker")
	assert.equal(dpr.props.reportProps.filters.mode, "daily")
	assert.equal(lotCut.props.report, undefined)
	assert.deepEqual(planningReports({ sewing: { ...sewing, sections: { reports: { can_read: false } } } }), [])
	assert.deepEqual(planningReports(), [])
})

test("old group links open the same report in the combined list", () => {
	assert.equal(legacyPlanningReportQuery({ report: "work-order" }), null)
	assert.deepEqual(legacyPlanningReportQuery({ group: "production", report: "inhouse-quantity", lot: "L1" }), { report: "inhouse-quantity", lot: "L1" })
	assert.deepEqual(legacyPlanningReportQuery({ group: "sewing", tab: "dpr", supplier: "U1" }), { report: "sewing-dpr", supplier: "U1" })
	assert.deepEqual(legacyPlanningReportQuery({ group: "cutting", report: "multi-ccr" }), { report: "cutting-multi-ccr" })
	assert.deepEqual(legacyPlanningReportQuery({ group: "finishing" }), {})
})

test("the Planning page loads only permitted groups and redirects old group links", async () => {
	const calls = [], navigations = []
	const stub = name => (props, { slots }) => Vue.h(name, props, slots?.default?.())
	const component = loadComponent(new URL("../src/departments/planning/PlanningReports.vue", import.meta.url).pathname, {
		"primevue/message": stub("message"), "primevue/skeleton": stub("skeleton"),
		"vue-router": { useRoute: () => ({ query: { group: "cutting", report: "daily-production" }, hash: "" }), useRouter: () => ({ replace: to => navigations.push(to) }) },
		"../../api/planning.js": { getPlanningCapabilities: async () => ({ sections: { reports: { groups: { cutting: true, sewing: false, production: true }, production: { work_order: { can_read: true } } } } }) },
		"../../api/cuttingReports.js": { getCuttingReportPermissions: async () => { calls.push("cutting"); return { "daily-production": true } } },
		"../../api/sewing.js": { getSewingCapabilities: async () => { calls.push("sewing"); return sewing } },
		"../../api/finishing.js": { getFinishingCapabilities: async () => { calls.push("finishing"); return {} } },
		"../../components/DepartmentPage.vue": stub("page"),
		"../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../components/reports/ReportWorkspace.vue": stub("workspace"),
		"./reports/planningReportCatalog.js": { legacyPlanningReportQuery, planningReports },
	})
	const root = mountComponent(component, {})
	try {
		await tick()
		assert.deepEqual(calls, ["cutting"])
		assert.deepEqual(navigations, [{ query: { report: "cutting-daily-production" }, hash: "" }])
		assert.deepEqual(nodes(root, "workspace")[0].props.reports.map(report => report.value), ["cutting-daily-production", "work-order"])
	} finally { root.__vue_app__.unmount() }
})

test("a unit-scoped report asks for the Sewing Unit before it runs", () => {
	const route = Vue.reactive({ path: "/planning/reports", query: {}, hash: "" })
	const component = loadComponent(new URL("../src/departments/planning/reports/SewingUnitReport.vue", import.meta.url).pathname, {
		"primevue/message": (_props, { slots }) => Vue.h("message", slots.default?.()),
		"../../sewing/SewingUnitPicker.vue": () => Vue.h("unit-picker"),
		"../../sewing/useSewingContext.js": { useSewingContext: () => ({ supplier: Vue.computed(() => route.query.supplier || "") }) },
	})
	const report = props => Vue.h("dpr", props)
	const root = mountComponent(component, { report, reportProps: { filters: { mode: "daily" } } })
	try {
		assert.equal(nodes(root, "unit-picker").length, 1)
		assert.equal(nodes(root, "dpr").length, 0)
		assert.equal(nodes(root, "message").length, 1)
	} finally { root.__vue_app__.unmount() }
	route.query = { supplier: "Unit A" }
	const ready = mountComponent(component, { report, reportProps: { filters: { mode: "daily" } } })
	try {
		assert.equal(nodes(ready, "dpr")[0].props.filters.mode, "daily")
		assert.equal(nodes(ready, "message").length, 0)
	} finally { ready.__vue_app__.unmount() }
})

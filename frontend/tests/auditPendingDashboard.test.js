import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as utils from "../src/departments/accounts/reports/auditPendingDashboardUtils.mjs"
import { formatDate } from "../src/components/reports/reportUtils.js"
import { getAuditPendingDashboard, getAuditPendingBreakdown, getAuditPendingDispatchDetail } from "../src/api/accounts.js"

const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const settle = async () => { for (let i = 0; i < 8; i++) await Vue.nextTick() }
const text = node => [node.text, ...node.children.map(text)].join(" ")
const plan = { name: "FP-1", lot: "LOT-1", item: "Kids Set", fp_status: "Dispatched", age_days: 20, status_since: "2026-05-15", total_cut: 100, sewing_received: 90, packed: 80, dispatch_history: [{ source_doctype: "SD YRP Finishing Plan Dispatch", source_name: "D-1", stock_entry: "STE-1", posting_date: "2026-05-15", boxes: 2, pieces: 20 }] }
const dashboard = { plans: [plan], summary: { overdue: 1, dispatched: 1, oldest_days: 20 }, as_of: "2026-10-20" }
const breakdown = total => ({ parts: ["Top", "Bottom"].map(name => ({ name, sizes: ["M"], categories: [
    ["loose_piece", "Loose Piece"], ["loose_piece_set", "Loose Piece Set"], ["rejected", "Rejected Pieces"], ["pending", "Rework Pending"],
].map(([key, label]) => ({ key, label, rows: key === "rejected" && name === "Top" ? [{ colour: "Navy", values: [total], total }] : [], size_totals: [key === "rejected" && name === "Top" ? total : 0], total: key === "rejected" && name === "Top" ? total : 0 })) })) })
const shell = Vue.defineComponent({
	emits: ["generate", "reset"],
	setup: (props, { slots, emit }) => () => Vue.h("report-shell", { ...props, onGenerate: () => emit("generate"), onReset: () => emit("reset") }, [slots.filters?.(), slots.default?.()]),
})
function mount(api) {
	const previousWindow = globalThis.window, previousDocument = globalThis.document
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	globalThis.document = { activeElement: { focus() {} }, querySelector: () => null, querySelectorAll: () => [] }
	const component = loadComponent(new URL("../src/departments/accounts/reports/AuditPendingFinishingPlans.vue", import.meta.url).pathname, {
		vue: { ...Vue, vModelSelect: {}, vModelCheckbox: {} },
		"../../../components/reports/ReportShell.vue": shell,
		"../../../components/reports/reportUtils.js": { formatDate },
		"../../../api/accounts.js": api,
		"./auditPendingDashboardUtils.mjs": utils,
	})
	const root = mountComponent(component)
	return { root, close() { root.__vue_app__.unmount(); globalThis.window = previousWindow; globalThis.document = previousDocument } }
}

test("audit APIs preserve the MRP mode and dispatch ownership arguments", async () => {
	const previousFetch = globalThis.fetch, previousWindow = globalThis.window
	const requests = []
	globalThis.window = { csrf_token: "token" }
	globalThis.fetch = async (url, options) => { requests.push({ url, args: JSON.parse(options.body) }); return { ok: true, status: 200, json: async () => ({ message: { ok: true } }) } }
	try {
		await getAuditPendingDashboard(false); await getAuditPendingDashboard(true)
		await getAuditPendingBreakdown("FP-1")
		await getAuditPendingDispatchDetail("FP-1", plan.dispatch_history[0])
		assert.deepEqual(requests.map(row => row.args), [{ show_partially_dispatched: 0 }, { show_partially_dispatched: 1 }, { finishing_plan: "FP-1" }, { finishing_plan: "FP-1", source_doctype: "SD YRP Finishing Plan Dispatch", source_name: "D-1", stock_entry: "STE-1" }])
		assert.ok(requests.every(row => row.url.startsWith("/api/method/essdee_yrp.accounts.audit_pending.")))
	} finally { globalThis.fetch = previousFetch; globalThis.window = previousWindow }
})

test("dashboard renders MRP metrics, Generate selects the checked mode and Reset returns to default", async () => {
	const requests = []
	const mounted = mount({ getAuditPendingDashboard: async mode => { requests.push(mode); return dashboard }, getAuditPendingBreakdown: async () => breakdown(6), getAuditPendingDispatchDetail: async () => ({}) })
	try {
		await settle()
		assert.ok(text(mounted.root).includes("15-05-2026"))
		assert.ok(text(mounted.root).includes("6 pcs"))
        assert.equal(findNodes(mounted.root, node => node.type === "article" && node.props.class?.includes("pending-card--")).length, 4)
        assert.deepEqual(findNodes(mounted.root, node => node.props.role === "tab").map(node => text(node).trim()), ["Top", "Bottom"])
        assert.ok(text(mounted.root).includes("No quantities pending"))
        assert.ok(!readFileSync(new URL("../src/departments/accounts/reports/AuditPendingFinishingPlans.vue", import.meta.url), "utf8").includes("<h2>Audit Pending Finishing Plans</h2>"))
		assert.equal(findNodes(mounted.root, node => node.props.class === "summary-card").length, 4)
		findNodes(mounted.root, node => node.type === "input" && node.props.type === "checkbox")[0].props["onUpdate:modelValue"](true)
		findNodes(mounted.root, node => node.type === "report-shell")[0].props.onGenerate(); await settle()
		findNodes(mounted.root, node => node.type === "report-shell")[0].props.onReset(); await settle()
		assert.deepEqual(requests, [false, true, false])
		assert.ok(findNodes(mounted.root, node => node.type === "a" && node.props.href === "/web/finishing/plans/FP-1").length)
	} finally { mounted.close() }
})

test("refresh discards pending quantities from an older generation", async () => {
	const pending = []
	const mounted = mount({ getAuditPendingDashboard: async () => dashboard, getAuditPendingBreakdown: () => { const item = deferred(); pending.push(item); return item.promise }, getAuditPendingDispatchDetail: async () => ({}) })
	try {
		await settle(); assert.equal(pending.length, 1)
		findNodes(mounted.root, node => node.type === "report-shell")[0].props.onGenerate(); await settle()
		assert.equal(pending.length, 2)
		pending[1].resolve(breakdown(7)); await settle()
		pending[0].resolve(breakdown(999)); await settle()
		assert.ok(text(mounted.root).includes("7 pcs")); assert.ok(!text(mounted.root).includes("999 pcs"))
	} finally { mounted.close() }
})

test("failed refresh preserves the last successful master rows and all pending matrices", async () => {
	let requests = 0
	const refresh = deferred()
	const mounted = mount({ getAuditPendingDashboard: async () => ++requests === 1 ? dashboard : refresh.promise, getAuditPendingBreakdown: async () => breakdown(6), getAuditPendingDispatchDetail: async () => ({}) })
	const pendingCards = () => findNodes(mounted.root, node => node.type === "article" && node.props.class?.includes("pending-card--"))
	try {
		await settle()
		assert.equal(pendingCards().length, 4)
		assert.ok(text(mounted.root).includes("6 pcs"))
		findNodes(mounted.root, node => node.type === "report-shell")[0].props.onGenerate()
		await settle()
		assert.equal(pendingCards().length, 4, "keep previous matrices while refreshing")
		refresh.reject(new Error("Dashboard unavailable"))
		await settle()
		assert.equal(pendingCards().length, 4, "a failed refresh must retain the previous matrices")
		assert.ok(text(mounted.root).includes("6 pcs"))
		assert.ok(findNodes(mounted.root, node => node.type === "a" && node.props.href === "/web/finishing/plans/FP-1").length)
		assert.ok(!text(mounted.root).includes("No pending quantities are available."))
		assert.equal(findNodes(mounted.root, node => node.type === "report-shell")[0].props.error, "Dashboard unavailable")
	} finally { mounted.close() }
})

test("closed dispatch detail ignores late responses and a later failure stays retryable", async () => {
	const requests = []
	const mounted = mount({ getAuditPendingDashboard: async () => dashboard, getAuditPendingBreakdown: async () => breakdown(6), getAuditPendingDispatchDetail: () => { const item = deferred(); requests.push(item); return item.promise } })
	try {
		await settle()
		const history = () => findNodes(mounted.root, node => node.type === "tr" && node.props.class === "history-row")[0]
		history().props.onClick(); await settle()
		findNodes(mounted.root, node => node.type === "button" && node.props.class === "modal-close")[0].props.onClick()
		requests[0].resolve({ destination: "Stale dispatch", rows: [], totals: {} }); await settle()
		assert.equal(findNodes(mounted.root, node => node.props.role === "dialog").length, 0)
		history().props.onClick(); await settle()
		requests[1].reject(new Error("Dispatch unavailable")); await settle()
		assert.ok(text(mounted.root).includes("Dispatch unavailable")); assert.ok(!text(mounted.root).includes("Stale dispatch"))
		assert.ok(findNodes(mounted.root, node => node.type === "button" && text(node).includes("Try again")).length)
	} finally { mounted.close() }
})

test("Desk loads a createApp wrapper for the same dashboard and Accounts links to it", () => {
	const read = path => readFileSync(new URL(path, import.meta.url), "utf8")
	assert.match(read("../src/desk/AuditPendingDesk.vue"), /import AuditPendingFinishingPlans from "\.\.\/departments\/accounts\/reports\/AuditPendingFinishingPlans.vue"/)
	assert.match(read("../src/desk/auditPendingDesk.js"), /createApp\(AuditPendingDesk\)/)
	const page = JSON.parse(read("../../essdee_yrp/essdee_yrp/page/audit_pending_finishing_plans/audit_pending_finishing_plans.json"))
	assert.equal(page.name, "audit-pending-finishing-plans")
	assert.deepEqual(page.roles.map(row => row.role), ["Accounts User", "Accounts Manager", "System Manager"])
	const workspace = JSON.parse(read("../../essdee_yrp/essdee_yrp/workspace/accounts/accounts.json"))
	assert.ok(workspace.links.some(link => link.link_type === "Page" && link.link_to === page.name))
	assert.match(read("../../essdee_yrp/essdee_yrp/page/audit_pending_finishing_plans/audit_pending_finishing_plans.js"), /frappe.require\("audit_pending_finishing_plans.bundle.js"\)/)
})

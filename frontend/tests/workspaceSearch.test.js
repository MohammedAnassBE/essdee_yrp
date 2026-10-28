import assert from "node:assert/strict"
import test from "node:test"

import {
	isWorkspaceSearchShortcut,
	visibleWorkspaceCards,
	workspaceReportTarget,
	workspaceSearchGroups,
	workspaceSearchRank,
} from "../src/components/common/workspaceSearch.js"

const CARDS = [
	{ key: "work_orders", label: "Work Orders", icon: "pi pi-briefcase", to: "/merch/work-orders" },
	{ key: "delivery_challans", label: "Delivery Challans", icon: "pi pi-truck", to: "/merch/delivery-challans" },
	{ key: "goods_received_notes", label: "Goods Received Notes", icon: "pi pi-inbox", to: "/merch/goods-received-notes" },
	{ key: "purchase_orders", label: "Purchase Orders", icon: "pi pi-shopping-cart", to: "/merch/purchase-orders" },
	{ key: "reports", label: "Reports", icon: "pi pi-chart-bar", to: "/merch/reports" },
]
const REPORTS = [
	{ value: "stock-balance", label: "Stock Balance" },
	{ value: "grn-report", label: "GRN Report", group: "Stores" },
	{ value: "inward-quantity", label: "Inward Quantity", group: "Production" },
]
const labels = (groups) => groups.map((group) => [group.label, group.items.map((item) => item.label)])

test("an empty search lists every card then every report, grouped", () => {
	assert.deepEqual(labels(workspaceSearchGroups(CARDS, REPORTS, "")), [
		["Cards", ["Work Orders", "Delivery Challans", "Goods Received Notes", "Purchase Orders", "Reports"]],
		["Reports", ["Stock Balance", "GRN Report", "Inward Quantity"]],
	])
})

test("options carry their kind and identity", () => {
	const [cards, reports] = workspaceSearchGroups(CARDS.slice(0, 1), REPORTS.slice(0, 1), "")
	assert.deepEqual(cards.items[0], { type: "card", id: "card:work_orders", key: "work_orders", label: "Work Orders", group: "", icon: "pi pi-briefcase" })
	assert.deepEqual(reports.items[0], { type: "report", id: "report:stock-balance", key: "stock-balance", label: "Stock Balance", group: "", icon: "pi pi-table" })
})

test("search ignores case and matches label or group words", () => {
	assert.deepEqual(labels(workspaceSearchGroups(CARDS, REPORTS, "ORDER")), [["Cards", ["Work Orders", "Purchase Orders"]]])
	assert.deepEqual(labels(workspaceSearchGroups(CARDS, REPORTS, "production")), [["Reports", ["Inward Quantity"]]])
	assert.deepEqual(workspaceSearchGroups(CARDS, REPORTS, "nothing here"), [])
})

test("initials find cards: GRN and DC", () => {
	assert.deepEqual(labels(workspaceSearchGroups(CARDS, REPORTS, "grn")), [["Cards", ["Goods Received Notes"]], ["Reports", ["GRN Report"]]])
	assert.deepEqual(labels(workspaceSearchGroups(CARDS, [], "DC")), [["Cards", ["Delivery Challans"]]])
})

test("initials skip small words like of, and, &", () => {
	assert.ok(workspaceSearchRank("bom", { label: "Bill of Materials" }) >= 0)
	assert.ok(workspaceSearchRank("mp", { label: "Merch & Purchase" }) >= 0)
})

test("aliases find labels whose initials differ", () => {
	assert.equal(workspaceSearchGroups(CARDS, [], "po")[0].items[0].label, "Purchase Orders")
	assert.ok(workspaceSearchRank("ppo", { label: "Production Orders" }) >= 0)
	assert.ok(workspaceSearchRank("ste", { label: "Stock Entries" }) >= 0)
	assert.ok(workspaceSearchRank("ipd", { label: "Item Production Details" }) >= 0)
})

test("label prefix and acronym matches rank above plain substring matches", () => {
	const cards = [
		{ key: "a", label: "Fabric Work Orders" },
		{ key: "b", label: "Work Orders" },
		{ key: "c", label: "Washing Orders" },
	]
	assert.deepEqual(labels(workspaceSearchGroups(cards, [], "wo")), [["Cards", ["Work Orders", "Fabric Work Orders", "Washing Orders"]]])
	assert.deepEqual(labels(workspaceSearchGroups(cards, [], "work")), [["Cards", ["Work Orders", "Fabric Work Orders"]]])
})

test("a picked card leaves only that card; no pick shows every card", () => {
	assert.deepEqual(visibleWorkspaceCards(CARDS, "delivery_challans").map((card) => card.key), ["delivery_challans"])
	assert.equal(visibleWorkspaceCards(CARDS, "").length, CARDS.length)
	assert.equal(visibleWorkspaceCards(CARDS, "missing").length, CARDS.length)
})

test("a picked report opens the department report page on that report", () => {
	assert.deepEqual(workspaceReportTarget("/cutting/reports", "multi-ccr"), { path: "/cutting/reports", query: { report: "multi-ccr" } })
	assert.deepEqual(
		workspaceReportTarget({ path: "/sewing/reports", query: { supplier: "Unit 1" } }, "dpr"),
		{ path: "/sewing/reports", query: { supplier: "Unit 1", report: "dpr" } },
	)
	assert.deepEqual(workspaceReportTarget("/sewing/reports", "dpr", "tab"), { path: "/sewing/reports", query: { tab: "dpr" } })
})

test("slash and Ctrl/Cmd+K focus the search except while typing", () => {
	const body = { tagName: "BODY", isContentEditable: false }
	const input = { tagName: "INPUT", isContentEditable: false }
	assert.equal(isWorkspaceSearchShortcut({ key: "/", target: body }), true)
	assert.equal(isWorkspaceSearchShortcut({ key: "k", ctrlKey: true, target: body }), true)
	assert.equal(isWorkspaceSearchShortcut({ key: "K", metaKey: true, target: body }), true)
	assert.equal(isWorkspaceSearchShortcut({ key: "k", ctrlKey: true, target: input }), false)
	assert.equal(isWorkspaceSearchShortcut({ key: "/", target: input }), false)
	assert.equal(isWorkspaceSearchShortcut({ key: "/", target: { tagName: "DIV", isContentEditable: true } }), false)
	assert.equal(isWorkspaceSearchShortcut({ key: "/", ctrlKey: true, target: body }), false)
	assert.equal(isWorkspaceSearchShortcut({ key: "k", target: body }), false)
})

test("the launcher shows only the picked card, gives reports only with a visible Reports card, and restores on clear", async () => {
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
	const component = loadComponent(new URL("../src/components/common/WorkspaceLauncher.vue", import.meta.url).pathname, {
		"primevue/skeleton": stub("skeleton"),
		"vue-router": { RouterLink: stub("router-link") },
		"../../router/departmentLock.js": { isWorkspaceInLayout: () => true },
		"../../router/listPermission.js": { canOpenList: () => true },
		"../navigation/InlinePageNavigation.vue": stub("navigation"),
		"./WorkspaceSearch.vue": stub("workspace-search"),
	})
	const props = Vue.reactive({ title: "Merch", items: CARDS, reports: REPORTS })
	const root = mountComponent({ render: () => Vue.h(component, props) }, {})
	const cardKeys = () => findNodes(root, (node) => node.type === "router-link").map((node) => node.props.to)
	const search = () => findNodes(root, (node) => node.type === "workspace-search")[0]
	try {
		assert.equal(cardKeys().length, CARDS.length)
		assert.deepEqual(search().props.reports, REPORTS)
		assert.equal(search().props["reports-to"], "/merch/reports")
		search().props.onSelectCard("delivery_challans")
		await Vue.nextTick()
		assert.deepEqual(cardKeys(), ["/merch/delivery-challans"])
		search().props.onSelectCard("")
		await Vue.nextTick()
		assert.equal(cardKeys().length, CARDS.length)
		props.items = CARDS.filter((card) => card.key !== "reports")
		await Vue.nextTick()
		assert.deepEqual(search().props.reports, [])
	} finally { root.__vue_app__.unmount() }
})

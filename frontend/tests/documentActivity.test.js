import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as activityUtils from "../src/utils/documentActivity.js"
import { formatRelativeTime } from "../src/composables/live/useRelativeTime.js"

const { activityRefreshKey, describeActivityEntry, formatActivityValue, isSavedDocumentName } = activityUtils
const source = (path) => readFileSync(resolve(`frontend/src/${path}`), "utf8")
const tick = async () => { for (let index = 0; index < 3; index += 1) { await new Promise((done) => setImmediate(done)); await Vue.nextTick() } }
const textOf = (node) => node.type === "comment" ? "" : (node.text || "") + node.children.map(textOf).join("")
const lineText = (line) => line.map((segment) => segment.text).join("")
const Button = (props) => Vue.h("button", props, props.label)
const toggleOf = (root) => findNodes(root, (node) => node.props.class === "document-activity__toggle")[0]
async function expand(root) { toggleOf(root).props.onClick(); await tick() }

function activityPage(versions, { hasMore = false, nextStart = versions.length } = {}) {
	return {
		created: { user: "maker@test", user_name: "Maker One", at: "2026-10-20 09:05:00.123", amended_from: null },
		modified: { user: "editor@test", user_name: "Editor Two", at: "2026-10-23 14:30:59.000" },
		versions, has_more: hasMore, next_start: nextStart,
	}
}

function version(name, overrides = {}) {
	return { name, user: "editor@test", user_name: "Editor Two", at: "2026-10-22 11:07:00", events: [], via: null, amended_from: null, changes: [], rows_added: [], rows_removed: [], row_changes: [], ...overrides }
}

async function activityComponent(getDocumentActivity) {
	return loadComponent(resolve("frontend/src/components/documents/DocumentActivity.vue"), {
		"primevue/button": Button,
		"../../api/frappe.js": { getDocumentActivity },
		"../../utils/documentActivity.js": activityUtils,
		// The shared 30 s ticker would keep the test process alive; one computed is enough here.
		"../../composables/live/useRelativeTime.js": { useRelativeTime: (value) => Vue.computed(() => formatRelativeTime(Vue.toValue(value))) },
	})
}

test("only saved document names count as saved", () => {
	assert.equal(isSavedDocumentName("DC-2026-00011"), true)
	for (const name of ["", null, undefined, "new-yrp-delivery-challan-1", "  "]) assert.equal(isSavedDocumentName(name), false, String(name))
})

test("activity values use the form display format", () => {
	assert.equal(formatActivityValue("2026-10-23", "Date"), "23-10-2026")
	assert.equal(formatActivityValue("23-10-2026", "Date"), "23-10-2026")
	assert.equal(formatActivityValue("23-10-2026 14:05:09", "Datetime"), "23-10-2026 14:05")
	assert.equal(formatActivityValue(1, "Check"), "Yes")
	assert.equal(formatActivityValue(0, "Check"), "No")
	assert.equal(formatActivityValue(null, "Data"), "(empty)")
	assert.equal(formatActivityValue("", "Link"), "(empty)")
	assert.equal(formatActivityValue(0, "Float"), "0")
	assert.equal(formatActivityValue("₹ 2,100.99", "Currency"), "₹ 2,100.99")
})

test("version entries are summarised like the Desk timeline", () => {
	const lines = describeActivityEntry(version("v1", {
		events: ["submitted"],
		changes: [{ label: "Posting Date", fieldtype: "Date", old: "2026-10-01", new: "2026-10-02" }, { label: "Is Urgent", fieldtype: "Check", old: 0, new: 1 }],
		rows_added: [{ table: "Items", count: 2 }],
		rows_removed: [{ table: "Items", count: 1 }],
		row_changes: [{ table: "Items", row: 3, changes: [{ label: "Qty", fieldtype: "Float", old: "21", new: "22" }] }],
	})).map(lineText)
	assert.deepEqual(lines, [
		"submitted this document",
		"changed Posting Date from 01-10-2026 to 02-10-2026, Is Urgent from No to Yes",
		"added 2 rows to Items",
		"removed 1 row from Items",
		"changed values for Items row #3: Qty from 21 to 22",
	])
	assert.deepEqual(describeActivityEntry(version("v2", { events: ["cancelled"] })).map(lineText), ["cancelled this document"])
	assert.deepEqual(describeActivityEntry(version("v3", { events: ["amended"], amended_from: "DC-1" })).map(lineText), ["amended this from DC-1"])
	assert.deepEqual(describeActivityEntry(version("v4", { events: ["created"], via: "Data Import DI-1" })).map(lineText), ["created this document via Data Import DI-1"])
})

test("refresh key follows saves, submits and cancels", () => {
	assert.equal(activityRefreshKey({ modified: "2026-10-23 10:00:00", docstatus: 1, status: "Submitted" }), "2026-10-23 10:00:00")
	assert.equal(activityRefreshKey({ docstatus: 1, status: "Submitted" }), "1|Submitted")
	assert.equal(activityRefreshKey({ name: "L-1" }), "")
	assert.equal(activityRefreshKey(null), "")
})

test("activity renders stamps and versions, newest first, and pages older entries", async () => {
	const calls = []
	const pages = [
		activityPage([version("v3", { events: ["submitted"] }), version("v2", { changes: [{ label: "Remarks", fieldtype: "Data", old: "a", new: "b" }] })], { hasMore: true, nextStart: 2 }),
		activityPage([version("v1", { rows_added: [{ table: "Items", count: 1 }] })]),
	]
	const component = await activityComponent(async (doctype, name, options) => { calls.push([doctype, name, options]); return pages[calls.length - 1] })
	const root = mountComponent(component, { doctype: "YRP Delivery Challan", name: "DC-1" })
	await tick()
	assert.equal(calls.length, 0, "collapsed by default, nothing fetched")
	assert.equal(toggleOf(root).props["aria-expanded"], false)
	await expand(root)
	const text = textOf(root)
	assert.match(text, /Editor Two modified this\s*· 23-10-2026 14:30/)
	assert.match(text, /Maker One created this\s*· 20-10-2026 09:05/)
	assert.ok(text.indexOf("submitted this document") < text.indexOf("changed Remarks from a to b"))
	assert.deepEqual(calls[0], ["YRP Delivery Challan", "DC-1", { start: 0, pageLength: 10 }])
	const more = findNodes(root, (node) => node.type === "button" && node.props.label === "Show more")
	assert.equal(more.length, 1)
	more[0].props.onClick()
	await tick()
	assert.deepEqual(calls[1][2], { start: 2, pageLength: 10 })
	assert.match(textOf(root), /added 1 row to Items/)
	assert.equal(findNodes(root, (node) => node.type === "button" && node.props.label === "Show more").length, 0)
	assert.equal(textOf(toggleOf(root)).trim(), "Activity3")
	await expand(root)
	await expand(root)
	assert.equal(calls.length, 2, "re-expanding reuses loaded activity")
})

test("activity collapses and stays hidden for unsaved documents", async () => {
	const calls = []
	const component = await activityComponent(async (...args) => { calls.push(args); return activityPage([]) })
	for (const name of ["", "new-yrp-delivery-challan-1"]) {
		const root = mountComponent(component, { doctype: "YRP Delivery Challan", name })
		await tick()
		assert.equal(findNodes(root, (node) => node.type === "section").length, 0)
	}
	assert.equal(calls.length, 0)
	const root = mountComponent(component, { doctype: "YRP Delivery Challan", name: "DC-9" })
	await tick()
	assert.equal(calls.length, 0)
	const toggle = toggleOf(root)
	await expand(root)
	assert.match(textOf(root), /No changes recorded since creation\./)
	assert.doesNotMatch(textOf(root), /Last modified/)
	assert.equal(calls.length, 1)
	toggle.props.onClick()
	await tick()
	assert.doesNotMatch(textOf(root), /created this/)
	assert.match(textOf(root), /Last modified 23-10-2026/)
	assert.equal(toggle.props["aria-expanded"], false)
})

test("activity refetches when the loaded record is saved or submitted", async () => {
	const calls = []
	const component = await activityComponent(async (...args) => { calls.push(args); return activityPage([]) })
	const props = Vue.reactive({ doctype: "SD YRP Lot", name: "L-1", record: null })
	const root = mountComponent(component, props)
	await tick()
	await expand(root)
	props.record = { modified: "2026-10-23 10:00:00", docstatus: 0, status: "Draft" }
	await tick()
	props.record = { modified: "2026-10-23 10:00:00", docstatus: 0 }
	await tick()
	assert.equal(calls.length, 1)
	props.record = { modified: "2026-10-23 10:05:00", docstatus: 1 }
	await tick()
	assert.equal(calls.length, 2)
	props.name = "L-2"
	await tick()
	assert.equal(calls.length, 2, "another document starts collapsed")
	await expand(root)
	assert.deepEqual(calls.map((call) => call[1]), ["L-1", "L-1", "L-2"])
})

test("collapsed activity marks saves stale and fetches once on expand", async () => {
	const calls = []
	const component = await activityComponent(async (...args) => { calls.push(args); return activityPage([version("v1")]) })
	const props = Vue.reactive({ doctype: "SD YRP Lot", name: "L-1", record: { modified: "2026-10-23 10:00:00" } })
	const root = mountComponent(component, props)
	await tick()
	props.record = { modified: "2026-10-23 10:05:00" }
	await tick()
	assert.equal(calls.length, 0)
	assert.equal(textOf(toggleOf(root)).trim(), "Activity")
	await expand(root)
	assert.equal(calls.length, 1)
	assert.equal(textOf(toggleOf(root)).trim(), "Activity1")
})

test("activity uses the page delivered with the document once, then fetches", async () => {
	const calls = []
	const component = await activityComponent(async (...args) => { calls.push(args); return activityPage([version("v9", { changes: [{ label: "Remarks", fieldtype: "Data", old: "x", new: "y" }] })]) })
	const initial = activityPage([version("v1", { changes: [{ label: "Remarks", fieldtype: "Data", old: "a", new: "b" }] })], { hasMore: true, nextStart: 1 })
	const props = Vue.reactive({ doctype: "YRP Delivery Challan", name: "DC-1", record: { modified: "2026-10-23 10:00:00" }, initialPage: initial })
	const root = mountComponent(component, props)
	await tick()
	assert.equal(calls.length, 0)
	assert.equal(toggleOf(root).props["aria-expanded"], false)
	assert.equal(textOf(toggleOf(root)).trim(), "Activity1+", "delivered page gives the collapsed count")
	assert.match(textOf(root), /Last modified 23-10-2026/)
	await expand(root)
	assert.match(textOf(root), /changed Remarks from a to b/)
	findNodes(root, (node) => node.type === "button" && node.props.label === "Show more")[0].props.onClick()
	await tick()
	assert.deepEqual(calls.map((call) => call[2]), [{ start: 1, pageLength: 10 }])
	props.record = { modified: "2026-10-23 10:05:00" }
	await tick()
	assert.deepEqual(calls.map((call) => call[2].start), [1, 0], "a consumed page is never reused")
	props.initialPage = activityPage([version("v2", { changes: [{ label: "Remarks", fieldtype: "Data", old: "b", new: "c" }] })])
	props.record = { modified: "2026-10-23 10:09:00" }
	await tick()
	assert.equal(calls.length, 2, "a new payload page replaces the fetch")
	assert.match(textOf(root), /changed Remarks from b to c/)
	props.name = "DC-2"
	await tick()
	await expand(root)
	assert.equal(calls.at(-1)[1], "DC-2")
})

test("fabric document shell and Purchase Order dialog pass the payload activity page", () => {
	assert.match(source("departments/fabric-store/FabricDocumentWorkspace.vue"), /<DocumentActivity [^>]*:initial-page="workspace\.activity \?\? null"/)
	assert.match(source("departments/fabric-store/PurchaseOrderDialog.vue"), /<DocumentActivity [^>]*:initial-page="payload\.activity \?\? null"/)
})

test("shared document shells include the activity section", async () => {
	const DepartmentPage = loadComponent(resolve("frontend/src/components/DepartmentPage.vue"), {
		"primevue/card": (props, { slots }) => Vue.h("card", props, slots.content?.()),
		"./documents/DocumentActivity.vue": (props) => Vue.h("document-activity", props),
		"./navigation/BackLink.vue": () => Vue.h("back-link"),
		"./navigation/pageNavigationContext.js": { pageNavigationKey: Symbol("navigation") },
		"../router/departmentLock.js": { isLockedExit: () => false },
	})
	const record = { name: "L-1", modified: "2026-10-23 10:00:00" }
	const withActivity = mountComponent(DepartmentPage, { title: "Lot", activityDoctype: "SD YRP Lot", activityName: "L-1", activityRecord: record })
	const [activity] = findNodes(withActivity, (node) => node.type === "document-activity")
	assert.deepEqual([activity.props.doctype, activity.props.name, activity.props.record], ["SD YRP Lot", "L-1", record])
	assert.equal(findNodes(mountComponent(DepartmentPage, { title: "Lots" }), (node) => node.type === "document-activity").length, 0)

	assert.match(source("departments/fabric-store/FabricDocumentWorkspace.vue"), /<DocumentActivity v-if="showActivity" :doctype="record\.doctype \|\| doctype" :name="record\.name \|\| ''"/)
})

test("every routed document page and document dialog wires the activity section", () => {
	const workspacePages = [
		"departments/FabricWorkOrder.vue", "departments/FabricPurchaseOrder.vue", "departments/hr/BillTracking.vue", "departments/quality/QualityInspection.vue",
		"departments/sales/ProductionOrder.vue", "departments/merch/lot/MerchLotPage.vue", "departments/merch/ipd/IpdPage.vue", "departments/merch/process-cost/ProcessCostPage.vue",
		"departments/planning/lot/LotPage.vue", "departments/purchase/lot/LotPage.vue", "departments/purchase/ItemPricePage.vue", "departments/accounts/PurchaseInvoice.vue",
		"departments/fabric-store/DeliveryChallanWorkspace.vue", "departments/fabric-store/GoodsReceivedNoteWorkspace.vue",
	]
	for (const page of workspacePages) {
		assert.match(source(page), /<FabricDocumentWorkspace/, page)
		assert.doesNotMatch(source(page), /:show-activity="false"/, page)
	}
	const shellPages = {
		"departments/CuttingBulkLaySheet.vue": "SD YRP Cutting Bulk Lay Sheets", "departments/CuttingLaySheetPlanner.vue": "SD YRP Cutting Laysheet Planner",
		"departments/CuttingOrder.vue": "SD YRP Cutting Order", "departments/CuttingPlan.vue": "SD YRP Cutting Plan",
		"departments/finishing/FinishingPlan.vue": "SD YRP Finishing Plan", "departments/finishing/FinishingDispatch.vue": "SD YRP Finishing Plan Dispatch",
		"departments/pd/ProductPage.vue": "SD YRP Product", "departments/pd/ProductReleasePage.vue": "SD YRP Product Release",
		"departments/pd/LotwiseItemProfitPage.vue": "SD YRP Lotwise Item Profit", "departments/purchase/ItemPage.vue": "Item",
		"departments/cut-panel-store/BoxStickerPrintPage.vue": "SD YRP Box Sticker Print",
	}
	for (const [page, doctype] of Object.entries(shellPages)) assert.match(source(page), new RegExp(`activity-doctype="${doctype}"`), page)
	const dialogs = [
		"components/documents/DocumentTransactionDialog.vue", "departments/accounts/Debits.vue",
		"departments/cut-panel-store/CutBundleEditDialog.vue", "departments/cut-panel-store/CutPanelMovementDialog.vue", "departments/cut-panel-store/ExcelStickerPrintDialog.vue",
		"departments/cutting/CpmMovementDialog.vue", "departments/cutting/CpmTransactionDialog.vue", "departments/cutting/CuttingLaySheetDialog.vue",
		"departments/cutting/CuttingMarkerDialog.vue", "departments/fabric-store/PurchaseOrderDialog.vue", "departments/planning/lot/LotDocumentDialog.vue",
		"departments/purchase/lot/LotDocumentDialog.vue",
	]
	for (const dialog of dialogs) assert.match(source(dialog), /<DocumentActivity /, dialog)
})

test("collapsed summary shows the record's latest modified time relative, exact time in the tooltip", async () => {
	const component = await activityComponent(async () => activityPage([]))
	const now = new Date(Date.now() - 5 * 60_000)
	const pad = (part) => String(part).padStart(2, "0")
	const modified = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
	const root = mountComponent(component, { doctype: "SD YRP Lot", name: "L-1", record: { modified } })
	await tick()
	assert.match(textOf(root), /Last modified 5 min ago/)
	const time = findNodes(root, (node) => node.type === "time")[0]
	assert.equal(time.props.title, `${pad(now.getDate())}-${pad(now.getMonth() + 1)}-${now.getFullYear()} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`)
})

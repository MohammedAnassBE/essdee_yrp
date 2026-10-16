#!/usr/bin/env node
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

import { IPD_LIST_COLUMNS, IPD_LIST_PATH, IPD_STATUS_OPTIONS, MERCH_ROUTES, MERCH_SECTION_ORDER, ipdEditPath, ipdEditRoute, ipdPath, ipdRoute, merchLauncherItems, visibleMerchLauncherItems } from "../frontend/src/departments/merch/merchViews.js"
import { webDocumentPath } from "../frontend/src/router/webDocumentRoutes.js"
import { sectionsFor } from "../frontend/src/departments/merch/ipd/ipdEditor.js"
import { listStatusFilters } from "../frontend/src/components/common/listStatusFilters.js"

for (const [key, name] of Object.entries({ lots: "merch-lots", lotNew: "merch-lot-new", lot: "merch-lot", lotEdit: "merch-lot-edit", ipds: "merch-ipds", ipdNew: "merch-ipd-new", ipd: "merch-ipd", ipdEdit: "merch-ipd-edit" })) {
	assert.equal(MERCH_ROUTES[key], name)
}
assert.equal(new Set(Object.values(MERCH_ROUTES)).size, Object.keys(MERCH_ROUTES).length)
for (const [plural, singular] of [["productionOrders", "productionOrder"], ["workOrders", "workOrder"], ["billTrackings", "billTracking"], ["purchaseInvoices", "purchaseInvoice"]]) {
	for (const key of [plural, singular, `${singular}New`, `${singular}Edit`]) assert.ok(MERCH_ROUTES[key], key)
}
assert.equal(IPD_LIST_PATH, "/merch/item-production-details")
assert.equal(ipdPath("Hamic - White Vest RN-1"), "/merch/item-production-details/Hamic%20-%20White%20Vest%20RN-1")
assert.equal(ipdEditPath("A/B-2"), "/merch/item-production-details/A%2FB-2/edit")
assert.deepEqual(ipdRoute("X-1", { hash: "#packing" }), { name: "merch-ipd", params: { ipdId: "X-1" }, hash: "#packing" })
assert.deepEqual(ipdEditRoute("X-1"), { name: "merch-ipd-edit", params: { ipdId: "X-1" } })

// Exercise every editor exit using its current tab, including tabs changed after
// the editor first opened and the modified timestamp returned by approval.
const editorComposable = readFileSync(new URL('../frontend/src/departments/merch/ipd/useIpdEditor.js', import.meta.url), 'utf8')
const exitFunctions = ['recordLocation', 'cancel', 'redirectIfReadOnly', 'approve'].map((name) => editorComposable.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\t\\}`))[0]).join('\n')
const exits = []
const exitContext = vm.createContext({
	ipdRoute, MERCH_ROUTES,
	name: { value: 'X-1' }, record: { value: { modified: 'before' } }, route: { hash: '#item_details_tab' },
	isNew: { value: false }, acting: { value: '' }, isDirty: { value: false }, actionError: { value: '' },
	preserveListNavigationState: (name, modified) => ({ name, modified }),
	router: { push: (to) => exits.push(to), replace: (to) => exits.push(to) },
	toast: { add() {} }, executeIpdCommand: async () => ({ record: { modified: 'approved' } }),
})
vm.runInContext(exitFunctions, exitContext)
for (const hash of ['#cutting_tab', '#packing_tab', '#advance_settings_tab']) {
	exitContext.route.hash = hash
	exitContext.cancel()
	assert.equal(exits.at(-1).hash, hash, 'More > Cancel retains the selected tab')
	await exitContext.approve()
	assert.equal(exits.at(-1).hash, hash, 'approval retains the selected tab')
	assert.equal(exits.at(-1).state.modified, 'approved')
	exitContext.redirectIfReadOnly({ record: { name: 'X-1', modified: 'readonly' }, capabilities: {} })
	assert.equal(exits.at(-1).hash, hash, 'view-only redirection retains the selected tab')
	assert.equal(exitContext.recordLocation().hash, hash, 'record/View destinations read the latest hash')
}
assert.equal([...editorComposable.matchAll(/\bipdRoute\(/g)].length, 1, 'every editor-to-record destination uses recordLocation')
assert.deepEqual(IPD_LIST_COLUMNS, ["item", "version", "tech_pack_version", "pattern_version", "primary_item_attribute", "dependent_attribute", "approval_status"])
assert.deepEqual(IPD_STATUS_OPTIONS, ["Not Approved", "Approved"])
assert.equal(webDocumentPath("YRP Item Production Detail", "Casual Designer Vest - 4-18"), "/web/merch/item-production-details/Casual%20Designer%20Vest%20-%204-18")

const router = readFileSync(new URL("../frontend/src/router/index.js", import.meta.url), "utf8")
const order = ["/merch/item-production-details\"", "/merch/item-production-details/new\"", "/merch/item-production-details/:ipdId\"", "/merch/item-production-details/:ipdId/edit\""]
const positions = order.map((path) => router.indexOf(path))
assert.ok(positions.every((position) => position > 0), "every IPD route is registered")
assert.deepEqual([...positions].sort((a, b) => a - b), positions, "/new is registered before /:ipdId")

const registry = readFileSync(new URL("../frontend/src/departments/merch/ipd/ipdSectionRegistry.js", import.meta.url), "utf8")
const sectionKeys = new Set([...sectionsFor(false), ...sectionsFor(true)].map((section) => section.key))
sectionKeys.delete("review")
sectionKeys.add("settings")
for (const key of sectionKeys) assert.match(registry, new RegExp(`\\b${key}: "\\./(sections|cloth)/Ipd\\w+Section\\.vue"`), `registry entry for ${key}`)

const editor = readFileSync(new URL("../frontend/src/departments/merch/ipd/IpdEditor.vue", import.meta.url), "utf8")
assert.match(editor, /retry-label="Reload"/)
assert.match(editor, /provide\(IPD_EDITOR_KEY, editor\.api\)/)
const page = readFileSync(new URL("../frontend/src/departments/merch/ipd/IpdPage.vue", import.meta.url), "utf8")
assert.match(page, /provide\(IPD_EDITOR_KEY, readOnlyApi\)/)
assert.doesNotMatch(page, /pointer-events:\s*none/)
const launcherItems = merchLauncherItems()
assert.equal(MERCH_ROUTES.reports, "merch-reports")
assert.equal(launcherItems.at(-1).key, "reports")
assert.deepEqual(visibleMerchLauncherItems({ reports: { can_read: true } }).map(({ key, to }) => ({ key, to })), [{ key: "reports", to: "/merch/reports" }])
assert.deepEqual(visibleMerchLauncherItems({ reports: { can_read: false } }), [])
assert.match(router, /path: "\/merch\/reports", name: MERCH_ROUTES.reports, component: MerchReports/)
const layout = JSON.parse(readFileSync(new URL("../essdee_yrp/fixtures/yrp_ui_layout.json", import.meta.url), "utf8")).find((row) => row.experience_key === "merch")
assert.deepEqual(JSON.parse(layout.config).experience_props.workspaces, MERCH_SECTION_ORDER)
assert.deepEqual(launcherItems.map((item) => item.key), JSON.parse(layout.config).experience_props.workspaces)
for (const key of ["lots", "item_production_details", "production_orders", "work_orders", "bill_tracking", "purchase_invoices"]) {
	assert.ok(launcherItems.some((item) => item.key === key), key)
}
assert.equal(launcherItems.find((item) => item.key === "item_production_details").to, "/merch/item-production-details")
for (const item of launcherItems) {
	assert.deepEqual(visibleMerchLauncherItems({ [item.key]: { can_read: true } }), [item])
	assert.deepEqual(visibleMerchLauncherItems({ [item.key]: { can_create: true } }), [])
	const sections = Object.fromEntries(launcherItems.map(({ key }) => [key, { can_read: key !== item.key }]))
	assert.deepEqual(visibleMerchLauncherItems(sections), launcherItems.filter(({ key }) => key !== item.key))
	assert.ok(item.to.startsWith("/merch/"))
}
assert.deepEqual(visibleMerchLauncherItems({ item_production_details: { can_read: false } }), [])
assert.deepEqual(visibleMerchLauncherItems({}), [])
assert.deepEqual(visibleMerchLauncherItems(undefined), [])

const merch = readFileSync(new URL("../frontend/src/departments/Merch.vue", import.meta.url), "utf8")
assert.doesNotMatch(merch, /WorkspacePlaceholder/)
for (const text of ["WorkspaceLauncher", "WorkspaceLoadError", "getMerchCapabilities", "inline-navigation"]) {
	assert.ok(merch.includes(text), `Merch landing page contains ${text}`)
}
console.log("merch views tests passed")

const listView = readFileSync(new URL("../frontend/src/components/common/ListView.vue", import.meta.url), "utf8")
const listFunction = (name) => listView.match(new RegExp(`function ${name}\\([^]*?\\n\\}`))[0]
const listContext = vm.createContext({
	props: { statusField: "approval_status", initialStatus: "Not Approved" },
	effectiveStatusField: { value: "approval_status" }, effectiveStatusOptions: { value: IPD_STATUS_OPTIONS },
	activeStatus: { value: "Not Approved" }, standardFilterFields: { value: [{ fieldname: "approval_status" }] },
	advancedFilters: { value: [] }, appliedSearch: { value: "" }, appliedQuickFilters: { value: {} },
	baseFilters: () => [], listStatusFilters, hasFilterValue: (value) => value !== "" && value != null,
})
vm.runInContext(["initialStatusQuickFilters", "quickFilterTuples", "allFilters"].map(listFunction).join("\n"), listContext)
listContext.appliedQuickFilters.value = listContext.initialStatusQuickFilters()
assert.deepEqual(JSON.parse(JSON.stringify(listContext.allFilters())), [["approval_status", "=", "Not Approved"]], "initial status filters a standard-filter status field")
assert.match(listFunction("initialise"), /appliedQuickFilters\.value = initialStatusQuickFilters\(\)/)

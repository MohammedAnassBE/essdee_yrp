#!/usr/bin/env node

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

import { LAYOUT_UNAVAILABLE_PATH } from "../frontend/src/router/departmentLock.js"
import { createMemoryHistory, createRouter } from "../frontend/node_modules/vue-router/dist/vue-router.mjs"
import { MERCH_ROUTES } from "../frontend/src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../frontend/src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../frontend/src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../frontend/src/departments/purchase/purchaseViews.js"
import { departments } from "../frontend/src/departments/registry.js"
import { canOpenList, NO_PERMISSION_PATH } from "../frontend/src/router/listPermission.js"

import {
	ACCOUNTS_REPORTS,
	ACCOUNTS_ROUTES,
	PURCHASE_INVOICE_EDITOR_GROUPS,
	PURCHASE_INVOICE_LIST_COLUMNS,
	PURCHASE_INVOICE_STATUS_OPTIONS,
	accountsReportTabs,
	addGrnsWithinLimit,
	applySupplierChange,
	filterEligibleGrns,
	groupedItemTotals,
	isCurrentRecordAction,
	isMaskedValue,
	mergeKnownGrns,
	purchaseInvoiceActionItems,
	purchaseInvoiceEditorField,
	purchaseInvoicePreviewTotals,
	purchaseInvoiceSaveValues,
} from "../frontend/src/departments/accounts/accountsViews.js"

const routerSource = readFileSync(new URL("../frontend/src/router/index.js", import.meta.url), "utf8")
const routes = vm.runInNewContext(`${routerSource.slice(routerSource.indexOf("const AdministratorPage"), routerSource.indexOf("const router = createRouter"))}; routes`, {
	ACCOUNTS_ROUTES, MERCH_ROUTES, PD_ROUTES, PLANNING_ROUTES, PURCHASE_ROUTES, LAYOUT_UNAVAILABLE_PATH, NO_PERMISSION_PATH, departments,
})
const router = createRouter({ history: createMemoryHistory("/web/"), routes })
const routeProps = (path) => {
	const route = router.resolve(path)
	const props = route.matched.at(-1).props.default
	return typeof props === "function" ? props(route) : props || {}
}
const billTrackingPath = "/accounts/bill-tracking"
for (const [suffix, name] of [
	["", ACCOUNTS_ROUTES.billTrackings],
	["/new", ACCOUNTS_ROUTES.billTrackingNew],
	["/A%2FB/edit", ACCOUNTS_ROUTES.billTrackingEdit],
	["/A%2FB", ACCOUNTS_ROUTES.billTracking],
]) {
	const path = billTrackingPath + suffix
	assert.equal(router.resolve(path).name, name)
	assert.equal(router.resolve(path).matched.at(-1).components.default, router.resolve(`/merch/bill-tracking${suffix}`).matched.at(-1).components.default)
	const props = routeProps(path)
	assert.equal(props.backTo || props.basePath, suffix ? billTrackingPath : "/accounts")
	if (suffix) assert.equal(props.listRouteName, ACCOUNTS_ROUTES.billTrackings)
	if (suffix.startsWith("/A")) assert.equal(props.billTrackingId, "A/B")
}
assert.equal(router.resolve({ name: ACCOUNTS_ROUTES.billTracking, params: { billTrackingId: "A/B" } }).path, `${billTrackingPath}/A%2FB`)
assert.equal(routeProps(billTrackingPath).eyebrow, "Accounts")
assert.equal(routeProps(billTrackingPath).viewRouteName, ACCOUNTS_ROUTES.billTracking)
assert.equal(routeProps(billTrackingPath).newRouteName, ACCOUNTS_ROUTES.billTrackingNew)
const billTrackingProps = routeProps(`${billTrackingPath}/BT-1`)
assert.equal(billTrackingProps.editRouteName, ACCOUNTS_ROUTES.billTrackingEdit)
assert.equal(router.resolve({ name: billTrackingProps.purchaseInvoiceNewRouteName }).path, "/accounts/purchase-invoices/new")
assert.equal(router.resolve({ name: billTrackingProps.purchaseInvoiceViewRouteName, params: { purchaseInvoiceId: "PI/1" } }).path, "/accounts/purchase-invoices/PI%2F1")
assert.equal(departments.find(({ key }) => key === "accounts").sections.bill_tracking, "bill-tracking")
assert.equal(canOpenList(billTrackingPath, { user: { can_read: ["YRP Bill Tracking"] } }), true)
assert.equal(canOpenList(billTrackingPath, { user: { can_read: [] } }), false)
const layouts = JSON.parse(readFileSync(new URL("../essdee_yrp/fixtures/yrp_ui_layout.json", import.meta.url), "utf8"))
assert.deepEqual(JSON.parse(layouts.find(({ name }) => name === "Accounts").config).experience_props.workspaces, ["purchase_invoices", "bill_tracking", "reports", "debits"])

assert.deepEqual(
	ACCOUNTS_REPORTS.slice(0, -1).map((report) => report.key),
	["stock_balance", "cutting_dpr", "sewing_dpr", "finishing_dispatch", "ironing_dpr"],
)
assert.deepEqual(
	accountsReportTabs({ sewing_dpr: { can_read: true } }).map((tab) => tab.value),
	["sewing-dpr"],
)
assert.deepEqual(accountsReportTabs({}), [])
assert.equal(ACCOUNTS_REPORTS.at(-1).key, "audit_pending_finishing_plans")
assert.deepEqual(
	accountsReportTabs({ audit_pending_finishing_plans: { can_read: true } }).map((tab) => tab.value),
	["audit-pending"],
)
assert.deepEqual(accountsReportTabs({ audit_pending_finishing_plans: { can_read: false } }), [])
const allAccountsTabs = accountsReportTabs(Object.fromEntries(
	ACCOUNTS_REPORTS.map(({ key }) => [key, { can_read: true }]),
))
assert.deepEqual(allAccountsTabs.map(({ value }) => value), [
	"stock-balance", "cutting-dpr", "sewing-dpr", "finishing-dispatch", "ironing-dpr", "audit-pending",
])
const auditPendingComponent = readFileSync(new URL("../frontend/src/departments/accounts/reports/AuditPendingFinishingPlans.vue", import.meta.url), "utf8")
for (const contract of [
    "ReportShell", "getAuditPendingDashboard", "getAuditPendingBreakdown", "getAuditPendingDispatchDetail",
    "filters.plan", "filters.lot", "filters.item", "filters.status", "filters.age",
    "/finishing/plans/${encodeURIComponent(name)}", "Overdue Plans", "Fully Dispatched", "Oldest Pending",
    "Show Partially Dispatched", "Total Cut", "Sewing Rx", "Packed", "Boxes Dispatched", "Dispatch History",
    "Size-wise Dispatch Detail", "selectedPart.sizes", "category.size_totals", "row.total", "category.total",
    "var(--erp-surface)", "var(--erp-text)", "pendingGeneration", "detailGeneration",
]) assert.ok(auditPendingComponent.includes(contract), `Missing Audit Pending contract: ${contract}`)
assert.ok(!auditPendingComponent.includes("useWebReport"), "The legacy flat audit report has been replaced")
const accountsReportPage = readFileSync(new URL("../frontend/src/departments/accounts/AccountsReports.vue", import.meta.url), "utf8")
assert.ok(accountsReportPage.includes('audit_pending_finishing_plans: defineAsyncComponent(() => import("./reports/AuditPendingFinishingPlans.vue"))'))
const reportProvider = readFileSync(new URL("../essdee_yrp/web_reports.py", import.meta.url), "utf8")
assert.ok(!reportProvider.includes('key="accounts-audit-pending-finishing-plans"'), "The obsolete flat report registration has been removed")

assert.deepEqual(
	groupedItemTotals(
		[
			{ qty: 10, rate: 12.5, tax: "GST 5" },
			{ qty: 2, rate: 100, tax_rate: 12 },
		],
		{ "GST 5": 5 },
	),
	{ total: 325, totalTax: 30.25, grandTotal: 355.25, quantity: 12 },
)
assert.deepEqual(groupedItemTotals([], {}), {
	total: 0,
	totalTax: 0,
	grandTotal: 0,
	quantity: 0,
})
assert.deepEqual(groupedItemTotals([{ qty: 1, rate: 53.5, tax_rate: 5 }]), {
	total: 53.5,
	totalTax: 2.68,
	grandTotal: 56.18,
	quantity: 1,
})
assert.deepEqual(groupedItemTotals([{ qty: 1, rate: 16.9, tax_rate: 5 }]), {
	total: 16.9,
	totalTax: 0.84,
	grandTotal: 17.74,
	quantity: 1,
})
assert.deepEqual(
	groupedItemTotals(Array.from({ length: 33 }, () => ({ qty: 1, rate: 53.5, tax_rate: 5 }))),
	{ total: 1765.5, totalTax: 88.27, grandTotal: 1853.78, quantity: 33 },
)
assert.deepEqual(
	groupedItemTotals(Array.from({ length: 2 }, () => ({ qty: 1, rate: 53.5, tax_rate: 5 }))),
	{ total: 107, totalTax: 5.35, grandTotal: 112.35, quantity: 2 },
)
const tinyTotals = groupedItemTotals([{ qty: 0.001, rate: 0.01, tax_rate: 5 }])
assert.deepEqual(tinyTotals, { total: 0, totalTax: 0, grandTotal: 0, quantity: 0 })
assert.equal(Number.isNaN(tinyTotals.totalTax), false)
assert.deepEqual(groupedItemTotals([{ qty: -1, rate: 16.9, tax_rate: 5 }]), {
	total: -16.9,
	totalTax: -0.84,
	grandTotal: -17.74,
	quantity: -1,
})
const negativeTinyTotals = groupedItemTotals([{ qty: -0.001, rate: 0.01, tax_rate: 5 }])
assert.deepEqual(negativeTinyTotals, { total: 0, totalTax: 0, grandTotal: 0, quantity: 0 })
assert.equal(Object.values(negativeTinyTotals).some((value) => Object.is(value, -0)), false)

assert.equal(PURCHASE_INVOICE_EDITOR_GROUPS.at(-1).key, "notes")
assert.deepEqual(
	purchaseInvoiceEditorField("supplier", { locked_fields: ["supplier"] }),
	{
		label: "Supplier", fieldtype: "Link", options: "Supplier", reqd: true,
		fieldname: "supplier", link_filters: { disabled: 0 }, read_only: true,
	},
)
assert.deepEqual(purchaseInvoicePreviewTotals([{ qty: 2, rate: 10, tax_rate: 5 }], {}), [
	{ key: "total", label: "Total", value: "20.00" },
	{ key: "tax", label: "Tax", value: "1.00" },
	{ key: "grand-total", label: "Grand Total", value: "21.00" },
	{ key: "quantity", label: "Quantity", value: "2" },
])
assert.deepEqual(
	purchaseInvoiceSaveValues({ supplier: "XXXX", bill_no: "B-1", bill_tracking: "BT-1" }, ["supplier", "bill_no"]),
	{ bill_no: "B-1", bill_tracking: "BT-1" },
)

const current = {
	values: { supplier: "A", billing_supplier: "A", bill_no: "INV-1" },
	grns: ["GRN-1"],
	items: [{}],
}
const next = applySupplierChange(current, "B")
assert.deepEqual(
	[next.values.supplier, next.values.billing_supplier, next.grns.length, next.items.length],
	["B", "B", 0, 0],
)
assert.equal(next.values.bill_no, "INV-1")
assert.notEqual(next, current)
assert.notEqual(next.values, current.values)
assert.deepEqual(current.grns, ["GRN-1"])

const eligibleGrns = [
	{ name: "GRN-1", against_id: "PO-100", supplier_document_no: "BILL-A" },
	{ name: "GRN-2", against_id: "WO-200", supplier_document_no: null },
]
assert.deepEqual(filterEligibleGrns(eligibleGrns, "grn-2"), [eligibleGrns[1]])
assert.deepEqual(filterEligibleGrns(eligibleGrns, "po-100"), [eligibleGrns[0]])
assert.deepEqual(filterEligibleGrns(eligibleGrns, "bill-a"), [eligibleGrns[0]])
assert.equal(filterEligibleGrns(eligibleGrns, "missing").length, 0)
assert.strictEqual(filterEligibleGrns(eligibleGrns, ""), eligibleGrns)
assert.deepEqual(filterEligibleGrns(eligibleGrns, "missing", ["GRN-2"]), [eligibleGrns[1]])
const knownGrns = mergeKnownGrns([], eligibleGrns, ["GRN-2", "GRN-SAVED"])
assert.deepEqual(knownGrns, [
	eligibleGrns[0],
	eligibleGrns[1],
	{ name: "GRN-SAVED", selected: true },
])
assert.deepEqual(mergeKnownGrns(knownGrns, [
	{ name: "GRN-SAVED", posting_date: "2026-10-13", selected: false },
	{ name: "GRN-3", against_id: "PO-300" },
], []), [
	eligibleGrns[0],
	eligibleGrns[1],
	{ name: "GRN-SAVED", posting_date: "2026-10-13", selected: false },
	{ name: "GRN-3", against_id: "PO-300" },
])
assert.deepEqual(mergeKnownGrns([], [], ["GRN-SAVED"]), [{ name: "GRN-SAVED", selected: true }])
const selected199 = Array.from({ length: 199 }, (_, index) => `GRN-${index + 1}`)
assert.deepEqual(
	addGrnsWithinLimit(selected199, ["GRN-1", "GRN-200", "GRN-201"], 200),
	[...selected199, "GRN-200"],
)
assert.deepEqual(addGrnsWithinLimit([" GRN-1 ", "GRN-1"], ["", "GRN-2"], 200), ["GRN-1", "GRN-2"])

assert.equal(isMaskedValue("XXXXXX"), true)
assert.equal(isMaskedValue("xxxxxx"), true)
assert.equal(isMaskedValue("******"), true)
assert.equal(isMaskedValue(" Xx** "), true)
assert.equal(isMaskedValue("SUP-1"), false)
assert.equal(isMaskedValue(""), false)
assert.equal(isMaskedValue("   "), false)

const submittedActions = purchaseInvoiceActionItems(
	{
		submit: { allowed: true, label: "Submit" },
		approve: { allowed: true, label: "Approve Invoice" },
		delete: { allowed: true, label: "Delete" },
	},
	{},
)
assert.equal(submittedActions.find((item) => item.primary).key, "submit")
assert.equal(submittedActions.find((item) => item.key === "delete").menuOnly, true)

const approvalActions = purchaseInvoiceActionItems(
	{
		approve: { allowed: true, label: "Approve Invoice" },
		edit: { allowed: true, label: "Edit" },
	},
	{ approve: () => "approved" },
)
assert.equal(approvalActions.find((item) => item.primary).key, "approve")
assert.equal(approvalActions.find((item) => item.key === "approve").command(), "approved")
const editActions = purchaseInvoiceActionItems({ edit: { allowed: true } }, {})
assert.equal(editActions.find((item) => item.primary).key, "edit")

const invoiceAction = { name: "PI-A", route: "/accounts/purchase-invoices/PI-A", sequence: 4 }
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction }), true)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, name: "PI-B" }), false)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, route: "/accounts/purchase-invoices/PI-B" }), false)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, sequence: 6 }), false)

assert.deepEqual(PURCHASE_INVOICE_STATUS_OPTIONS, [
	"Draft",
	"Approval Initiated",
	"Approval Pending",
	"Approved",
	"Submitted",
	"Cancelled",
])
assert.deepEqual(PURCHASE_INVOICE_LIST_COLUMNS, [
	"supplier",
	"bill_no",
	"posting_date",
	"against",
	"grand_total",
	"status",
])

const accountsRequests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	accountsRequests.push({ url, body: JSON.parse(options.body) })
	return { ok: true, status: 200, json: async () => ({ message: {} }) }
}
const { executePurchaseInvoiceCommand, getEligibleGrns, savePurchaseInvoice } = await import("../frontend/src/api/accounts.js")
await savePurchaseInvoice({ values: {}, grns: [], items: [] }, {
	name: "PI-1",
	expectedModified: "2026-10-13 10:00:00.000000",
})
await executePurchaseInvoiceCommand("PI-1", "submit", {}, "2026-10-13 10:00:00.000000")
await savePurchaseInvoice({ values: {}, grns: [], items: [] })
await getEligibleGrns({ supplier: "SUP-1", against: "Purchase Order", searchText: "needle", limit: 200 })
assert.equal(accountsRequests[0].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(accountsRequests[1].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(accountsRequests[2].body.expected_modified, null)
assert.equal(accountsRequests[3].body.limit, 200)
assert.equal(accountsRequests[3].body.search_text, "needle")

console.log("accounts views OK")

const accountsViews = await import("../frontend/src/departments/accounts/accountsViews.js")
const { Vue, findNodes, loadComponent, mountComponent } = await import("./helpers/vue_renderer.mjs")
for (const billing_supplier of ["BILLING-SUP", "", null, undefined]) {
	assert.equal(
		accountsViews.purchaseInvoiceGrnSupplier({ supplier: "BILL-SUP", billing_supplier }),
		billing_supplier || "BILL-SUP",
	)
}

const control = (props) => Vue.h("control", props)
const flush = async () => {
	await Vue.nextTick()
	await Vue.nextTick()
}
const grnRequests = []
const bodyComponent = loadComponent("frontend/src/departments/accounts/components/PurchaseInvoiceEditorBody.vue", {
	"primevue/button": control,
	"primevue/message": control,
	"primevue/column": control,
	"primevue/checkbox": control,
	"primevue/datatable": control,
	"primevue/inputtext": control,
	"primevue/tag": control,
	"../../../components/common/FormField.vue": control,
	"../../../components/documents/DocumentFieldGroupGrid.vue": control,
	"./PurchaseInvoiceGroupedItems.vue": control,
	"../accountsViews.js": accountsViews,
	"../../../api/accounts.js": {
		getEligibleGrns: async (args) => {
			grnRequests.push(args)
			return [{ name: `GRN-${args.supplier}`, total_received_quantity: 12 }]
		},
	},
})
const bodyProps = Vue.reactive({
	groups: [], grns: [], items: [], previewTotals: [], currentName: "PI-1",
	form: { supplier: "BILL-SUP", billing_supplier: "BILLING-SUP", against: "Purchase Order" },
})
mountComponent(bodyComponent, bodyProps)
await flush()
assert.equal(grnRequests.at(-1).supplier, "BILLING-SUP")
for (const billingSupplier of ["CHANGED-SUP", "", "XXXXXXXX"]) {
	const count = grnRequests.length
	bodyProps.form.billing_supplier = billingSupplier
	await flush()
	assert.equal(grnRequests.length, count + 1)
	assert.equal(grnRequests.at(-1).supplier, billingSupplier === "XXXXXXXX" ? undefined : billingSupplier || "BILL-SUP")
	assert.equal(grnRequests.at(-1).purchaseInvoice, "PI-1")
}

const fetchRequests = []
const pageComponent = loadComponent("frontend/src/departments/accounts/PurchaseInvoiceEditorPage.vue", {
	"primevue/skeleton": control,
	"primevue/usetoast": { useToast: () => ({ add() {} }) },
	"vue-router": {
		useRoute: () => ({ params: {}, query: {}, fullPath: "/accounts/purchase-invoices/PI-1/edit" }),
		useRouter: () => ({}), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {},
	},
	"../../api/accounts.js": {
		getPurchaseInvoiceEditor: async () => ({
			values: { supplier: "BILL-SUP", billing_supplier: "BILLING-SUP", against: "Purchase Order" },
			grns: ["GRN-1"], items: [{ qty: 12, rate: 5 }], is_rate_only: false,
		}),
		fetchGrnDetails: async (args) => { fetchRequests.push(args); return {} },
	},
	"../../components/DepartmentPage.vue": (_props, { slots }) => Vue.h("page", {}, slots.default()),
	"../../components/common/WorkspaceLoadError.vue": control,
	"../../components/documents/DocumentConfirmationDialog.vue": control,
	"../../components/documents/DocumentErrorDialog.vue": control,
	"../../router/listDocumentNavigation.js": { preserveListNavigationState() {} },
	"./accountsViews.js": accountsViews,
	"./components/PurchaseInvoiceEditorBody.vue": (props) => Vue.h("editor-body", props),
	"./components/PurchaseInvoiceEditorHeader.vue": control,
})
globalThis.window.addEventListener = () => {}
globalThis.window.removeEventListener = () => {}
const page = mountComponent(pageComponent, { purchaseInvoiceId: "PI-1" })
await flush()
const editorBody = () => findNodes(page, (node) => node.type === "editor-body")[0].props
editorBody().onFetch()
await flush()
assert.equal(fetchRequests.at(-1).supplier, "BILLING-SUP")
for (const billingSupplier of ["CHANGED-SUP", "", "XXXXXXXX"]) {
	editorBody().onUpdateField("billing_supplier", billingSupplier)
	await flush()
	assert.equal(editorBody().form.supplier, "BILL-SUP")
	assert.deepEqual(editorBody().grns, [])
	assert.deepEqual(editorBody().items, [])
	editorBody()["onUpdate:grns"](["GRN-2"])
	await flush()
	editorBody().onFetch()
	await flush()
	assert.equal(fetchRequests.at(-1).supplier, billingSupplier === "XXXXXXXX" ? undefined : billingSupplier || "BILL-SUP")
}
console.log("accounts billing supplier GRN refresh and fetch OK")

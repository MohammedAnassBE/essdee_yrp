import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

import { LAYOUT_UNAVAILABLE_PATH } from "../frontend/src/router/departmentLock.js"
import { NO_PERMISSION_PATH } from "../frontend/src/router/listPermission.js"

import { createMemoryHistory, createRouter } from "../frontend/node_modules/vue-router/dist/vue-router.mjs"
import { ACCOUNTS_ROUTES } from "../frontend/src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../frontend/src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../frontend/src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../frontend/src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../frontend/src/departments/purchase/purchaseViews.js"

const read = (path) => readFileSync(new URL(`../frontend/src/${path}`, import.meta.url), "utf8")
const copy = (value) => JSON.parse(JSON.stringify(value))
const source = read("router/index.js")
const routes = vm.runInNewContext(`${source.slice(source.indexOf("const AdministratorPage"), source.indexOf("const router = createRouter"))}; routes`, {
	ACCOUNTS_ROUTES, MERCH_ROUTES, PD_ROUTES, PLANNING_ROUTES, PURCHASE_ROUTES, LAYOUT_UNAVAILABLE_PATH, NO_PERMISSION_PATH, departments: [],
})
const router = createRouter({ history: createMemoryHistory("/web/"), routes })
const routeProps = (path) => {
	const route = router.resolve(path)
	const props = route.matched.at(-1).props.default
	return typeof props === "function" ? props(route) : props || {}
}
const families = [
	["production-orders", "productionOrder", "productionOrderId"],
	["work-orders", "workOrder", "workOrderId"],
	["bill-tracking", "billTracking", "billTrackingId"],
	["purchase-invoices", "purchaseInvoice", "purchaseInvoiceId"],
]
for (const [section, key, parameter] of families) {
	const path = `/merch/${section}`
	assert.equal(router.resolve(`${path}/new`).name, MERCH_ROUTES[`${key}New`])
	assert.equal(router.resolve(`${path}/A%2FB/edit`).name, MERCH_ROUTES[`${key}Edit`])
	assert.equal(router.resolve(`${path}/A%2FB`).name, MERCH_ROUTES[key])
	assert.equal(router.resolve({ name: MERCH_ROUTES[key], params: { [parameter]: "A/B" } }).path, `${path}/A%2FB`)
	for (const suffix of ["/new", "/A%2FB/edit", "/A%2FB"]) {
		const props = routeProps(path + suffix)
		assert.equal(props.backTo || props.basePath, path)
		assert.equal(props.listRouteName || `${props.viewRouteName}s`, router.resolve(path).name)
	}
}
assert.equal(routeProps("/merch/production-orders").initialStatus, "PPO Request")
assert.equal(routeProps("/merch/production-orders").eyebrow, "Merch")
assert.equal(routeProps("/merch/production-orders/A").transferViewRouteName, MERCH_ROUTES.productionOrder)
assert.equal(routeProps("/merch/work-orders").storeName, "Merch")
assert.equal(routeProps("/merch/work-orders").basePath, "/merch")
assert.equal(routeProps("/merch/work-orders").processFilter, undefined)
assert.equal(routeProps("/merch/work-orders/WO-1").processCostViewRouteName, MERCH_ROUTES.processCost)
for (const path of ["/merch/bill-tracking", "/merch/purchase-invoices"]) {
	assert.equal(routeProps(path).eyebrow, "Merch")
	assert.equal(routeProps(path).backTo, "/merch")
}

const expectedDefaults = {
	"sales/SalesSection.vue": { backTo: "/sales", backLabel: "Sales", viewRouteName: "sales-production-order", newRouteName: "sales-production-order-new", initialStatus: "", eyebrow: "Sales" },
	"sales/ProductionOrders.vue": { viewRouteName: "sales-production-order", newRouteName: "sales-production-order-new", initialStatus: "", eyebrow: "Sales" },
	"sales/ProductionOrder.vue": { backTo: "/sales/production-orders", backLabel: "Production Orders", viewRouteName: "sales-production-order", transferViewRouteName: "sales-production-order", editRouteName: "sales-production-order-edit", listRouteName: "sales-production-orders" },
	"sales/ProductionOrderTransferHistory.vue": { viewRouteName: "sales-production-order" },
	"FabricWorkOrder.vue": { backTo: "/fabric-store/work-orders", backLabel: "Work Orders", viewRouteName: "fabric-work-order", newRouteName: "fabric-work-order-new", editRouteName: "fabric-work-order-edit", processCostViewRouteName: "" },
	"hr/BillTrackings.vue": { backTo: "/hr", backLabel: "HR", eyebrow: "HR", viewRouteName: "hr-bill-tracking", newRouteName: "hr-bill-tracking-new" },
	"hr/BillTracking.vue": { backTo: "/hr/bill-tracking", backLabel: "Bill Tracking", listRouteName: "hr-bill-trackings", editRouteName: "hr-bill-tracking-edit", purchaseInvoiceNewRouteName: "accounts-purchase-invoice-new", purchaseInvoiceViewRouteName: "accounts-purchase-invoice" },
	"hr/BillTrackingEditorPage.vue": { basePath: "/hr/bill-tracking", viewRouteName: "hr-bill-tracking", listRouteName: "hr-bill-trackings" },
	"accounts/PurchaseInvoices.vue": { backTo: "/accounts", backLabel: "Accounts", eyebrow: "Accounts", viewRouteName: "accounts-purchase-invoice", newRouteName: "accounts-purchase-invoice-new" },
	"accounts/PurchaseInvoice.vue": { backTo: "/accounts/purchase-invoices", backLabel: "Purchase Invoices", listRouteName: "accounts-purchase-invoices", editRouteName: "accounts-purchase-invoice-edit" },
	"accounts/PurchaseInvoiceEditorPage.vue": { basePath: "/accounts/purchase-invoices", viewRouteName: "accounts-purchase-invoice", listRouteName: "accounts-purchase-invoices" },
}
function defaults(file) {
	const definition = read(`departments/${file}`).match(/defineProps\((\{[^]*?\})\)/)[1]
	const schema = vm.runInNewContext(`(${definition})`)
	return Object.fromEntries(Object.entries(schema).map(([key, value]) => [key, value.default]))
}
for (const [file, expected] of Object.entries(expectedDefaults)) {
	const actual = defaults(file)
	for (const [prop, value] of Object.entries(expected)) assert.equal(actual[prop], value, `${file}: ${prop}`)
}
assert.match(read("departments/sales/SalesSection.vue"), /:initial-status="initialStatus" :eyebrow="eyebrow"/)
assert.match(read("departments/sales/ProductionOrders.vue"), /:initial-status="initialStatus"/)
assert.match(read("departments/sales/ProductionOrder.vue"), /:view-route-name="transferViewRouteName"/)
assert.match(read("departments/sales/ProductionOrderTransferHistory.vue"), /name: viewRouteName/)
for (const file of ["FabricWorkOrder.vue", "fabric-store/WorkOrderDetails.vue", "fabric-store/WorkOrderSummary.vue"]) {
	assert.match(read(`departments/${file}`), /:process-cost-view-route-name="processCostViewRouteName"/)
	assert.match(read(`departments/${file}`), /processCostViewRouteName: \{ type: String, default: "" \}/)
}
const matrix = read("departments/fabric-store/WorkOrderItemMatrix.vue")
assert.match(matrix, /v-if="processCostViewRouteName"/)
assert.match(matrix, /name: processCostViewRouteName, params: \{ processCostId: name \}/)
const processCostNames = vm.runInNewContext(`(${matrix.match(/function processCostNames\([^]*?\n\}/)[0]})`)
assert.deepEqual(copy(processCostNames([{ process_cost: "PC-1" }, {}, { process_cost: "PC-1" }, { process_cost: "PC-2" }])), ["PC-1", "PC-2"])

function harness(file, functions, props, extra = {}) {
	const navigation = []
	const context = vm.createContext({
		props, router: { push: (target) => navigation.push(copy(target)), replace: (target) => navigation.push(copy(target)) },
		workspace: { value: { record: { name: "RECORD-1", modified: "now", purchase_invoice: "PI-1" } } },
		editor: { value: { modified: "now" } }, currentName: { value: "RECORD-1" },
		preserveListNavigationState: () => ({}), ...extra,
	})
	const component = read(`departments/${file}`)
	for (const name of functions) {
		const definition = component.match(new RegExp(`(?:async )?function ${name}\\([^]*?\\n\\}`))[0]
		vm.runInContext(definition, context)
	}
	return { context, navigation }
}
for (const props of [defaults("hr/BillTracking.vue"), routeProps("/merch/bill-tracking/BT-1"), routeProps("/accounts/bill-tracking/BT-1")]) {
	const { context, navigation } = harness("hr/BillTracking.vue", ["openEditor", "createPurchaseInvoice", "showPurchaseInvoice"], props, { recordName: () => "BT-1" })
	context.openEditor()
	context.createPurchaseInvoice()
	context.showPurchaseInvoice()
	assert.deepEqual(navigation.map(({ name }) => name), [props.editRouteName, props.purchaseInvoiceNewRouteName, props.purchaseInvoiceViewRouteName])
	assert.deepEqual(navigation[1].query, { bill_tracking: "BT-1" })
}
for (const file of ["hr/BillTrackingEditorPage.vue", "accounts/PurchaseInvoiceEditorPage.vue"]) {
	const section = file.startsWith("hr") ? "bill-tracking" : "purchase-invoices"
	const variants = [defaults(file), routeProps(`/merch/${section}/new`)]
	if (section === "bill-tracking") variants.push(routeProps("/accounts/bill-tracking/new"))
	for (const props of variants) {
		const { context, navigation } = harness(file, ["navigateBack"], props)
		context.navigateBack()
		assert.equal(navigation.at(-1).name, props.viewRouteName)
		context.currentName.value = ""
		context.navigateBack()
		assert.equal(navigation.at(-1).name, props.listRouteName)
		const backExpression = read(`departments/${file}`).match(/const backTo = computed\(\(\) => ([^]*?)\)\nconst /)[1]
		for (const name of ["A/B", ""]) {
			context.currentName.value = name
			assert.equal(vm.runInContext(backExpression, context), name ? `${props.basePath}/A%2FB` : props.basePath)
		}
	}
}
for (const props of [defaults("accounts/PurchaseInvoice.vue"), routeProps("/merch/purchase-invoices/PI-1")]) {
	const { context, navigation } = harness("accounts/PurchaseInvoice.vue", ["openEditor", "openExpenseHeadEditor", "runDocumentCommand"], props, {
		beginRecordAction: () => ({}), isOriginatingRecord: () => true, finishRecordAction: () => {},
		executePurchaseInvoiceCommand: async (_name, command) => command === "delete" ? { deleted: true } : { record: { name: "AMENDED", modified: "now" } },
	})
	context.openEditor()
	context.openExpenseHeadEditor()
	await context.runDocumentCommand("amend")
	await context.runDocumentCommand("delete")
	assert.deepEqual(navigation.map(({ name }) => name), [props.editRouteName, props.editRouteName, props.editRouteName, props.listRouteName])
	assert.deepEqual(navigation[1].query, { fetchExpenseHead: "1" })
	assert.equal(navigation[2].params.purchaseInvoiceId, "AMENDED")
}
console.log("merch reuse routes tests passed")

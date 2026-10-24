import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as statusTone from "../src/utils/statusTone.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const settle = async () => { await tick(); await tick(); await tick() }
const stub = name => (props) => Vue.h(name, props)
const GATED_PAGES = [
	"departments/CuttingPlans.vue",
	"departments/CuttingOrders.vue",
	"departments/CuttingBulkLaySheets.vue",
	"departments/CuttingLaySheetPlanners.vue",
	"departments/finishing/FinishingPlans.vue",
	"departments/finishing/FinishingDispatches.vue",
	"departments/merch/ipd/IpdList.vue",
	"departments/merch/lot/MerchLotsList.vue",
	"departments/planning/lot/LotsList.vue",
	"departments/purchase/lot/LotsList.vue",
	"departments/quality/QualityInspections.vue",
	"departments/merch/process-cost/ProcessCostsList.vue",
	"departments/accounts/PurchaseInvoices.vue",
]

// Capability payloads of any department shape: every can_* flag is the given value; "lots" sections are absent when denied.
function capabilities(allowed) {
	const handler = {
		get(_, key) {
			if (typeof key !== "string" || key.startsWith("__v") || key === "then" || key === "toJSON") return undefined
			if (key.startsWith("can_")) return allowed
			if (key === "lots" && !allowed) return null
			if (key === "workflow_states") return []
			return proxy
		},
	}
	const proxy = new Proxy({}, handler)
	return proxy
}

async function mountPage(file) {
	const path = resolve("frontend/src", file)
	const source = readFileSync(path, "utf8")
	let settleCapabilities
	const request = new Promise((done, fail) => { settleCapabilities = { allow: () => done(capabilities(true)), deny: () => done(capabilities(false)), fail: () => fail(new Error("offline")) } })
	const modules = {
		"primevue/button": stub("button"),
		"primevue/message": (props, { slots }) => Vue.h("message", props, slots.default?.()),
		"vue-router": { useRouter: () => ({ push() {} }) },
	}
	for (const [, names, specifier] of source.matchAll(/^import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']/gm)) {
		if (specifier in modules || specifier === "vue") continue
		if (specifier.includes("/api/")) {
			modules[specifier] = Object.fromEntries(names.replace(/[{}\s]/g, "").split(",").map(name => [name, () => request]))
		} else if (specifier.endsWith("ListView.vue")) {
			modules[specifier] = (props, { slots }) => Vue.h("list-view", props, [slots["toolbar-actions"]?.()])
		} else if (specifier.endsWith("DepartmentPage.vue")) {
			modules[specifier] = (props, { slots }) => Vue.h("department-page", props, slots.default?.())
		} else if (specifier.endsWith(".vue")) {
			modules[specifier] = stub(specifier.split("/").pop())
		} else if (specifier.endsWith("listDocumentNavigation.js")) {
			modules[specifier] = { openListDocument() {} }
		} else {
			modules[specifier] = await import(resolve(dirname(path), specifier))
		}
	}
	const root = mountComponent(loadComponent(path, modules), Vue.reactive({}))
	await settle()
	const list = () => findNodes(root, node => node.type === "list-view")[0]
	const createButtons = () => findNodes(root, node => node.type === "button" && /^(Create|New)\b/.test(node.props.label || ""))
	const denied = () => findNodes(root, node => node.type === "message" || (node.type === "WorkspaceLoadError.vue" && node.props.retryable === false)).length > 0
	const loadFailed = () => findNodes(root, node => node.type === "WorkspaceLoadError.vue" && node.props.retryable !== false).length > 0
	return { source, settleCapabilities, list, createButtons, denied, loadFailed }
}

for (const file of GATED_PAGES) {
	test(`${file} starts the list before capabilities and never shows actions or rows early`, async () => {
		const page = await mountPage(file)
		assert.ok(page.list(), "the list mounts (and fetches) while capabilities load")
		assert.equal(page.list().props["can-read"], false, "only the skeleton renders until read is known")
		assert.equal(page.createButtons().length, 0, "no privileged action before capabilities")
		assert.equal(page.denied(), false)
		page.settleCapabilities.allow()
		await settle()
		assert.equal(page.list().props["can-read"], true)
		if (/label="(Create|New)\b/.test(page.source)) assert.ok(page.createButtons().length > 0)
	})

	test(`${file} lets the permission denial win`, async () => {
		const page = await mountPage(file)
		page.settleCapabilities.deny()
		await settle()
		assert.equal(page.list(), undefined)
		assert.equal(page.createButtons().length, 0)
		assert.equal(page.denied(), true)
	})

	test(`${file} replaces the list with the load error when capabilities fail`, async () => {
		const page = await mountPage(file)
		page.settleCapabilities.fail()
		await settle()
		assert.equal(page.list(), undefined)
		assert.equal(page.createButtons().length, 0)
		assert.equal(page.loadFailed(), true)
	})
}

async function mountList(props, overrides = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const calls = []
	const fields = [{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Open\nClosed", in_list_view: 1 }]
	const api = {
		getMeta: async () => { calls.push("meta"); return [{ name: "Entry", fields }] },
		getActiveWorkflow: async () => { calls.push("workflow"); return null },
		getUserListview: async () => { calls.push("listview"); return { fields: [{ fieldname: "name" }, ...fields], columns: null } },
		getItemFilterValues: async () => ({}),
		getList: async () => { calls.push("rows"); return [{ name: "ENT-1", status: "Open" }] },
		getCount: async () => { calls.push("total"); return 1 },
		getCounts: async (doctype, sets) => { calls.push("counts"); return sets.map(() => 1) },
		...overrides,
	}
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/entries" }) },
		"../../api/frappe.js": api,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("./ListviewFilters.vue") }
	const reactiveProps = Vue.reactive({ doctype: "Entry", navigationEnabled: false, statusField: "status", statusOptions: ["Open", "Closed"], ...props })
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), reactiveProps)
	await settle()
	return { root, calls, props: reactiveProps, restore: () => { globalThis.window = previousWindow } }
}

test("ListView loads data but renders only the skeleton until read is allowed, then shows it without refetching", async () => {
	const list = await mountList({ canRead: false })
	try {
		assert.deepEqual([...list.calls].sort(), ["counts", "listview", "meta", "rows", "total", "workflow"])
		assert.equal(findNodes(list.root, node => node.type === "list-page-skeleton").length, 1)
		assert.equal(findNodes(list.root, node => node.type === "datatable").length, 0)
		assert.equal(findNodes(list.root, node => node.type === "button").length, 0)
		const fetched = list.calls.length
		list.props.canRead = true
		await settle()
		assert.equal(findNodes(list.root, node => node.type === "list-page-skeleton").length, 0)
		assert.equal(findNodes(list.root, node => node.type === "datatable").length, 1)
		assert.equal(list.calls.length, fetched)
	} finally { list.restore() }
})

test("ListView renders normally by default", async () => {
	const list = await mountList({})
	try {
		assert.equal(findNodes(list.root, node => node.type === "list-page-skeleton").length, 0)
		assert.equal(findNodes(list.root, node => node.type === "datatable").length, 1)
	} finally { list.restore() }
})

test("ListView keeps a failed list request hidden while read is unknown", async () => {
	const denied = async () => { throw Object.assign(new Error("No permission for Entry"), { exc_type: "PermissionError" }) }
	const list = await mountList({ canRead: false }, { getList: denied, getCount: denied })
	try {
		assert.equal(findNodes(list.root, node => node.type === "list-page-skeleton").length, 1)
		assert.equal(findNodes(list.root, node => node.type === "message").length, 0)
		assert.equal(findNodes(list.root, node => String(node.text || "").includes("No permission")).length, 0)
	} finally { list.restore() }
})

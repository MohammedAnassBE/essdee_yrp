import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as views from "../src/departments/merch/process-cost/processCostViews.js"
import * as lotViews from "../src/departments/purchase/lot/lotViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import * as duplicateAction from "../src/composables/useDuplicateAction.js"

const fieldnames = ["lot", "process_name", "item", "uom", "is_rework", "supplier", "supplier_name", "tax_slab", "from_date", "to_date", "is_expired", "approved_by", "depends_on_attribute", "attribute"]
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
const control = (props, { slots }) => Vue.h("control", props, slots.default?.())
const capture = (name) => (props) => Vue.h(name, props)
const { LOT_DOCUMENT_SECTIONS, lotDocumentSections } = lotViews

test("Process Cost groups contain all fourteen Desk fields exactly once", () => {
	assert.deepEqual(views.PROCESS_COST_SECTIONS.map((group) => group.key), ["process", "supplier", "validity", "attribute"])
	assert.deepEqual(views.PROCESS_COST_SECTIONS.flatMap((group) => group.fields).sort(), [...fieldnames].sort())
	for (const group of views.PROCESS_COST_SECTIONS) {
		assert.ok(group.label && group.description)
		assert.match(group.icon, /^pi pi-/)
	}
	assert.deepEqual(views.PROCESS_COST_TABS, [{ key: "details", label: "Details" }, { key: "values", label: "Process Cost Values" }])
})

test("custom document sections show only Work Orders and preserve preview/count/permissions", () => {
	const rows = Array.from({ length: 6 }, (_, index) => ({ name: `WO-${index}` }))
	const payload = { work_orders: { permitted: true, count: 9, rows } }
	const [section] = lotDocumentSections(payload, {}, 3, views.PROCESS_COST_DOCUMENT_SECTIONS)
	assert.deepEqual(views.PROCESS_COST_DOCUMENT_SECTIONS, [LOT_DOCUMENT_SECTIONS.find((item) => item.key === "work_orders")])
	assert.deepEqual(lotDocumentSections(payload, {}, 3, views.PROCESS_COST_DOCUMENT_SECTIONS).map((item) => item.key), ["work_orders"])
	assert.equal(section.count, 9)
	assert.deepEqual(section.visibleRows, rows.slice(0, 3))
	assert.equal(section.hasMore, true)
	assert.deepEqual(lotDocumentSections(payload, { work_orders: true }, 3, views.PROCESS_COST_DOCUMENT_SECTIONS)[0].visibleRows, rows)
	assert.deepEqual(lotDocumentSections({ work_orders: { permitted: false } }, {}, 5, views.PROCESS_COST_DOCUMENT_SECTIONS), [])
})

test("Lot document sections retain all four default sections and empty states", () => {
	const sections = lotDocumentSections()
	assert.deepEqual(sections.map((section) => section.key), ["work_orders", "purchase_orders", "goods_received_notes", "delivery_challans"])
	assert.ok(sections.every((section) => section.count === 0 && section.visibleRows.length === 0 && !section.hasMore))
})

test("shared rail renders the custom Work Order empty state and keeps Lot defaults", () => {
	const previousWindow = globalThis.window
	globalThis.window = { matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) }
	try {
		const rail = loadComponent(resolve("frontend/src/departments/purchase/lot/LotDocumentsRail.vue"), {
			"primevue/button": control, "primevue/skeleton": control,
			"./LotDocumentContext.vue": control,
			"../../../components/common/WorkspaceLoadError.vue": control,
			"../../../components/documents/DocumentStatusBadge.vue": control,
			"./lotViews.js": lotViews,
		})
		const root = mountComponent(rail, { sections: views.PROCESS_COST_DOCUMENT_SECTIONS, ariaLabel: "Process Cost work orders" })
		assert.equal(nodes(root, "aside")[0].props["aria-label"], "Process Cost work orders")
		assert.deepEqual(nodes(root, "h2").map(text), ["Work Orders"])
		assert.ok(text(root).includes("No Work Orders"))
		const lotRoot = mountComponent(rail, {})
		assert.equal(nodes(lotRoot, "aside")[0].props["aria-label"], "Lot purchase documents")
		assert.deepEqual(nodes(lotRoot, "h2").map(text), LOT_DOCUMENT_SECTIONS.map((section) => section.label))
	} finally { globalThis.window = previousWindow }
})

function mountPage(payload, query = {}, pageProps = { processCostId: "PC" }) {
	const route = Vue.reactive({ query })
	const replacements = []
	const pushes = []
	const calls = []
	const workspaceControl = { setup(props, { attrs, slots }) { return () => Vue.h("workspace", attrs, [
		slots.header?.({ record: attrs.workspace.record || {}, headingId: "process-cost-heading" }),
		slots["header-actions"]?.(), slots.matrix?.(), slots.rail?.(),
	]) } }
	const modules = {
		"vue-router": { useRoute: () => route, useRouter: () => ({
			push: (to) => pushes.push(to),
			replace: (to) => { replacements.push(to); route.query = to.query },
		}) },
		"../../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({ listNavigation: "preserved" }) },
		"../../../api/merch.js": {
			getProcessCostWorkspace: async (name) => { if (payload instanceof Error) throw payload; return typeof payload === "function" ? payload(name) : payload },
			executeProcessCostCommand: async (...args) => { calls.push(["workflow", ...args]); return payload },
			deleteProcessCost: async (...args) => calls.push(["delete", ...args]),
		},
		"../../../components/DepartmentPage.vue": control,
		"../../../components/common/DocumentLink.vue": capture("document-link"),
		"../../fabric-store/FabricDocumentWorkspace.vue": workspaceControl,
		"../../purchase/lot/LotDocumentsRail.vue": capture("rail"),
		"./ProcessCostGrid.vue": capture("values-grid"),
		"./processCostViews.js": views,
		"../merchViews.js": { MERCH_ROUTES },
		"../../../composables/useDuplicateAction.js": duplicateAction,
		...Object.fromEntries(["DocumentOverview", "DocumentStatusBadge", "DocumentActionStrip", "DocumentConfirmationDialog", "DocumentErrorDialog"].map((name) => [`../../../components/documents/${name}.vue`, capture(name)])),
		...Object.fromEntries(["tab", "tablist", "tabpanel", "tabpanels", "tabs", "message"].map((name) => [`primevue/${name}`, (props, { slots }) => Vue.h(name, props, slots.default?.())])),
	}
	const component = loadComponent(resolve("frontend/src/departments/merch/process-cost/ProcessCostPage.vue"), modules)
	const root = mountComponent(component, pageProps)
	return { root, route, replacements, pushes, calls }
}

const workspace = (state = "Draft", docstatus = 0) => ({
	record: { name: "PC", process_name: "Stitching", workflow_state: state, docstatus, modified: "version" },
	fields: fieldnames.map((fieldname) => ({ fieldname, label: `Desk ${fieldname}`, value: null })),
	tiers: [{ min_order_qty: 0, price: 12 }], tier_fields: [],
	work_orders: { permitted: true, count: 0, rows: [] }, actions: [],
})

test("Details defaults safely; Values renders only in its tab and preserves list navigation", async () => {
	const payload = workspace()
	const { root, route, replacements } = mountPage(payload, { tab: "unknown", filter: "supplier" })
	await tick()
	assert.equal(nodes(root, "tabs")[0].props.value, "details")
	assert.equal(nodes(root, "tabs")[0].props.scrollable, "")
	assert.equal(nodes(root, "values-grid").length, 0)
	assert.deepEqual(nodes(root, "DocumentOverview")[0].props.fields, payload.fields)
	assert.ok(text(nodes(root, "tab")[1]).includes("Process Cost Values1"))
	nodes(root, "tabs")[0].props["onUpdate:value"]("values")
	await tick()
	assert.deepEqual(replacements, [{ query: { tab: "values", filter: "supplier" }, state: { listNavigation: "preserved" } }])
	assert.equal(nodes(root, "DocumentOverview").length, 0)
	assert.deepEqual(nodes(root, "values-grid")[0].props.tiers, payload.tiers)
	assert.equal(nodes(root, "values-grid")[0].props.readonly, "")
	route.query = {}
	await tick()
	assert.equal(nodes(root, "tabs")[0].props.value, "details")
})

test("Draft, Approved and Expired show identity/status; waiting note and denied rail render safely", async () => {
	for (const [state, status] of [["Draft", 0], ["Approved", 1], ["Expired", 2]]) {
		const payload = workspace(state, status)
		payload.work_orders.permitted = false
		payload.waiting_note = state === "Draft" ? "Waiting for a Purchase User to submit" : ""
		const { root } = mountPage(payload)
		await tick()
		assert.equal(nodes(root, "h1")[0].props.id, "process-cost-heading")
		assert.equal(nodes(root, "DocumentStatusBadge")[0].props.label, state)
		assert.equal(nodes(root, "DocumentStatusBadge")[0].props.docstatus, status)
		assert.deepEqual(nodes(root, "DocumentActionStrip")[0].props.actions, [])
		assert.equal(nodes(root, "rail").length, 0)
		assert.equal(nodes(root, "message").length, state === "Draft" ? 1 : 0)
	}
})

test("Work Order rail opens the Merch Work Order route", async () => {
	const { root, pushes } = mountPage(workspace())
	await tick()
	const rail = nodes(root, "rail")[0]
	assert.equal(rail.props["aria-label"], "Process Cost work orders")
	assert.deepEqual(rail.props.sections, views.PROCESS_COST_DOCUMENT_SECTIONS)
	rail.props.onOpen({ doctype: "YRP Work Order", name: "WO/1" })
	assert.deepEqual(pushes, [{ name: "merch-work-order", params: { workOrderId: "WO/1" } }])
})

test("workflow and own Delete retain confirmation and expected modified checks", async () => {
	const payload = { ...workspace(), actions: [{ action: "Submit", label: "Submit" }], can_edit: true, can_delete: true }
	const { root, calls, pushes } = mountPage(payload)
	await tick()
	const actions = nodes(root, "DocumentActionStrip")[0].props.actions
	assert.equal(actions[0].primary, true)
	assert.equal(actions[1].key, "edit")
	assert.equal(actions[2].menuOnly, true)
	actions[0].command()
	await tick()
	assert.equal(nodes(root, "DocumentConfirmationDialog")[0].props.visible, true)
	await nodes(root, "DocumentConfirmationDialog")[0].props.onConfirm()
	assert.deepEqual(calls, [["workflow", "PC", "Submit", "version"]])
	actions[2].command()
	await tick()
	await nodes(root, "DocumentConfirmationDialog")[0].props.onConfirm()
	assert.deepEqual(calls[1], ["delete", "PC", "version"])
	assert.deepEqual(pushes, ["/merch/process-costs"])
})

test("failed navigation to another Process Cost hides the previous document and its actions", async () => {
	const pageProps = Vue.reactive({ processCostId: "PC" })
	const { root } = mountPage((name) => { if (name === "PC") return { ...workspace(), can_edit: true }; throw new Error("Not found") }, {}, pageProps)
	await tick()
	assert.equal(nodes(root, "workspace")[0].props.workspace.record.name, "PC")
	pageProps.processCostId = "OTHER"
	await tick()
	await tick()
	assert.deepEqual(nodes(root, "workspace")[0].props.workspace, {})
	assert.equal(nodes(root, "workspace")[0].props.error, "Not found")
	assert.deepEqual(nodes(root, "DocumentActionStrip")[0].props.actions, [])
})

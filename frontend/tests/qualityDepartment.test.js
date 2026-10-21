import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"
import { departments } from "../src/departments/registry.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import * as views from "../src/departments/quality/qualityViews.js"
import * as fields from "../src/departments/quality/inspectionFields.js"
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
const selection = {
	colours: [{ colour: "Blue", selected: 1 }, { colour: "Red", selected: 0 }],
	sizes: [{ size: "M", selected: true }, { size: "L", selected: 0 }],
}

const overview = await import("../src/utils/documentOverview.js")

test("Quality registry follows Finishing and automatically feeds the landing cards", () => {
	const index = departments.findIndex(({ key }) => key === "quality")
	assert.equal(departments[index - 1].key, "finishing")
	assert.deepEqual({ ...departments[index], component: undefined }, {
		key: "quality", label: "Quality", shortLabel: "QA", path: "/quality", component: undefined,
	})
	assert.match(read("components/AdministratorPage.vue"), /v-for="department in departments"/)
	assert.match(String(departments[index].component), /Quality.vue/)
})

test("actual router resolves the Quality launcher, list, create, edit and view", () => {
	const source = read("router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => null }
	vm.runInNewContext(source, context)
	for (const [path, name] of [
		["/quality", "quality"], ["/quality/inspections", "quality-inspections"],
		["/quality/inspections/new?against_id=WO-1&grn=GRN-1", "quality-inspection-new"],
		["/quality/inspections/EQI-1/edit", "quality-inspection-edit"], ["/quality/inspections/EQI-1", "quality-inspection"],
		["/quality/work-orders", "quality-work-orders"], ["/quality/work-orders/WO-1", "quality-work-order"],
		["/quality/reports?report=quality-inspection-rft", "quality-reports"],
	]) assert.equal(context.router.resolve(path).name, name)
	assert.equal(context.router.resolve("/quality/inspections/EQI%20%231").params.inspectionId, "EQI #1")
	const props = (path) => JSON.parse(JSON.stringify(context.router.resolve(path).matched.at(-1).props.default))
	assert.deepEqual(props("/quality/work-orders"), { section: "work_orders", storeName: "Quality", basePath: "/quality", workOrderViewRouteName: "quality-work-order" })
	assert.deepEqual(props("/quality/work-orders/WO-1"), { backTo: "/quality/work-orders", backLabel: "Work Orders", viewRouteName: "quality-work-order", showEditorActions: false, quality: true })
	assert.ok(!context.router.hasRoute("quality-work-order-new"))
	assert.ok(!context.router.hasRoute("quality-work-order-edit"))
	assert.notEqual(context.router.resolve("/quality/work-orders/WO-1/edit").name, "quality-work-order")
})

test("record links encode inspection names and scope Work Orders to Quality", () => {
	assert.equal(webDocumentPath(views.INSPECTION_DOCTYPE, "EQI /#"), "/web/quality/inspections/EQI%20%2F%23")
	assert.equal(webDocumentPath(views.INSPECTION_DOCTYPE, "EQI", "/web/quality"), "/web/quality/inspections/EQI")
	assert.equal(webDocumentPath("YRP Work Order", "WO /", "/web/quality/inspections/EQI"), "/web/quality/work-orders/WO%20%2F")
	assert.equal(webDocumentPath("YRP Work Order", "WO", "/web/sewing"), "/web/sewing/work-orders/WO")
})

test("inspection list columns, result tones and strict permission-based primary order", () => {
	assert.deepEqual(views.INSPECTION_LIST_COLUMNS, ["inspection_type", "against_id", "lot", "item", "supplier", "result", "posting_date"])
	assert.deepEqual(["Pass", "Fail", "Hold", ""].map(views.resultTone), ["success", "danger", "warning", "neutral"])
	const keys = ["submit", "update_status", "create_debit", "edit", "amend"]
	for (let index = 0; index < keys.length; index++) {
		const allowed = Object.fromEntries(keys.slice(index).map((key) => [key, { allowed: true }]))
		const handler = () => {}
		const actions = views.inspectionActionItems({ ...allowed, share: { allowed: false }, cancel: { allowed: true, label: "Cancel Inspection" } }, { [keys[index]]: handler })
		assert.equal(actions.find(({ primary }) => primary).key, keys[index])
		assert.equal(actions[0].command, handler)
		assert.equal(actions.at(-1).label, "Cancel Inspection")
		assert.ok(actions.at(-1).menuOnly)
		assert.ok(!actions.some(({ key }) => key === "share"))
	}
	assert.deepEqual(views.inspectionActionItems(), [])
})

test("inspection field types, options and required flags match the DocType", () => {
	const doctype = JSON.parse(readFileSync(new URL("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_essdee_quality_inspection/sd_yrp_essdee_quality_inspection.json", import.meta.url), "utf8"))
	for (const field of Object.values(fields.INSPECTION_FIELDS)) {
		const source = doctype.fields.find(({ fieldname }) => fieldname === field.fieldname)
		assert.ok(source, field.fieldname)
		assert.equal(field.fieldtype, source.fieldtype, `${field.fieldname} fieldtype`)
		assert.equal(field.options, source.options, `${field.fieldname} options`)
		assert.equal(Boolean(field.reqd), Boolean(source.reqd), `${field.fieldname} reqd`)
	}
	const inspection = fields.INSPECTION_GROUPS.find(({ key }) => key === "inspection")
	assert.ok(fields.visibleInspectionFields(inspection, { is_third_party: 1 }).find(({ fieldname }) => fieldname === "third_party_supplier").reqd)
	assert.ok(!fields.visibleInspectionFields(inspection, { is_third_party: 0 }).some(({ fieldname }) => fieldname === "third_party_supplier"))
	assert.ok(!fields.INSPECTION_GROUPS.some(({ key }) => key === "third_party"))
	assert.ok(fields.INSPECTION_GROUPS.every(({ icon }) => icon?.startsWith("pi pi-")))
})

test("Quality API uses workspace amendment defaults and the debit endpoint that attaches uploads", async () => {
	const calls = []
	const context = { callMethod: async (method, args) => { calls.push([method, args]); return { name: "DEBIT-1" } } }
	vm.runInNewContext(read("api/quality.js").replace(/^import .*\n/gm, "").replace(/export function /g, "function "), context)
	await context.getNewInspectionDefaults({ amend_from: "EQI /#1" })
	const result = await context.createInspectionDebit("EQI-1", { debit_value: 100, reason: "Defect", debit_document: "/files/proof.pdf" })
	assert.deepEqual(JSON.parse(JSON.stringify(calls)), [
		["essdee_yrp.quality.web_workspace.get_new_inspection_defaults", { amend_from: "EQI /#1" }],
		["essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection.create_inspection_debit", { quality_inspection: "EQI-1", debit_value: 100, reason: "Defect", debit_document: "/files/proof.pdf" }],
	])
	assert.equal(result.name, "DEBIT-1")
})

test("share caption matches Desk text exactly including selected sizes and zero defaults", () => {
	const record = { inspection_type: "Pre-FInal", supplier_name: "Unit A", supplier: "SUP-1", item: "STYLE", lot: "LOT", description: "Check", order_qty: 100, offer_qty: 80, sample_piece_count: 20, major_defect_maximum_allowed: 2, major_defect_found: 1, minor_defect_maximum_allowed: 3, result: "Pass" }
	assert.equal(views.inspectionShareCaption(record, selection), "Pre-FInal\nSupplier: Unit A\nStyle: STYLE\nLot: LOT\nSize: M\nColour: Blue\nDescription: Check\nOrder Qty: 100\nOffer Qty: 80\nAQL Sample: 20\nAllowed Major: 2\nFound Major: 1\nAllowed Minor: 3\nFound Minor: 0\nResult: Pass")
	assert.match(views.inspectionShareCaption({ supplier: "SUP-1" }), /^\nSupplier: \nStyle:/)
})

test("payload excludes record identity, lifecycle, derived values and permissions", () => {
	const payload = views.inspectionPayload({ name: "EQI", docstatus: 1, modified: "old", against: "Other", supplier: "FORGED", order_qty: 900, calculated_result: "Pass", inspector: "Administrator", permissions: {}, offer_qty: 50, against_id: "WO", result: "Hold" }, selection)
	assert.deepEqual(payload, { offer_qty: 50, against_id: "WO", result: "Hold", colour_and_size_data: views.cleanSelection(selection) })
	assert.equal(views.inspectionResultPreview({ major_defect_maximum_allowed: 2, minor_defect_maximum_allowed: 3, major_defect_found: 2, minor_defect_found: 3 }), "Pass")
	assert.equal(views.inspectionResultPreview({ major_defect_maximum_allowed: 2, minor_defect_maximum_allowed: 3, major_defect_found: 3 }), "Fail")
	assert.equal(views.inspectionResultPreview({}), "")
	assert.equal(views.inspectionPayload({ amended_from: "EQI-1" }, selection).amended_from, "EQI-1")
	for (const amended_from of [undefined, null, ""]) assert.ok(!Object.hasOwn(views.inspectionPayload({ amended_from }, selection), "amended_from"))
})

test("selection toggles and group select-all preserve other groups without mutation", () => {
	const before = structuredClone(selection)
	const all = views.selectAll(selection, "colours", true)
	assert.deepEqual(all.colours.map(({ selected }) => selected), [1, 1])
	assert.deepEqual(all.sizes, views.cleanSelection(selection).sizes)
	assert.deepEqual(views.selectAll(all, "colours", false).colours.map(({ selected }) => selected), [0, 0])
	assert.deepEqual(views.toggleSelection(all, "sizes", "L").sizes.map(({ selected }) => selected), [1, 1])
	assert.deepEqual(views.toggleSelection(all, "colours", "Blue").colours.map(({ selected }) => selected), [0, 1])
	assert.deepEqual(selection, before)
})

const defaults = { against_id: "WO-1", posting_date: "2026-10-21", checking_level: "Level 2", major_aql_level: "Level-2.5", minor_aql_level: "Level-4.0", against_details: { ...selection, item: "STYLE", lot: "LOT", supplier: "SUP", order_qty: 100 } }
const saved = { record: { ...defaults, name: "EQI-1", modified: "modified-1", docstatus: 0, offer_qty: 50, inspection_type: "Final" }, colour_size_data: selection, actions: { edit: { allowed: true }, submit: { allowed: true } } }

async function editor(api = {}, props = {}, query = {}) {
	const navigations = [], guards = [], toasts = [], calls = []
	const route = Vue.reactive({ params: {}, query })
	const root = mountComponent(component("QualityInspectionEditorPage", {
		"primevue/message": (props, { slots }) => Vue.h("message", props, slots.default?.()),
		"primevue/button": Button, "primevue/usetoast": { useToast: () => ({ add: (message) => toasts.push(message) }) },
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: async (target) => navigations.push(target), push: async (target) => navigations.push(target) }), onBeforeRouteLeave: (guard) => guards.push(guard), onBeforeRouteUpdate: () => {} },
		"../../api/frappe.js": { submitDoc: async (...args) => calls.push(["submit", ...args]) },
		"../../api/quality.js": { getInspectionWorkspace: async () => saved, getNewInspectionDefaults: async () => defaults, getInspectionAgainstDetails: async () => defaults.against_details, getInspectionAqlLimits: async () => ({ sample: 20, major_allowed: 2, minor_allowed: 3 }), saveInspection: async (...args) => { calls.push(["save", ...args]); return saved }, ...api },
		"../../components/DepartmentPage.vue": container,
		"../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
		"../../components/common/FormField.vue": (props) => Vue.h("field", props),
		"../../components/common/ListPageSkeleton.vue": () => null,
		"../../components/common/WorkspaceLoadError.vue": (props) => Vue.h("load-error", props),
		"../../components/documents/DocumentSaveButton.vue": (props) => Vue.h("save-control", props),
		"../../components/documents/DocumentConfirmationDialog.vue": (props) => Vue.h("confirmation", props),
		"../../components/documents/DocumentErrorDialog.vue": (props) => Vue.h("error-dialog", props),
		"../../components/documents/DocumentStatusBadge.vue": (props) => Vue.h("badge", props),
		"../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"./components/InspectionColourSizePicker.vue": (props) => Vue.h("picker", props),
		"./components/InspectionImageUpload.vue": (props) => Vue.h("upload", props),
		"../../utils/documentOverview.js": overview,
		"./inspectionFields.js": fields, "./qualityViews.js": views,
		"../qualityViews.js": views,
	}), props)
	await tick(); await tick()
	const change = async (name, value) => {
		nodes(root, "field").find(({ props }) => props.field.fieldname === name).props["onUpdate:modelValue"](value)
		await tick()
	}
	return { root, route, navigations, guards, toasts, calls, change, primary: () => nodes(root, "save-control")[0] }
}

test("create editor loads WO/GRN defaults, enforces required values and saves only editable payload", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const defaultsCalls = []
		const ui = await editor({ getNewInspectionDefaults: async (args) => { defaultsCalls.push(args); return defaults } }, {}, { against_id: "WO-1", grn: "GRN-1" })
		assert.deepEqual(defaultsCalls, [{ against_id: "WO-1", grn: "GRN-1", amend_from: undefined }])
		assert.ok(ui.primary().props.disabled)
		await ui.change("inspection_type", "Pre-FInal")
		await ui.change("offer_qty", 50)
		assert.equal(ui.primary().props.disabled, false)
		await ui.change("is_third_party", 1)
		assert.ok(ui.primary().props.disabled)
		await ui.change("third_party_supplier", "SUP-2")
		nodes(ui.root, "upload")[0].props.onUploadingChange(true); await tick()
		assert.ok(ui.primary().props.disabled)
		nodes(ui.root, "upload")[0].props.onUploadingChange(false); await tick()
		ui.primary().props.onSave(); await tick()
		assert.equal(ui.calls[0][0], "save")
		assert.equal(ui.calls[0][1].inspection_type, "Pre-FInal")
		assert.equal(ui.calls[0][1].supplier, undefined)
		assert.equal(ui.calls[0][1].posting_date, undefined)
		assert.deepEqual(ui.calls[0][1].colour_and_size_data, views.cleanSelection(selection))
		assert.equal(ui.navigations[0].params.inspectionId, "EQI-1")
	} finally { globalThis.window = previous }
})

test("Amend action opens a new inspection with amendment defaults, title, selections and payload", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const name = "EQI /#1"
		const cancelled = { ...saved, record: { ...saved.record, name, docstatus: 2 }, actions: { amend: { allowed: true } } }
		const view = await inspectionView(cancelled)
		assert.equal(view.action("amend").label, "Amend")
		assert.equal(view.action("amend").primary, true)
		view.action("amend").command()
		assert.deepEqual(view.navigations, ["/quality/inspections/new?amend_from=EQI%20%2F%231"])
		const denied = await inspectionView({ ...cancelled, actions: { amend: { allowed: false } } })
		assert.equal(denied.action("amend"), undefined)
		const requests = []
		const amendment = { ...defaults, amended_from: name, inspection_type: "Final", offer_qty: 50, spi_found: 8, upload_quality_approval_sheet: "/files/approval.jpg" }
		const ui = await editor({ getNewInspectionDefaults: async (args) => { requests.push(args); return amendment } }, {}, { amend_from: name })
		assert.deepEqual(requests, [{ against_id: undefined, grn: undefined, amend_from: name }])
		assert.equal(nodes(ui.root, "h1")[0].text, `Amend ${name}`)
		assert.deepEqual(nodes(ui.root, "picker")[0].props.modelValue, views.cleanSelection(selection))
		assert.equal(ui.primary().props.disabled, false)
		assert.equal(ui.primary().props.dirty, false)
		await ui.change("spi_found", 9)
		await ui.primary().props.onSave()
		assert.equal(ui.calls[0][1].amended_from, name)
		assert.equal(ui.calls[0][1].spi_found, 9)
		assert.equal(ui.calls[0][1].upload_quality_approval_sheet, "/files/approval.jpg")
		assert.deepEqual(ui.calls[0][1].colour_and_size_data, views.cleanSelection(selection))
		assert.equal(ui.calls[0][2].name, "")
	} finally { globalThis.window = previous }
})

test("draft editor requires edit permission and passes modified on save/submit", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const denied = await editor({ getInspectionWorkspace: async () => ({ ...saved, actions: {} }) }, { inspectionId: "EQI-1" })
		assert.match(nodes(denied.root, "load-error")[0].props.message, /cannot be edited/)
		const ui = await editor({}, { inspectionId: "EQI-1" })
		assert.equal(ui.primary().props.dirty, false)
		assert.equal(ui.primary().props["show-submit"], true)
		ui.primary().props.onSubmit(); await tick()
		assert.deepEqual(ui.calls[0], ["submit", views.INSPECTION_DOCTYPE, "EQI-1", "modified-1"])
		const changed = await editor({}, { inspectionId: "EQI-1" })
		assert.ok(nodes(changed.root, "strong").some(({ props }) => props.class?.includes("quality-result-badge--pass")))
		await changed.change("major_defect_found", 3)
		assert.ok(nodes(changed.root, "strong").some(({ props }) => props.class?.includes("quality-result-badge--fail")))
		assert.ok(nodes(changed.root, "div").some(({ props }) => props.class?.includes("quality-stat-tile--danger")))
		changed.primary().props.onSave(); await tick()
		assert.equal(changed.calls[0][2].expectedModified, "modified-1")
	} finally { globalThis.window = previous }
})

test("AQL recalculation clears stale limits, ignores old responses and blocks invalid quantities", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const requests = []
		const ui = await editor({ getInspectionAqlLimits: (values) => { const task = deferred(); requests.push({ ...task, values }); return task.promise } }, { inspectionId: "EQI-1" })
		assert.ok(ui.primary().props.disabled)
		await ui.change("offer_qty", 100)
		requests[1].resolve({ sample: 32, major_allowed: 3, minor_allowed: 5 }); await tick()
		assert.equal(ui.primary().props.disabled, false)
		requests[0].resolve({ sample: 1, major_allowed: 0, minor_allowed: 0 }); await tick()
		assert.equal(ui.primary().props.disabled, false)
		await ui.change("offer_qty", 0)
		assert.ok(ui.primary().props.disabled)
		await ui.change("offer_qty", 1.5)
		assert.ok(ui.primary().props.disabled)
		assert.equal(requests.length, 2)
	} finally { globalThis.window = previous }
})

test("editor protects dirty navigation and permits confirmed discard", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const ui = await editor({}, { inspectionId: "EQI-1" })
		await ui.change("description", "Unsaved")
		const next = []
		ui.guards[0]({}, {}, (value) => next.push(value)); await tick()
		assert.deepEqual(next, [])
		assert.equal(nodes(ui.root, "confirmation")[0].props.visible, true)
		nodes(ui.root, "confirmation")[0].props.onConfirm(); await tick()
		assert.deepEqual(next, [undefined])
	} finally { globalThis.window = previous }
})

async function inspectionView(payload, api = {}) {
	const calls = [], toasts = [], navigations = []
	const route = Vue.reactive({ params: {}, query: {} })
	const props = Vue.reactive({ inspectionId: "EQI-1" })
	const root = mountComponent(component("QualityInspection", {
		...Object.fromEntries(["tab", "tablist", "tabpanel", "tabpanels", "tabs"].map((name) => [`primevue/${name}`, (props, { slots }) => Vue.h(name, props, slots.default?.())])),
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
		"primevue/message": (props, { slots }) => Vue.h("message", props, slots.default?.()),
		"primevue/usetoast": { useToast: () => ({ add: (value) => toasts.push(value) }) },
		"vue-router": { useRoute: () => route, useRouter: () => ({ push: (target) => navigations.push(target), replace: (target) => { navigations.push(target); route.query = target.query } }) },
		"../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({ listNavigation: "preserved" }) },
		"../../api/frappe.js": { submitDoc: async (...args) => calls.push(["submit", ...args]), cancelDoc: async (...args) => calls.push(["cancel", ...args]) },
		"../../api/quality.js": { getInspectionWorkspace: async () => { calls.push(["load"]); return structuredClone(payload) }, updateInspectionResult: async (...args) => calls.push(["result", ...args]), createInspectionDebit: async (...args) => { calls.push(["debit", ...args]); return { name: "DEBIT-1" } }, ...api },
		"../../components/DepartmentPage.vue": container,
		"../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
		"../../components/common/ListPageSkeleton.vue": () => null,
		"../../components/common/WorkspaceLoadError.vue": (props) => Vue.h("load-error", props),
		"../../components/documents/DocumentActionStrip.vue": (props, { slots }) => Vue.h("action-strip", props, slots.primary?.()),
		"../../components/documents/DocumentConfirmationDialog.vue": (props) => Vue.h("confirmation", props),
		"../../components/documents/DocumentDeleteButton.vue": () => null,
		"../../components/documents/DocumentPrintButton.vue": () => null,
		"../../components/documents/DocumentErrorDialog.vue": (props) => Vue.h("error-dialog", props),
		"../../components/documents/DocumentSaveButton.vue": (props) => Vue.h("save-control", props),
		"../../components/documents/DocumentStatusBadge.vue": (props) => Vue.h("badge", props),
		"../../components/documents/DocumentOverview.vue": (props) => Vue.h("overview", props),
		"../fabric-store/FabricDocumentWorkspace.vue": (props, { slots }) => Vue.h("workspace", props, props.loading ? [] : [slots.header?.({ record: props.workspace.record || {}, headingId: "inspection-heading" }), slots["header-actions"]?.(), slots.matrix?.(), slots.rail?.()]),
		"../../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
		"../../../utils/documentOverview.js": overview,
		"../inspectionFields.js": fields, "../qualityViews.js": views,
		"./components/InspectionDebitDetails.vue": (props) => Vue.h("debits", props),
		"./components/InspectionDebitDialog.vue": (props) => Vue.h("debit-dialog", props),
		"./components/InspectionResultDialog.vue": (props) => Vue.h("result-dialog", props),
		"../../utils/documentOverview.js": overview,
		"./inspectionFields.js": fields, "./qualityViews.js": views,
	}), props)
	await tick()
	return { root, calls, toasts, navigations, route, props, action: (key) => nodes(root, "action-strip")[0].props.actions.find((action) => action.key === key) }
}

test("inspection workspace keeps heading identity, one action bar and query-backed tabs", async () => {
	const ui = await inspectionView({ ...saved, actions: { delete: { allowed: true }, edit: { allowed: true } }, permissions: { can_print: true }, print_formats: ["Standard"], debit_details: [{ name: "D1" }] })
	const workspace = nodes(ui.root, "workspace")[0]
	assert.equal(workspace.props["show-delete"], false)
	assert.equal(workspace.props["show-lifecycle-actions"], false)
	assert.equal(nodes(ui.root, "h1")[0].props.id, "inspection-heading")
	assert.equal(nodes(ui.root, "action-strip").length, 1)
	assert.equal(nodes(ui.root, "footer").length, 0)
	assert.ok(ui.action("delete"))
	assert.equal(ui.action("print"), undefined)
	assert.equal(nodes(ui.root, "tabs")[0].props.value, "inspection")
	ui.route.query = { tab: "invalid", filter: "retained" }; await tick()
	assert.equal(nodes(ui.root, "tabs")[0].props.value, "inspection")
	nodes(ui.root, "tabs")[0].props["onUpdate:value"]("details"); await tick()
	assert.deepEqual(ui.navigations.at(-1), { query: { tab: "details", filter: "retained" }, state: { listNavigation: "preserved" } })
	assert.ok(nodes(ui.root, "overview")[0].props.fields.some(({ fieldname }) => fieldname === "against_id"))
	ui.route.query.tab = "debits"; await tick()
	assert.equal(nodes(ui.root, "debits")[0].props.debits.length, 1)
	workspace.props.onReload(); await tick()
	assert.equal(ui.calls.filter(([key]) => key === "load").length, 2)
})

test("inspection tabs hide empty notes and selection groups and show the debit empty state", async () => {
	const ui = await inspectionView({ record: { name: "EQI-1", docstatus: 0 }, actions: {} })
	assert.equal(nodes(ui.root, "picker").length, 0)
	assert.equal(nodes(ui.root, "img").length, 0)
	assert.deepEqual(nodes(ui.root, "h2").map(({ text }) => text), ["Key facts"])
	ui.route.query.tab = "debits"; await tick()
	assert.equal(nodes(ui.root, "p")[0].text, "No debits raised for this inspection.")
})

test("inspection route changes close dialogs and ignore a stale load", async () => {
	const stale = deferred()
	const payload = { ...saved, actions: { update_status: { allowed: true }, create_debit: { allowed: true }, cancel: { allowed: true } } }
	const ui = await inspectionView(payload, { getInspectionWorkspace: async (name) => name === "EQI-2" ? stale.promise : { ...payload, record: { ...saved.record, name } } })
	for (const key of ["update_status", "create_debit", "cancel"]) ui.action(key).command()
	await tick()
	assert.equal(nodes(ui.root, "result-dialog")[0].props.visible, true)
	assert.equal(nodes(ui.root, "debit-dialog")[0].props.visible, true)
	ui.props.inspectionId = "EQI-2"; await tick()
	ui.props.inspectionId = "EQI-3"; await tick()
	stale.resolve({ ...saved, record: { name: "STALE" } }); await tick()
	assert.equal(nodes(ui.root, "workspace")[0].props.workspace.record.name, "EQI-3")
	assert.equal(nodes(ui.root, "result-dialog")[0].props.visible, false)
	assert.equal(nodes(ui.root, "debit-dialog")[0].props.visible, false)
	assert.equal(nodes(ui.root, "confirmation")[0].props.visible, false)
})

test("view updates Hold result with modified, creates debit, toasts and reloads", async () => {
	const ui = await inspectionView({ ...saved, record: { ...saved.record, docstatus: 1, result: "Hold" }, actions: { update_status: { allowed: true }, create_debit: { allowed: true } } })
	assert.equal(ui.action("update_status").primary, true)
	assert.equal(ui.action("edit"), undefined)
	ui.action("update_status").command(); await tick()
	assert.equal(nodes(ui.root, "result-dialog")[0].props.visible, true)
	nodes(ui.root, "result-dialog")[0].props.onConfirm("Pass"); await tick(); await tick()
	assert.deepEqual(ui.calls[1], ["result", "EQI-1", "Pass", "modified-1"])
	assert.equal(ui.calls[2][0], "load")
	const values = { debit_value: 100, reason: "Defect", debit_document: "/files/proof.pdf" }
	ui.action("create_debit").command(); await tick()
	nodes(ui.root, "debit-dialog")[0].props.onConfirm(values); await tick(); await tick()
	assert.deepEqual(ui.calls[3], ["debit", "EQI-1", values])
	assert.equal(ui.toasts.at(-1).summary, "Debit DEBIT-1 created")
})

test("view lifecycle uses latest modified and shows action errors without reloading", async () => {
	const draft = await inspectionView(saved)
	nodes(draft.root, "save-control")[0].props.onSubmit(); await tick()
	assert.deepEqual(draft.calls[1], ["submit", views.INSPECTION_DOCTYPE, "EQI-1", "modified-1"])
	const submitted = { ...saved, record: { ...saved.record, docstatus: 1 }, actions: { cancel: { allowed: true }, update_status: { allowed: true } } }
	const ui = await inspectionView(submitted, { updateInspectionResult: async () => { throw new Error("Document changed") } })
	ui.action("cancel").command(); await tick()
	nodes(ui.root, "confirmation")[0].props.onConfirm(); await tick()
	assert.deepEqual(ui.calls[1], ["cancel", views.INSPECTION_DOCTYPE, "EQI-1", "modified-1"])
	nodes(ui.root, "result-dialog")[0].props.onConfirm("Fail"); await tick()
	assert.equal(nodes(ui.root, "error-dialog")[0].props.message, "Document changed")
	assert.equal(ui.calls.filter(([key]) => key === "load").length, 2)
})

test("view Share copies the exact Desk caption and falls back to the copied toast", async () => {
	const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator"), copies = []
	Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async (value) => copies.push(value) } } })
	try {
		const payload = { ...saved, actions: { share: { allowed: true } } }
		const ui = await inspectionView(payload)
		await ui.action("share").command()
		assert.deepEqual(copies, [views.inspectionShareCaption(payload.record, selection)])
		assert.equal(ui.toasts[0].summary, "Inspection details copied")
	} finally { Object.defineProperty(globalThis, "navigator", descriptor) }
})

test("Share downloads through frappe.handler and shares the approval sheet with the copied caption", async () => {
	const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator"), previousFetch = globalThis.fetch
	const downloads = [], shares = [], copies = []
	Object.defineProperty(globalThis, "navigator", { configurable: true, value: {
		clipboard: { writeText: async (value) => copies.push(value) },
		canShare: () => true, share: async (data) => shares.push(data),
	} })
	globalThis.fetch = async (...args) => { downloads.push(args); return { ok: true, blob: async () => new Blob(["image"], { type: "image/jpeg" }) } }
	try {
		const ui = await inspectionView({ ...saved, record: { ...saved.record, upload_quality_approval_sheet: "/private/files/approval #1.jpg" }, actions: { share: { allowed: true } } })
		await ui.action("share").command()
		assert.deepEqual(downloads, [["/api/method/frappe.handler.download_file?file_url=%2Fprivate%2Ffiles%2Fapproval%20%231.jpg", { credentials: "include" }]])
		assert.equal(shares[0].text, copies[0])
		assert.equal(shares[0].files[0].type, "image/jpeg")
		assert.equal(await shares[0].files[0].text(), "image")
		assert.equal(nodes(ui.root, "error-dialog")[0].props.message, "")
	} finally { Object.defineProperty(globalThis, "navigator", descriptor); globalThis.fetch = previousFetch }
})

test("Share reports download and share failures after copying, while AbortError remains quiet", async () => {
	const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator"), previousFetch = globalThis.fetch
	try {
		for (const failure of ["http", "network", "blob", "share", "abort"]) {
			const copies = []
			Object.defineProperty(globalThis, "navigator", { configurable: true, value: {
				clipboard: { writeText: async (value) => copies.push(value) },
				share: async () => { throw Object.assign(new Error("Share failed"), { name: failure === "abort" ? "AbortError" : "Error" }) },
			} })
			globalThis.fetch = async () => {
				if (failure === "network") throw new Error("Network failed")
				return { ok: failure !== "http", blob: async () => { if (failure === "blob") throw new Error("Download failed"); return new Blob(["image"]) } }
			}
			const ui = await inspectionView({ ...saved, record: { ...saved.record, upload_quality_approval_sheet: "/files/approval.jpg" }, actions: { share: { allowed: true } } })
			await ui.action("share").command(); await tick()
			assert.equal(copies.length, 1)
			assert.equal(nodes(ui.root, "error-dialog")[0].props.message, failure === "abort" ? "" : "Sharing failed, but inspection details were copied.")
			assert.equal(ui.toasts.length, failure === "abort" ? 1 : 0)
			assert.equal(ui.action("share").disabled, false)
		}
	} finally { Object.defineProperty(globalThis, "navigator", descriptor); globalThis.fetch = previousFetch }
})

test("copyText falls back to execCommand without the Clipboard API", async () => {
	const { copyText } = await import("../src/departments/quality/qualityViews.js")
	const appended = []
	const area = { style: {}, setAttribute() {}, select() { this.selected = true }, remove() { this.removed = true } }
	const doc = { createElement: () => area, body: { appendChild: (node) => appended.push(node) }, execCommand: (command) => command === "copy" && area.selected }
	assert.equal(await copyText("caption", doc, undefined), true)
	assert.equal(area.value, "caption")
	assert.equal(area.removed, true)
	let written = ""
	assert.equal(await copyText("secure", doc, { writeText: async (text) => { written = text } }), true)
	assert.equal(written, "secure")
})

test("Supplier links show the party name", async () => {
	const { linkLabel } = await import("../src/departments/quality/qualityViews.js")
	assert.equal(linkLabel("supplier", { supplier: "S-0172", supplier_name: "Essdee Sewing Unit - Tirupur" }), "Essdee Sewing Unit - Tirupur")
	assert.equal(linkLabel("third_party_supplier", { third_party_supplier_name: "Checker" }), "Checker")
	assert.equal(linkLabel("supplier", { supplier: "S-0172" }), undefined)
	assert.equal(linkLabel("lot", { lot: "L1" }), undefined)
})

test("copyText falls back when the Clipboard API rejects", async () => {
	const { copyText } = await import("../src/departments/quality/qualityViews.js")
	const area = { style: {}, setAttribute() {}, select() {}, remove() {} }
	const doc = { createElement: () => area, body: { appendChild() {} }, execCommand: () => true }
	assert.equal(await copyText("caption", doc, { writeText: async () => { throw new Error("denied") } }), true)
	assert.equal(await copyText("caption", { ...doc, execCommand: () => { throw new Error("blocked") } }, undefined), false)
})

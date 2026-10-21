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
import * as reportConfig from "../src/components/reports/deskReportConfig.js"
import { reconcileReportLayout, reportCellValue, cellAlign } from "../src/composables/reportColumns.js"
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
	const thirdParty = fields.INSPECTION_GROUPS.find(({ key }) => key === "third_party")
	assert.ok(fields.visibleInspectionFields(thirdParty, { is_third_party: 1 }).find(({ fieldname }) => fieldname === "third_party_supplier").reqd)
	assert.equal(fields.visibleInspectionFields(thirdParty, { is_third_party: 0 }).length, 1)
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

function uploadComponent(uploadFile) {
	return component("components/InspectionImageUpload", {
		"primevue/button": Button, "../../../api/frappe.js": { uploadFile },
		"../../../components/documents/DocumentErrorDialog.vue": (props) => Vue.h("error-dialog", props),
		"../qualityViews.js": views,
	})
}

test("real image component renders distinct environment camera and gallery inputs", () => {
	const root = mountComponent(uploadComponent(), {})
	const [camera, gallery] = nodes(root, "input")
	assert.equal(camera.props.type, "file")
	assert.equal(camera.props.accept, "image/*")
	assert.equal(camera.props.capture, "environment")
	assert.equal(gallery.props.accept, "image/*")
	assert.equal(gallery.props.capture, undefined)
	assert.deepEqual(nodes(root, "button").map(({ props }) => props.label), ["Take photo", "Choose from gallery"])
	const any = mountComponent(uploadComponent(), { acceptAny: true })
	assert.equal(nodes(any, "input")[1].props.accept, undefined)
	assert.equal(nodes(any, "input")[0].props.capture, "environment")
})

test("image upload is immediate, public, attached to the saved field, and reports busy/progress", async () => {
	const task = deferred(), requests = [], changes = [], busy = []
	const root = mountComponent(uploadComponent((file, options) => { requests.push({ file, options }); return task.promise }), {
		docname: "EQI-1", "onUpdate:modelValue": (value) => changes.push(value), "onUploading-change": (value) => busy.push(value),
	})
	const file = new File(["image"], "photo.jpg", { type: "image/jpeg" })
	nodes(root, "input")[0].props.onChange({ target: { files: [file], value: "photo.jpg" } })
	await tick()
	assert.equal(requests[0].file, file)
	assert.equal(requests[0].options.doctype, views.INSPECTION_DOCTYPE)
	assert.equal(requests[0].options.docname, "EQI-1")
	assert.equal(requests[0].options.isPrivate, 0)
	assert.equal(requests[0].options.fieldname, "upload_quality_approval_sheet")
	assert.ok(nodes(root, "button").every(({ props }) => props.disabled))
	requests[0].options.onProgress(48); await tick()
	assert.equal(nodes(root, "progress")[0].props.value, 48)
	task.resolve({ file_url: "/files/photo.jpg" }); await tick()
	assert.deepEqual(changes, ["/files/photo.jpg"])
	assert.deepEqual(busy, [true, false])
})

test("failed image upload keeps the value and surfaces its server error", async () => {
	const changes = []
	const root = mountComponent(uploadComponent(async () => { throw new Error("Upload denied") }), {
		modelValue: "/files/previous.jpg", "onUpdate:modelValue": (value) => changes.push(value),
	})
	nodes(root, "input")[1].props.onChange({ target: { files: [new File(["x"], "x.jpg", { type: "image/jpeg" })], value: "" } })
	await tick()
	assert.deepEqual(changes, [])
	assert.equal(nodes(root, "error-dialog")[0].props.message, "Upload denied")
	assert.equal(nodes(root, "img")[0].props.src, "/files/previous.jpg")
})

const defaults = { against_id: "WO-1", posting_date: "2026-10-21", checking_level: "Level 2", major_aql_level: "Level-2.5", minor_aql_level: "Level-4.0", against_details: { ...selection, item: "STYLE", lot: "LOT", supplier: "SUP", order_qty: 100 } }
const saved = { record: { ...defaults, name: "EQI-1", modified: "modified-1", docstatus: 0, offer_qty: 50, inspection_type: "Final" }, colour_size_data: selection, actions: { edit: { allowed: true }, submit: { allowed: true } } }

async function editor(api = {}, props = {}, query = {}) {
	const navigations = [], guards = [], toasts = [], calls = []
	const route = Vue.reactive({ params: {}, query })
	const root = mountComponent(component("QualityInspectionEditorPage", {
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
		await changed.change("major_defect_found", 3)
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

test("picker renders only selected options when readonly and emits immutable selections when editable", async () => {
	const changes = []
	const props = Vue.reactive({ modelValue: selection, readonly: false, "onUpdate:modelValue": (value) => changes.push(value) })
	const root = mountComponent(component("components/InspectionColourSizePicker", { "primevue/button": Button, "../qualityViews.js": views }), props)
	const all = nodes(root, "button").find(({ props }) => props.label === "Select all")
	all.props.onClick()
	assert.deepEqual(changes[0].colours.map(({ selected }) => selected), [1, 1])
	props.readonly = true; await tick()
	assert.equal(nodes(root, "button").length, 2)
	assert.ok(nodes(root, "button").every(({ props }) => props.disabled))
})

test("Debit dialog requires a positive value, nonblank reason and completed document upload", async () => {
	const changes = []
	const root = mountComponent(component("components/InspectionDebitDialog", {
		"primevue/button": Button, "primevue/dialog": container,
		"../../../components/common/FormField.vue": (props) => Vue.h("field", props),
		"./InspectionImageUpload.vue": (props) => Vue.h("upload", props),
	}), { visible: true, onConfirm: (value) => changes.push(value) })
	const confirm = () => nodes(root, "button").find(({ props }) => props.label === "Create Debit")
	const change = async (name, value) => { nodes(root, "field").find(({ props }) => props.field.fieldname === name).props["onUpdate:modelValue"](value); await tick() }
	assert.ok(confirm().props.disabled)
	await change("debit_value", -10)
	await change("reason", "Rejected stitching")
	nodes(root, "upload")[0].props["onUpdate:modelValue"]("/files/debit.pdf"); await tick()
	assert.ok(confirm().props.disabled)
	await change("debit_value", 100)
	assert.equal(confirm().props.disabled, false)
	nodes(root, "upload")[0].props.onUploadingChange(true); await tick()
	assert.ok(confirm().props.disabled)
	nodes(root, "upload")[0].props.onUploadingChange(false); await tick()
	confirm().props.onClick()
	assert.deepEqual(changes, [{ debit_value: 100, reason: "Rejected stitching", debit_document: "/files/debit.pdf" }])
})

async function inspectionView(payload, api = {}) {
	const calls = [], toasts = [], navigations = []
	const root = mountComponent(component("QualityInspection", {
		"primevue/usetoast": { useToast: () => ({ add: (value) => toasts.push(value) }) },
		"vue-router": { useRoute: () => ({ params: {} }), useRouter: () => ({ push: (target) => navigations.push(target) }) },
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
		"./components/InspectionColourSizePicker.vue": (props) => Vue.h("picker", props),
		"./components/InspectionDebitDetails.vue": (props) => Vue.h("debits", props),
		"./components/InspectionDebitDialog.vue": (props) => Vue.h("debit-dialog", props),
		"./components/InspectionResultDialog.vue": (props) => Vue.h("result-dialog", props),
		"../../utils/documentOverview.js": overview,
		"./inspectionFields.js": fields, "./qualityViews.js": views,
	}), { inspectionId: "EQI-1" })
	await tick()
	return { root, calls, toasts, navigations, action: (key) => nodes(root, "action-strip")[0].props.actions.find((action) => action.key === key) }
}

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

test("action strip keeps its default primary and accepts the confirming Submit control", async () => {
	const strip = loadComponent(resolve("frontend/src/components/documents/DocumentActionStrip.vue"), {
		"primevue/button": Button, "primevue/menu": (props) => Vue.h("menu", props),
	})
	const actions = [{ key: "submit", label: "Submit", primary: true }, { key: "cancel", label: "Cancel", menuOnly: true }]
	const original = mountComponent(strip, { actions })
	assert.equal(nodes(original, "button")[0].props.label, "Submit")
	const confirmations = [], submitted = []
	const saveButton = loadComponent(resolve("frontend/src/components/documents/DocumentSaveButton.vue"), {
		"primevue/button": Button,
		"./documentPrimaryAction.js": await import("../src/components/documents/documentPrimaryAction.js"),
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => (value) => confirmations.push(value) },
	})
	const root = mountComponent(() => Vue.h(strip, { actions }, { primary: () => Vue.h(saveButton, {
		saved: true, dirty: false, showSubmit: true, documentLabel: "Quality Inspection EQI-1", onSubmit: () => submitted.push(true),
	}) }))
	nodes(root, "button")[0].props.onClick()
	assert.equal(confirmations[0].message, "Permanently Submit Quality Inspection EQI-1?")
	assert.deepEqual(submitted, [])
	confirmations[0].accept()
	assert.deepEqual(submitted, [true])
})

const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
function workOrderList(basePath, { processes = async () => ["Stitching", "Finishing Inward"], qualityCapability = { can_read: true, can_create: true } } = {}) {
	const requests = [], navigations = []
	const workOrders = loadComponent(resolve("frontend/src/departments/fabric-store/FabricWorkOrders.vue"), {
		"primevue/button": Button, "vue-router": { useRouter: () => ({ push: (to) => navigations.push(to) }) },
		"../../components/common/ListView.vue": (props, { slots }) => Vue.h("list", props, slots["toolbar-actions"]?.()),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": { openListDocument: (_router, row, _snapshot, options) => navigations.push({ name: options.routeName, params: { [options.paramName]: row.name } }) },
	})
	const section = loadComponent(resolve("frontend/src/departments/FabricStoreSection.vue"), {
		"primevue/message": stub("message"),
		"../api/fabricStore.js": { getFabricStoreCapabilities: async () => { requests.push("fabric"); return { sections: { work_orders: { can_read: true, can_create: true } } } } },
		"../api/quality.js": { getQualityCapabilities: async () => { requests.push("quality"); return { sections: { work_orders: qualityCapability } } } },
		"../api/sewing.js": { getSewingWorkOrderProcesses: () => { requests.push("processes"); return processes() } },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/FabricWorkOrders.vue": workOrders,
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
	})
	const props = Vue.reactive({ section: "work_orders", basePath, storeName: "Quality", workOrderViewRouteName: "quality-work-order" })
	return { root: mountComponent(section, props), props, requests, navigations }
}

test("Quality Work Orders use Quality capabilities, submitted sewing filters and view-only list navigation", async () => {
	const processes = deferred()
	const page = workOrderList("/quality", { processes: () => processes.promise })
	await tick()
	assert.equal(nodes(page.root, "list").length, 0)
	processes.resolve(["Stitching", "Finishing Inward"])
	await tick()
	assert.deepEqual(page.requests, ["quality", "processes"])
	const list = nodes(page.root, "list")[0]
	assert.deepEqual(list.props.filters, [["docstatus", "=", 1], ["process_name", "in", ["Stitching", "Finishing Inward"]]])
	assert.equal(nodes(page.root, "button").length, 0)
	list.props.onRowClick({ name: "WO /1" })
	assert.deepEqual(page.navigations, [{ name: "quality-work-order", params: { workOrderId: "WO /1" } }])
})

test("Quality Work Orders fail closed for denied access, empty settings and failed process lookup", async () => {
	const denied = workOrderList("/quality", { qualityCapability: { can_read: false, can_create: true } })
	const empty = workOrderList("/quality", { processes: async () => [] })
	const failed = workOrderList("/quality", { processes: async () => { throw new Error("No processes") } })
	await tick()
	assert.deepEqual(denied.requests, ["quality"])
	assert.equal(nodes(denied.root, "list").length, 0)
	assert.deepEqual(nodes(empty.root, "list")[0].props.filters, [["docstatus", "=", 1], ["process_name", "in", []]])
	assert.equal(nodes(failed.root, "list").length, 0)
	assert.equal(nodes(failed.root, "error")[0].props.message, "No processes")
})

test("Sewing and Fabric Store retain their original capability source, filters and Create button", async () => {
	for (const basePath of ["/sewing", "/fabric-store"]) {
		const page = workOrderList(basePath)
		await tick()
		assert.deepEqual(page.requests, basePath === "/sewing" ? ["fabric", "processes"] : ["fabric"])
		assert.deepEqual(nodes(page.root, "list")[0].props.filters, basePath === "/sewing" ? [["process_name", "in", ["Stitching", "Finishing Inward"]]] : [])
		assert.equal(nodes(page.root, "button")[0].props.label, "Create Work Order")
	}
})

test("late Quality process results cannot replace Fabric Store filters or create capability", async () => {
	const task = deferred(), page = workOrderList("/quality", { processes: () => task.promise })
	await tick()
	page.props.basePath = "/fabric-store"
	await tick()
	task.resolve(["Stitching"])
	await tick()
	assert.deepEqual(nodes(page.root, "list")[0].props.filters, [])
	assert.equal(nodes(page.root, "button")[0].props.label, "Create Work Order")
})

function inspectionRail({ capability = { can_read: true, can_create: true }, getList = async () => [], getCapabilities } = {}) {
	return component("components/QualityWorkOrderInspections", {
		"../../../api/frappe.js": { getList },
		"../../../api/quality.js": { getQualityCapabilities: getCapabilities || (async () => ({ sections: { inspections: capability } })) },
		"../../../components/common/DocumentLink.vue": stub("document-link"),
		"../../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../../components/reports/reportUtils.js": { formatDate: (value) => value },
		"../qualityViews.js": views,
	})
}

async function workOrderPage({ quality = true, docstatus = 1, canCreate = true, showEditorActions = !quality, list = async () => [] } = {}) {
	const navigations = [], qualityRequests = []
	const route = Vue.reactive({ params: { workOrderId: "WO /#1" } })
	const modules = {
		"vue-router": { useRoute: () => route, useRouter: () => ({ push: (to) => navigations.push(to) }) },
		"../api/fabricStore.js": { getWorkOrderWorkspace: async (name) => ({ record: { name, docstatus }, permissions: { can_create: true }, capabilities: { save: {}, amend: {}, create_delivery_challan: {} } }) },
		"../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"../utils/documentValues.js": { hasDocumentDisplayValue: () => true },
		"../components/DepartmentPage.vue": container,
		"../components/common/DocumentLink.vue": stub("document-link"),
		"../components/common/LinkField.vue": stub("link-field"),
		"../components/documents/DocumentActionStrip.vue": stub("action-strip"),
		"../components/documents/DocumentConfirmationDialog.vue": stub("confirmation"),
		"../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"./fabric-store/FabricDocumentWorkspace.vue": (props, { slots }) => Vue.h("workspace", props, [slots["header-actions"]?.(), slots.rail?.()]),
		"./quality/components/QualityWorkOrderInspections.vue": inspectionRail({ getCapabilities: async () => { qualityRequests.push(true); return { sections: { inspections: { can_read: true, can_create: canCreate } } } }, getList: list }),
	}
	for (const name of ["button", "dialog", "message", "tab", "tablist", "tabpanel", "tabpanels", "tabs"]) modules[`primevue/${name}`] = stub(name)
	for (const name of ["FabricStockOperationDialog", "RelatedDocumentWorkspaceDialog", "WorkOrderActionPanel", "WorkOrderActivityRail", "WorkOrderDetails", "WorkOrderOverview", "WorkOrderSummary"]) modules[`./fabric-store/${name}.vue`] = stub(name)
	const root = mountComponent(loadComponent(resolve("frontend/src/departments/FabricWorkOrder.vue"), modules), { quality, showEditorActions })
	await tick()
	return { root, navigations, qualityRequests, route, actions: () => nodes(root, "action-strip")[0].props.actions }
}

test("Quality WO primary inspection action uses inspection create permission and preserves the WO name", async () => {
	const page = await workOrderPage()
	const action = page.actions().find(({ key }) => key === "new_quality_inspection")
	assert.equal(action.label, "New Quality Inspection")
	assert.equal(action.icon, "pi pi-verified")
	assert.equal(action.primary, true)
	assert.equal(page.actions().filter(({ primary }) => primary).length, 1)
	action.command()
	assert.deepEqual(page.navigations, [{ path: "/quality/inspections/new", query: { against_id: "WO /#1" } }])
	assert.ok(!page.actions().some(({ key }) => ["save", "duplicate", "amend"].includes(key)))
	for (const options of [{ docstatus: 0 }, { docstatus: 2 }, { canCreate: false }]) {
		const restricted = await workOrderPage(options)
		assert.ok(!restricted.actions().some(({ key }) => key === "new_quality_inspection"))
	}
})

test("other departments keep WO editor actions and never load Quality capabilities or inspection links", async () => {
	const page = await workOrderPage({ quality: false })
	assert.deepEqual(page.qualityRequests, [])
	assert.ok(!page.actions().some(({ key }) => key === "new_quality_inspection"))
	assert.ok(["save", "duplicate", "amend"].every((key) => page.actions().some((action) => action.key === key)))
	assert.equal(nodes(page.root, "document-link").length, 0)
})

test("Quality WO inspection rail requests all EQIs against the WO and renders record links and status", async () => {
	const requests = []
	const page = await workOrderPage({ list: async (...args) => { requests.push(args); return [{ name: "EQI /1", inspection_type: "Final", posting_date: "2026-10-21", result: "Pass", docstatus: 1 }] } })
	assert.deepEqual(requests, [[views.INSPECTION_DOCTYPE, {
		filters: [["against_id", "=", "WO /#1"]], fields: ["name", "inspection_type", "posting_date", "result", "docstatus"],
		orderBy: "posting_date desc, creation desc", pageLength: 0,
	}]])
	const link = nodes(page.root, "document-link")[0]
	assert.equal(link.props.doctype, views.INSPECTION_DOCTYPE)
	assert.equal(link.props.name, "EQI /1")
	assert.equal(webDocumentPath(link.props.doctype, link.props.name, link.props.currentPath), "/web/quality/inspections/EQI%20%2F1")
	assert.equal(nodes(page.root, "badge").find(({ props }) => props.label === "Pass").props.tone, "success")
})

test("inspection rail avoids unauthorized reads, ignores stale results and allows error retry", async () => {
	const events = []
	const denied = mountComponent(inspectionRail({ capability: { can_read: false, can_create: false }, getList: () => assert.fail("Unauthorized inspection read") }), { workOrder: "WO", onCanCreate: (value) => events.push(value) })
	await tick()
	assert.equal(nodes(denied, "document-link").length, 0)
	assert.ok(events.every((value) => value === false))
	const pending = deferred()
	const props = Vue.reactive({ workOrder: "WO-1" })
	const rail = mountComponent(inspectionRail({ getList: async (_doctype, options) => options.filters[0][2] === "WO-1" ? pending.promise : [{ name: "EQI-2" }] }), props)
	await tick()
	props.workOrder = "WO-2"
	await tick()
	pending.resolve([{ name: "STALE" }]); await tick()
	assert.deepEqual(nodes(rail, "document-link").map(({ props }) => props.name), ["EQI-2"])
	let fail = true
	const retry = mountComponent(inspectionRail({ getList: async () => { if (fail) throw new Error("Read failed"); return [{ name: "EQI" }] } }), { workOrder: "WO" })
	await tick()
	assert.equal(nodes(retry, "error")[0].props.message, "Read failed")
	fail = false
	nodes(retry, "error")[0].props.onRetry(); await tick()
	assert.equal(nodes(retry, "document-link")[0].props.name, "EQI")
})

async function qualityReports(capabilities, query = {}) {
	const route = Vue.reactive({ query, hash: "#report" }), navigations = []
	const modules = {
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: (to) => navigations.push(to) }) },
		"../../api/quality.js": { getQualityCapabilities: async () => capabilities },
		"../../components/DepartmentPage.vue": container,
		"../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../components/reports/DeskBackedReport.vue": stub("desk-report"),
	}
	for (const name of ["select", "skeleton", "tab", "tablist", "tabpanel", "tabpanels", "tabs"]) modules[`primevue/${name}`] = stub(name)
	const root = mountComponent(component("QualityReports", modules), {})
	await tick()
	return { root, route, navigations }
}

test("Quality report tabs gate the RFT report by its capability and preserve query/hash navigation", async () => {
	for (const capabilities of [{}, { sections: { reports: { can_read: true } } }, { reports: { quality_inspection_rft: { can_read: false } } }]) {
		const denied = await qualityReports(capabilities)
		assert.equal(nodes(denied.root, "desk-report").length, 0)
		assert.equal(nodes(denied.root, "error")[0].props.title, "Reports unavailable")
	}
	const page = await qualityReports({ reports: { quality_inspection_rft: { can_read: true } } }, { report: "unknown", lot: "LOT" })
	assert.equal(nodes(page.root, "desk-report")[0].props["report-key"], "quality-inspection-rft")
	const select = nodes(page.root, "select")[0]
	assert.equal(select.props.modelValue, "quality-inspection-rft")
	assert.deepEqual(select.props.options.map(({ label, value }) => ({ label, value })), [{ label: "Quality Inspection RFT", value: "quality-inspection-rft" }])
	select.props["onUpdate:modelValue"]("quality-inspection-rft")
	assert.deepEqual(page.navigations, [{ query: { report: "quality-inspection-rft", lot: "LOT" }, hash: "#report" }])
	page.route.query = { report: "quality-inspection-rft" }; await tick()
	assert.equal(nodes(page.root, "tabs")[0].props.value, "quality-inspection-rft")
})

test("RFT config matches optional Desk filters, blank All selection and no date defaults", () => {
	const config = reportConfig.deskReportConfig["quality-inspection-rft"]
	assert.equal(config.title, "Quality Inspection RFT")
	assert.equal(config.dateDefaults, "none")
	assert.deepEqual(config.filters.map(({ fieldname }) => fieldname), ["lot", "item", "from_date", "to_date", "supplier", "result"])
	for (const [name, doctype] of [["lot", "SD YRP Lot"], ["item", "Item"], ["supplier", "Supplier"]]) {
		const field = config.filters.find(({ fieldname }) => fieldname === name)
		assert.equal(field.fieldtype, "Link")
		assert.equal(field.options, doctype)
	}
	assert.ok(config.filters.every((field) => !field.reqd))
	for (const field of config.filters.filter(({ fieldtype }) => fieldtype === "Date")) assert.equal(field.reqd, 0)
	assert.deepEqual(config.filters.at(-1).options, [{ value: "", label: "All" }, ...["Pass", "Fail", "Hold"].map((value) => ({ value, label: value }))])
	assert.deepEqual(reportConfig.deskReportDefaults("quality-inspection-rft", "2026-10-21"), { lot: "", item: "", from_date: "", to_date: "", supplier: "", result: "" })
})

test("RFT cell tone is opt-in and applies only to result fieldnames with known results", () => {
	const tone = reportConfig.deskReportConfig["quality-inspection-rft"].cellTone
	for (const field of ["result", "result_1", "result_20", "calculated_result"]) {
		assert.deepEqual(["Pass", "Fail", "Hold", "", null, "Other"].map((value) => tone(field, value)), ["success", "danger", "warning", "", "", ""])
	}
	for (const field of ["posting_date_1", "supplier", undefined]) assert.equal(tone(field, "Pass"), "")
	assert.equal(reportConfig.deskReportConfig["grn-report"].cellTone, undefined)
})

function dynamicRftColumns(count) {
	return ["against_id", "supplier", "lot", "item", "colour", "sizes", "description"].map((fieldname) => ({ fieldname, label: fieldname, fieldtype: "Data" })).concat(
		Array.from({ length: count }, (_, i) => [
			{ fieldname: `posting_date_${i + 1}`, label: `Inspection ${i + 1} Date`, fieldtype: "Date" },
			{ fieldname: `result_${i + 1}`, label: `Result ${i + 1}`, fieldtype: "Data" },
		]).flat(),
	)
}

test("report layout keeps every dynamic RFT date/result pair from 1 through 20 inspections", () => {
	for (let count = 1; count <= 20; count++) {
		const columns = reconcileReportLayout(dynamicRftColumns(count), [{ kind: "base", column_key: "base:against_id", visible: 1 }])
		assert.equal(columns.length, 7 + 2 * count)
		assert.ok(columns.every(({ visible }) => visible))
		assert.equal(columns.at(-1).fieldname, `result_${count}`)
	}
})

test("DeskBackedReport generates RFT with empty filters and renders all dynamic columns with cell tones", async () => {
	const requests = [], sourceColumns = Vue.ref(dynamicRftColumns(1)), sourceRows = Vue.ref([{ result_1: "Pass", supplier: "Pass" }])
	const empty = () => Vue.ref([])
	const report = loadComponent(resolve("frontend/src/components/reports/DeskBackedReport.vue"), {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/button": Button, "primevue/checkbox": () => null, "primevue/inputnumber": () => null, "primevue/select": () => null,
		"../common/DateField.vue": stub("date-field"), "../common/LinkField.vue": stub("link-field"),
		"./ReportShell.vue": (props, { slots }) => Vue.h("report-shell", props, [slots.filters?.(), slots.default?.()]),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": reportConfig,
		"./reportUtils.js": { todayIso: () => "2026-10-21", stockCellValue: (value) => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({ sourceColumns, sourceRows, activeFilters: Vue.ref(null), filtersChanged() {}, generate: async (filters) => requests.push(filters) }) },
		"../../composables/useReportColumns.js": { useReportColumns: () => {
			const columns = Vue.computed(() => reconcileReportLayout(sourceColumns.value, null))
			return { columns, displayColumns: columns, rows: sourceRows, linkSources: empty(), fieldsBySource: empty(), loadLayout() {}, cellValue: reportCellValue, cellAlign }
		} },
	})
	const root = mountComponent(report, { reportKey: "quality-inspection-rft" })
	assert.ok(nodes(root, "date-field").every(({ props }) => !props.required))
	await nodes(root, "report-shell")[0].props.onGenerate()
	assert.deepEqual(requests, [{ lot: "", item: "", from_date: "", to_date: "", supplier: "", result: "" }])
	assert.equal(nodes(root, "th").length, 9)
	assert.ok(nodes(root, "td").find((cell) => cell.text === "Pass" && cell.props.class.includes("desk-report-cell--success")))
	assert.ok(!nodes(root, "td")[1].props.class.includes("desk-report-cell--success"))
	sourceColumns.value = dynamicRftColumns(20)
	sourceRows.value = [{ result_1: "Pass", result_2: "Fail", result_20: "Hold" }]
	await tick()
	assert.equal(nodes(root, "th").length, 47)
	assert.equal(nodes(root, "th").at(-1).text, "Result 20")
	for (const [value, tone] of [["Pass", "success"], ["Fail", "danger"], ["Hold", "warning"]]) assert.ok(nodes(root, "td").find((cell) => cell.text === value).props.class.includes(`desk-report-cell--${tone}`))
	const source = read("components/reports/DeskBackedReport.vue")
	for (const token of ["--erp-success-text", "--erp-danger", "--erp-warning"]) assert.ok(source.includes(`var(${token})`))
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

test("Quality Work Order page hides DC and GRN creation", () => {
	const source = readFileSync(resolve("frontend/src/departments/FabricWorkOrder.vue"), "utf8")
	assert.match(source, /QUALITY_HIDDEN_ACTIONS = \["create_delivery_challan", "create_goods_received_note"\]/)
	assert.match(source, /if \(props\.quality && QUALITY_HIDDEN_ACTIONS\.includes\(key\)\) return/)
	assert.match(source, /\[key, \{ \.\.\.value, can_create: false \}\]/)
})

test("copyText falls back when the Clipboard API rejects", async () => {
	const { copyText } = await import("../src/departments/quality/qualityViews.js")
	const area = { style: {}, setAttribute() {}, select() {}, remove() {} }
	const doc = { createElement: () => area, body: { appendChild() {} }, execCommand: () => true }
	assert.equal(await copyText("caption", doc, { writeText: async () => { throw new Error("denied") } }), true)
	assert.equal(await copyText("caption", { ...doc, execCommand: () => { throw new Error("blocked") } }, undefined), false)
})

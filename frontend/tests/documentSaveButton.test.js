import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as fieldErrors from "../src/utils/fieldErrors.js"
import * as stockHeaders from "../src/departments/fabric-store/stockHeaderFields.js"

const component = (path, modules) => loadComponent(resolve(`frontend/src/${path}.vue`), modules)
const Button = props => Vue.h("button", props, props.label)
const nodes = (root, type) => findNodes(root, n => n.type === type)
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
async function saveButton(confirm = () => {}) {
	const actions = await import("../src/components/documents/documentPrimaryAction.js")
	return component("components/documents/DocumentSaveButton", {
		"primevue/button": Button, "primevue/splitbutton": props => Vue.h("split-button", props),
		"./documentPrimaryAction.js": actions,
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => confirm },
	})
}

test("document primary action truth table", async () => {
	const { getDocumentPrimaryAction: action } = await import("../src/components/documents/documentPrimaryAction.js")
	for (const [state, expected] of [
		[{}, "save"], [{ saved: false, dirty: false, showSubmit: true }, "save"],
		[{ saved: true, dirty: true, showSubmit: true }, "save"],
		[{ saved: true, dirty: false, showSubmit: true }, "submit"],
		[{ saved: true, dirty: false }, "save-disabled"],
		[{ docstatus: 1, showSubmit: true }, "none"], [{ docstatus: 2 }, "none"],
		[{ showSave: false, showSubmit: true }, "submit"],
		[{ saved: true, dirty: false, showSave: false, showSubmit: true }, "submit"],
		[{ showSave: false }, "none"],
		[{ saved: true, dirty: true, docstatus: 1, allowUpdateAfterSubmit: true }, "save"],
		[{ saved: true, dirty: false, docstatus: 1, allowUpdateAfterSubmit: true }, "save-disabled"],
		[{ saved: true, dirty: true, docstatus: 2, allowUpdateAfterSubmit: true }, "none"],
	]) assert.equal(action(state), expected, JSON.stringify(state))
})

test("single primary button transitions Save to Submit to edited Save and hides submitted documents", async () => {
	const props = Vue.reactive({ saved: false, dirty: true, showSubmit: true, docstatus: 0 })
	const root = mountComponent(await saveButton(), props)
	const button = () => nodes(root, "button")[0]
	assert.equal(nodes(root, "split-button").length, 0)
	assert.equal(nodes(root, "button").length, 1)
	assert.equal(button().props.label, "Save")
	props.saved = true; props.dirty = false; await tick()
	assert.equal(button().props.label, "Submit")
	props.dirty = true; await tick()
	assert.equal(button().props.label, "Save")
	props.dirty = false; props.showSubmit = false; await tick()
	assert.equal(button().props.label, "Save")
	assert.equal(button().props.disabled, true)
	props.docstatus = 1; await tick()
	assert.equal(nodes(root, "button").length, 0)
})

test("Submit confirms document identity and emits only on accept; confirmation is optional", async () => {
	const confirmations = [], events = []
	const props = Vue.reactive({ saved: true, dirty: false, showSubmit: true, documentLabel: "Stock Entry STE-1", onSubmit: () => events.push("submit") })
	const root = mountComponent(await saveButton(options => confirmations.push(options)), props)
	nodes(root, "button")[0].props.onClick()
	assert.deepEqual(events, [])
	assert.equal(confirmations[0].header, "Confirm")
	assert.equal(confirmations[0].message, "Permanently Submit Stock Entry STE-1?")
	assert.equal(confirmations[0].acceptLabel, "Submit")
	assert.equal(confirmations[0].acceptSeverity, "primary")
	assert.equal(confirmations[0].acceptIcon, "pi pi-check")
	assert.equal(confirmations[0].rejectLabel, "Cancel")
	confirmations[0].accept(); assert.deepEqual(events, ["submit"])
	props.documentLabel = ""; await tick()
	nodes(root, "button")[0].props.onClick()
	assert.equal(confirmations[1].message, "Permanently Submit this document?")
	props.confirmSubmit = false; await tick()
	nodes(root, "button")[0].props.onClick()
	assert.equal(confirmations.length, 2)
	assert.equal(events.length, 2)
})

test("Save-only defaults and independent save and submit disabling", async () => {
	const events = []
	const props = Vue.reactive({ onSave: () => events.push("save"), saveDisabled: true })
	const root = mountComponent(await saveButton(), props)
	const button = () => nodes(root, "button")[0]
	assert.equal(button().props.label, "Save"); assert.equal(button().props.disabled, true)
	props.saveDisabled = false; await tick()
	button().props.onClick(); assert.deepEqual(events, ["save"])
	Object.assign(props, { saved: true, dirty: false, showSubmit: true, submitDisabled: true }); await tick()
	assert.equal(button().props.label, "Submit"); assert.equal(button().props.disabled, true)
})

test("Fabric stock draft stays open, adopts saved identity, and tracks header and item edits", async () => {
	const visibility = [], changed = [], requests = [], loads = [], confirmations = []
	const groups = [{ item: "ITEM", items: [{ qty: 1 }] }]
	const payload = { dimensions: [], permissions: { can_create: true, can_write: true, can_submit: true }, defaults: { comments: "" }, item_groups: groups, modified: "latest-modified" }
	const root = mountComponent(component("departments/fabric-store/FabricStockOperationDialog", {
		"primevue/button": Button,
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
		"primevue/skeleton": () => null,
		"../../config/fields/stock-entry.js": { linkSearchHandlers: {} },
		"../../api/frappe.js": { getCount: async () => 1 },
		"../../api/fabricStore.js": {
			getFabricStockOperationEditor: async (_operation, options) => { loads.push(options); return payload },
			saveFabricStockOperation: async (...args) => { requests.push(args); return { record: { name: "STE-NEW", docstatus: args[2].submit ? 1 : 0 } } },
		},
		"../../components/common/FormField.vue": props => Vue.h("field", props),
		"../../components/stock/StockItemComposer.vue": props => Vue.h("composer", props),
		"../../components/documents/DocumentErrorDialog.vue": () => null,
		"../../components/documents/DocumentDeleteButton.vue": () => null,
		"../../components/documents/DocumentSaveButton.vue": await saveButton(options => confirmations.push(options)),
		"../../utils/fieldErrors.js": { ...fieldErrors, requiredFieldErrors: () => ({}) },
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
		"../../utils/stockItemComposer.js": { applyStockUpdateRates: row => row },
		"./stockHeaderFields.js": { ...stockHeaders, buildStockHeaderFields: () => [{ fieldname: "comments" }] },
	}), Vue.reactive({ visible: true, operation: "stock_entry", expectedModified: "stale", onChanged: doc => changed.push(doc), "onUpdate:visible": value => visibility.push(value) }))
	await tick()
	const primary = () => nodes(root, "button").find(n => ["Save", "Submit"].includes(n.props.label))
	assert.equal(primary().props.label, "Save")
	primary().props.onClick(); await tick(); await tick()
	assert.deepEqual(visibility, [])
	assert.equal(changed.length, 1)
	assert.equal(loads.at(-1).name, "STE-NEW")
	assert.equal(nodes(root, "dialog")[0].props.header, "Edit Stock Entry · STE-NEW")
	assert.equal(primary().props.label, "Submit")
	nodes(root, "field")[0].props["onUpdate:modelValue"]("changed"); await tick()
	assert.equal(primary().props.label, "Save")
	primary().props.onClick(); await tick(); await tick()
	assert.equal(requests.at(-1)[2].name, "STE-NEW")
	assert.equal(requests.at(-1)[2].expectedModified, "latest-modified")
	assert.equal(primary().props.label, "Submit")
	nodes(root, "composer")[0].props["onUpdate:modelValue"]([{ item: "ITEM", items: [{ qty: 2 }] }]); await tick()
	assert.equal(primary().props.label, "Save")
	primary().props.onClick(); await tick(); await tick()
	primary().props.onClick(); confirmations.at(-1).accept(); await tick(); await tick()
	assert.deepEqual(visibility, [false])
	assert.equal(requests.at(-1)[2].submit, true)
})

for (const kind of ["WorkOrderDeliveryDialog", "CpmMovementTransactionDialog", "CpmStockOperationDialog"]) for (const canSubmitDocument of [true, false]) {
	test(`${kind} draft stays open and ${canSubmitDocument ? "submits the saved document without creating another" : "keeps Save disabled without document submit permission"}`, async () => {
		const documentPermissions = { can_write: true, can_submit: canSubmitDocument }
		const visibility = [], updates = [], creates = [], editorLoads = []
		const group = [{ items: [{ values: { default: { ref_docname: "LINE", qty: 2 } } }] }]
		const props = Vue.reactive({ visible: false, cuttingPlan: "PLAN", operation: "stock_entry", movement: null, movements: [{ name: "MOVE" }], permissions: { can_create: true, can_submit: true }, "onUpdate:visible": value => visibility.push(value) })
		if (kind === "WorkOrderDeliveryDialog") { delete props.operation; delete props.movement; delete props.movements }
		if (kind === "CpmStockOperationDialog") { delete props.movement; delete props.movements }
		const created = { name: "DRAFT-1", docstatus: 0, modified: "old" }
		const dcEditor = { record: { ...created, modified: "latest" }, permissions: documentPermissions, values: { vehicle_no: "NA" }, matrices: { items: group, correction_items: [] } }
		const root = mountComponent(component(`departments/cutting/${kind}`, {
			"primevue/button": Button, "primevue/select": props => Vue.h("select", props), "primevue/checkbox": props => Vue.h("checkbox", props), "primevue/skeleton": () => null,
			"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
			"../../components/common/LinkField.vue": props => Vue.h("link", props),
			"../../components/documents/DocumentErrorDialog.vue": () => null,
			"../../components/documents/DocumentSaveButton.vue": await saveButton(options => options.accept()),
			"./WorkOrderDeliveryMatrix.vue": props => Vue.h("matrix", props),
			"./StockItemComposer.vue": props => Vue.h("composer", props),
			"./cpmApi.js": {
				getWorkOrderDeliveryEditor: async () => ({ item_details: group }),
				getStockOperationEditor: async () => ({ defaults: {}, context: {} }),
				createWorkOrderDeliveryChallan: async (...args) => { creates.push(args); return created },
				createMovementTransaction: async (...args) => { creates.push(args); return created },
				saveStockOperation: async (...args) => { creates.push(args); return created },
			},
			"../../api/fabricStore.js": {
				getDeliveryChallanWorkspace: async name => { editorLoads.push(name); return dcEditor },
				saveDeliveryChallan: async (...args) => { updates.push(args); return { ...dcEditor, record: { ...created, docstatus: 1 } } },
				getFabricStockOperationEditor: async (_operation, options) => { editorLoads.push(options.name); return { defaults: { purpose: "Material Issue", to_warehouse: "WH" }, item_groups: group, modified: "latest", permissions: documentPermissions } },
				saveFabricStockOperation: async (...args) => { updates.push(args); return { record: { ...created, docstatus: 1 } } },
			},
		}), props)
		props.visible = true; await tick()
		if (kind === "WorkOrderDeliveryDialog") nodes(root, "matrix")[0].props.onUpdate("LINE", 2)
		if (kind === "CpmMovementTransactionDialog") { nodes(root, "select")[0].props["onUpdate:modelValue"]("MOVE"); nodes(root, "link")[0].props["onUpdate:modelValue"]("WH") }
		if (kind === "CpmStockOperationDialog") {
			nodes(root, "select")[0].props["onUpdate:modelValue"]("Material Issue")
			nodes(root, "composer")[0].props["onUpdate:modelValue"](group)
		}
		await tick()
		const primary = () => nodes(root, "button").find(n => ["Save", "Submit"].includes(n.props.label))
		assert.equal(primary().props.label, "Save")
		primary().props.onClick(); await tick(); await tick()
		assert.deepEqual(visibility, [])
		assert.match(nodes(root, "dialog")[0].props.header, /Edit .* · DRAFT-1/)
		if (props.movements) { props.movements = []; await tick() }
		if (!canSubmitDocument) {
			assert.equal(primary().props.label, "Save")
			assert.equal(primary().props.disabled, true)
			return
		}
		assert.equal(primary().props.label, "Submit")
		assert.equal(primary().props.disabled, false)
		assert.equal(editorLoads.at(-1), "DRAFT-1")
		primary().props.onClick(); await tick(); await tick()
		assert.deepEqual(visibility, [false])
		assert.equal(creates.length, 1)
		assert.equal(updates.length, 1)
		const options = updates[0].at(-1)
		assert.equal(options.name, "DRAFT-1")
		assert.equal(options.expectedModified, "latest")
		assert.equal(options.submit, true)
	})
}

const callers = [
	"fabric-store/FabricStockOperationDialog", "cutting/WorkOrderDeliveryDialog", "finishing/FinishingDispatch",
	"cutting/plan/CuttingPlanEditor", "sales/ProductionOrderEditor", "cutting/CpmMovementDialog",
	"cutting/order/CuttingOrderEditor", "hr/BillTrackingEditorPage", "purchase/ItemPriceEditor",
	"accounts/components/PurchaseInvoiceEditorHeader", "cutting/CuttingMarkerDialog",
	"cutting/CpmMovementTransactionDialog", "cutting/CpmStockOperationDialog",
]
for (const name of [...callers, "accounts/PurchaseInvoiceEditorPage"]) {
	test(`primary action state wiring and SFC loading: ${name}`, () => {
		const source = readFileSync(resolve(`frontend/src/departments/${name}.vue`), "utf8")
		const button = source.match(/<(?:DocumentSaveButton|PurchaseInvoiceEditorHeader)\b[\s\S]*?\/>/)[0]
		for (const prop of ["saved", "dirty", "docstatus"]) assert.match(button, new RegExp(`:${prop}="`))
		if (name !== "accounts/PurchaseInvoiceEditorPage") assert.match(button, /:document-label="/)
		assert.doesNotMatch(button, /Save &|:show-save="!name \|\| dirty"/)
		const modules = {}
		for (const match of source.matchAll(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']/g)) {
			if (match[2] !== "vue") modules[match[2]] = {}
		}
		assert.ok(component(`departments/${name}`, modules))
	})
}

test("submit-only documents and custom workflow labels use one confirmed primary action", async () => {
	const confirmations = []
	const props = Vue.reactive({ showSave: false, showSubmit: true, submitLabel: "Submit Completion" })
	const root = mountComponent(await saveButton(options => confirmations.push(options)), props)
	assert.equal(nodes(root, "button").length, 1)
	assert.equal(nodes(root, "button")[0].props.label, "Submit Completion")
	nodes(root, "button")[0].props.onClick()
	assert.equal(confirmations.length, 1)
	Object.assign(props, { showSave: true, saved: true, dirty: false, submitLabel: "Request Approval" }); await tick()
	assert.equal(nodes(root, "button")[0].props.label, "Request Approval")
	props.dirty = true; await tick()
	assert.equal(nodes(root, "button")[0].props.label, "Save")
})

test("CPM preserves generation and selection gates while switching Save and Submit", async () => {
	const selection = Vue.ref(false), creates = []
	const props = Vue.reactive({ visible: false, cuttingPlan: "PLAN" })
	const movement = { panels: [], data: {}, accessory_data: [], collapsed_details: [], is_set_item: 0 }
	const editor = Vue.defineComponent({
		setup(_props, { expose, attrs }) {
			expose({ hasSelection: selection, selectionSummaryText: "1 bundle" })
			return () => Vue.h("movement", attrs)
		},
	})
	const root = mountComponent(component("departments/cutting/CpmMovementDialog", {
		"primevue/button": Button, "primevue/message": () => null, "primevue/skeleton": () => null,
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
		"../../components/documents/DocumentSaveButton.vue": await saveButton(),
		"../../components/documents/DocumentDeleteButton.vue": () => null,
		"../../components/documents/DocumentErrorDialog.vue": () => null,
		"../../components/documents/DocumentStatusBadge.vue": () => null,
		"./DocumentPrintButton.vue": () => null,
		"./CutPanelMovementEditor.vue": editor,
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
		"./cpmApi.js": {
			getMovementEditor: async () => ({ permissions: { can_create: true, can_submit: true }, movement_data: movement }),
			generateMovementBundles: async () => movement,
			saveMovement: async (...args) => { creates.push(args); return { name: "CPM-1", docstatus: 0, permissions: { can_write: true, can_submit: true }, movement_data: movement } },
		},
	}), props)
	props.visible = true; await tick()
	const primary = () => nodes(root, "button").find(n => ["Save", "Submit"].includes(n.props.label))
	assert.equal(primary().props.label, "Save"); assert.equal(primary().props.disabled, true)
	await nodes(root, "movement")[0].props.onGenerate(); await tick()
	assert.equal(primary().props.disabled, false)
	primary().props.onClick(); await tick()
	assert.equal(primary().props.label, "Submit"); assert.equal(primary().props.disabled, true)
	selection.value = true; await tick()
	assert.equal(primary().props.disabled, false)
	nodes(root, "movement")[0].props["onUpdate:modelValue"]({ ...movement, accessory_data: [{ weight: 1 }] }); await tick()
	assert.equal(primary().props.label, "Save")
	assert.equal(creates.length, 1)
})

test("Finishing Dispatch tracks child entry quantities and resets clean state after draft save", async () => {
	const path = "departments/finishing/FinishingDispatch"
	const source = readFileSync(resolve(`frontend/src/${path}.vue`), "utf8")
	const modules = {}
	for (const match of source.matchAll(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']/g)) if (match[2] !== "vue") modules[match[2]] = () => null
	const workspace = quantity => ({ record: { name: "DISPATCH-1", docstatus: 0 }, permissions: { can_write: true, can_submit: true }, items: [{ doc_name: "PLAN", values: { S: { dispatch_qty: quantity } } }] })
	Object.assign(modules, {
		"primevue/button": Button,
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"vue-router": { useRoute: () => ({ params: { dispatchId: "DISPATCH-1" } }), useRouter: () => ({ replace() {} }) },
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
		"../../components/DepartmentPage.vue": (_props, { slots }) => Vue.h("page", slots.default?.()),
		"../../components/documents/DocumentSaveButton.vue": await saveButton(),
		"../../api/finishing.js": { getDispatchWorkspace: async () => workspace(1), saveDispatch: async items => workspace(items[0].values.S.dispatch_qty) },
		"./finishingEntries.js": await import("../src/departments/finishing/finishingEntries.js"),
		"./components/FinishingDispatchEntry.vue": Vue.defineComponent({
			props: ["initial"],
			setup(props, { expose }) {
				const quantity = Vue.ref(props.initial.legacy.S)
				expose({ values: () => ({ quantities: { S: quantity.value }, colour_details: {}, packing_batch_dispatches: [] }) })
				return () => Vue.h("entry", { onEdit: value => { quantity.value = value } })
			},
		}),
	})
	const root = mountComponent(component(path, modules), {})
	await tick(); await tick()
	const primary = () => nodes(root, "button").find(n => ["Save", "Submit"].includes(n.props.label))
	assert.equal(primary().props.label, "Submit")
	nodes(root, "entry")[0].props.onEdit(2); await tick()
	assert.equal(primary().props.label, "Save")
	primary().props.onClick(); await tick(); await tick()
	assert.equal(primary().props.label, "Submit")
})

test("saved clean Cutting Marker shows Submit or disabled Save before entering edit mode", async () => {
	for (const canSubmit of [true, false]) {
		const path = "departments/cutting/CuttingMarkerDialog"
		const source = readFileSync(resolve(`frontend/src/${path}.vue`), "utf8")
		const modules = {}
		for (const match of source.matchAll(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']/g)) if (match[2] !== "vue") modules[match[2]] = () => null
		Object.assign(modules, {
			"primevue/button": Button,
			"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
			"../../components/documents/DocumentSaveButton.vue": await saveButton(),
			"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
			"../../api/frappe.js": { callMethod: async () => ({ marker: { name: "MARKER-1", docstatus: 0, permissions: { can_write: true, can_submit: canSubmit } } }) },
		})
		const props = Vue.reactive({ visible: false, markerName: "MARKER-1" })
		const root = mountComponent(component(path, modules), props)
		props.visible = true; await tick()
		const primary = nodes(root, "button").find(n => ["Save", "Submit"].includes(n.props.label))
		assert.ok(primary)
		assert.equal(primary.props.label, canSubmit ? "Submit" : "Save")
		assert.equal(primary.props.disabled, !canSubmit)
	}
})

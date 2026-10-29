import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { defaultOption } from "../src/utils/supplierDefaults.js"
import { normaliseFrappeTime } from "../src/utils/documentValues.js"
import { useDuplicateAction } from "../src/composables/useDuplicateAction.js"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"

const read = path => readFileSync(resolve(`frontend/src/${path}`), "utf8")
const script = path => read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
function setup(path, bindings, names) {
	const values = { ...Vue, watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {}, onBeforeRouteLeave: () => {}, defineProps: () => ({}), defineEmits: () => () => {}, useToast: () => ({ add() {} }), useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }), useDuplicateAction, PLANNING_ROUTES, takeNewDocumentDefaults, withNewDocumentDefaults, ...bindings }
	return new Function(...Object.keys(values), `${script(path)}\nreturn { ${names} }`)(...Object.values(values))
}
const nodes = (root, type) => findNodes(root, node => node.type === type)
const Button = props => Vue.h("button", props, props.label)
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

test("F-C15 reason-disabled rail actions", async () => {
	const creates = []
	const component = loadComponent(resolve("frontend/src/departments/cut-panel-store/CutPanelMovementRail.vue"), {
		"primevue/button": Button, "primevue/skeleton": () => null,
		"../../utils/documentValues.js": { normaliseFrappeTime },
		"../../components/documents/DocumentStatusBadge.vue": () => null,
	})
	const root = mountComponent(component, { linked: { sections: {}, actions: { stock_entry: { can_create: true, eligible: false, label: "Create Stock Entry", reason: "Already linked" } } }, onCreate: value => creates.push(value) })
	const button = nodes(root, "button").find(node => node.props.label === "Create Stock Entry")
	assert.equal(button.props.disabled, false)
	assert.equal(button.props["aria-disabled"], true)
	assert.equal(button.props.title, "Already linked")
	assert.match(button.props["aria-label"], /Unavailable: Already linked/)
	button.props.onFocus(); button.props.onClick(); await tick()
	assert.deepEqual(creates, [])
	assert.equal(nodes(root, "small")[0].text, "Already linked")
	const source = read("styles/enterprise.css")
	assert.match(source, /\.p-button\[aria-disabled="true"\]:hover/)
	assert.match(source, /background: var\(--erp-surface-muted\) !important/)
	assert.match(source, /color: var\(--erp-text-muted\) !important/)
	assert.match(source, /cursor: not-allowed;\s*opacity: 1;\s*transform: none;\s*box-shadow: none/)
	assert.doesNotMatch(read("components/documents/DocumentActionStrip.vue"), /opacity: \.5;/)
})

function bundle(bindings = {}) {
	const events = []
	const state = setup("departments/cut-panel-store/CutBundleEditDialog.vue", {
		defineProps: () => ({ visible: true, documentName: "CBE-1" }), defineEmits: () => (...args) => events.push(args), ...bindings,
	}, "form, editor, error, preview, choices, previewed, requestCommand, confirmCommand, confirmationTitle, confirmationMessage, acting")
	return { ...state, events }
}

test("F-B30 colour validation", async () => {
	const requests = []
	const state = bundle({ previewCutBundleSource: async (...args) => { requests.push(args); return { choices: { colours: ["Navy"] } } } })
	state.form.lot = "LOT-1"; state.form.warehouse = "STORE"
	await state.preview()
	assert.equal(state.error.value, "Select a Colour to fetch bundles.")
	assert.equal(state.previewed.value, false)
	assert.deepEqual(requests, [])
	await state.preview(0, "CBE-1", true)
	assert.deepEqual(state.choices.colours, ["Navy"])
	assert.equal(state.previewed.value, false)
	state.form.selected_colour = "Navy"
	await state.preview()
	assert.equal(requests[1][2].selected_colour, "Navy")
	assert.equal(state.previewed.value, true)
	assert.equal(state.error.value, "")
})

test("F-B30 amendment opens draft", async () => {
	const calls = []
	const draft = { name: "CBE-1-1", docstatus: 0, permissions: { can_write: true } }
	const state = bundle({ executeCutBundleCommand: async (...args) => { calls.push(args); return draft } })
	state.editor.record = { name: "CBE-1", docstatus: 2, modified: "old", permissions: { can_amend: true } }
	state.requestCommand("amend")
	assert.equal(state.confirmationTitle.value, "Amend Cut Bundle Edit?")
	assert.match(state.confirmationMessage.value, /CBE-1/)
	assert.deepEqual(calls, [])
	await state.confirmCommand()
	assert.deepEqual(calls, [["CBE-1", "amend", "old"]])
	assert.equal(state.editor.record.name, draft.name)
	assert.equal(state.editor.record.docstatus, 0)
	assert.deepEqual(state.events, [["changed", draft]])
	assert.match(read("departments/cut-panel-store/CutBundleEditDialog.vue"), /record\?\.docstatus === 2 && record\?\.permissions\?\.can_amend/)
	const list = setup("departments/cut-panel-store/CutBundleEdits.vue", {}, "changed, selectedName, listView")
	let refreshed = false
	list.listView.value = { refresh: () => { refreshed = true } }
	await list.changed(draft)
	assert.equal(list.selectedName.value, draft.name)
	assert.equal(refreshed, true)
})

test("F-B39 Cutting Plan lifecycle", async () => {
	const calls = [], routes = []
	const route = { name: "cutting-plan", params: { cuttingPlanId: "CP-1" } }
	const state = setup("departments/CuttingPlan.vue", {
		useRoute: () => route, useRouter: () => ({ replace: value => routes.push(value) }), preserveListNavigationState: name => ({ name }),
		changeCuttingPlanStatus: async (...args) => { calls.push(args); return { record: { name: args[1] === "amend" ? "CP-1-1" : "CP-1", docstatus: args[1] === "amend" ? 0 : 2 } } },
	}, "requestLifecycleAction, confirmLifecycleAction, currentDocument, lifecycleConfirmVisible, pendingLifecycleCommand, formView, editorProbe")
	let reloads = 0
	state.formView.value = { reload: () => { reloads++ } }
	state.currentDocument.value = { name: "CP-1", docstatus: 1, modified: "old" }
	state.requestLifecycleAction("cancel")
	assert.equal(state.lifecycleConfirmVisible.value, true)
	assert.deepEqual(calls, [])
	await state.confirmLifecycleAction()
	assert.deepEqual(calls, [["CP-1", "cancel", "old"]])
	assert.equal(reloads, 1)
	assert.equal(state.editorProbe.value.record.docstatus, 2)
	state.requestLifecycleAction("amend")
	await state.confirmLifecycleAction()
	assert.equal(routes[0].params.cuttingPlanId, "CP-1-1")
	const source = read("departments/CuttingPlan.vue")
	assert.match(source, /currentDocument\?\.docstatus === 1 && editorProbe\?\.permissions\?\.can_cancel/)
	assert.match(source, /currentDocument\?\.docstatus === 2 && editorProbe\?\.permissions\?\.can_amend/)
	assert.match(source, /<DocumentConfirmationDialog[^>]*Cancel \$\{cuttingPlanId\}/)
	assert.doesNotMatch(read("departments/cutting/CuttingPlanActions.vue"), /cp_status/)
})

test("F-C02 Lot item default", async () => {
	const context = { item_options: ["SHIRT"], options: [{ item: "SHIRT", production_detail: "IPD" }] }
	const state = setup("departments/fabric-store/WorkOrderEditor.vue", {
		defaultOption, getDoc: async () => ({ item: "SHIRT", production_detail: "IPD" }), getWorkOrderSelectionContext: async () => context,
	}, "applySourceChange, form, selectionContext, loading")
	state.loading.value = false
	await state.applySourceChange("lot", "LOT-1")
	assert.equal(state.form.item, "SHIRT")
	assert.equal(state.form.production_detail, "IPD")
	state.form.process_name = "Cutting"
	context.item_options.push("PANTS"); context.options.push({ item: "PANTS", production_detail: "IPD-2" })
	state.form.item = "PANTS"; state.form.production_detail = "IPD-2"
	await state.applySourceChange("lot", "LOT-2")
	assert.equal(state.form.item, "PANTS")
	assert.equal(state.form.production_detail, "IPD-2")
})

test("F-C02 supplier address defaults", () => {
	assert.equal(defaultOption("", [{ name: "A" }, { name: "B" }]), "")
	assert.equal(defaultOption("", [{ name: "Only" }]), "Only")
	const source = read("departments/fabric-store/WorkOrderEditor.vue")
	assert.match(source, /changeParty\("supplier", value\)/)
	assert.match(source, /changeParty\("delivery_location", value\)/)
})

test("F-D15/F-B16 supplier primary-address default and Delivery Challan Comments", () => {
	assert.match(read("departments/fabric-store/DeliveryChallanWorkspace.vue"), /preferPrimaryAddress: true/)
	assert.match(read("departments/fabric-store/DeliveryChallanWorkspace.vue"), /<th>Comments<\/th><th class="erp-number">Total/)
})

test("F-B19 marker title and ratio error", () => {
	const source = read("departments/cutting/CuttingMarkerDialog.vue")
	const header = source.match(/<RecordDialogHeader[\s\S]*?:title="([^"]+)"/)[1]
	const title = new Function("record", "canEdit", `return ${header}`)
	assert.equal(title({ name: "CM-1" }, false), "Cutting Marker · CM-1")
	assert.equal(title({ name: "CM-1" }, true), "Edit Cutting Marker · CM-1")
	assert.equal(title(null, true), "Create New Marker")
	const python = readFileSync(resolve("essdee_yrp/essdee_yrp/doctype/sd_yrp_cutting_marker/sd_yrp_cutting_marker.py"), "utf8")
	assert.equal(python.split("only 0.5 increments are allowed.").length - 1, 2)
	assert.doesNotMatch(python, /Only 0.5 (increment|addition) is acceptable/)
})

test("F-B06 recut labels and columns", () => {
	const state = setup("departments/fabric-store/WorkOrderActionPanel.vue", {}, "attributeText")
	assert.equal(state.attributeText({ Stage: "Piece", Panel: "", Colour: "Navy", Empty: null, Space: " " }), "Stage: Piece · Colour: Navy")
	const source = read("departments/fabric-store/WorkOrderActionPanel.vue")
	assert.match(source, /<table v-entry-table="\{ fixed: false \}" class="erp-data-table work-order-recut-table">/)
	assert.match(source, /<th v-for="value in primaryValues\(group\)" :key="value" class="erp-number">/)
	assert.doesNotMatch(source, /repeat\(auto-fit, minmax\(110px, 150px\)\)/)
})

test("F-B18 DC creation handoff", async () => {
	const events = [], calls = []
	const state = setup("departments/cutting/WorkOrderDeliveryDialog.vue", {
		defineProps: () => ({ cuttingPlan: "CP", permissions: { can_create: true } }), defineEmits: () => (...args) => events.push(args),
		createWorkOrderDeliveryChallan: async (...args) => { calls.push(args); return { record: { name: "DC-1" } } },
	}, "save, quantities, correctionQuantities")
	Object.assign(state.quantities, { YES: 2, ZERO: 0 })
	Object.assign(state.correctionQuantities, { CORRECTION: 1, EMPTY: null })
	await state.save(true)
	assert.deepEqual(calls, [["CP", { quantities: { YES: 2 }, correction_quantities: { CORRECTION: 1 } }, true]])
	assert.deepEqual(events.filter(([name]) => name !== "changed"), [["created", { doctype: "YRP Delivery Challan", name: "DC-1" }], ["update:visible", false]])
	assert.match(read("departments/cutting/CuttingPlanStockTransfers.vue"), /<WorkOrderDeliveryDialog[^>]*@created="openTransaction"/)
	assert.match(read("departments/cutting/WorkOrderDeliveryDialog.vue"), /if \(!submit\) await load\(\)/)
})

test("F-B18 submitting a saved draft opens the submitted DC", async () => {
	const events = []
	const state = setup("departments/cutting/WorkOrderDeliveryDialog.vue", {
		defineProps: () => ({ cuttingPlan: "CP", permissions: { can_create: true } }), defineEmits: () => (...args) => events.push(args),
		saveDeliveryChallan: async () => ({ record: { name: "DC-2", docstatus: 1 } }),
	}, "save, quantities, currentName, savedEditor, editor")
	state.currentName.value = "DC-2"
	Object.assign(state.editor, { item_details: [], correction_item_details: [] })
	state.savedEditor.value = { values: {}, record: { modified: "m" }, permissions: { can_write: true } }
	state.quantities.YES = 2
	await state.save(true)
	assert.deepEqual(events.filter(([name]) => name !== "changed"), [["created", { doctype: "YRP Delivery Challan", name: "DC-2" }], ["update:visible", false]])
})

test("F-B18 quantity input labels", () => {
	const component = loadComponent(resolve("frontend/src/departments/cutting/WorkOrderDeliveryMatrix.vue"), {})
	const row = { name: "SHIRT", values: { S: { ref_docname: "ROW-S" }, M: { ref_docname: "ROW-M" } } }
	const root = mountComponent(component, { groups: [{ primary_attribute: "Size", primary_attribute_values: ["S", "M"], items: [row, { ...row, values: { S: { ref_docname: "ROW-S-2" }, M: { ref_docname: "ROW-M-2" } } }] }], quantities: {} })
	const labels = nodes(root, "input").map(node => node.props["aria-label"])
	assert.equal(labels.length, 4)
	assert.equal(new Set(labels).size, 4)
	assert.match(labels[0], /SHIRT · S/)
	assert.match(labels[1], /SHIRT · M/)
	const fabric = { name: "FABRIC", attributes: { Colour: "Liver", Dia: "60 Dia" }, values: { default: { ref_docname: "ROW-1" } } }
	const fabricRoot = mountComponent(component, { groups: [{ attributes: ["Colour", "Dia"], primary_attribute_values: [], items: [fabric] }], quantities: {} })
	const fabricLabel = nodes(fabricRoot, "input")[0].props["aria-label"]
	assert.match(fabricLabel, /FABRIC · Liver · 60 Dia · Quantity/)
	assert.doesNotMatch(fabricLabel, /ROW-1/)
})

test("F-B36 Cutting Plan From CPM Stock Entry offers Skip Transit", () => {
	const source = read("departments/cutting/CpmMovementTransactionDialog.vue")
	assert.match(source, /<Checkbox v-model="form.skip_transit" binary/)
	assert.match(source, /skip_transit: false/)
	assert.match(source, /skip_transit: form.skip_transit \? 1 : 0/)
})

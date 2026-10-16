import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { buildProcessCostGrid, mergeProcessCostRows, processCostGridValues, processCostActions, processCostActionMessage, processCostFieldError, processCostPath, validateProcessCostRows, PROCESS_COST_STATES } from "../src/departments/merch/process-cost/processCostViews.js"
import { MERCH_ROUTES, merchLauncherItems, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import { extractServerMessage } from "../src/api/errorMessages.js"
import { Vue, loadComponent, mountComponent, findNodes } from "../../scripts/helpers/vue_renderer.mjs"
import * as processCostViews from "../src/departments/merch/process-cost/processCostViews.js"
import { pageNavigationKey, usePageNavigation } from "../src/components/navigation/pageNavigationContext.js"

const values = [{ name: "size-1", label: "60–70 cm" }, { name: "size-2", label: "75–80 cm" }]
const tiers = [{ attribute_value: "size-1", min_order_qty: 0, price: 12.5 }, { attribute_value: "size-1", min_order_qty: 10, price: 11 }]
const merged = mergeProcessCostRows(values, tiers, "Size")
assert.equal(merged.length, 3)
assert.equal(merged[0].attribute_value_label, "60–70 cm")
assert.equal(merged[1].price, 11)
assert.equal(merged[2].attribute_value, "size-2")
const grid = buildProcessCostGrid(merged)
assert.deepEqual(grid.rows.map((row) => row.label), ["60–70 cm", "60–70 cm", "75–80 cm"])
grid.model["tier-2"].price = 17
assert.equal(processCostGridValues(merged, grid.model)[2].price, 17)
assert.deepEqual(mergeProcessCostRows([], [], ""), [{ attribute_value: null, min_order_qty: 0, price: 0 }])
assert.deepEqual(validateProcessCostRows(merged, "Size", values), { cells: {}, message: "" })
assert.match(validateProcessCostRows([...tiers, tiers[0]], "Size", values).cells["tier-2"].min_order_qty, /Duplicate/)
assert.match(validateProcessCostRows([{ attribute_value: "bad", min_order_qty: 0, price: 1 }], "Size", values).cells["tier-0"].price, /Attribute Value/)
assert.match(validateProcessCostRows([], "", []).message, /greater than 0/)
assert.match(validateProcessCostRows([{ min_order_qty: -1, price: 1 }], "", []).cells["tier-0"].min_order_qty, /non-negative/)
assert.match(validateProcessCostRows([{ min_order_qty: 0, price: null }], "", []).cells["tier-0"].price, /non-negative/)

const called = []
const actions = processCostActions({ actions: [{ action: "Approve", label: "Approve", allowed: false, reason: "Same From Date" }], can_edit: true, can_delete: true }, { execute: (action) => called.push(action.action), edit: () => called.push("Edit"), remove: () => called.push("Delete") })
assert.deepEqual(actions.map((action) => action.key), ["Approve", "edit", "delete"])
assert.equal(actions[0].disabledReason, "Same From Date")
assert.equal(actions[2].menuOnly, true)
actions[1].command()
assert.deepEqual(called, ["Edit"])
assert.deepEqual(processCostActions({}, {}), [])
assert.equal(processCostActionMessage({ action: "Expired" }), "Cancels this rate. Work Orders stop using it from now.")
assert.match(processCostActionMessage({ action: "Approve", preview: "Approving will end PC-old on 31-12-2098" }), /PC-old/)
assert.equal(processCostPath("PC/A B"), "/merch/process-costs/PC%2FA%20B")
assert.equal(webDocumentPath("YRP Process Cost", "PC/A B", "/web/sewing"), "/web/merch/process-costs/PC%2FA%20B")
assert.equal(MERCH_ROUTES.processCostEdit, "merch-process-cost-edit")
assert.deepEqual(PROCESS_COST_STATES, ["Draft", "Approval Pending", "Approved", "Rejected", "Expired"])
const card = merchLauncherItems().find((item) => item.key === "process_costs")
assert.equal(card.label, "Process Cost")
assert.equal(card.to, "/merch/process-costs")
assert.deepEqual(visibleMerchLauncherItems({ process_costs: { can_read: true } }), [card])
assert.deepEqual(visibleMerchLauncherItems({ process_costs: { can_read: false } }), [])
const keys = merchLauncherItems().map((item) => item.key)
if (keys.includes("work_orders")) assert.ok(keys.indexOf("work_orders") < keys.indexOf("process_costs"))
if (keys.includes("bill_tracking")) assert.ok(keys.indexOf("process_costs") < keys.indexOf("bill_tracking"))

const serverError = processCostFieldError(new Error(JSON.stringify({ field_errors: { process_cost_values: "Duplicate" }, row: 2, column: "min_order_qty" })), [])
assert.equal(serverError.row, 2)
assert.equal(serverError.column, "min_order_qty")
assert.equal(serverError.field_errors.process_cost_values, "Duplicate")
const wireMessage = "Process Cost validation failed.\n" + JSON.stringify({ field_errors: { process_cost_values: "Duplicate" }, row: 2, column: "min_order_qty" })
const wireError = extractServerMessage({ _server_messages: JSON.stringify([JSON.stringify({ message: wireMessage, title: "Message" })]) })
assert.equal(processCostFieldError(new Error(wireError), []).row, 2, "the shared API preserves field and cell errors")
assert.equal(processCostFieldError(new Error("Select a cloth Item configured for this Lot and Process."), [{ fieldname: "item", label: "Item" }]).field_errors.item, "Select a cloth Item configured for this Lot and Process.")
const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const router = source("../src/router/index.js")
assert.ok(router.indexOf('path: "/merch/process-costs/new"') < router.indexOf('path: "/merch/process-costs/:processCostId"'))
for (const suffix of ["", "/new", "/:processCostId", "/:processCostId/edit"]) assert.ok(router.includes(`path: "/merch/process-costs${suffix}"`))
const editor = source("../src/departments/merch/process-cost/ProcessCostEditor.vue")
for (const text of ["Select Lot and Process first", "searchProcessCostAttributes", "ENTRY_GRID_INVALID_KEY", "parsed.column", "onBeforeRouteLeave", "isStale"]) assert.ok(editor.includes(text), text)
const page = source("../src/departments/merch/process-cost/ProcessCostPage.vue")
for (const text of ["DocumentOverview", "DocumentActionStrip", "DocumentConfirmationDialog", "DocumentErrorDialog", "waiting_note", "workflow_state"]) assert.ok(page.includes(text), text)

const { h, computed, provide, ref, nextTick } = Vue
const button = { props: ["label", "disabled"], setup: (props, { attrs }) => () => h("button", { ...attrs, disabled: props.disabled }, props.label) }
const empty = { render: () => null }
const field = {
	props: ["field", "modelValue", "error", "searchHandler", "disabled"],
	setup: (props) => () => h("div", { "data-field": props.field.fieldname }, [
		h("label", props.field.label), h("button", { onClick: () => props.searchHandler?.(""), disabled: props.disabled }, "Search"),
		props.error ? h("small", { role: "alert" }, props.error) : null,
	]),
}
const departmentPage = {
	props: { backTo: String, backLabel: String, inlineNavigation: Boolean },
	setup(props, { slots }) {
		provide(pageNavigationKey, { backTo: computed(() => props.backTo), backLabel: computed(() => props.backLabel), inline: computed(() => props.inlineNavigation) })
		return () => h("main", slots.default?.())
	},
}
const permissionMessage = "You cannot read YRP Item Production Detail IPD-1 needed to price by Attribute."
const fields = processCostViews.PROCESS_COST_DETAILS.map((fieldname) => ({ fieldname, label: { item: "Item", uom: "UOM", supplier_name: "Supplier Name", attribute: "Attribute" }[fieldname] || fieldname }))
const initialValues = { lot: "LOT-1", process_name: "Stitching", item: "ITEM-1", uom: "Nos", supplier_name: "Supplier One", supplier: "SUP-1", from_date: "2099-01-01", tax_slab: "TAX-1", attribute: "", process_cost_values: [{ min_order_qty: 0, price: 12 }] }
const selection = { item: "ITEM-1", uom: "Nos", is_cloth_process: false, attribute_values: [] }
const testRouter = { push: async () => {} }
const route = { query: {} }
let attributeResponse = { options: [], field_errors: { attribute: permissionMessage } }
let saved = null
const modules = {
	"primevue/button": button, "primevue/select": empty, "primevue/message": empty,
	"vue-router": { useRoute: () => route, useRouter: () => testRouter, onBeforeRouteLeave: () => {}, onBeforeRouteUpdate: () => {},
		RouterLink: { props: ["to"], setup: (props, { slots, attrs }) => () => h("a", { ...attrs, href: props.to }, slots.default?.()) } },
	"../../../api/frappe.js": { getDoc: async () => ({}) },
	"../../../api/merch.js": {
		getProcessCostEditor: async () => ({ values: structuredClone(initialValues), fields, tier_fields: [], context: selection }),
		getProcessCostGrid: async () => selection,
		searchProcessCostAttributes: async () => attributeResponse,
		saveProcessCost: async (values) => { saved = JSON.parse(JSON.stringify(values)); return { record: { name: "PC-1" } } },
		getProcessCostWorkspace: async () => ({ record: { name: "PC-1", process_name: "Stitching" }, fields: [], tiers: [], tier_fields: [] }),
	},
	"../../../components/DepartmentPage.vue": departmentPage,
	"../../../components/common/FormField.vue": field,
	"../../../components/common/EntryGrid.vue": empty,
	"../../../components/common/WorkspaceLoadError.vue": empty,
	"../../../components/common/entryGrid.js": { ENTRY_GRID_INVALID_KEY: Symbol() },
	"../../../components/documents/DocumentConfirmationDialog.vue": empty,
	"../../../components/documents/DocumentErrorDialog.vue": empty,
	"../../../components/documents/DocumentOverview.vue": empty,
	"../../../components/documents/DocumentStatusBadge.vue": empty,
	"../../../components/documents/DocumentActionStrip.vue": empty,
	"./processCostViews.js": processCostViews,
	"./pageNavigationContext.js": { usePageNavigation },
	"../../router/departmentLock.js": { isLockedExit: () => false },
	"../../composables/useDocumentListNavigation.js": { useDocumentListNavigation: () => ({ hasContext: ref(false), sourceFullPath: ref("") }) },
}
const previousWindow = globalThis.window
globalThis.window = { addEventListener() {}, removeEventListener() {} }
const editorComponent = loadComponent(new URL("../src/departments/merch/process-cost/ProcessCostEditor.vue", import.meta.url).pathname, modules)
const flush = async () => { await Promise.resolve(); await nextTick(); await Promise.resolve(); await nextTick() }
const editorRoot = mountComponent(editorComponent, {})
await flush()
const searchButton = () => findNodes(editorRoot, (node) => node.props["data-field"] === "attribute")[0].children.find((node) => node.type === "button")
await searchButton().props.onClick()
await flush()
assert.equal(findNodes(editorRoot, (node) => node.props["data-field"] === "attribute")[0].children.find((node) => node.props.role === "alert").text, permissionMessage, "attribute_permission_message_renders_under_attribute")
const saveButton = findNodes(editorRoot, (node) => node.type === "button" && node.text === "Save")[0]
assert.equal(saveButton.props.disabled, false, "attribute_permission_message_keeps_save_enabled_without_attribute")
await saveButton.props.onClick()
assert.equal(saved.attribute, "", "no_attribute_cost_saves_after_attribute_permission_failure")
assert.equal(saved.process_cost_values[0].price, 12)
attributeResponse = { options: [{ name: "Size", label: "Size" }] }
await searchButton().props.onClick()
await flush()
assert.equal(findNodes(editorRoot, (node) => node.props.role === "alert").length, 0, "successful_attribute_search_clears_permission_message")
const outputs = findNodes(editorRoot, (node) => node.type === "output")
assert.deepEqual(outputs.map((node) => node.text), ["ITEM-1", "Nos", "Supplier One"], "derived_fields_render_as_read_only_values")
assert.equal(findNodes(editorRoot, (node) => node.props["data-field"] === "item" || node.props["data-field"] === "uom" || node.props["data-field"] === "supplier_name").length, 0)
assert.equal(findNodes(editorRoot, (node) => node.type === "label" && node.text === "Attribute Value").length, 0, "no_attribute_hides_tier_value_label")
assert.equal(findNodes(editorRoot, (node) => node.type === "button" && node.text === "Add tier").length, 1, "no_attribute_keeps_add_tier")
const backLink = (root) => findNodes(root, (node) => node.type === "a" && String(node.props["aria-label"]).startsWith("Back"))[0]
assert.equal(backLink(editorRoot).props.href, "/merch/process-costs", "new_editor_back_link_returns_to_process_costs")
assert.equal(backLink(editorRoot).props["aria-label"], "Back to Process Costs")
const editRoot = mountComponent(editorComponent, { processCostId: "PC/1" })
await flush()
assert.equal(backLink(editRoot).props.href, "/merch/process-costs/PC%2F1", "edit_back_link_returns_to_record")
const pageComponent = loadComponent(new URL("../src/departments/merch/process-cost/ProcessCostPage.vue", import.meta.url).pathname, modules)
const pageRoot = mountComponent(pageComponent, { processCostId: "PC-1" })
await flush()
assert.equal(backLink(pageRoot).props.href, "/merch/process-costs", "record_back_link_returns_to_process_costs")
assert.equal(backLink(pageRoot).props["aria-label"], "Back to Process Costs")
globalThis.window = previousWindow
console.log("process cost views tests passed")

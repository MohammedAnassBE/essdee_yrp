import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
function setup(operation, editor, name = "STOCK-1") {
	const confirmations = [], discarded = [], events = []
	const root = mountComponent(loadComponent(resolve("frontend/src/departments/fabric-store/FabricStockOperationDialog.vue"), {
		"primevue/button": props => Vue.h("button", props, props.label),
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
		"primevue/skeleton": () => null,
		"../../config/fields/stock-entry.js": { linkSearchHandlers: {} },
		"../../api/frappe.js": {},
		"../../api/fabricStore.js": { discardCompletionDraft: async (...args) => { discarded.push(args); return { name } } },
		"../../components/common/FormField.vue": () => null,
		"../../components/documents/DocumentDeleteButton.vue": Vue.defineComponent({
			props: ["doctype", "documentLabel", "name", "docstatus", "disabled", "redirect"], emits: ["deleted"],
			setup: (props, { emit }) => () => Vue.h("delete-button", { ...props, onDeleted: () => emit("deleted") }),
		}),
		"../../components/documents/DocumentSaveButton.vue": () => null,
		"../../components/documents/DocumentErrorDialog.vue": () => null,
		"../../components/stock/StockItemComposer.vue": () => null,
		"../../utils/fieldErrors.js": {}, "../../utils/stockItemComposer.js": {},
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => options => confirmations.push(options) },
		"./stockHeaderFields.js": { buildStockHeaderFields: () => [], createWarehouseCheck: () => ({}), createSupplierAutofill: () => ({ forget() {} }) },
		"./stockEntryAutofill.js": { createStockEntryAutofill: () => ({ forget() {} }) },
	}), { visible: true, operation, name, initialEditor: editor, onChanged: value => events.push(["changed", value]), "onUpdate:visible": value => events.push(["visible", value]) })
	return { root, confirmations, discarded, events }
}

for (const [operation, doctype, label] of [
	["stock_reconciliation", "YRP Stock Reconciliation", "Stock Reconciliation"],
	["stock_update", "YRP Stock Update", "Stock Update"],
	["stock_entry", "YRP Stock Entry", "Stock Entry"],
	["lot_transfer", "SD YRP Lot Transfer", "Lot Transfer"],
]) {
	test(`${label} saved draft offers embedded Delete and refreshes the list on deletion`, async () => {
		const { root, events } = setup(operation, { doctype, docstatus: 0, permissions: { can_delete: true } })
		await tick()
		const button = nodes(root, "delete-button")[0]
		assert.ok(button)
		assert.equal(button.props.doctype, doctype)
		assert.equal(button.props.documentLabel, label)
		assert.equal(button.props.name, "STOCK-1")
		assert.equal(button.props.docstatus, 0)
		assert.equal(button.props.redirect, false)
		assert.equal(nodes(root, "button").some(node => node.props.label === "Discard Draft"), false)
		button.props.onDeleted()
		assert.deepEqual(events, [["visible", false], ["changed", undefined]])
	})
}

test("stock Delete is hidden for unsaved, submitted, cancelled, or unpermitted documents", async () => {
	for (const [name, docstatus, can_delete] of [["", 0, true], ["STOCK-1", 1, true], ["STOCK-1", 2, true], ["STOCK-1", 0, false]]) {
		const { root } = setup("stock_entry", { doctype: "YRP Stock Entry", docstatus, permissions: { can_delete } }, name)
		await tick()
		assert.equal(nodes(root, "delete-button").length, 0)
	}
})

test("protected stock completion drafts keep Discard Draft and never also show Delete", async () => {
	const state = setup("stock_entry", { doctype: "YRP Stock Entry", protected_completion: true, modified: "latest", permissions: { can_delete: true } })
	await tick()
	assert.equal(nodes(state.root, "delete-button").length, 0)
	const discard = nodes(state.root, "button").find(node => node.props.label === "Discard Draft")
	assert.ok(discard)
	discard.props.onClick()
	assert.equal(state.confirmations[0].header, "Discard completion draft?")
	assert.deepEqual(state.discarded, [])
	await state.confirmations[0].accept()
	assert.deepEqual(state.discarded, [["STOCK-1", "latest"]])
	assert.deepEqual(state.events, [["changed", { name: "STOCK-1" }], ["visible", false]])
})

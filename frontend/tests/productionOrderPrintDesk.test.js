import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

function desk(docstatus = 1, { status = "Open", canCreatePurchaseOrder = false } = {}) {
	const calls = [], opened = [], dialogs = [], messages = [], buttons = [], routes = [], newDocs = []
	let handlers
	const frappe = {
		ui: {
			form: { on: (_doctype, value) => { handlers = value } },
			Dialog: class {
				constructor(options) { Object.assign(this, options); dialogs.push(this) }
				show() { this.visible = true }
				hide() { this.visible = false }
				get_values() { return this.values }
			},
		},
		call: options => calls.push(options),
		msgprint: message => messages.push(message),
		urllib: { get_full_url: url => `https://test.local${url}` },
		meta: { has_field: () => false }, perm: { has_perm: () => true },
		model: {
			can_create: doctype => doctype === "Purchase Order" && canCreatePurchaseOrder,
			with_doctype: (_doctype, callback) => callback(),
			get_new_doc: doctype => { const doc = { doctype, name: "new-purchase-order-1" }; newDocs.push(doc); return doc },
		},
		user: { has_role: () => false },
		set_route: (...args) => routes.push(args),
	}
	const context = vm.createContext({ frappe, __: text => text, window: { open: (...args) => opened.push(args) } })
	vm.runInContext(readFileSync(new URL("../../essdee_yrp/public/js/production_order_workflow.js", import.meta.url), "utf8"), context)
	vm.runInContext("render_production_order_editor = () => {}; setup_ppo_approval_actions = () => {};", context)
	const frm = { doc: { doctype: "YRP Production Order", name: "PPO/1 & 2#x", docstatus, status }, set_df_property() {}, clear_custom_buttons() {}, change_custom_button_type() {}, add_custom_button: (label, click, group) => buttons.push({ label, click, group }) }
	handlers.refresh(frm)
	return { calls, opened, dialogs, messages, buttons, routes, newDocs, frm }
}

test("Desk Print appears only in the submitted block and fetches frozen print settings", () => {
	for (const status of [0, 2]) assert.equal(desk(status).buttons.some(button => button.label === "Print"), false)
	const state = desk()
	state.buttons.find(button => button.label === "Print").click()
	assert.equal(state.calls[0].method, "essdee_yrp.production_order_workflow.get_production_order_print_settings")
	assert.equal(state.calls[0].args.production_order, "PPO/1 & 2#x")
	assert.equal(state.calls[0].freeze, true)
	state.calls[0].callback({ message: { fg_item_exists: true, pieces_per_box: 10 } })
	assert.equal(state.dialogs.length, 0)
	assert.deepEqual(state.opened, [["https://test.local/printview?doctype=YRP%20Production%20Order&name=PPO%2F1%20%26%202%23x&format=Essdee%20Production%20Order&trigger_print=1&pieces_per_box=10", "_blank"]])
})

test("Desk dialog matches legacy fields, validates, and opens only after valid input", () => {
	for (const fg_item_exists of [false, true]) {
		const state = desk()
		state.buttons.find(button => button.label === "Print").click()
		state.calls[0].callback({ message: { fg_item_exists, pieces_per_box: 0 } })
		const dialog = state.dialogs[0]
		assert.equal(dialog.title, "Print Production Order")
		assert.equal(dialog.primary_action_label, "Print")
		const field = dialog.fields[0]
		assert.equal(field.fieldname, "pieces_per_box")
		assert.equal(field.fieldtype, "Int")
		assert.equal(field.label, "Pieces per Box")
		assert.equal(field.reqd, 1)
		assert.equal("default" in field, false)
		assert.equal(field.description, fg_item_exists ? "Pieces per Box is not configured in FG Item Master." : "The item is not available in FG Item Master.")
		dialog.primary_action()
		assert.equal(dialog.visible, true)
		for (const pieces_per_box of [0, -1]) {
			dialog.values = { pieces_per_box }
			dialog.primary_action()
			assert.equal(dialog.visible, true)
			assert.equal(state.messages.at(-1), "Pieces per Box must be greater than zero.")
		}
		dialog.hide()
		assert.deepEqual(state.opened, [])
		dialog.show()
		dialog.values = { pieces_per_box: 7 }
		dialog.primary_action()
		assert.equal(dialog.visible, false)
		assert.equal(new URL(state.opened[0][0]).searchParams.get("pieces_per_box"), "7")
	}
})

test("Desk standard print (printer icon / menu / Ctrl+P) asks for pieces per box on every docstatus", () => {
	for (const docstatus of [0, 1, 2]) {
		const state = desk(docstatus)
		state.frm.print_doc()
		assert.equal(state.calls[0].method, "essdee_yrp.production_order_workflow.get_production_order_print_settings")
		state.calls[0].callback({ message: { fg_item_exists: true, pieces_per_box: 0 } })
		assert.equal(state.dialogs[0].title, "Print Production Order")
	}
})

test("Desk Create > Purchase Order opens a new PO against an open submitted PPO for PO creators only", () => {
	const createButton = state => state.buttons.find(button => button.label === "Purchase Order" && button.group === "Create")
	const state = desk(1, { canCreatePurchaseOrder: true })
	createButton(state).click()
	assert.deepEqual(state.newDocs, [{ doctype: "Purchase Order", name: "new-purchase-order-1", is_yrp_managed: 1, naming_series: "YRP-PO-.YYYY.-", against: "YRP Production Order", against_id: "PPO/1 & 2#x" }])
	assert.deepEqual(state.routes, [["Form", "Purchase Order", "new-purchase-order-1"]])
	assert.equal(createButton(desk(1)), undefined)
	assert.equal(createButton(desk(0, { canCreatePurchaseOrder: true })), undefined)
	assert.equal(createButton(desk(1, { status: "Closed", canCreatePurchaseOrder: true })), undefined)
})

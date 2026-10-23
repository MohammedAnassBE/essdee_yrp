import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

const read = path => readFileSync(new URL(path, import.meta.url), "utf8")

test("/web dispatch shows Print Stock Entry for the linked YRP Stock Entry via the shared print dialog", () => {
	const source = read("../src/departments/finishing/FinishingDispatch.vue")
	const button = source.match(/<DocumentPrintButton[^>]*label="Print Stock Entry"[^>]*\/>/)?.[0]
	assert.ok(button, "Print Stock Entry button is rendered")
	assert.match(button, /v-if="dispatchId && record\.stock_entry"/)
	assert.match(button, /doctype="YRP Stock Entry"/)
	assert.match(button, /:name="record\.stock_entry"/)
	assert.doesNotMatch(button, /:formats=/, "formats stay null so the button checks print permission on the Stock Entry")
})

test("DocumentPrintButton without formats is gated on the document's print permission", () => {
	const source = read("../src/components/documents/DocumentPrintButton.vue")
	assert.match(source, /formats !== null \|\| permissions\?\.print/)
})

function desk({ stockEntry = "STE-1", canPrint = true, docstatus = 1 } = {}) {
	const buttons = [], routes = [], printChecks = []
	let handlers
	const frappe = {
		ui: { form: { on: (_doctype, value) => { handlers = value } } },
		model: { can_print: doctype => { printChecks.push(doctype); return canPrint } },
		set_route: (...args) => routes.push(args),
	}
	const context = vm.createContext({ frappe, __: text => text, essdee_yrp: {} })
	vm.runInContext(read("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_finishing_plan_dispatch/sd_yrp_finishing_plan_dispatch.js"), context)
	vm.runInContext("configure_naming_series = () => {}; mount_dispatch_editor = () => {};", context)
	const frm = { doc: { name: "FPD-1", docstatus, stock_entry: stockEntry }, perm: [{ write: 1 }], add_custom_button: (label, click) => buttons.push({ label, click }) }
	handlers.refresh(frm)
	return { buttons, routes, printChecks }
}

test("Desk Print Stock Entry opens the Frappe print view for the linked Stock Entry", () => {
	const state = desk()
	const button = state.buttons.find(entry => entry.label === "Print Stock Entry")
	assert.ok(button)
	assert.deepEqual(state.printChecks, ["YRP Stock Entry"])
	button.click()
	assert.deepEqual(state.routes, [["print", "YRP Stock Entry", "STE-1"]])
})

test("Desk hides Print Stock Entry without a linked Stock Entry or print permission", () => {
	assert.equal(desk({ stockEntry: "" }).buttons.some(entry => entry.label === "Print Stock Entry"), false)
	assert.equal(desk({ canPrint: false }).buttons.some(entry => entry.label === "Print Stock Entry"), false)
	assert.equal(desk({ docstatus: 0 }).buttons.some(entry => entry.label === "Print Stock Entry"), false)
})

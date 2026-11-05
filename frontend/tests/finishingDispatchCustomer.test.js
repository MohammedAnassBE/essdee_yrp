import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"

const read = path => readFileSync(new URL(path, import.meta.url), "utf8")

test("/web dispatch header has an optional Customer link editable only on a writable draft", () => {
	const source = read("../src/departments/finishing/FinishingDispatch.vue")
	const field = source.match(/<LinkField[^>]*label="Customer"[^>]*\/>/)?.[0]
	assert.ok(field, "Customer LinkField is rendered")
	assert.match(field, /v-model="customer"/)
	assert.match(field, /doctype="Customer"/)
	assert.doesNotMatch(field, /\brequired\b/)
	assert.match(field, /:disabled="!draft \|\| busy \|\| !permissions\.can_write"/)
})

test("/web dispatch saves the Customer and counts it as an unsaved change", () => {
	const source = read("../src/departments/finishing/FinishingDispatch.vue")
	assert.match(source, /saveDispatch\(collectItems\(\), dispatchId\.value, submit, record\.value\.modified, customer\.value\)/)
	assert.match(source, /customer\.value = data\?\.record\?\.customer \|\| ""/)
	assert.match(source, /JSON\.stringify\(\{ items: collectItems\(\), customer: customer\.value \}\)/)
})

test("saveDispatch posts the Customer to save_dispatch", () => {
	const source = read("../src/api/finishing.js")
	assert.match(source, /export function saveDispatch\(items, name = "", submit = false, expectedModified = "", customer = ""\)/)
	assert.match(source, /customer: customer \|\| null/)
})

function deskDispatchFields(customer) {
	let dialogOptions
	const frappe = {
		ui: { form: { on: () => {} }, Dialog: function Dialog(options) { dialogOptions = options; this.show = () => {} } },
	}
	const essdee_yrp = {
		dispatch_location_fields: () => ["from_supplier", "from_warehouse", "to_supplier", "to_warehouse"].map(fieldname => ({ fieldname, reqd: 1 })),
	}
	const context = vm.createContext({ frappe, __: text => text, essdee_yrp })
	vm.runInContext(read("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_finishing_plan_dispatch/sd_yrp_finishing_plan_dispatch.js"), context)
	context.show_dispatch_dialog({ doc: { name: "FPD-1", customer } })
	return [...dialogOptions.fields].map(field => field.fieldname)
}

test("Desk Dispatch Stock skips To Supplier and To Warehouse for a Customer dispatch", () => {
	assert.deepEqual(deskDispatchFields("CUST-1"), ["from_supplier", "from_warehouse", "goods_value", "vehicle_no"])
	assert.deepEqual(deskDispatchFields(""), ["from_supplier", "from_warehouse", "to_supplier", "to_warehouse", "goods_value", "vehicle_no"])
})

test("/web Dispatch Stock hides and stops requiring To Supplier and To Warehouse for a Customer dispatch", () => {
	const source = read("../src/departments/finishing/FinishingDispatch.vue")
	for (const fieldname of ["to_supplier", "to_warehouse"]) {
		const field = source.match(new RegExp(`<LinkField[^>]*stock\\.${fieldname}[^>]*/>`))?.[0]
		assert.ok(field, `${fieldname} field is rendered`)
		assert.match(field, /v-if="!record\.customer"/)
	}
	assert.match(source, /\.filter\(\(\[field\]\) => !record\.value\.customer \|\| !field\.startsWith\("to_"\)\)/)
})

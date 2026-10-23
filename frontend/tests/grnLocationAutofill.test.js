import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { forgetAutofill } from "../src/composables/useSingleOptionAutofill.js"
import { autofillGoodsReceivedNoteLocation, GRN_LOCATION_AUTOFILL } from "../src/departments/fabric-store/grnLocationAutofill.js"

const workspace = readFileSync(new URL("../src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue", import.meta.url), "utf8")
const options = {
	"Unit One": { warehouse: "WH One", address: "Addr One" },
	"Unit Two": { warehouse: "WH Two", address: "Addr Two" },
	"Unit Many": { warehouse: null, address: null },
}
const calls = []
const fetchOptions = async (args) => {
	calls.push(args)
	return options[args.supplier]
}
const fill = (form, fieldname) => autofillGoodsReceivedNoteLocation(form, fieldname, { fetchOptions })

test("supplier fills From Warehouse and Billing Address; Delivery Location fills To Warehouse", async () => {
	assert.deepEqual(GRN_LOCATION_AUTOFILL.supplier.targets, { warehouse: "from_warehouse", address: "billing_address" })
	assert.deepEqual(GRN_LOCATION_AUTOFILL.delivery_location.targets, { warehouse: "to_warehouse" })
	const form = { supplier: "Unit One", delivery_location: "Unit Two" }
	assert.deepEqual(await fill(form, "supplier"), { from_warehouse: "WH One", billing_address: "Addr One" })
	assert.deepEqual(await fill(form, "delivery_location"), { to_warehouse: "WH Two" })
	assert.equal(form.to_warehouse, "WH Two")
})

test("other GRN fields do not call the endpoint", async () => {
	calls.length = 0
	assert.deepEqual(await fill({ supplier: "Unit One" }, "posting_date"), {})
	assert.equal(calls.length, 0)
})

test("a supplier with several warehouses leaves the fields empty", async () => {
	const form = { supplier: "Unit Many", from_warehouse: "" }
	assert.deepEqual(await fill(form, "supplier"), {})
	assert.equal(form.from_warehouse, "")
})

test("supplier change replaces stale auto-fills but keeps the user's warehouse", async () => {
	const form = { supplier: "Unit One" }
	await fill(form, "supplier")
	form.supplier = "Unit Two"
	assert.deepEqual(await fill(form, "supplier"), { from_warehouse: "WH Two", billing_address: "Addr Two" })
	form.from_warehouse = "Picked WH"
	form.supplier = "Unit Many"
	await fill(form, "supplier")
	assert.equal(form.from_warehouse, "Picked WH")
	assert.equal(form.billing_address, "")
})

test("forgetting after a record load stops stale auto-fill tracking", async () => {
	const form = { supplier: "Unit One" }
	await fill(form, "supplier")
	forgetAutofill(form)
	form.supplier = "Unit Two"
	await fill(form, "supplier")
	assert.equal(form.from_warehouse, "WH One")
})

test("GRN workspace runs the autofill on party changes and resets it on load", () => {
	assert.match(workspace, /import \{ autofillGoodsReceivedNoteLocation, GRN_LOCATION_AUTOFILL \} from "\.\/grnLocationAutofill\.js"/)
	assert.match(workspace, /await Promise\.all\(\[addressField && defaultAddress\(addressField, value\), fillSingleLocationOptions\(fieldname\)\]\)/)
	assert.match(workspace, /autofillGoodsReceivedNoteLocation\(form, fieldname, \{ onChange: markDirty \}\)/)
	assert.match(workspace, /function applyWorkspace\(nextWorkspace\) \{\n\tinvalidateAddresses\(\)\n\tforgetAutofill\(form\)/)
	assert.match(workspace, /function clearWorkspaceState\(name = ""\) \{\n\tinvalidateAddresses\(\)\n\tforgetAutofill\(form\)/)
	assert.match(workspace, /const busy = Boolean\(acting\.value\) \|\| addressPending\.value/)
	assert.match(workspace, /locationAutofillPending\.value > 0/)
	assert.match(workspace, /if \(editingSubmitted\.value \|\| !\(fieldname in GRN_LOCATION_AUTOFILL\)\) return/)
})

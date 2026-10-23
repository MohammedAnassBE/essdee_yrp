import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { isAutofilled } from "../src/composables/useSingleOptionAutofill.js"
import { changeWorkOrderParty } from "../src/departments/fabric-store/workOrderAddresses.js"

const editor = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderEditor.vue", import.meta.url), "utf8")
const optionsBySupplier = {
	"Unit A": { address: "Addr A", address_display: "A street" },
	"Unit B": { address: "Addr B", address_display: "B street" },
	"Unit Many": { address: null, address_display: null },
}
const calls = []
const fetchOptions = async (args) => { calls.push(args); return optionsBySupplier[args.supplier] }

test("supplier with one address fills the supplier address only", async () => {
	const form = { supplier: "", supplier_address: "", delivery_location: "", delivery_address: "" }
	await changeWorkOrderParty(form, "supplier", "Unit A", { fetchOptions })
	assert.deepEqual(form, { supplier: "Unit A", supplier_address: "Addr A", delivery_location: "", delivery_address: "" })
	assert.ok(isAutofilled(form, "supplier_address"))
})

test("delivery location with one address fills the delivery address", async () => {
	const form = { supplier: "Unit B", supplier_address: "Picked", delivery_location: "", delivery_address: "" }
	calls.length = 0
	await changeWorkOrderParty(form, "delivery_location", "Unit A", { fetchOptions })
	assert.deepEqual(calls, [{ supplier: "Unit A" }])
	assert.equal(form.delivery_address, "Addr A")
	assert.equal(form.supplier_address, "Picked")
})

test("party with several addresses leaves the address empty", async () => {
	const form = { supplier: "Unit A", supplier_address: "Addr A" }
	await changeWorkOrderParty(form, "supplier", "Unit Many", { fetchOptions })
	assert.equal(form.supplier_address, "")
})

test("changing or clearing the party drops the previous party's address", async () => {
	const form = { delivery_location: "Unit A", delivery_address: "User picked" }
	await changeWorkOrderParty(form, "delivery_location", "Unit B", { fetchOptions })
	assert.equal(form.delivery_address, "Addr B")
	calls.length = 0
	await changeWorkOrderParty(form, "delivery_location", "", { fetchOptions })
	assert.deepEqual(form, { delivery_location: "", delivery_address: "" })
	assert.deepEqual(calls, [])
})

test("address picked while the lookup is pending is kept", async () => {
	const form = { supplier: "", supplier_address: "" }
	let release
	const slow = (args) => new Promise((resolve) => { release = () => resolve(optionsBySupplier[args.supplier]) })
	const change = changeWorkOrderParty(form, "supplier", "Unit A", { fetchOptions: slow })
	form.supplier_address = "User picked"
	release()
	await change
	assert.equal(form.supplier_address, "User picked")
})

test("older supplier response is ignored after a newer supplier is chosen", async () => {
	const form = { supplier: "", supplier_address: "" }
	const releases = {}
	const slow = (args) => new Promise((resolve) => { releases[args.supplier] = () => resolve(optionsBySupplier[args.supplier]) })
	const first = changeWorkOrderParty(form, "supplier", "Unit A", { fetchOptions: slow })
	const second = changeWorkOrderParty(form, "supplier", "Unit B", { fetchOptions: slow })
	releases["Unit B"](); await second
	releases["Unit A"](); await first
	assert.deepEqual(form, { supplier: "Unit B", supplier_address: "Addr B" })
})

test("Work Order editor routes both parties through the shared autofill", () => {
	assert.match(editor, /function changeSupplier\(value\) \{ return changeParty\("supplier", value\) \}/)
	assert.match(editor, /function changeDeliveryLocation\(value\) \{ return changeParty\("delivery_location", value\) \}/)
	assert.match(editor, /changeWorkOrderParty\(form, partyField, value\)/)
	assert.match(editor, /forgetAutofill\(form\)\n\t\tObject\.assign\(form, editor\.value\.values/)
	assert.doesNotMatch(editor, /fillSupplierDefaults/)
})

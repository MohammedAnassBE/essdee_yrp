import assert from "node:assert/strict"
import test from "node:test"
import { nextTick, reactive } from "vue"
import {
	autofillSingleOptions,
	forgetAutofill,
	isAutofilled,
	SINGLE_LOCATION_OPTIONS_METHOD,
	useSingleOptionAutofill,
} from "../src/composables/useSingleOptionAutofill.js"

const targets = { warehouse: "to_warehouse", address: "supplier_address", address_display: "supplier_address_details" }
const optionsBySupplier = {
	"Unit A": { warehouse: "WH A", address: "Addr A", address_display: "A street" },
	"Unit B": { warehouse: "WH B", address: "Addr B", address_display: "B street" },
	"Unit Many": { warehouse: null, address: null, address_display: null },
}
const fetchOptions = async ({ supplier }) => optionsBySupplier[supplier]
const config = { trigger: "supplier", targets, fetchOptions }
const deferred = () => {
	let resolve
	const promise = new Promise((done) => { resolve = done })
	return { promise, resolve }
}

test("endpoint path is the whitelisted single-option reader", () => {
	assert.equal(SINGLE_LOCATION_OPTIONS_METHOD, "essdee_yrp.api.supplier_warehouse.get_single_location_options")
})

test("fills empty warehouse, address and address details from the only options", async () => {
	const form = { supplier: "Unit A" }
	const changes = await autofillSingleOptions(form, config)

	assert.deepEqual(changes, { to_warehouse: "WH A", supplier_address: "Addr A", supplier_address_details: "A street" })
	assert.equal(isAutofilled(form, "to_warehouse"), true)
})

test("leaves fields empty when the location has several options", async () => {
	const form = { supplier: "Unit Many", to_warehouse: "" }
	assert.deepEqual(await autofillSingleOptions(form, config), {})
	assert.equal(form.to_warehouse, "")
})

test("never overwrites a user's choice", async () => {
	const form = { supplier: "Unit A", to_warehouse: "Picked WH", supplier_address: "Picked Addr", supplier_address_details: "Picked street" }
	assert.deepEqual(await autofillSingleOptions(form, config), {})
	assert.equal(form.supplier_address_details, "Picked street")
})

test("refills stale auto-filled values after the supplier changes", async () => {
	const form = { supplier: "Unit A" }
	await autofillSingleOptions(form, config)
	form.supplier = "Unit B"
	await autofillSingleOptions(form, config)
	assert.deepEqual([form.to_warehouse, form.supplier_address, form.supplier_address_details], ["WH B", "Addr B", "B street"])
})

test("clears stale auto-filled values when the new supplier has several options or is cleared", async () => {
	const form = { supplier: "Unit A" }
	await autofillSingleOptions(form, config)
	form.supplier = "Unit Many"
	assert.deepEqual(await autofillSingleOptions(form, config), { to_warehouse: "", supplier_address: "", supplier_address_details: "" })

	form.supplier = "Unit A"
	await autofillSingleOptions(form, config)
	form.supplier = ""
	let fetched = false
	await autofillSingleOptions(form, { ...config, fetchOptions: async () => { fetched = true } })
	assert.equal(fetched, false)
	assert.equal(form.to_warehouse, "")
})

test("a value the user edits after auto-fill stays when the supplier changes", async () => {
	const form = { supplier: "Unit A" }
	await autofillSingleOptions(form, config)
	form.supplier_address = "Picked Addr"
	form.supplier = "Unit B"
	const changes = await autofillSingleOptions(form, config)
	assert.deepEqual(changes, { to_warehouse: "WH B" })
	assert.equal(form.supplier_address, "Picked Addr")
	assert.equal(form.supplier_address_details, "A street", "details follow the user's address, not the new supplier")
})

test("ignores an older response that arrives after a newer supplier", async () => {
	const slow = deferred()
	const form = { supplier: "Unit A" }
	const first = autofillSingleOptions(form, { ...config, fetchOptions: () => slow.promise })
	form.supplier = "Unit B"
	await autofillSingleOptions(form, config)
	slow.resolve(optionsBySupplier["Unit A"])
	assert.deepEqual(await first, {})
	assert.equal(form.to_warehouse, "WH B")
})

test("forgetting a reloaded record drops responses still in flight", async () => {
	const slow = deferred()
	const form = { supplier: "Unit A" }
	const first = autofillSingleOptions(form, { ...config, fetchOptions: () => slow.promise })
	forgetAutofill(form)
	const reload = deferred()
	const second = autofillSingleOptions(form, { ...config, fetchOptions: () => reload.promise })
	slow.resolve(optionsBySupplier["Unit A"])
	assert.deepEqual(await first, {})
	assert.equal(form.to_warehouse, undefined)
	reload.resolve(optionsBySupplier["Unit A"])
	await second
	assert.equal(form.to_warehouse, "WH A")
})

test("preferPrimaryAddress asks the endpoint for the primary address", async () => {
	let args
	await autofillSingleOptions({ supplier: "Unit A" }, { ...config, preferPrimaryAddress: true, fetchOptions: async (request) => { args = request; return {} } })
	assert.deepEqual(args, { supplier: "Unit A", prefer_primary: 1 })
})

test("warehouse trigger fills only the address targets", async () => {
	const form = { from_warehouse: "WH A" }
	let args
	await autofillSingleOptions(form, {
		trigger: "from_warehouse",
		triggerType: "warehouse",
		targets: { address: "from_address", address_display: "from_address_details" },
		fetchOptions: async (request) => { args = request; return optionsBySupplier["Unit A"] },
	})
	assert.deepEqual(args, { warehouse: "WH A" })
	assert.deepEqual(form, { from_warehouse: "WH A", from_address: "Addr A", from_address_details: "A street" })
})

test("child rows keep their own auto-fill state", async () => {
	const rows = [{ supplier: "Unit A" }, { supplier: "Unit B", warehouse: "Picked" }]
	const rowConfig = { trigger: "supplier", targets: { warehouse: "warehouse" }, fetchOptions }
	await Promise.all(rows.map((row) => autofillSingleOptions(row, rowConfig)))
	assert.deepEqual(rows.map((row) => row.warehouse), ["WH A", "Picked"])
})

test("composable watches the trigger, reports changes, and respects isEnabled", async () => {
	const form = reactive({ supplier: "" })
	const reported = []
	let enabled = true
	const { refresh } = useSingleOptionAutofill(form, { ...config, isEnabled: () => enabled, onChange: (changes) => reported.push(changes) })
	form.supplier = "Unit A"
	await nextTick()
	await refresh()
	assert.equal(form.to_warehouse, "WH A")
	assert.deepEqual(reported[0], { to_warehouse: "WH A", supplier_address: "Addr A", supplier_address_details: "A street" })

	enabled = false
	form.supplier = "Unit B"
	await nextTick()
	await new Promise((done) => setTimeout(done))
	assert.equal(form.to_warehouse, "WH A")
})

test("composable routes fetch failures to onError", async () => {
	const form = reactive({ supplier: "" })
	const errors = []
	useSingleOptionAutofill(form, { ...config, fetchOptions: async () => { throw new Error("boom") }, onError: (reason) => errors.push(reason.message) })
	form.supplier = "Unit A"
	await nextTick()
	await new Promise((done) => setTimeout(done))
	assert.deepEqual(errors, ["boom"])
})

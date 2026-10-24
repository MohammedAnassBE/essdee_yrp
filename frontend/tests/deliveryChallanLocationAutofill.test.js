import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"
import { autofillSingleOptions, forgetAutofill } from "../src/composables/useSingleOptionAutofill.js"
import { withNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"

const source = readFileSync(resolve("frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue"), "utf8")
const script = source.split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
const optionsByLocation = {
	"Unit One": { supplier: "Unit One", warehouse: "WH One", address: "Addr One", address_display: "One street" },
	"Unit Many": { supplier: "Unit Many", warehouse: null, address: null, address_display: null },
	"Unit Primary": { supplier: "Unit Primary", warehouse: null, address: "Addr Primary", address_display: "Primary street" },
}
const settle = () => new Promise((done) => setImmediate(done))

function workspace() {
	const calls = []
	const bindings = {
		...Vue,
		watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {},
		defineProps: () => ({}), defineEmits: () => () => {},
		useRouter: () => ({}), useToast: () => ({ add() {} }),
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		autofillSingleOptions: (target, config) => autofillSingleOptions(target, {
			...config,
			fetchOptions: async (args) => { calls.push(["options", args]); return optionsByLocation[args.supplier] },
		}),
		forgetAutofill,
		withNewDocumentDefaults,
	}
	const state = new Function(...Object.keys(bindings), `${script}\nreturn { setField, applyWorkspace, form, dirty, loading }`)(...Object.values(bindings))
	state.loading.value = false
	return { ...state, calls }
}
const draft = (values) => ({ record: {}, values, permissions: { can_create: 1 } })

test("choosing a location with one warehouse and one address fills both and the address details", async () => {
	const state = workspace()
	await state.setField("supplier", "Unit One")
	assert.equal(state.form.to_warehouse, "WH One")
	assert.equal(state.form.supplier_address, "Addr One")
	assert.equal(state.form.supplier_address_details, "One street")
	assert.equal(state.dirty.value, true)
	await state.setField("from_location", "Unit One")
	assert.deepEqual([state.form.from_warehouse, state.form.from_address, state.form.from_address_details], ["WH One", "Addr One", "One street"])
	assert.deepEqual(state.calls.filter(([kind]) => kind === "options").map(([, args]) => args), [{ supplier: "Unit One", prefer_primary: 1 }, { supplier: "Unit One", prefer_primary: 1 }])
})

test("a location with several options leaves warehouse and address empty for the user", async () => {
	const state = workspace()
	await state.setField("supplier", "Unit Many")
	assert.deepEqual([state.form.to_warehouse, state.form.supplier_address, state.form.supplier_address_details], ["", "", ""])
})

test("several addresses still fall back to the location's primary address", async () => {
	const state = workspace()
	await state.setField("from_location", "Unit Primary")
	assert.equal(state.form.from_warehouse, "")
	assert.equal(state.form.from_address, "Addr Primary")
	assert.equal(state.form.from_address_details, "Primary street")
})

test("changing to a location with several options clears the stale auto-filled values", async () => {
	const state = workspace()
	await state.setField("supplier", "Unit One")
	await state.setField("supplier", "Unit Many")
	assert.deepEqual([state.form.to_warehouse, state.form.supplier_address, state.form.supplier_address_details], ["", "", ""])
	await state.setField("supplier", "")
	assert.equal(state.form.to_warehouse, "")
})

test("a new draft fills only empty location fields and keeps source defaults", async () => {
	const state = workspace()
	state.applyWorkspace(draft({ supplier: "Unit One", to_warehouse: "WO warehouse", from_location: "Unit One", from_address: "WO address" }))
	await settle()
	assert.equal(state.form.to_warehouse, "WO warehouse")
	assert.equal(state.form.supplier_address, "Addr One")
	assert.equal(state.form.from_warehouse, "WH One")
	assert.equal(state.form.from_address, "WO address")
	assert.equal(state.form.from_address_details ?? "", "")
	assert.equal(state.dirty.value, false)
})

test("a saved Delivery Challan is never auto-filled on load", async () => {
	const state = workspace()
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 0 }, values: { supplier: "Unit One", to_warehouse: "" }, permissions: { can_write: 1 } })
	await settle()
	assert.equal(state.form.to_warehouse, "")
	assert.deepEqual(state.calls, [])
})

test("address status delivered with the workspace is used once, then fetched", async () => {
	const fetched = []
	const bindings = {
		...Vue,
		watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {},
		defineProps: () => ({}), defineEmits: () => () => {},
		useRouter: () => ({}), useToast: () => ({ add() {} }),
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		autofillSingleOptions: () => {}, forgetAutofill, withNewDocumentDefaults,
		getLocationAddressStatus: async (party) => { fetched.push(party); return { party, has_address: true, message: "" } },
	}
	const state = new Function(...Object.keys(bindings), `${script}\nreturn { applyWorkspace, refreshAddressStatus, addressStatus, form }`)(...Object.values(bindings))
	const missing = { party: "Unit Two", supplier_name: "Unit Two", has_address: false, message: "No address" }
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 1 }, values: { from_location: "Unit One", supplier: "Unit Two" }, location_address_status: { "Unit Two": missing } })
	await state.refreshAddressStatus()
	assert.deepEqual(fetched, ["Unit One"])
	assert.deepEqual(state.addressStatus.supplier_address, missing)
	await state.refreshAddressStatus()
	assert.deepEqual(fetched, ["Unit One", "Unit One", "Unit Two"])
	state.applyWorkspace({ record: { name: "DC-2", docstatus: 1 }, values: { supplier: "constructor" } })
	await state.refreshAddressStatus()
	assert.deepEqual(fetched.at(-1), "constructor")
})

test("address status delivered with the workspace expires after the apply tick", async () => {
	const fetched = []
	const bindings = {
		...Vue,
		watch: () => {}, onMounted: () => {}, onBeforeUnmount: () => {},
		defineProps: () => ({}), defineEmits: () => () => {},
		useRouter: () => ({}), useToast: () => ({ add() {} }),
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		autofillSingleOptions: () => {}, forgetAutofill, withNewDocumentDefaults,
		getLocationAddressStatus: async (party) => { fetched.push(party); return { party, has_address: true, message: "" } },
	}
	const state = new Function(...Object.keys(bindings), `${script}\nreturn { applyWorkspace, refreshAddressStatus }`)(...Object.values(bindings))
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 1 }, values: { supplier: "Unit Two" }, location_address_status: { "Unit Two": { party: "Unit Two", has_address: false } } })
	await settle()
	await state.refreshAddressStatus()
	assert.deepEqual(fetched, ["Unit Two"], "a later refresh (window focus) never reuses the load-time status")
})

test("the real party watcher consumes the delivered status; command responses, reloads and focus behave as before", async () => {
	const fetched = []
	const bindings = {
		...Vue,
		onMounted: () => {}, onBeforeUnmount: () => {},
		defineProps: () => ({}), defineEmits: () => () => {},
		useRouter: () => ({}), useToast: () => ({ add() {} }),
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		autofillSingleOptions: () => {}, forgetAutofill, withNewDocumentDefaults,
		getLocationAddressStatus: async (party) => { fetched.push(party); return { party, has_address: true, message: "fetched" } },
	}
	const state = new Function(...Object.keys(bindings), `${script}\nreturn { applyWorkspace, refreshAddressStatus, addressStatus }`)(...Object.values(bindings))
	const values = { from_location: "Unit One", supplier: "Unit Two" }
	const delivered = { "Unit One": { party: "Unit One", message: "delivered" }, "Unit Two": { party: "Unit Two", message: "delivered" } }
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 1 }, values, location_address_status: delivered })
	await settle()
	assert.deepEqual(fetched, [])
	assert.equal(state.addressStatus.from_address.message, "delivered")
	assert.equal(state.addressStatus.supplier_address.message, "delivered")
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 1 }, values })
	await settle()
	assert.deepEqual(fetched, ["Unit One", "Unit Two"], "a command response without statuses fetches")
	state.applyWorkspace({ record: { name: "DC-1", docstatus: 1 }, values, location_address_status: delivered })
	await settle()
	assert.equal(fetched.length, 2, "a reload with unchanged parties still uses its own statuses")
	assert.equal(state.addressStatus.supplier_address.message, "delivered")
	await state.refreshAddressStatus()
	assert.equal(fetched.length, 4, "a focus refresh fetches")
	assert.equal(state.addressStatus.supplier_address.message, "fetched")
})

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { computed, defineComponent, nextTick, reactive, ref, watch } from "../frontend/node_modules/vue/index.mjs"
import { prepareActualDiaGroups } from "../frontend/src/departments/fabric-store/grnActualDia.js"
import { mergeStockItemDraft } from "../frontend/src/utils/stockItemComposer.js"

const source = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8")
const deferred = () => {
	let resolve, reject
	const promise = new Promise((yes, no) => { resolve = yes; reject = no })
	return { promise, resolve, reject }
}
const settle = async () => { for (let i = 0; i < 8; i++) await nextTick() }
function setup(path, bindings, exposed) {
	const script = source(path).match(/<script setup>([\s\S]*?)<\/script>/)[1]
		.replace(/^import[\s\S]*?from ["'][^"']+["'];?\s*$/gm, "")
	const globals = { prepareActualDiaGroups, computed, defineComponent, reactive, ref, watch, ...bindings }
	return new Function(...Object.keys(globals), `${script}\nreturn { ${exposed} }`)(...Object.values(globals))
}

async function cutBundle() {
	const path = "frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue"
	const text = source(path)
	const template = text.split("<script setup>")[0]
	for (const [, event, handler] of template.matchAll(/@([\w:.-]+)="(\w+)"/g)) {
		const signature = text.match(new RegExp(`function ${handler}\\(([^)]*)\\)`))?.[1]
		assert.ok(!signature?.includes("="), `${event} must not pass an event to defaulted arguments`)
	}
	const click = text.match(/label="Fetch Bundles"[^\n]*@click="([^"]+)"/)[1]
	assert.equal(click, "preview()")
	const props = reactive({ visible: false, documentName: "" })
	const pending = [], commands = [], printed = [], events = []
	let existing = false
	const record = { name: "CBE-1", docstatus: 0, permissions: { can_write: true }, inputs: [], outputs: [] }
	const dialog = setup(path, {
		defineProps: () => props, defineEmits: () => (...args) => events.push(args),
		getCutBundleEditor: async () => ({ permissions: { can_create: true }, defaults: { lot: "LOT", warehouse: "WH" }, record: existing ? record : null }),
		previewCutBundleSource: () => { const request = deferred(); pending.push(request); return request.promise },
		saveCutBundle: async () => record,
		executeCutBundleCommand: async (name, command) => { commands.push(command); return record },
		getCutBundlePrintData: async () => ({ zpl: "LABEL" }),
		printQzRaw: async (...args) => printed.push(args), confirmCutBundlePrint: async () => record,
	}, "preview, form, acting, availableRows, choices, colourChanged, sourceChanged, inputs, outputs, toggleInput, useSelectedBundles, addOutput, updateOutput, removeOutput, splitCompositeOutputs, save, requestCommand, confirmCommand, printLabels, requestClose, dirty, busy")
	props.visible = true
	await settle()
	const payload = (colour) => ({ context: {}, choices: { colours: [colour] }, available: { panels: ["Front"], data: { [colour]: { data: [{ lay_no: 1, bundle_no: 7, size: "S", shade: "A", Front: 3 }] } } } })
	const first = new Function("preview", "$event", `return ${click}`)(dialog.preview, { type: "click" })
	assert.equal(dialog.acting.value, "preview")
	pending[0].resolve(payload("Blue"))
	await first
	assert.equal(dialog.busy.value, false)
	assert.equal(dialog.availableRows.value.length, 1)
	const older = dialog.preview(), latest = dialog.preview()
	pending[1].resolve(payload("Old")); await older
	assert.equal(dialog.acting.value, "preview")
	pending[2].resolve(payload("New")); await latest
	assert.deepEqual([...dialog.choices.colours], ["New"])
	assert.equal(dialog.acting.value, "")
	const staleError = dialog.preview(), newer = dialog.preview()
	pending[4].resolve(payload("Newest")); await newer
	pending[3].reject(new Error("stale")); await staleError
	assert.deepEqual([...dialog.choices.colours], ["Newest"])
	assert.equal(dialog.acting.value, "")
	dialog.form.selected_colour = "Red"; dialog.colourChanged()
	pending[5].resolve(payload("Red")); await settle()
	assert.equal(dialog.availableRows.value[0].colour, "Red")
	const superseded = dialog.preview()
	dialog.form.selected_colour = ""; dialog.colourChanged()
	assert.equal(dialog.acting.value, "")
	pending[6].resolve(payload("Ignored")); await superseded
	const closing = dialog.preview()
	props.visible = false; await settle()
	props.visible = true; await settle()
	pending[7].resolve(payload("Closed")); await closing
	assert.equal(dialog.acting.value, "")
	assert.equal(dialog.availableRows.value.length, 0)
	existing = true; props.documentName = "CBE-1"; await settle()
	assert.equal(dialog.acting.value, "preview", "existing draft auto-previews")
	pending[8].resolve(payload("Draft")); await settle()
	assert.equal(dialog.acting.value, "")
	dialog.toggleInput(dialog.availableRows.value[0]); dialog.useSelectedBundles()
	assert.equal(dialog.inputs.value.length, 1)
	dialog.addOutput(); assert.equal(dialog.outputs.value.length, 2)
	dialog.updateOutput({ index: 0, field: "shade", value: "B" })
	dialog.splitCompositeOutputs(); dialog.removeOutput(1)
	assert.equal(dialog.outputs.value[0].shade, "B")
	await dialog.save()
	for (const command of ["submit", "cancel"]) { dialog.requestCommand(command); await dialog.confirmCommand() }
	assert.deepEqual(commands, ["submit", "cancel"])
	await dialog.printLabels("PRINTER")
	assert.deepEqual(printed, [["PRINTER", "LABEL"]])
	dialog.dirty.value = true; dialog.requestClose(); await dialog.confirmCommand()
	assert.ok(events.some(([event, value]) => event === "update:visible" && value === false))
	console.log("Cut Bundle: C1–C5 request ordering, cleanup, reopen, and actions passed")
}

async function grn() {
	const path = "frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue"
	const requests = [], searches = []
	const requestAddress = (field, party) => {
		const request = deferred()
		requests.push({ ...request, field, party })
		return request.promise
	}
	const workspace = setup(path, {
		defineProps: () => ({ name: "", sourceContext: {} }), defineEmits: () => () => {},
		useToast: () => ({}), useActionConfirmation: () => () => {}, onMounted: () => {}, onBeforeUnmount: () => {},
		useRouter: () => ({}),
		getGoodsReceivedNoteDeliveryAddress: (party) => requestAddress("delivery_address", party),
		getGoodsReceivedNoteSupplierAddress: (party) => requestAddress("supplier_address", party),
		searchLink: (...args) => searches.push(args), searchLinkedDocument: (...args) => searches.push(args),
		watch: () => {},
	}, "setField, form, addressPending, linkSearchHandler, applyWorkspace, clearWorkspaceState, error, goodsReceivedNoteActions, loading")
	workspace.loading.value = false
	const woAddress = "Essdee Knitting Mills Private Limited-Billing-4"
	workspace.applyWorkspace({
		record: { name: null, docstatus: 0, against: "YRP Work Order", against_id: "WO-2627-01298" },
		permissions: { can_create: true }, capabilities: { save: {} },
		values: { delivery_location: "S-0171", supplier_address: woAddress, delivery_address: woAddress },
	})
	assert.equal(workspace.form.delivery_address, woAddress, "C9: new WO GRN keeps the server's Shipping default")
	assert.equal(workspace.form.supplier_address, woAddress)
	assert.equal(requests.length, 0, "applying WO defaults must not start another address lookup")
	assert.equal(workspace.goodsReceivedNoteActions.value.find((action) => action.key === "save").disabled, false)
	workspace.form.supplier = "SUPPLIER"
	workspace.linkSearchHandler({ fieldname: "delivery_address" })("Essdee Knitting")
	assert.deepEqual(searches.pop(), ["Address", "Essdee Knitting", { disabled: 0 }])
	for (const field of ["supplier_address", "billing_address", "contact_person"]) {
		workspace.linkSearchHandler({ fieldname: field })("text")
		assert.deepEqual(searches.pop(), [field === "contact_person" ? "Contact" : "Address", "Supplier", "SUPPLIER", "text"])
	}
	const stored = { record: { name: "GRN-1", docstatus: 0 }, permissions: { can_write: true }, capabilities: { save: {} }, values: { supplier: "SUPPLIER", supplier_address: "PICKED-BILLING", delivery_address: "PICKED-SHIPPING" } }
	workspace.applyWorkspace(stored)
	assert.equal(workspace.form.supplier_address, "PICKED-BILLING")
	assert.equal(workspace.form.delivery_address, "PICKED-SHIPPING")
	assert.equal(requests.length, 0, "loading stored/user-picked addresses must not default them again")
	for (const [partyField, addressField] of [["delivery_location", "delivery_address"], ["supplier", "supplier_address"]]) {
		const start = requests.length
		workspace.form[addressField] = "STALE"
		const change = workspace.setField(partyField, "NEW")
		assert.equal(workspace.form[addressField], "")
		assert.equal(workspace.addressPending.value, true)
		assert.equal(workspace.goodsReceivedNoteActions.value.find((action) => action.key === "save").disabled, true)
		assert.equal(requests[start].field, addressField)
		assert.equal(requests[start].party, "NEW")
		requests[start].resolve("DEFAULT"); await change
		assert.equal(workspace.form[addressField], "DEFAULT")
		const old = workspace.setField(partyField, "OLD"), latest = workspace.setField(partyField, "LATEST")
		requests[start + 1].resolve("WRONG"); await old
		assert.equal(workspace.addressPending.value, true, "stale completion must not enable Save")
		requests[start + 2].resolve(""); await latest
		assert.equal(workspace.form[addressField], "")
		const picking = workspace.setField(partyField, "PICKING")
		await workspace.setField(addressField, "USER-PICKED")
		requests[start + 3].resolve("DEFAULT"); await picking
		assert.equal(workspace.form[addressField], "USER-PICKED")
		assert.equal(workspace.addressPending.value, false)
		const refresh = workspace.setField(partyField, "REFRESH")
		workspace.applyWorkspace(stored)
		requests[start + 4].resolve("LATE"); await refresh
		assert.equal(workspace.form[addressField], stored.values[addressField])
		const staleError = workspace.setField(partyField, "OLD-ERROR"), current = workspace.setField(partyField, "CURRENT")
		requests[start + 6].resolve("CURRENT"); await current
		requests[start + 5].reject(new Error("stale")); await staleError
		assert.equal(workspace.form[addressField], "CURRENT")
		assert.equal(workspace.error.value, "")
		const clearing = workspace.setField(partyField, "CLEARING")
		await workspace.setField(partyField, "")
		assert.equal(workspace.form[addressField], "")
		requests[start + 7].resolve("LATE"); await clearing
		assert.equal(workspace.form[addressField], "")
		assert.equal(workspace.addressPending.value, false)
	}
	const start = requests.length
	const supplier = workspace.setField("supplier", "NEW-SUPPLIER")
	const delivery = workspace.setField("delivery_location", "NEW-LOCATION")
	requests[start].resolve("BILLING"); await supplier
	assert.equal(workspace.addressPending.value, true, "independent delivery lookup still blocks Save")
	requests[start + 1].resolve("SHIPPING"); await delivery
	assert.equal(workspace.form.supplier_address, "BILLING")
	assert.equal(workspace.form.delivery_address, "SHIPPING")
	assert.equal(workspace.addressPending.value, false)
	const closing = workspace.setField("supplier", "CLOSING")
	workspace.clearWorkspaceState()
	requests[start + 2].resolve("LATE"); await closing
	assert.equal(workspace.form.supplier_address, undefined)
	assert.equal(workspace.addressPending.value, false)
	console.log("GRN: C6/C6b/C8/C8b/C9/C10 address search, stored values, independent defaults, Save guards, and races passed")
}

async function lotTransfer() {
	const text = source("essdee_yrp/public/js/vue_plugins.js")
	const mount = text.slice(text.indexOf("essdee_yrp.mount_lot_transfer ="))
	const frappe = { utils: { icon: (name) => name } }, essdee_yrp = {}
	const calls = []
	new Function("essdee_yrp", "createApp", "LotTransferEditor", "SetVueGlobals", mount)(
		essdee_yrp,
		(_, props) => ({ config: { globalProperties: {} }, mount() { calls.push("mount"); assert.equal(this.config.globalProperties.frappe.utils.icon("edit"), "edit"); return props } }),
		{}, (app) => { calls.push("globals"); app.config.globalProperties.frappe = frappe },
	)
	for (const docstatus of [0, 1]) essdee_yrp.mount_lot_transfer({}, { doc: { docstatus } })
	assert.deepEqual(calls, ["globals", "mount", "globals", "mount"])
	const path = "frontend/src/components/stock/StockItemComposer.vue"
	const entry = { name: "STYLE", dimensions: { from_lot: "FROM", to_lot: "TO", warehouse: "WH", received_type: "Accepted" }, from_lot: "FROM", to_lot: "TO", warehouse: "WH", received_type: "Accepted", set_combination: '{"Colour":"Blue"}', table_index: 4, row_index: 8, default_uom: "Nos", primary_attribute: "Size", values: { S: { qty: 5, rate: 2 } } }
	const group = { primary_attribute: "Size", attributes: [], primary_attribute_values: ["S"], items: [entry] }
	const composer = setup(path, {
		defineProps: () => ({ operation: "lot_transfer", modelValue: [group], editor: { dimensions: Object.keys(entry.dimensions).map((fieldname) => ({ fieldname, mandatory: true })) }, entryDefaults: {}, entryFields: [], schemaLoader: async () => ({ item: "STYLE", primary_attribute: "Size", primary_attribute_values: ["S"], attributes: [], default_uom: "Nos" }) }),
		defineEmits: () => () => {}, mergeStockItemDraft,
	}, "editItem, stageItem, groups, dimensionValues")
	await composer.editItem(0, 0)
	assert.deepEqual({ ...composer.dimensionValues }, entry.dimensions)
	await composer.stageItem()
	const saved = composer.groups.value[0].items[0]
	for (const field of ["set_combination", "table_index", "row_index", "from_lot", "to_lot", "warehouse", "received_type"]) assert.equal(saved[field], entry[field])
	assert.deepEqual({ ...saved.values.S }, entry.values.S)
	console.log("Lot Transfer: Desk globals on drafts/submitted and composer metadata preservation passed")
}

const cases = { cutBundle, grn, lotTransfer }
if (process.argv[2]) await cases[process.argv[2]]()
else for (const run of Object.values(cases)) await run()

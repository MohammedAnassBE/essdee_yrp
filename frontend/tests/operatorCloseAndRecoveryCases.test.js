import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, loadComponent, mountComponent, findNodes } from "../../scripts/helpers/vue_renderer.mjs"
import { pendingWorkOrderGroups } from "../src/departments/fabric-store/workOrderClose.js"
import { initialEntry, fillEntry } from "../src/departments/finishing/finishingEntries.js"
import { normaliseFrappeTime } from "../src/utils/documentValues.js"
import { getQzPrinters } from "../src/api/qzPrinter.js"

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
function script(path, bindings, expose) {
	const source = read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*?from ["'][^"']+["'];?$/gm, "")
	const injections = { ...Vue, onMounted() {}, onUnmounted() {}, ...bindings }
	return new Function(...Object.keys(injections), `${source}\nreturn { ${expose} }`)(...Object.values(injections))
}
const tick = async () => { for (let index = 0; index < 8; index++) await Promise.resolve(); await Vue.nextTick() }
const text = root => findNodes(root, () => true).map(node => node.text).join(" ")
const Link = { props: ["name"], setup: props => () => Vue.h("span", props.name) }

test("F-G01: close shows only pending combinations and the existing size summary metrics", () => {
	const pending = { name: "Style", attributes: { Colour: "Red" }, total_qty: 20, total_delivered: 15, total_received: 10, values: { S: { qty: 20, delivered: 15, received: 10 } } }
	const groups = [{ attributes: ["Colour"], primary_attribute_values: ["S"], items: [pending, { total_delivered: 10, total_received: 10 }, { total_delivered: 0, total_received: 2 }] }, { items: [] }]
	const result = pendingWorkOrderGroups(groups)
	assert.deepEqual(result[0].items, [pending])
	assert.equal(groups[0].items.length, 3)
	const Matrix = loadComponent("frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue", { "../../components/common/DocumentLink.vue": Link })
	const root = mountComponent(Matrix, { groups: result, mode: "summary" })
	for (const label of ["Red", "S", "Planned", "Delivered", "Received", "Pending", "5"]) assert.ok(text(root).includes(label), label)
	const recut = mountComponent(Matrix, { groups: result, mode: "recut" })
	assert.ok(text(recut).includes("Quantity"))
	assert.ok(!text(recut).includes("Pending"))
	assert.match(read("departments/fabric-store/WorkOrderActionPanel.vue"), /All items fully received/)
	assert.match(read("departments/fabric-store/WorkOrderActionPanel.vue"), /v-for="recut in closeContext.recuts/)
})

test("F-G01: close and approve close call the server only after shared confirmation", async () => {
	for (const mode of ["close", "approve_close"]) {
		const commands = [], props = { mode, visible: false, workOrder: { name: "WO-1", modified: "now" }, editor: {} }
		const panel = script("departments/fabric-store/WorkOrderActionPanel.vue", {
			defineProps: () => props, defineEmits: () => () => {}, pendingWorkOrderGroups,
			executeWorkOrderCommand: async (...args) => { commands.push(args); return {} },
		}, "draft, submit, confirmClose, closeConfirmVisible")
		panel.draft.close_reason = "Others"; panel.draft.close_other_reason = "Shortage"
		await panel.submit()
		assert.equal(commands.length, 0)
		assert.equal(panel.closeConfirmVisible.value, true)
		panel.closeConfirmVisible.value = false
		assert.equal(commands.length, 0)
		await panel.submit(); await panel.confirmClose()
		assert.equal(commands.length, 1)
		assert.equal(commands[0][1], mode)
	}
})

test("F-D18: cancellation names only submitted DC Completions", () => {
	const source = read("departments/fabric-store/DeliveryChallanWorkspace.vue")
	const declarations = source.split("\n").filter(line => /^const (completionCancellationMessage|lifecycleConfirmMessage) =/.test(line)).join("\n")
	const workspace = Vue.ref({ related: { completion_entries: [{ name: "STE-SUBMITTED", docstatus: 1 }, { name: "STE-DRAFT", docstatus: 0 }, { name: "STE-CANCELLED", docstatus: 2 }] } })
	const message = new Function("computed", "workspace", "currentName", "pendingLifecycleCommand", `${declarations}\nreturn lifecycleConfirmMessage`)(Vue.computed, workspace, Vue.ref("DC-1"), Vue.ref("cancel"))
	assert.ok(message.value.includes("This also cancels DC Completion STE-SUBMITTED."))
	assert.ok(!message.value.includes("STE-DRAFT")); assert.ok(!message.value.includes("STE-CANCELLED"))
	workspace.value.related.completion_entries = []
	assert.ok(!message.value.includes("DC Completion"))
})

test("F-F08: choosing Loose Piece resets quantities and Fill explicitly copies the selected balance", () => {
	const payload = { primary_values: ["S"], data: { data: { Red: { values: { S: { balance: 50, return_qty: 12, pack_return: 3 } } } } } }
	const panel = script("departments/finishing/FinishingEntryDialog.vue", {
		defineProps: () => ({ visible: false, workspace: {}, action: "", name: "FP-1" }), defineEmits: () => () => {},
		ENTRY_DEFINITIONS: {}, initialEntry, fillEntry,
	}, "source, form, entry, resetQuantities, fill")
	panel.source.value = payload; panel.entry.value = initialEntry(payload)
	assert.equal(panel.entry.value.Red.sizes.S, 0)
	panel.form.selected_type = "balance"; panel.fill()
	assert.equal(panel.entry.value.Red.sizes.S, 50)
	panel.form.selected_type = "return_qty"; panel.resetQuantities()
	assert.equal(panel.entry.value.Red.sizes.S, 0)
	panel.fill(); assert.equal(panel.entry.value.Red.sizes.S, 12)
	assert.match(read("departments/finishing/FinishingEntryDialog.vue"), /@change="resetQuantities"/)
})

function printerAssets(t) {
	const previousWindow = globalThis.window, previousDocument = globalThis.document
	const scripts = [], requests = []
	const qz = { api: { setPromiseType() {}, setSha256Type() {} }, websocket: { isActive: () => true }, printers: { find: async () => ["Printer"] } }
	globalThis.window = {}
	globalThis.document = {
		querySelector: selector => scripts.find(script => selector === `script[src="${script.src}"]`),
		createElement: () => Object.assign(new EventTarget(), {
			dataset: {}, remove() { const index = scripts.indexOf(this); if (index >= 0) scripts.splice(index, 1) },
		}),
		head: { appendChild(script) { scripts.push(script); requests.push(script) } },
	}
	t.after(() => { globalThis.window = previousWindow; globalThis.document = previousDocument })
	const load = script => {
		if (script.src.includes("sha256")) window.sha256 = () => "hash"
		else window.qz = qz
		script.dispatchEvent(new Event("load"))
	}
	return { scripts, requests, load }
}

for (const asset of ["sha256", "qz-tray"]) for (const failure of ["error", "timeout"]) for (const existing of [false, true]) {
	test(`F-B26: retry requests a new ${asset} script after ${failure} (existing=${existing})`, async t => {
		t.mock.timers.enable({ apis: ["setTimeout"] })
		const { scripts, requests, load } = printerAssets(t)
		if (asset === "qz-tray") window.sha256 = () => "hash"
		if (existing) {
			const script = document.createElement("script")
			script.src = asset === "sha256" ? "/assets/frappe/node_modules/js-sha256/build/sha256.min.js" : "/assets/frappe/node_modules/qz-tray/qz-tray.js"
			document.head.appendChild(script)
		}
		const first = getQzPrinters()
		const rejected = assert.rejects(first, /Could not load QZ Tray printing support/)
		const failed = scripts.at(-1)
		if (failure === "error") failed.dispatchEvent(new Event("error"))
		else t.mock.timers.tick(15000)
		await rejected
		assert.ok(!scripts.includes(failed))
		assert.equal(failed.dataset.loaded, undefined)
		const count = requests.length
		const retry = getQzPrinters()
		assert.equal(requests.length, count + 1)
		assert.equal(requests.at(-1).src, failed.src)
		assert.notEqual(requests.at(-1), failed)
		// A late event from the failed attempt must not revive it.
		failed.dispatchEvent(new Event("load"))
		assert.equal(failed.dataset.loaded, undefined)
		load(scripts.at(-1)); await tick()
		if (!window.qz) { load(scripts.at(-1)); await tick() }
		assert.deepEqual(await retry, ["Printer"])
	})
}

test("F-B26: each QZ asset gets its own load timeout, so a slow SHA request does not fail the QZ script", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { scripts, load } = printerAssets(t)
	const first = getQzPrinters()
	t.mock.timers.tick(14000)
	load(scripts[0]); await tick()
	assert.ok(scripts.at(-1).src.includes("qz-tray"))
	t.mock.timers.tick(14000)
	load(scripts.at(-1))
	assert.deepEqual(await first, ["Printer"])
})

test("F-B26: an unreachable QZ Tray gives an actionable error and permits retry", async t => {
	const previous = globalThis.window
	const qz = { api: { setPromiseType() {}, setSha256Type() {} }, websocket: { isActive: () => false, connect: async () => { throw new Error("Unable to establish connection with QZ") } }, printers: { find: async () => ["Printer"] } }
	globalThis.window = { qz, sha256() {} }
	t.after(() => { globalThis.window = previous })
	await assert.rejects(getQzPrinters(), /Could not connect to QZ Tray\. Make sure QZ Tray is running on this computer\./)
	qz.websocket.connect = async () => {}
	assert.deepEqual(await getQzPrinters(), ["Printer"])
	assert.match(read("departments/cut-panel-store/PrinterDialog.vue"), /label="Retry"[^>]*@click="loadPrinters"/)
})

test("F-D20: revert confirmation names inspection, plan, WO and Lot; only accept clears every row", async () => {
	const calls = [], filters = { lot: "LOT-1", plan: "PLAN-1", inspectionType: "pre_final", inputType: "" }
	const plan = { details: { work_order: "WO-1", lot: "LOT-1" }, colours: { Red: { variant_colour: "Red", values: { S: { order_detail: "ROW-1" } } } } }
	const state = Vue.reactive({ busy: false, refreshRequired: false, response: { data: { "LOT-1": { "PLAN-1": plan } } }, inspectionDrafts: {}, entryDrafts: {} })
	const panel = script("departments/sewing/plan/SewingDataEntry.vue", {
		defineProps: () => ({ state, filters, actions: { plan: { can_write: true } }, mutate: async payload => calls.push(payload) }),
		useSewingContext: () => ({ supplier: Vue.ref("SUPPLIER"), requestGeneration: Vue.ref(0), beginRequest() {}, isCurrent() {} }),
	}, "revertConfirmVisible, revertInspectionMessage, confirmRevertInspection")
	panel.revertConfirmVisible.value = true
	assert.equal(calls.length, 0)
	for (const name of ["Pre Final", "PLAN-1", "WO-1", "LOT-1", "every colour and size"]) assert.ok(panel.revertInspectionMessage.value.includes(name))
	panel.revertConfirmVisible.value = false; assert.equal(calls.length, 0)
	await panel.confirmRevertInspection()
	assert.equal(calls[0].rows[0].qty.S.pre_final, 0)
	assert.match(read("departments/sewing/plan/SewingDataEntry.vue"), /DocumentConfirmationDialog[^>]*@confirm="confirmRevertInspection"/)
})

test("F-C09: CPM picker labels identify WO, process and supplier", () => {
	const source = read("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(source, /\[workOrder.name, workOrder.process_name, workOrder.supplier\]\.filter\(Boolean\)\.join\(' · '\)/)
})

test("F-G15: mobile PI title wraps and GRN posting time uses the shared HH:MM:SS formatter", () => {
	const header = read("departments/accounts/components/PurchaseInvoiceHeader.vue")
	const rule = header.match(/\.purchase-invoice-header__identity h1 \{([^}]+)\}/)[1]
	assert.match(rule, /min-width: 0/); assert.match(rule, /white-space: normal/); assert.match(rule, /overflow-wrap: anywhere/)
	assert.doesNotMatch(rule, /white-space: nowrap/)
	const source = read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue")
	const declaration = source.slice(source.indexOf("function formatFieldValue(field) {"), source.indexOf("\nfunction titleCase"))
	const format = new Function("normaliseFrappeTime", `const form = {}; ${declaration}; return formatFieldValue`)(normaliseFrappeTime)
	assert.equal(format({ fieldname: "posting_time", fieldtype: "Time", value: "9:05:7.123456" }), "09:05:07")
	assert.equal(normaliseFrappeTime("9:05:7.123456"), "09:05:07")
	assert.match(read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue"), /field.fieldtype === "Time"\) return normaliseFrappeTime\(value\)/)
	assert.match(read("departments/accounts/components/PurchaseInvoiceOverview.vue"), /:label="formatDocumentOverviewValue\(field\)"/)
})

test("F-B38: internal name is retained as the row key and excluded from displayed columns", () => {
	const source = read("departments/cut-panel-store/CutBundleBalanceReport.vue")
	assert.match(source, /:key="`\$\{row.name/)
	const declaration = source.split("\n").find(line => line.startsWith("const columns ="))
	const columns = new Function("computed", "reportColumns", `${declaration}\nreturn columns`)(Vue.computed, Vue.ref([{ fieldname: "name" }, { fieldname: "lot" }]))
	assert.deepEqual(columns.value, [{ fieldname: "lot" }])
})

test("F-B36: From CPM offers Skip Transit and forwards the selected value", () => {
	const source = read("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(source, /Skip Transit<\/span><Checkbox v-model="transactionForm.skip_transit"/)
	assert.match(source, /skip_transit: false/)
	assert.match(source, /const request = \{ \.\.\.transactionForm \}/)
})

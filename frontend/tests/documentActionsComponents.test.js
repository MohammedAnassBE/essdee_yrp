import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { getRawPrintCommands } from "../src/api/frappe.js"
import * as printUrl from "../src/utils/printUrl.js"
import * as productionOrderPrint from "../src/utils/productionOrderPrint.js"
import { getCustomPrintButtons } from "../src/utils/customPrintButtons.js"
import { useDocumentPermissions } from "../src/composables/useDocumentPermissions.js"
import * as documentDelete from "../src/utils/documentDelete.js"

const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const component = (name, modules) => loadComponent(resolve(rootPath, `frontend/src/${name}.vue`), modules)
const Button = (props) => Vue.h("button", props, props.label)
const Dialog = (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null
const Select = Vue.defineComponent({
	props: { modelValue: String, options: Array, showClear: Boolean },
	emits: ["update:modelValue"],
	setup: (props, { emit }) => () => Vue.h("select", { ...props, "onUpdate:modelValue": value => emit("update:modelValue", value) }),
})
const InputNumber = Vue.defineComponent({
	props: { modelValue: Number, required: Boolean, maxFractionDigits: Number },
	emits: ["update:modelValue"],
	setup: (props, { emit }) => () => Vue.h("input", { ...props, "onUpdate:modelValue": value => emit("update:modelValue", value) }),
})
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const options = { formats: ["Standard", "Custom"], default_format: "Custom", letter_heads: ["Company"], default_letter_head: "Company" }

function mountPrint(api, props = {}, rawApi = {}) {
	return mountComponent(component("components/documents/DocumentPrintDialog", {
		"primevue/button": Button, "primevue/dialog": Dialog, "primevue/select": Select,
		"../../api/frappe.js": { getPrintOptions: api, getRawPrintCommands: rawApi.getRawPrintCommands },
		"../../api/qzPrinter.js": rawApi, "../../utils/printUrl.js": printUrl,
	}), Vue.reactive({ visible: true, doctype: "Test Doc", name: "DOC/1", ...props }))
}

test("print dialog loads defaults and prints the selected format and letter head", async () => {
	const oldWindow = globalThis.window
	const opened = [], visibility = []
	globalThis.window = { open: (...args) => { opened.push(args); return {} } }
	try {
		const root = mountPrint(async (...args) => { assert.deepEqual(args, ["Test Doc", "DOC/1"]); return options }, { "onUpdate:visible": value => visibility.push(value) })
		assert.equal(nodes(root, "button")[0].props.disabled, true)
		await tick()
		assert.deepEqual(nodes(root, "select").map(n => n.props.modelValue), ["Custom", "Company"])
		assert.equal(nodes(root, "select")[1].props.showClear, true)
		nodes(root, "select")[0].props["onUpdate:modelValue"]("Standard")
		nodes(root, "select")[1].props["onUpdate:modelValue"](null)
		await tick()
		nodes(root, "button")[0].props.onClick()
		const query = new URL(opened[0][0], "https://test.local").searchParams
		assert.equal(query.get("format"), "Standard")
		assert.equal(query.get("no_letterhead"), "1")
		assert.deepEqual(visibility, [false])
	} finally { globalThis.window = oldWindow }
})
test("print dialog shows server errors and blocked popup messages", async () => {
	const failed = mountPrint(async () => { throw new Error("Print permission denied") })
	await tick()
	assert.ok(findNodes(failed, n => n.text.includes("Print permission denied")).length)
	assert.equal(nodes(failed, "button")[0].props.disabled, true)
	const oldWindow = globalThis.window
	globalThis.window = { open: () => null }
	try {
		const visibility = []
		const root = mountPrint(async () => options, { "onUpdate:visible": value => visibility.push(value) })
		await tick()
		nodes(root, "button")[0].props.onClick()
		await tick()
		assert.ok(findNodes(root, n => n.text.includes("Please enable pop-ups to print.")).length)
		assert.deepEqual(visibility, [])
	} finally { globalThis.window = oldWindow }
})
test("raw print requests use Desk's rendered-command endpoint", async () => {
	const oldWindow = globalThis.window, oldFetch = globalThis.fetch
	globalThis.window = { csrf_token: "test-token" }
	globalThis.fetch = async (url, request) => {
		assert.equal(url, "/api/method/frappe.www.printview.get_rendered_raw_commands")
		assert.equal(request.method, "POST")
		assert.deepEqual(JSON.parse(request.body), { doc: "Test Doc", name: "DOC/1", print_format: "Raw" })
		return { status: 200, ok: true, json: async () => ({ message: { raw_commands: "^XA^XZ" } }) }
	}
	try {
		assert.deepEqual(await getRawPrintCommands("Test Doc", "DOC/1", "Raw"), { raw_commands: "^XA^XZ" })
	} finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("selecting a raw format sends rendered commands to the selected QZ printer", async () => {
	const oldWindow = globalThis.window
	const opened = [], printed = [], visibility = []
	globalThis.window = { open: (...args) => { opened.push(args); return {} } }
	try {
		const root = mountPrint(async () => ({ ...options, formats: ["Standard", "Raw"], default_format: "Standard", raw_formats: ["Raw"] }), {
			"onUpdate:visible": value => visibility.push(value),
		}, {
			getQzPrinters: async () => ["Label Printer", "Other Printer"],
			getRawPrintCommands: async (...args) => {
				assert.deepEqual(args, ["Test Doc", "DOC/1", "Raw"])
				return { raw_commands: "^XA^FDLabel^FS^XZ" }
			},
			printQzRaw: async (...args) => printed.push(args),
		})
		await tick()
		nodes(root, "select")[0].props["onUpdate:modelValue"]("Raw")
		await tick()
		const printer = nodes(root, "select").find(node => node.props.options?.includes("Label Printer"))
		assert.ok(printer, "Raw formats must offer a QZ printer selection")
		printer.props["onUpdate:modelValue"]("Other Printer")
		await tick()
		await nodes(root, "button")[0].props.onClick()
		assert.deepEqual(printed, [["Other Printer", "^XA^FDLabel^FS^XZ"]])
		assert.deepEqual(opened, [])
		assert.deepEqual(visibility, [false])
		root.__vue_app__.unmount()
	} finally { globalThis.window = oldWindow }
})

test("raw print errors keep the dialog open without falling back to printview", async () => {
	const visibility = []
	const root = mountPrint(async () => ({ ...options, formats: ["Raw", "Standard"], default_format: "Raw", raw_formats: ["Raw"] }), {
		"onUpdate:visible": value => visibility.push(value),
	}, {
		getQzPrinters: async () => ["Label Printer"],
		getRawPrintCommands: async () => ({ raw_commands: "raw data" }),
		printQzRaw: async () => { throw new Error("Printer disconnected") },
	})
	await tick()
	await nodes(root, "button")[0].props.onClick()
	await tick()
	assert.ok(findNodes(root, n => n.text.includes("Printer disconnected")).length)
	assert.deepEqual(visibility, [])
	nodes(root, "select")[0].props["onUpdate:modelValue"]("Standard")
	await tick()
	assert.equal(findNodes(root, n => n.text.includes("Printer disconnected")).length, 0)
	root.__vue_app__.unmount()
})

test("print button opens the dialog only when enabled with formats", async () => {
	const props = Vue.reactive({ doctype: "Test Doc", name: "DOC/1", formats: [] })
	const root = mountComponent(component("components/documents/DocumentPrintButton", {
		"primevue/button": Button,
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: source => useDocumentPermissions(source, () => false) },
		"./DocumentPrintDialog.vue": props => Vue.h("print-dialog", props),
	}), props)
	const button = () => nodes(root, "button")[0]
	assert.equal(button().props.disabled, true)
	button().props.onClick()
	await tick()
	assert.equal(nodes(root, "print-dialog")[0].props.visible, false)
	props.formats = ["Standard", "Custom"]
	await tick()
	button().props.onClick()
	await tick()
	assert.equal(nodes(root, "print-dialog")[0].props.visible, true)
})

function mountDelete(api, overrides = {}) {
	const replacements = []
	const deleted = []
	const toasts = []
	const props = Vue.reactive({ doctype: "Test Doc", name: "DOC-1", docstatus: 0, onDeleted: () => deleted.push(true), ...overrides })
	const root = mountComponent(component("components/documents/DocumentDeleteButton", {
		"primevue/button": Button,
		"primevue/usetoast": { useToast: () => ({ add: message => toasts.push({ message, targets: [...replacements] }) }) },
		"vue-router": { useRouter: () => ({ replace: target => replacements.push(target) }) },
		"../navigation/pageNavigationContext.js": { usePageNavigation: () => ({ backTo: Vue.ref("/list") }) },
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: source => useDocumentPermissions(source, () => true, api.getDocPermissions) },
		"../../api/frappe.js": api, "../../utils/documentDelete.js": documentDelete,
		"./DocumentConfirmationDialog.vue": props => Vue.h("confirmation", props),
		"./DocumentErrorDialog.vue": props => Vue.h("error-dialog", props),
	}), props)
	return { root, props, replacements, deleted, toasts }
}
test("delete button hides without permission and ignores stale permission responses", async () => {
	let resolveOld
	const { root, props } = mountDelete({ getDocPermissions: (_doctype, name) => name === "DOC-1" ? new Promise(resolve => { resolveOld = resolve }) : Promise.resolve({ delete: 0 }) })
	assert.equal(nodes(root, "button").length, 0)
	props.name = "DOC-2"
	await tick()
	resolveOld({ delete: 1 })
	await tick()
	assert.equal(nodes(root, "button").length, 0)
})
test("delete button reloads on status changes and never offers submitted deletion", async () => {
	let calls = 0
	const { root, props } = mountDelete({ getDocPermissions: async () => { calls++; return { delete: 1 } } })
	await tick()
	assert.equal(nodes(root, "button").length, 1)
	props.docstatus = 1
	await tick()
	assert.equal(nodes(root, "button").length, 0)
	props.docstatus = 2
	await tick()
	assert.equal(nodes(root, "button").length, 1)
	assert.equal(calls, 3)
})
test("delete confirms, emits success, and follows the navigation target", async () => {
	const calls = []
	const { root, replacements, deleted, toasts } = mountDelete({ getDocPermissions: async () => ({ delete: 1 }), deleteDoc: async (...args) => calls.push(args) })
	await tick()
	nodes(root, "button")[0].props.onClick()
	await tick()
	const confirm = nodes(root, "confirmation")[0]
	assert.equal(confirm.props.title, "Delete document?")
	assert.equal(confirm.props.message, "Permanently delete Test Doc DOC-1?")
	await confirm.props.onConfirm()
	await tick()
	assert.deepEqual(calls, [["Test Doc", "DOC-1"]])
	assert.deepEqual(deleted, [true])
	assert.deepEqual(replacements, ["/list"])
	assert.deepEqual(toasts, [{ message: { severity: "success", summary: "Test Doc DOC-1 deleted", life: 3500 }, targets: ["/list"] }])
})
test("embedded delete emits success without redirecting", async () => {
	const { root, replacements, deleted } = mountDelete({ getDocPermissions: async () => ({ delete: 1 }), deleteDoc: async () => {} }, { redirect: false })
	await tick()
	await nodes(root, "confirmation")[0].props.onConfirm()
	assert.deepEqual(deleted, [true])
	assert.deepEqual(replacements, [])
})
test("delete completion after unmount does not emit or navigate", async () => {
	let resolveDelete
	const { root, replacements, deleted } = mountDelete({
		getDocPermissions: async () => ({ delete: 1 }),
		deleteDoc: () => new Promise(resolve => { resolveDelete = resolve }),
	})
	await tick()
	const pending = nodes(root, "confirmation")[0].props.onConfirm()
	root.__vue_app__.unmount()
	resolveDelete()
	await pending
	await tick()
	assert.deepEqual(deleted, [])
	assert.deepEqual(replacements, [])
})
test("failed delete closes confirmation and displays the cleaned Frappe error", async () => {
	const { root, replacements, deleted, toasts } = mountDelete({ getDocPermissions: async () => ({ delete: 1 }), deleteDoc: async () => { throw new Error("Linked with Invoice INV-1") } })
	await tick()
	nodes(root, "button")[0].props.onClick()
	await tick()
	await nodes(root, "confirmation")[0].props.onConfirm()
	await tick()
	assert.equal(nodes(root, "confirmation")[0].props.visible, false)
	assert.equal(nodes(root, "error-dialog")[0].props.message, "Linked with Invoice INV-1")
	assert.deepEqual(toasts, [])
	assert.deepEqual(replacements, [])
	assert.deepEqual(deleted, [])
})

function mountShell(overrides = {}) {
	const events = []
	const props = Vue.reactive({ doctype: "Fallback Doc", title: "Document", workspace: { record: { doctype: "Test Doc", name: "DOC-1", docstatus: 2 } }, ...overrides })
	const root = mountComponent(component("departments/fabric-store/FabricDocumentWorkspace", {
		"primevue/button": Button, "primevue/dialog": Dialog,
		"vue-router": { onBeforeRouteLeave: () => {} },
		"../../components/documents/CustomPrintButtons.vue": () => null,
		"../../components/documents/DocumentPrintButton.vue": props => Vue.h("print-button", props),
		"../../components/documents/DocumentDeleteButton.vue": props => Vue.h("delete-button", props),
		"../../components/documents/DocumentErrorDialog.vue": () => null,
		"../../components/documents/DocumentStatusBadge.vue": () => null,
		"../../components/navigation/InlinePageNavigation.vue": () => null,
	}), { ...props, onClose: () => events.push("close"), onDeleted: overrides.onDeleted })
	return { root, events }
}
test("shared shell passes delete identity and disables deletion while dirty or acting", () => {
	const oldWindow = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const { root } = mountShell({ dirty: true })
		const button = nodes(root, "delete-button")[0]
		assert.equal(button.props.doctype, "Test Doc")
		assert.equal(button.props.name, "DOC-1")
		assert.equal(button.props.docstatus, 2)
		assert.equal(button.props.disabled, true)
		assert.equal(button.props.redirect, true)
		assert.equal(nodes(mountShell({ acting: "save" }).root, "delete-button")[0].props.disabled, true)
		assert.equal(nodes(mountShell({ showDelete: false }).root, "delete-button").length, 0)
	} finally { globalThis.window = oldWindow }
})
test("embedded shell disables redirect, re-emits deleted, or closes without a handler", () => {
	const oldWindow = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const { root, events } = mountShell({ presentation: "embedded" })
		const button = nodes(root, "delete-button")[0]
		assert.equal(button.props.redirect, false)
		button.props.onDeleted()
		assert.deepEqual(events, ["close"])
		const handled = []
		const shell = mountShell({ presentation: "embedded", onDeleted: () => handled.push("deleted") })
		nodes(shell.root, "delete-button")[0].props.onDeleted()
		assert.deepEqual(handled, ["deleted"])
		assert.deepEqual(shell.events, [])
	} finally { globalThis.window = oldWindow }
})
test("pages with domain delete actions opt out of shared Delete", () => {
	for (const file of ["sales/ProductionOrder", "hr/BillTracking", "accounts/PurchaseInvoice", "purchase/ItemPricePage"]) {
		const source = readFileSync(resolve(rootPath, `frontend/src/departments/${file}.vue`), "utf8")
		assert.match(source, /<FabricDocumentWorkspace\b[^>]*:show-delete="false"/)
	}
})

test("print button self-checks permission only when formats are omitted", async () => {
	const calls = []
	const props = Vue.reactive({ doctype: "Self Print", name: "DOC-S", docstatus: 0 })
	const root = mountComponent(component("components/documents/DocumentPrintButton", {
		"primevue/button": Button,
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: (source, enabled) => useDocumentPermissions(source, enabled, async (...args) => { calls.push(args); return { print: 1 } }) },
		"./DocumentPrintDialog.vue": props => Vue.h("print-dialog", props),
	}), props)
	assert.equal(nodes(root, "button").length, 0)
	await tick()
	assert.equal(nodes(root, "button")[0].props.disabled, false)
	nodes(root, "button")[0].props.onClick()
	await tick()
	assert.equal(nodes(root, "print-dialog")[0].props.visible, true)
	assert.equal(calls.length, 1)
	props.formats = []
	await tick()
	assert.equal(nodes(root, "button")[0].props.disabled, true)
	assert.equal(calls.length, 1)
})
test("print permission denial hides the self-check button", async () => {
	const root = mountComponent(component("components/documents/DocumentPrintButton", {
		"primevue/button": Button,
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: (source, enabled) => useDocumentPermissions(source, enabled, async () => ({ print: 0 })) },
		"./DocumentPrintDialog.vue": () => null,
	}), { doctype: "Private", name: "PRIVATE-1" })
	await tick()
	assert.equal(nodes(root, "button").length, 0)
})
test("shell falls back to permission loading only when can_print is absent", () => {
	const oldWindow = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const fallback = nodes(mountShell().root, "print-button")[0]
		assert.equal(fallback.props.formats, null)
		const workspace = { record: { name: "BILL-1" }, permissions: { can_print: true }, print_formats: [{ format: "Standard" }] }
		const explicit = nodes(mountShell({ workspace, printLabel: "Print Format" }).root, "print-button")[0]
		assert.deepEqual(explicit.props.formats, workspace.print_formats)
		assert.equal(explicit.props.label, "Print Format")
		workspace.permissions.can_print = false
		assert.equal(nodes(mountShell({ workspace }).root, "print-button").length, 0)
	} finally { globalThis.window = oldWindow }
})

function mountCustomPrint(api, overrides = {}) {
	return mountComponent(component("components/documents/CustomPrintButtons", {
		"primevue/button": Button, "primevue/dialog": Dialog,
		"primevue/inputnumber": InputNumber,
		"../../api/frappe.js": { callMethod: api },
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: (source, enabled) => useDocumentPermissions(source, enabled) },
		"../../utils/customPrintButtons.js": { getCustomPrintButtons },
		"../../utils/productionOrderPrint.js": productionOrderPrint,
		"../../utils/printUrl.js": printUrl,
		"./DocumentErrorDialog.vue": props => Vue.h("error-dialog", props),
	}), { doctype: "YRP Production Order", record: { name: "PPO/1 & 2#x", docstatus: 1 }, permissions: { can_print: true }, ...overrides })
}

test("custom Production Order print fetches settings and reports blocked pop-ups", async () => {
	const oldWindow = globalThis.window
	const opened = [], calls = []
	globalThis.window = { open: (...args) => { opened.push(args); return null } }
	try {
		const root = mountCustomPrint(async (...args) => { calls.push(args); return { fg_item_exists: true, pieces_per_box: 10 } })
		const button = nodes(root, "button")[0]
		assert.equal(button.props.label, "Print")
		button.props.onClick()
		await tick()
		assert.deepEqual(calls, [["essdee_yrp.production_order_workflow.get_production_order_print_settings", { production_order: "PPO/1 & 2#x" }]])
		assert.deepEqual(opened, [["/printview?doctype=YRP+Production+Order&name=PPO%2F1+%26+2%23x&trigger_print=1&format=Essdee+Production+Order&pieces_per_box=10", "_blank"]])
		assert.equal(nodes(root, "dialog").length, 0)
		assert.equal(nodes(root, "error-dialog")[0].props.message, "Please enable pop-ups to print.")
	} finally { globalThis.window = oldWindow }
})

test("custom Production Order settings resolving after unmount do not open print", async () => {
	const oldWindow = globalThis.window, opened = []
	globalThis.window = { open: (...args) => { opened.push(args); return {} } }
	try {
		let resolveSettings
		const root = mountCustomPrint(() => new Promise(resolve => { resolveSettings = resolve }))
		const pending = nodes(root, "button")[0].props.onClick()
		root.__vue_app__.unmount()
		resolveSettings({ fg_item_exists: true, pieces_per_box: 10 })
		await pending
		await tick()
		assert.deepEqual(opened, [])
	} finally { globalThis.window = oldWindow }
})

test("custom Production Order dialog validates, prints pieces, and closes", async () => {
	const oldWindow = globalThis.window, opened = []
	globalThis.window = { open: (...args) => { opened.push(args); return {} } }
	try {
		const root = mountCustomPrint(async () => ({ fg_item_exists: false, pieces_per_box: null }))
		await nodes(root, "button")[0].props.onClick()
		await tick()
		assert.equal(nodes(root, "dialog")[0].props.header, "Print Production Order")
		assert.ok(findNodes(root, n => n.text.includes("Pieces per Box")).length)
		assert.ok(findNodes(root, n => n.text.includes("The item is not available in FG Item Master.")).length)
		assert.equal(nodes(root, "input")[0].props.modelValue, null)
		assert.equal(nodes(root, "input")[0].props.required, true)
		assert.equal(nodes(root, "input")[0].props.maxFractionDigits, 0)
		const submit = () => nodes(root, "button").find(n => n.props.label === "Print" && n !== nodes(root, "button")[0]).props.onClick()
		submit()
		await tick()
		assert.ok(findNodes(root, n => n.props.role === "alert" && n.text === "Pieces per Box is required.").length)
		for (const [value, message] of [[0, "Pieces per Box is required."], [-1, "Pieces per Box must be greater than zero."]]) {
			nodes(root, "input")[0].props["onUpdate:modelValue"](value)
			submit()
			await tick()
			assert.ok(findNodes(root, n => n.text === message).length)
			assert.equal(nodes(root, "dialog").length, 1)
		}
		assert.deepEqual(opened, [])
		nodes(root, "input")[0].props["onUpdate:modelValue"](7)
		submit()
		await tick()
		assert.equal(nodes(root, "dialog").length, 0)
		assert.equal(opened.length, 1)
		assert.equal(new URL(opened[0][0], "https://test.local").searchParams.get("pieces_per_box"), "7")
	} finally { globalThis.window = oldWindow }
})

test("custom Production Order dialog cancels without printing and resets its input", async () => {
	const oldWindow = globalThis.window, opened = []
	globalThis.window = { open: (...args) => opened.push(args) }
	try {
		const root = mountCustomPrint(async () => ({ fg_item_exists: true, pieces_per_box: 0 }))
		await nodes(root, "button")[0].props.onClick()
		await tick()
		assert.ok(findNodes(root, n => n.text === "Pieces per Box is not configured in FG Item Master.").length)
		nodes(root, "input")[0].props["onUpdate:modelValue"](8)
		nodes(root, "button").find(n => n.props.label === "Cancel").props.onClick()
		await tick()
		assert.equal(nodes(root, "dialog").length, 0)
		assert.deepEqual(opened, [])
		await nodes(root, "button")[0].props.onClick()
		await tick()
		assert.equal(nodes(root, "input")[0].props.modelValue, null)
		nodes(root, "dialog")[0].props["onUpdate:visible"](false)
		await tick()
		assert.equal(nodes(root, "dialog").length, 0)
		assert.deepEqual(opened, [])
	} finally { globalThis.window = oldWindow }
})

test("custom print settings errors use DocumentErrorDialog; disabled clicks do nothing", async () => {
	let calls = 0
	const api = async () => { calls++; throw new Error("Print permission denied") }
	const root = mountCustomPrint(api)
	await nodes(root, "button")[0].props.onClick()
	await tick()
	assert.equal(nodes(root, "error-dialog")[0].props.message, "Print permission denied")
	assert.equal(nodes(root, "dialog").length, 0)
	const disabled = mountCustomPrint(api, { disabled: true })
	await nodes(disabled, "button")[0].props.onClick()
	assert.equal(calls, 1)
})

test("other custom print buttons open their URL without fetching settings", async () => {
	const oldWindow = globalThis.window, opened = []
	globalThis.window = { open: (...args) => { opened.push(args); return {} } }
	try {
		const root = mountCustomPrint(() => { assert.fail("unexpected settings call") }, { doctype: "SD YRP Product", record: { name: "PRODUCT/1" } })
		await nodes(root, "button")[0].props.onClick()
		assert.deepEqual(opened, [["/printview?doctype=SD+YRP+Product&name=PRODUCT%2F1&trigger_print=1&format=Essdee+Product+Tech+Pack&no_letterhead=1", "_blank"]])
	} finally { globalThis.window = oldWindow }
})


test("Cutting Plan delete uses the human label in confirmation and toast", async () => {
	const { root, toasts } = mountDelete({ getDocPermissions: async () => ({ delete: 1 }), deleteDoc: async () => {} }, { doctype: "SD YRP Cutting Plan", documentLabel: "Cutting Plan", name: "CP-1" })
	await tick()
	assert.equal(nodes(root, "confirmation")[0].props.message, "Permanently delete Cutting Plan CP-1?")
	await nodes(root, "confirmation")[0].props.onConfirm()
	assert.equal(toasts[0].message.summary, "Cutting Plan CP-1 deleted")
	const source = readFileSync(resolve(rootPath, "frontend/src/departments/CuttingPlan.vue"), "utf8")
	const buttons = source.match(/<DocumentDeleteButton\b[^>]+\/>/g)
	assert.equal(buttons.length, 2)
	for (const button of buttons) assert.match(button, /document-label="Cutting Plan"/)
})

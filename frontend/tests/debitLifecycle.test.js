import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const debitFields = (await import("../src/config/fields/debit.js")).default
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
const helpers = new Proxy({}, { get: () => () => ({}) })
const meta = [{ name: "YRP Debit", fields: [{ fieldname: "work_order", label: "Work Order", fieldtype: "Link", options: "YRP Work Order" }, { fieldname: "debit_value", label: "Debit Value", fieldtype: "Currency" }] }]

function mountDebits({ doc, permissions, route = { params: { debitId: doc.name }, query: {} } }) {
	const filename = resolve("frontend/src/departments/accounts/Debits.vue")
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	const modules = Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop()) : helpers]))
	const calls = { cancel: [], submit: [], pushes: [], confirms: [], refreshes: 0, loads: 0 }
	let current = { ...doc }
	const list = { setup(_props, { expose }) { expose({ refresh: () => { calls.refreshes += 1 } }); return () => Vue.h("listview") } }
	const component = loadComponent(filename, {
		...modules,
		vue: Vue,
		"vue-router": { useRoute: () => Vue.reactive(route), useRouter: () => ({ push: async (target) => calls.pushes.push(target) }) },
		"../../config/fields/debit.js": debitFields,
		"../../router/departmentLock.js": { isOutsideLayout: () => false, getHomePath: () => "/" },
		"../../api/frappe.js": {
			getDoc: async () => { calls.loads += 1; return { ...current } },
			getMeta: async () => meta,
			callMethod: async () => false,
			cancelDoc: async (...args) => { calls.cancel.push(args); current = { ...current, docstatus: 2, status: "Cancelled" } },
			submitDoc: async (...args) => { calls.submit.push(args); current = { ...current, docstatus: 1 } },
		},
		"../../composables/useDocumentPermissions.js": { useDocumentPermissions: () => Vue.ref(permissions) },
		"../../composables/useDuplicateAction.js": { loadDuplicateValues: async () => ({ work_order: "WO-1", debit_value: 40 }) },
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => (options) => calls.confirms.push(options) },
		"../../components/common/ListView.vue": list,
		"../../components/common/FormView.vue": (props) => Vue.h("form-view", props),
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, slots.default?.()) : null,
		"primevue/button": (props) => Vue.h("button", props, props.label),
	})
	const root = mountComponent(component, {})
	const button = (label) => findNodes(root, (node) => node.type === "button" && node.props.label === label)[0]
	return { root, calls, button }
}

const approved = { name: "WOD-1", work_order: "WO-1", debit_value: 40, docstatus: 1, status: "Approved", modified: "2026-11-02 10:00:00" }

test("Debit dialog shows metadata labels instead of field names", async () => {
	const view = mountDebits({ doc: approved, permissions: {} })
	await tick(); await tick()
	const labels = findNodes(view.root, (node) => node.type === "dt").map(text)
	assert.ok(labels.includes("Work Order") && labels.includes("Debit Value"), labels.join(","))
	assert.ok(!labels.includes("work order"))
})

test("Cancel confirms, cancels the submitted debit, then reloads the record and list", async () => {
	const view = mountDebits({ doc: approved, permissions: { cancel: 1 } })
	await tick(); await tick()
	const cancel = view.button("Cancel")
	assert.equal(cancel.props.severity, "danger")
	cancel.props.onClick()
	assert.equal(view.calls.confirms.length, 1)
	assert.deepEqual(view.calls.cancel, [])
	await view.calls.confirms[0].accept()
	await tick()
	assert.deepEqual(view.calls.cancel, [["YRP Debit", "WOD-1", "2026-11-02 10:00:00"]])
	assert.equal(view.calls.refreshes, 1)
	assert.equal(view.calls.loads, 2)
	assert.equal(view.button("Cancel"), undefined)
	assert.equal(view.button("Approve"), undefined)
})

test("Cancel stays hidden without cancel permission or on drafts", async () => {
	for (const [doc, permissions] of [[approved, { cancel: 0 }], [{ ...approved, docstatus: 0 }, { cancel: 1 }]]) {
		const view = mountDebits({ doc, permissions })
		await tick(); await tick()
		assert.equal(view.button("Cancel"), undefined)
	}
})

test("Amend on a cancelled debit opens a new debit form linked to the source", async () => {
	const cancelled = { ...approved, docstatus: 2, status: "Cancelled" }
	const denied = mountDebits({ doc: cancelled, permissions: { amend: 0, cancel: 1 } })
	await tick(); await tick()
	assert.equal(denied.button("Amend"), undefined)
	const view = mountDebits({ doc: cancelled, permissions: { amend: 1 } })
	await tick(); await tick()
	view.button("Amend").props.onClick()
	await view.calls.confirms[0].accept()
	assert.deepEqual(view.calls.pushes, [{ path: "/accounts/debits", query: { amend_from: "WOD-1" } }])
	const form = mountDebits({ doc: cancelled, permissions: {}, route: { params: {}, query: { amend_from: "WOD-1" } } })
	await tick(); await tick()
	const props = findNodes(form.root, (node) => node.type === "form-view")[0].props
	assert.deepEqual(props["initial-values"], { work_order: "WO-1", debit_value: 40, amended_from: "WOD-1" })
})

test("Submit is offered on a draft debit with submit permission", async () => {
	const view = mountDebits({ doc: { ...approved, docstatus: 0, status: "Debit Requested" }, permissions: { submit: 1 } })
	await tick(); await tick()
	await view.button("Submit").props.onClick()
	await tick()
	assert.deepEqual(view.calls.submit, [["YRP Debit", "WOD-1", "2026-11-02 10:00:00"]])
	assert.equal(view.calls.refreshes, 1)
	assert.equal(view.button("Submit"), undefined)
})

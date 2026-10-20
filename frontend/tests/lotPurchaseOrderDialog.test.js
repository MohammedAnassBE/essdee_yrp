import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as actions from "../src/departments/purchase/lot/lotPurchaseActions.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)

function mountDialog(api, mode = "link") {
	const toasts = [], visibility = [], changed = []
	const component = loadComponent(new URL("../src/departments/purchase/lot/LotPurchaseOrderDialog.vue", import.meta.url).pathname, {
		"primevue/button": props => Vue.h("button", props),
		"primevue/dialog": (_props, { slots }) => Vue.h("dialog", [slots.default?.(), slots.footer?.()]),
		"primevue/message": (_props, { slots }) => Vue.h("message", slots.default?.()),
		"primevue/textarea": props => Vue.h("reason", props),
		"primevue/usetoast": { useToast: () => ({ add: message => toasts.push(message) }) },
		"../../../components/common/MultiSelectField.vue": props => Vue.h("purchase-orders", props),
		"../../../api/frappe.js": api, "./lotPurchaseActions.js": actions,
	})
	const root = mountComponent(component, { visible: true, lot: "LOT-1", mode,
		"onUpdate:visible": value => visibility.push(value), onChanged: () => changed.push(true) })
	return { root, toasts, visibility, changed }
}

test("link dialog requires selections and reason, searches open submitted POs and sends the exact Desk payload", async () => {
	const updates = [], searches = []
	const { root, toasts, changed } = mountDialog({
		searchLink: async (...args) => { searches.push(args); return [{ name: args[1] ? "PO-2" : "PO-1" }] },
		callMethod: async (...args) => updates.push(args),
	})
	try {
		await tick()
		assert.deepEqual(searches[0], ["Purchase Order", "", { docstatus: 1, open_status: "Open" }, 20])
		const submit = () => nodes(root, "button").find(node => node.props.label === "Link").props.onClick()
		await submit()
		assert.deepEqual(updates, [])
		nodes(root, "purchase-orders")[0].props["onUpdate:modelValue"](["PO-1"])
		await submit()
		assert.deepEqual(updates, [])
		nodes(root, "reason")[0].props["onUpdate:modelValue"]("  Stock requirement  ")
		nodes(root, "purchase-orders")[0].props.onFilter({ value: "PO-2" })
		await tick()
		assert.deepEqual(nodes(root, "purchase-orders")[0].props.options.map(row => row.value), ["PO-1", "PO-2"])
		await submit()
		assert.deepEqual(updates, [["essdee_yrp.purchase_order_lots.update_lot_po_links", { lot: "LOT-1", add_pos: ["PO-1"], remove_pos: [], comment: "  Stock requirement  " }]])
		assert.equal(toasts[0].severity, "success")
		assert.deepEqual(changed, [true])
	} finally { root.__vue_app__.unmount() }
})

test("unlink dialog lists linked submitted POs and reports when none exist", async () => {
	for (const linked of [[], ["PO-9"]]) {
		const calls = []
		const { root, toasts, visibility, changed } = mountDialog({ callMethod: async (method, args) => {
			calls.push([method, args]); return method.endsWith("get_purchase_orders_for_lot") ? linked : undefined
		} }, "unlink")
		try {
			await tick()
			assert.deepEqual(calls[0], ["essdee_yrp.purchase_order_lots.get_purchase_orders_for_lot", { lot: "LOT-1" }])
			if (!linked.length) {
				assert.equal(toasts[0].summary, "This lot is not linked to any submitted PO")
				assert.equal(toasts[0].severity, "info")
				assert.deepEqual(visibility, [false])
			} else {
				assert.deepEqual(nodes(root, "purchase-orders")[0].props.options, [{ value: "PO-9", label: "PO-9" }])
				nodes(root, "purchase-orders")[0].props["onUpdate:modelValue"](["PO-9"])
				nodes(root, "reason")[0].props["onUpdate:modelValue"]("Wrong PO")
				await nodes(root, "button").find(node => node.props.label === "Unlink").props.onClick()
				assert.deepEqual(calls[1][1], { lot: "LOT-1", add_pos: [], remove_pos: ["PO-9"], comment: "Wrong PO" })
				assert.deepEqual(changed, [true])
			}
		} finally { root.__vue_app__.unmount() }
	}
})

test("failed PO updates keep the dialog open without success or reload", async () => {
	const { root, toasts, visibility, changed } = mountDialog({ searchLink: async () => [{ name: "PO-1" }], callMethod: async () => { throw new Error("No write permission") } })
	try {
		await tick()
		nodes(root, "purchase-orders")[0].props["onUpdate:modelValue"](["PO-1"])
		nodes(root, "reason")[0].props["onUpdate:modelValue"]("Reason")
		await nodes(root, "button").find(node => node.props.label === "Link").props.onClick()
		assert.deepEqual(toasts, [])
		assert.deepEqual(visibility, [])
		assert.deepEqual(changed, [])
	} finally { root.__vue_app__.unmount() }
})

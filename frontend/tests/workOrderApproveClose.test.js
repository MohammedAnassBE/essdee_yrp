import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const tick = async () => { for (let index = 0; index < 3; index += 1) { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() } }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())

async function mountWorkOrders(permission, approve = async () => ({})) {
	const calls = []
	const component = loadComponent("frontend/src/departments/fabric-store/FabricWorkOrders.vue", {
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({}) },
		"../../api/planning.js": {
			getWorkOrderClosePermission: async () => permission,
			approveCloseRequests: async (names) => { calls.push(names); return approve(names) },
		},
		"../../components/common/ListView.vue": stub("list"),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": {},
	})
	const root = mountComponent(component, Vue.reactive({ capability: {} }))
	await tick()
	return { calls, actions: () => findNodes(root, (node) => node.type === "list")[0].props["custom-bulk-actions"] }
}

test("Work Order list offers Approve Close only to closing approvers", async () => {
	assert.deepEqual((await mountWorkOrders({ is_close_manager: false })).actions(), [])
	assert.deepEqual((await mountWorkOrders(null)).actions(), [])
	const [action] = (await mountWorkOrders({ approver_role: "WO Approver", is_close_manager: true })).actions()
	assert.equal(action.label, "Approve Close")
})

test("Approve Close sends every selected Work Order and maps server failures for the result dialog", async () => {
	const list = await mountWorkOrders({ is_close_manager: true }, async () => ({
		approved: ["WO-1"],
		failed: [{ work_order: "WO-2", error: "Work Order WO-2 does not have a pending Close Request." }],
	}))
	const result = await list.actions()[0].run([{ name: "WO-1" }, { name: "WO-2" }])
	assert.deepEqual(list.calls, [["WO-1", "WO-2"]])
	assert.deepEqual(result, {
		done: ["WO-1"],
		failed: [{ name: "WO-2", error: "Work Order WO-2 does not have a pending Close Request." }],
	})
})

import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const hrViews = await import("../src/departments/hr/hrViews.js")
globalThis.window ||= {}
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const slotStub = (tag) => (props, { slots }) => Vue.h(tag, props, Object.values(slots || {}).map((slot) => slot?.()))

function mountBillTrackings(query = {}) {
	const route = Vue.reactive({ name: "accounts-bill-trackings", query, hash: "", params: {} })
	const replaced = []
	const router = {
		push: async () => {},
		replace: async (location) => {
			replaced.push(location)
			route.query = location.query
		},
	}
	const component = loadComponent("frontend/src/departments/hr/BillTrackings.vue", {
		"primevue/button": slotStub("button"),
		"primevue/message": slotStub("message"),
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"vue-router": { useRoute: () => route, useRouter: () => router },
		"../../api/hr.js": {
			getHrCapabilities: async () => ({ sections: { bill_tracking: { can_read: true } } }),
			getUserDepartments: async () => ["Accounts"],
			bulkAssignBills: async () => ({}),
		},
		"../../components/DepartmentPage.vue": slotStub("page"),
		"../../components/common/ListView.vue": (props, { slots }) => Vue.h("list-view", props, slots["toolbar-actions"]?.()),
		"../../components/common/ListPageSkeleton.vue": () => null,
		"../../components/common/WorkspaceLoadError.vue": () => null,
		"../../components/documents/DocumentErrorDialog.vue": () => null,
		"../../components/documents/DocumentStatusBadge.vue": () => null,
		"../../router/listDocumentNavigation.js": { openListDocument: async () => {} },
		"./components/BillTrackingAssignDialog.vue": () => null,
		"./hrViews.js": hrViews,
	})
	const root = mountComponent(component, {})
	const listFilters = () => findNodes(root, (node) => node.type === "list-view")[0]?.props.filters
	const assignedButton = () => findNodes(root, (node) => node.type === "button" && node.props.label === "Assigned to me")[0]
	return { route, replaced, listFilters, assignedButton }
}

test("Assigned to me is kept in the list URL so Back restores the filter", async () => {
	const page = mountBillTrackings()
	await tick(); await tick()
	assert.deepEqual(page.listFilters(), [])

	await page.assignedButton().props.onClick()
	await tick()
	assert.deepEqual(page.route.query, { assigned_to_me: "1" })
	assert.deepEqual(page.listFilters(), hrViews.assignedToMeFilters(["Accounts"]))

	await page.assignedButton().props.onClick()
	await tick()
	assert.deepEqual(page.route.query, { assigned_to_me: undefined })
	assert.deepEqual(page.listFilters(), [])
})

test("Opening the list with assigned_to_me applies the filter before the list renders", async () => {
	const page = mountBillTrackings({ assigned_to_me: "1" })
	await tick(); await tick(); await tick()
	assert.deepEqual(page.listFilters(), hrViews.assignedToMeFilters(["Accounts"]))
	assert.equal(page.assignedButton().props["aria-pressed"], true)
	assert.deepEqual(page.replaced, [])
})

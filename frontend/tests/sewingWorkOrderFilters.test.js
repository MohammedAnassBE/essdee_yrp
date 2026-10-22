import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = name => (props, { slots }) => Vue.h(name, props, slots.default?.())
function setup(basePath, getProcesses) {
	const workOrders = loadComponent("frontend/src/departments/fabric-store/FabricWorkOrders.vue", {
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({}) },
		"../../components/common/ListView.vue": stub("list"),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": {},
	})
	const component = loadComponent("frontend/src/departments/FabricStoreSection.vue", {
		"primevue/message": stub("message"),
		"./cut-panel-store/CutPanelDocuments.vue": stub("documents"),
		"../api/fabricStore.js": { getFabricStoreCapabilities: async () => ({ sections: { work_orders: { can_create: 1 } } }) },
		"../api/sewing.js": { getSewingWorkOrderProcesses: getProcesses },
		"../api/finishing.js": { getFinishingCapabilities: () => assert.fail("Only Finishing uses Finishing capabilities") },
		"../api/quality.js": { getQualityCapabilities: () => assert.fail("Existing departments must use Fabric Store capabilities") },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/FabricWorkOrders.vue": workOrders,
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
	})
	const props = Vue.reactive({ section: "work_orders", basePath })
	return { props, root: mountComponent(component, props) }
}
const lists = root => findNodes(root, node => node.type === "list")

test("F-D24 Sewing waits for its process filter before mounting the Work Order list", async () => {
	let resolveProcesses
	const { root } = setup("/sewing", () => new Promise(resolve => { resolveProcesses = resolve }))
	await tick()
	assert.equal(lists(root).length, 0)
	resolveProcesses(["Stitching", "Stitching Group"])
	await tick()
	assert.deepEqual(lists(root)[0].props.filters, [["process_name", "in", ["Stitching", "Stitching Group"]]])
})

test("F-D24 Fabric Store stays unfiltered and ignores a stale Sewing lookup", async () => {
	let resolveProcesses
	const { root, props } = setup("/sewing", () => new Promise(resolve => { resolveProcesses = resolve }))
	await tick()
	props.basePath = "/fabric-store"
	await tick()
	assert.deepEqual(lists(root)[0].props.filters, [])
	resolveProcesses(["Stitching"])
	await tick()
	assert.deepEqual(lists(root)[0].props.filters, [])
	const fabric = setup("/fabric-store", () => { assert.fail("Fabric Store must not request sewing processes") })
	await tick()
	assert.deepEqual(lists(fabric.root)[0].props.filters, [])
})

test("F-D24 empty process settings stay filtered and lookup failures do not show all Work Orders", async () => {
	const empty = setup("/sewing", async () => [])
	await tick()
	assert.deepEqual(lists(empty.root)[0].props.filters, [["process_name", "in", []]])
	const failed = setup("/sewing", async () => { throw new Error("Process lookup failed") })
	await tick()
	assert.equal(lists(failed.root).length, 0)
	assert.equal(findNodes(failed.root, node => node.type === "error")[0].props.message, "Process lookup failed")
})

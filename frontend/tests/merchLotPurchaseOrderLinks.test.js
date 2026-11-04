import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as purchaseActions from "../src/departments/merch/lot/lotPurchaseActions.js"
import * as duplicateAction from "../src/composables/useDuplicateAction.js"
import * as merchViews from "../src/departments/merch/lot/merchLotViews.js"
import * as lotLayout from "../src/departments/merch/lot/lotLayout.js"
import * as lotViews from "../src/departments/merch/lot/lotViews.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = type => (props, { slots }) => Vue.h(type, props, Object.values(slots || {}).map(slot => slot?.({ headingId: "h" })))

function mountMerchLot(workspace) {
	const loads = []
	const component = loadComponent(new URL("../src/departments/merch/lot/MerchLotPage.vue", import.meta.url).pathname, {
		"primevue/button": stub("button"), "primevue/message": stub("message"), "primevue/tab": stub("tab"),
		"primevue/tablist": stub("tablist"), "primevue/tabpanel": stub("tabpanel"), "primevue/tabpanels": stub("tabpanels"),
		"primevue/tabs": stub("tabs"),
		"primevue/usetoast": { useToast: () => ({ add: () => {} }) },
		"vue-router": { useRoute: () => ({ query: {} }), useRouter: () => ({ replace: () => {}, push: () => {} }) },
		"../../../api/merch.js": { getMerchLotWorkspace: async name => { loads.push(name); return workspace }, executeMerchLotCommand: async () => workspace },
		"../../../components/DepartmentPage.vue": stub("page"),
		"../../../components/documents/DocumentActionStrip.vue": stub("actions"),
		"../../../components/documents/DocumentConfirmationDialog.vue": stub("confirm"),
		"../../../components/documents/DocumentErrorDialog.vue": stub("error"),
		"../../../components/documents/DocumentOverview.vue": stub("overview"),
		"../../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"../../fabric-store/FabricDocumentWorkspace.vue": stub("workspace"),
		"./LotIdentity.vue": stub("identity"),
		"./LotViewMain.vue": stub("lot-main"),
		"./LotBomPanel.vue": stub("bom-panel"),
		"./lotEditor.js": { editTabFor: tab => lotLayout.resolveLotTab(tab).tab },
		"./lotLayout.js": lotLayout,
		"./lotViews.js": lotViews,
		"./useLotLayout.js": { useLotLayout: () => ({ activeTab: Vue.ref("lot"), expanded: Vue.ref([]), scrollTo: Vue.ref(""), openSection() {} }) },
		"./ClothProgramBuildDialog.vue": stub("cloth-build"),
		"./LotFabricTab.vue": stub("fabric"),
		"./LotDiaConversionsTab.vue": stub("dia-conversions"),
		"./LotEmptyState.vue": stub("empty"),
		"./LotPurchaseOrderDialog.vue": stub("po-dialog"),
		"./lotPurchaseActions.js": purchaseActions,
		"../merchViews.js": { MERCH_ROUTES: { lotEdit: "merch-lot-edit", lotNew: "merch-lot-new" } },
		"../../../composables/useDuplicateAction.js": duplicateAction,
		"./merchLotViews.js": merchViews,
		"./MerchClothProgramDialog.vue": stub("cloth"),
		"./MerchLotBomTab.vue": stub("bom"),
		"./MerchLotDocuments.vue": stub("documents"),
		"./MerchLotPpoPanel.vue": stub("ppo"),
	})
	const root = mountComponent(component, { lotId: "LOT-1" })
	const find = type => findNodes(root, node => node.type === type)
	return { loads, find, actions: () => find("actions")[0].props.actions, dialog: () => find("po-dialog")[0].props }
}

test("PO link actions follow the Purchase Lot write rule and disable while acting", () => {
	const run = () => {}
	assert.deepEqual(purchaseActions.purchaseOrderLinkActions({ name: "LOT-1" }, run), [])
	assert.deepEqual(purchaseActions.purchaseOrderLinkActions({}, run), [])
	const rows = purchaseActions.purchaseOrderLinkActions({ name: "LOT-1", permissions: { can_write: true } }, run, "reload")
	assert.deepEqual(rows.map(row => row.label), ["Link to PO", "Unlink from PO"])
	assert.ok(rows.every(row => row.disabled))
})

test("Merch Lot opens the shared PO dialog for Link and Unlink and reloads after a change", async () => {
	const page = mountMerchLot({ name: "LOT-1", modified: "m1", permissions: { can_write: true }, capabilities: {} })
	await tick()
	const actions = page.actions()
	assert.deepEqual(actions.map(row => row.key), ["link_po", "unlink_po"])
	assert.equal(page.dialog().visible, false)
	actions[0].command()
	await tick()
	assert.deepEqual([page.dialog().visible, page.dialog().mode, page.dialog().lot], [true, "link", "LOT-1"])
	page.dialog().onChanged()
	await tick()
	assert.deepEqual(page.loads, ["LOT-1", "LOT-1"])
	page.actions()[1].command()
	await tick()
	assert.deepEqual([page.dialog().visible, page.dialog().mode], [true, "unlink"])
})

test("Merch Lot hides PO link actions from readers", async () => {
	const page = mountMerchLot({ name: "LOT-1", modified: "m1", permissions: { can_write: false }, capabilities: {} })
	await tick()
	assert.deepEqual(page.actions(), [])
})

test("Merch Build Cloth Program opens setup first, builds, then opens the live popup", async () => {
	const build = { label: "Build Cloth Program", allowed: true, visible: true }
	const page = mountMerchLot({ name: "LOT-1", modified: "m1", permissions: { can_write: false }, capabilities: { build_cloth_programs: build } })
	await tick()
	const props = () => [page.find("cloth-build")[0].props, page.find("cloth")[0].props]
	page.actions().find(row => row.key === "build_cloth_programs").command()
	await tick()
	assert.deepEqual(props().map(row => row.visible), [false, true])
	assert.equal(props()[0].onSetup, undefined)
	props()[1].onBuild({ selections: [], excess_percentage: 4.8 })
	await tick()
	assert.deepEqual(props().map(row => row.visible), [true, false])
	assert.deepEqual([props()[0].lot, props()[0].modified], ["LOT-1", "m1"])
	props()[0].onSaved()
	await tick()
	assert.deepEqual(page.loads, ["LOT-1", "LOT-1"])
})

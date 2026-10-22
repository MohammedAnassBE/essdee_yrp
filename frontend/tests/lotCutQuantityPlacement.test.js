import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const shell = (_props, { slots }) => Vue.h("section", slots.default?.())
const tabMocks = {
	"primevue/message": shell, "primevue/select": () => null, "primevue/skeleton": () => null,
	"primevue/tab": shell, "primevue/tablist": shell, "primevue/tabpanel": shell,
	"primevue/tabpanels": shell, "primevue/tabs": shell,
}
const asyncStub = loader => {
	const name = String(loader).match(/\/([A-Za-z]+)\.vue/)[1]
	return props => Vue.h(name, props)
}
const vueWithStubs = { ...Vue, defineAsyncComponent: asyncStub }
const text = root => findNodes(root, node => node.type !== "comment" && node.text).map(node => node.text)
const canReadCuttingPlan = node => node.props.canReadCuttingPlan ?? node.props["can-read-cutting-plan"]
const flush = async () => { for (let index = 0; index < 5; index += 1) await Vue.nextTick() }
const lotCutCapability = { label: "Lot Cut Quantity", can_read: true, can_report: true, can_read_cutting_plan: true }

test("Lot Cut Quantity offers Copy Report", async () => {
	const shellProps = []
	const component = loadComponent(new URL("../src/components/reports/LotCutQuantityReport.vue", import.meta.url).pathname, {
		"../../api/purchaseReports.js": { getLotCutQuantity: async () => ({ lots: [] }) },
		"../../departments/cutting/CuttingCompletedReport.vue": () => null,
		"../../departments/cutting/cuttingCompletedReport.js": { normaliseCompletedGroups: () => [] },
		"../../departments/cutting/reports/AsyncLinkMultiSelect.vue": () => null,
		"./ReportShell.vue": Vue.defineComponent({
			props: { copyable: { type: Boolean, default: false } },
			setup: props => { shellProps.push(props); return () => null },
		}),
		"./reportUtils.js": { errorMessage: (_error, fallback) => fallback, number: String },
	})
	const root = mountComponent(component, {})
	try {
		assert.equal(shellProps[0].copyable, true)
	} finally { root.__vue_app__.unmount() }
})

async function mountSewingReports(reports, tab) {
	const component = loadComponent(new URL("../src/departments/sewing/SewingReportsWorkspace.vue", import.meta.url).pathname, {
		...tabMocks, vue: vueWithStubs,
		"vue-router": { useRoute: () => ({ path: "/sewing/reports", query: { tab } }), useRouter: () => ({ replace() {} }) },
		"../../components/reports/DeskBackedReport.vue": () => null,
		"../../components/reports/deskReportConfig.js": await import("../src/components/reports/deskReportConfig.js"),
		"./useSewingContext.js": { useSewingContext: () => ({ supplier: Vue.ref("") }) },
	})
	return mountComponent(component, { capabilities: { reports } })
}

test("Sewing reports list Lot Cut Quantity and In-house Quantity", async () => {
	const reports = {
		dpr: { label: "DPR", can_read: true, can_report: true },
		lot_cut_quantity: lotCutCapability,
		inhouse_quantity: { label: "In-house Quantity", can_read: true, can_report: true },
	}
	let root = await mountSewingReports(reports, "lot-cut-quantity")
	try {
		assert.ok(text(root).includes("Lot Cut Quantity"))
		assert.ok(text(root).includes("In-house Quantity"))
		const report = findNodes(root, node => node.type === "LotCutQuantityReport")
		assert.equal(report.length, 1)
		assert.equal(canReadCuttingPlan(report[0]), true)
	} finally { root.__vue_app__.unmount() }
	root = await mountSewingReports(reports, "inhouse-quantity")
	try {
		assert.equal(findNodes(root, node => node.type === "InhouseQuantityReport").length, 1)
	} finally { root.__vue_app__.unmount() }
})

test("Sewing hides Lot Cut Quantity and In-house Quantity without capability", async () => {
	const root = await mountSewingReports({ dpr: { label: "DPR", can_read: true, can_report: true } }, "lot-cut-quantity")
	try {
		assert.ok(!text(root).includes("Lot Cut Quantity"))
		assert.ok(!text(root).includes("In-house Quantity"))
	} finally { root.__vue_app__.unmount() }
})

test("Finishing reports list Lot Cut Quantity", async () => {
	const component = loadComponent(new URL("../src/departments/finishing/FinishingReports.vue", import.meta.url).pathname, {
		...tabMocks, vue: vueWithStubs,
		"vue-router": { useRoute: () => ({ path: "/finishing/reports", query: { report: "lot-cut-quantity" } }), useRouter: () => ({ replace() {} }) },
		"../../api/finishing.js": { getFinishingCapabilities: async () => ({ sections: { reports: { reports: {
			packing_dpr: { label: "Packing DPR", can_read: true }, lot_cut_quantity: lotCutCapability,
		} } } }) },
		"../../components/DepartmentPage.vue": shell,
		"../../components/reports/DeskBackedReport.vue": () => null,
		"../../components/reports/deskReportConfig.js": await import("../src/components/reports/deskReportConfig.js"),
		"../../components/common/WorkspaceLoadError.vue": () => null,
	})
	const root = mountComponent(component, {})
	try {
		await flush()
		assert.ok(text(root).includes("Lot Cut Quantity"))
		const report = findNodes(root, node => node.type === "LotCutQuantityReport")
		assert.equal(report.length, 1)
		assert.equal(canReadCuttingPlan(report[0]), true)
	} finally { root.__vue_app__.unmount() }
})

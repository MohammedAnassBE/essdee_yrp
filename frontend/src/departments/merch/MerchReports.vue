<template>
	<DepartmentPage :title="`${source.label} · Reports`" :back-to="source.path" :back-label="source.label" :show-title="false" flat full-width inline-navigation>
		<div class="merch-reports erp-workspace">
			<div v-if="loading" :aria-label="`Loading ${source.label} reports`"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" :message="`You do not have permission to view ${source.label} reports.`" :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" :label="`${source.label} reports`" :storage-key="department" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"
import { getMerchCapabilities, getMerchPurchaseCapabilities } from "../../api/merch.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import { combinedDeskReports } from "../../components/reports/deskReportConfig.js"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import { departments } from "../registry.js"

const REPORTS = [
	{ key: "work_in_progress", value: "work-in-progress", label: "Work In Progress", icon: "pi pi-chart-bar", component: defineAsyncComponent(() => import("./reports/WorkInProgressReport.vue")) },
	{ key: "inward_quantity", value: "inward-quantity", label: "Inward Quantity", icon: "pi pi-sign-in", component: defineAsyncComponent(() => import("../planning/reports/InwardQuantityReport.vue")) },
	{ key: "work_order", value: "work-order", label: "Work Order", icon: "pi pi-briefcase", component: defineAsyncComponent(() => import("../planning/reports/WorkOrderReport.vue")) },
	{ key: "planning_work_in_progress", value: "planning-work-in-progress", label: "Work In Progress", icon: "pi pi-chart-line", component: defineAsyncComponent(() => import("../planning/reports/WorkInProgressReport.vue")) },
	{ key: "size_wise_stock", value: "size-wise-stock", label: "Size-wise Stock", icon: "pi pi-th-large", component: defineAsyncComponent(() => import("../planning/reports/SizeWiseStockReport.vue")) },
	{ key: "multi_ccr", value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter", component: defineAsyncComponent(() => import("../cutting/reports/MultiCCRReport.vue")) },
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report", icon: "pi pi-file", component: defineAsyncComponent(() => import("../sales/PpoReport.vue")), props: { canExport: true } },
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")) },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue")), capabilityProps: (report) => ({ canReadCuttingPlan: Boolean(report.can_read_cutting_plan) }) },
]
/** Report pages by department key: whose capabilities load and whose desk reports join the tabs. */
const SOURCES = {
	merch: { load: getMerchCapabilities, deskDepartments: ["merch"] },
	"merch-purchase": { load: getMerchPurchaseCapabilities, deskDepartments: ["merch", "purchase"] },
}
const props = defineProps({ department: { type: String, default: "merch" } })
const source = { ...departments.find((item) => item.key === props.department), ...SOURCES[props.department] }
const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const deskTabs = computed(() => combinedDeskReports(source.deskDepartments, reports.value).map((tab) => ({ ...tab, component: DeskBackedReport })))
const tabs = computed(() => [
	...REPORTS.filter((report) => reports.value[report.key]?.can_read)
		.map((report) => ({ ...report, props: { ...report.props, ...report.capabilityProps?.(reports.value[report.key]) } })),
	...deskTabs.value,
])
async function load() {
	loading.value = true
	loadError.value = ""
	try {
		reports.value = (await source.load())?.reports || {}
	} catch (reason) {
		reports.value = {}
		loadError.value = reason?.message || `Unable to load ${source.label} reports.`
	} finally {
		loading.value = false
	}
}
onMounted(load)
</script>

<style scoped>
.merch-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
</style>

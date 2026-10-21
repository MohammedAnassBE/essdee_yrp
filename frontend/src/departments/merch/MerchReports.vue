<template>
	<DepartmentPage :title="`${source.label} · Reports`" :back-to="source.path" :back-label="source.label" :show-title="false" flat full-width inline-navigation>
		<div class="merch-reports erp-workspace">
			<div v-if="loading" :aria-label="`Loading ${source.label} reports`"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" :message="`You do not have permission to view ${source.label} reports.`" :retryable="false" />
			<template v-else>
				<div class="merch-reports__mobile common-field">
					<label for="merch-report-view">Report</label>
					<Select input-id="merch-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs">
					<TabList class="merch-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
					</TabList>
					<TabPanels class="merch-reports__panels">
						<TabPanel :key="active" :value="active"><component :is="currentTab.component" v-bind="currentTab.props" /></TabPanel>
					</TabPanels>
				</Tabs>
			</template>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { getMerchCapabilities, getMerchPurchaseCapabilities } from "../../api/merch.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import { combinedDeskReports } from "../../components/reports/deskReportConfig.js"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
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
const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const deskTabs = computed(() => combinedDeskReports(source.deskDepartments, reports.value).map((tab) => ({ ...tab, component: DeskBackedReport })))
const tabs = computed(() => [
	...REPORTS.filter((report) => reports.value[report.key]?.can_read)
		.map((report) => ({ ...report, props: { ...report.props, ...report.capabilityProps?.(reports.value[report.key]) } })),
	...deskTabs.value,
])
const active = computed({
	get: () => tabs.value.some((tab) => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value,
	set: (report) => router.replace({ query: { ...route.query, report } }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])
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
.merch-reports { display: grid; min-width: 0; gap: var(--erp-space-2); }
.merch-reports :deep(.p-tabs) { min-width: 0; }
.merch-reports :deep(.p-tab) { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; }
.merch-reports__panels { padding: 12px 0 0; background: transparent; }
.merch-reports__panels :deep(.p-tabpanel) { padding: 0; }
.merch-reports__mobile { display: none; }
@media (max-width: 700px) {
	.merch-reports__desktop { display: none; }
	.merch-reports__mobile { display: grid; gap: 6px; }
}
</style>

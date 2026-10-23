<template>
	<DepartmentPage title="Finishing Reports" back-to="/finishing" back-label="Finishing" :show-title="false" flat full-width inline-navigation>
		<div class="finishing-reports erp-workspace">
			<div v-if="loading" class="finishing-reports__loading" aria-label="Loading Finishing reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Finishing reports." :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" label="Finishing reports" storage-key="finishing" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import { getFinishingCapabilities } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import "./finishing.css"

const REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")) },
	{ key: "packing_dpr", value: "packing-dpr", label: "Packing DPR", icon: "pi pi-box", component: defineAsyncComponent(() => import("./reports/FinishingPackingDpr.vue")) },
	{ key: "dispatch_report", value: "dispatch-report", label: "Dispatch Report", icon: "pi pi-truck", component: defineAsyncComponent(() => import("./reports/FinishingDispatchReport.vue")) },
	{ key: "ironing_dpr", value: "ironing-dpr", label: "Ironing DPR", icon: "pi pi-sliders-h", component: defineAsyncComponent(() => import("./reports/FinishingIroningDpr.vue")) },
	{ key: "finishing_plan_report", value: "finishing-plan-report", label: "Finishing Plan Report", icon: "pi pi-table", component: defineAsyncComponent(() => import("./reports/FinishingPlanReport.vue")) },
	{ key: "rejection_details", value: "rejection-details", label: "Rejection Details", icon: "pi pi-ban", component: defineAsyncComponent(() => import("./reports/FinishingRejectionReport.vue")) },
	{ key: "rework_completion", value: "rework-completion", label: "Rework Completion", icon: "pi pi-check-square", component: defineAsyncComponent(() => import("./reports/FinishingReworkCompletion.vue")) },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue")), capabilityProps: (report) => ({ canReadCuttingPlan: Boolean(report.can_read_cutting_plan) }) },
	{ key: "inhouse_quantity", value: "inhouse-quantity", label: "In-house Quantity", icon: "pi pi-building", component: defineAsyncComponent(() => import("../planning/reports/InhouseQuantityReport.vue")) },
]

const route = useRoute()
const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const tabs = computed(() => [...REPORTS.filter((report) => reports.value[report.key]?.can_read).map((report) => ({ ...report, props: report.capabilityProps?.(reports.value[report.key]) })), ...departmentDeskReports(route.path.split("/")[1], reports.value).map(tab => ({ ...tab, component: DeskBackedReport }))])

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		reports.value = (await getFinishingCapabilities())?.sections?.reports?.reports || {}
	} catch (reason) {
		reports.value = {}
		loadError.value = reason?.message || "Unable to load Finishing reports."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.finishing-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
.finishing-reports__loading { display: grid; gap: var(--erp-space-3); }
</style>

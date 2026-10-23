<template>
	<DepartmentPage
		title="Cutting Reports"
		back-to="/cutting"
		back-label="Cutting"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="cutting-reports erp-workspace" aria-label="Cutting Reports">
			<div v-if="loadingPermissions" class="report-permission-loading"><Skeleton height="3rem" /><Skeleton height="14rem" /></div>
			<WorkspaceLoadError v-else-if="permissionError" title="Reports could not be loaded" :message="permissionError" :loading="loadingPermissions" @retry="load" />
			<ReportWorkspace v-else-if="visibleTabs.length" :reports="visibleTabs" label="Cutting reports" storage-key="cutting" keep-alive />
			<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DeskBackedReport from "../components/reports/DeskBackedReport.vue"
import { departmentDeskReports } from "../components/reports/deskReportConfig.js"
import ReportWorkspace from "../components/reports/ReportWorkspace.vue"
import StockBalanceReport from "../components/reports/StockBalanceReport.vue"
import CuttingDetailReport from "./cutting/reports/CuttingDetailReport.vue"
import DailyCutSheetReport from "./cutting/reports/DailyCutSheetReport.vue"
import DailyProductionReport from "./cutting/reports/DailyProductionReport.vue"
import MultiCCRReport from "./cutting/reports/MultiCCRReport.vue"

const route = useRoute()
const loadingPermissions = ref(true)
const permissionError = ref("")
const reportPermissions = ref({})
const tabs = [
	{ value: "daily-production", label: "Daily Production", icon: "pi pi-chart-line", component: DailyProductionReport },
	{ value: "daily-cut-sheet", label: "Daily Cut Sheet", icon: "pi pi-table", component: DailyCutSheetReport },
	{ value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter", component: MultiCCRReport },
	{ value: "cutting-detail", label: "Cutting Detail", icon: "pi pi-chart-bar", component: CuttingDetailReport },
	{ value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
]
const deskTabs = computed(() => departmentDeskReports(route.path.split("/")[1], Object.fromEntries(Object.entries(reportPermissions.value).map(([key, can_read]) => [key.replaceAll("-", "_"), { can_read }]))))
const visibleTabs = computed(() => [...tabs.filter((tab) => reportPermissions.value[tab.value]), ...deskTabs.value.map((tab) => ({ ...tab, component: DeskBackedReport }))])

async function load() {
	loadingPermissions.value = true
	permissionError.value = ""
	try {
		reportPermissions.value = await getCuttingReportPermissions() || {}
	} catch (reason) {
		reportPermissions.value = {}
		permissionError.value = reason?.message || "Unable to load report permissions."
	} finally {
		loadingPermissions.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.cutting-reports {
	width: 100%;
	min-width: 0;
	padding: var(--erp-space-2) 0 var(--erp-space-5);
}

.report-permission-loading {
	display: grid;
	gap: 10px;
}
</style>

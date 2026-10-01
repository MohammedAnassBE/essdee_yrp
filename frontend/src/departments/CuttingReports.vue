<template>
	<DepartmentPage
		title="Cutting Reports"
		accent="#0b8f65"
		back-to="/cutting"
		back-label="Cutting"
		:show-title="false"
		flat
		full-width
	>
		<section class="cutting-reports erp-workspace" aria-label="Cutting Reports">
			<div v-if="loadingPermissions" class="report-permission-loading"><Skeleton height="3rem" /><Skeleton height="14rem" /></div>
			<Message v-else-if="permissionError" severity="error" :closable="false">{{ permissionError }}</Message>
			<Tabs v-else-if="visibleTabs.length" v-model:value="activeTab" class="erp-tabs report-tabs">
				<TabList class="report-tabs__list">
					<Tab v-for="tab in visibleTabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" /><span>{{ tab.label }}</span></Tab>
				</TabList>
				<TabPanels class="report-tabs__panels">
					<TabPanel v-if="reportPermissions['daily-production']" value="daily-production"><DailyProductionReport /></TabPanel>
					<TabPanel v-if="reportPermissions['daily-cut-sheet']" value="daily-cut-sheet"><DailyCutSheetReport /></TabPanel>
					<TabPanel v-if="reportPermissions['multi-ccr']" value="multi-ccr"><MultiCCRReport /></TabPanel>
					<TabPanel v-if="reportPermissions['cutting-detail']" value="cutting-detail"><CuttingDetailReport /></TabPanel>
					<TabPanel v-if="reportPermissions['stock-balance']" value="stock-balance"><StockBalanceReport /></TabPanel>
				</TabPanels>
			</Tabs>
			<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, onMounted, ref } from "vue"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import CuttingDetailReport from "./cutting/reports/CuttingDetailReport.vue"
import DailyCutSheetReport from "./cutting/reports/DailyCutSheetReport.vue"
import DailyProductionReport from "./cutting/reports/DailyProductionReport.vue"
import MultiCCRReport from "./cutting/reports/MultiCCRReport.vue"
import StockBalanceReport from "./cutting/reports/StockBalanceReport.vue"

const activeTab = ref("")
const loadingPermissions = ref(true)
const permissionError = ref("")
const reportPermissions = ref({})
const tabs = [
	{ value: "daily-production", label: "Daily Production", icon: "pi pi-chart-line" },
	{ value: "daily-cut-sheet", label: "Daily Cut Sheet", icon: "pi pi-table" },
	{ value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter" },
	{ value: "cutting-detail", label: "Cutting Detail", icon: "pi pi-chart-bar" },
	{ value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
]
const visibleTabs = computed(() => tabs.filter((tab) => reportPermissions.value[tab.value]))

onMounted(async () => {
	try {
		reportPermissions.value = await getCuttingReportPermissions() || {}
		activeTab.value = visibleTabs.value[0]?.value || ""
	} catch (reason) {
		permissionError.value = reason.message || "Unable to load report permissions."
	} finally {
		loadingPermissions.value = false
	}
})
</script>

<style scoped>
.cutting-reports { max-width: 1800px; margin: 0 auto; padding: 0 2px 20px; }
.report-permission-loading { display: grid; gap: 10px; }
.report-tabs { min-width: 0; }
.report-tabs__list { position: sticky; top: 0; z-index: 8; background: var(--erp-bg); }
.report-tabs :deep(.p-tab) { display: inline-flex; align-items: center; white-space: nowrap; }
.report-tabs :deep(.p-tab i) { margin-right: 7px; font-size: 0.76rem; }
.report-tabs__panels { padding: 10px 0 0; background: transparent; }
.report-tabs__panels :deep(.p-tabpanel) { padding: 0; }
@media (max-width: 820px) { .report-tabs__list { overflow-x: auto; } }
</style>

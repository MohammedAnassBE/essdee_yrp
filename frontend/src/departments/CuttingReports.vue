<template>
	<DepartmentPage
		title="Cutting Reports"
		:embedded="embedded"
		back-to="/cutting"
		back-label="Cutting"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="cutting-reports erp-workspace" :class="{ 'cutting-reports--embedded': embedded }" aria-label="Cutting Reports">
			<div v-if="loadingPermissions" class="report-permission-loading"><Skeleton height="3rem" /><Skeleton height="14rem" /></div>
			<WorkspaceLoadError v-else-if="permissionError" title="Reports could not be loaded" :message="permissionError" :loading="loadingPermissions" @retry="load" />
			<Tabs v-else-if="visibleTabs.length" v-model:value="activeTab" class="erp-tabs report-tabs">
				<div class="report-tabs__mobile">
					<label for="cutting-report-select">Report</label>
					<Select
						v-model="activeTab"
						input-id="cutting-report-select"
						:options="visibleTabs"
						option-label="label"
						option-value="value"
						placeholder="Choose a report"
						fluid
					/>
				</div>
				<TabList class="report-tabs__list">
					<Tab v-for="tab in visibleTabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" /><span>{{ tab.label }}</span></Tab>
				</TabList>
				<TabPanels class="report-tabs__panels">
					<TabPanel v-if="reportPermissions['daily-production']" value="daily-production"><DailyProductionReport /></TabPanel>
					<TabPanel v-if="reportPermissions['daily-cut-sheet']" value="daily-cut-sheet"><DailyCutSheetReport /></TabPanel>
					<TabPanel v-if="reportPermissions['multi-ccr']" value="multi-ccr"><MultiCCRReport /></TabPanel>
					<TabPanel v-if="reportPermissions['cutting-detail']" value="cutting-detail"><CuttingDetailReport /></TabPanel>
					<TabPanel v-if="reportPermissions['stock-balance']" value="stock-balance"><StockBalanceReport /></TabPanel>
					<TabPanel v-for="tab in deskTabs" :key="tab.value" :value="tab.value"><DeskBackedReport :report-key="tab.value" /></TabPanel>
				</TabPanels>
			</Tabs>
			<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DeskBackedReport from "../components/reports/DeskBackedReport.vue"
import { departmentDeskReports } from "../components/reports/deskReportConfig.js"
import StockBalanceReport from "../components/reports/StockBalanceReport.vue"
import CuttingDetailReport from "./cutting/reports/CuttingDetailReport.vue"
import DailyCutSheetReport from "./cutting/reports/DailyCutSheetReport.vue"
import DailyProductionReport from "./cutting/reports/DailyProductionReport.vue"
import MultiCCRReport from "./cutting/reports/MultiCCRReport.vue"

defineProps({ embedded: { type: Boolean, default: false } })

const route = useRoute()
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
const deskTabs = computed(() => departmentDeskReports(route.path.split("/")[1], Object.fromEntries(Object.entries(reportPermissions.value).map(([key, can_read]) => [key.replaceAll("-", "_"), { can_read }]))))
const visibleTabs = computed(() => [...tabs.filter((tab) => reportPermissions.value[tab.value]), ...deskTabs.value])

async function load() {
	loadingPermissions.value = true
	permissionError.value = ""
	try {
		reportPermissions.value = await getCuttingReportPermissions() || {}
		activeTab.value = visibleTabs.value[0]?.value || ""
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
	padding: 0 0 var(--erp-space-5);
}

.report-permission-loading {
	display: grid;
	gap: 10px;
}

.report-tabs {
	min-width: 0;
}

.report-tabs__mobile {
	display: none;
}

.report-tabs__list {
	position: sticky;
	z-index: var(--erp-layer-sticky);
	top: var(--erp-shell-header-height);
	background: var(--erp-bg);
}

.cutting-reports--embedded .report-tabs__list,
.cutting-reports--embedded .report-tabs__mobile {
	top: calc(var(--erp-shell-header-height) + var(--planning-reports-sticky-offset, 0px));
}

.report-tabs :deep(.p-tab) {
	display: inline-flex;
	min-height: 44px;
	align-items: center;
	white-space: nowrap;
}

.report-tabs :deep(.p-tab i) {
	margin-right: 7px;
	font-size: var(--erp-font-size-caption);
}

.report-tabs__panels {
	padding: var(--erp-space-3) 0 0;
	background: transparent;
}

.report-tabs__panels :deep(.p-tabpanel) {
	padding: 0;
}

@media (max-width: 700px) {
	.report-tabs__mobile {
		position: sticky;
		z-index: var(--erp-layer-sticky);
		top: var(--erp-shell-header-height);
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		align-items: center;
		gap: 6px;
		padding: var(--erp-space-2) 0;
		background: var(--erp-bg);
	}

	.report-tabs__mobile label {
		color: var(--erp-text-muted);
		font-size: var(--erp-font-size-min);
		font-weight: 750;
		letter-spacing: 0.035em;
		text-transform: uppercase;
	}

	.report-tabs__list {
		display: none;
	}
}
</style>

<template>
	<DepartmentPage title="Accounts Reports" back-to="/accounts" back-label="Accounts" :show-title="false" flat full-width inline-navigation>
		<div class="accounts-reports erp-workspace">
			<div v-if="loading" class="accounts-reports__loading" aria-label="Loading Accounts reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Accounts reports." :retryable="false" />
			<template v-else>
				<div class="accounts-reports__mobile common-field">
					<label for="accounts-report-view">Report</label>
					<Select input-id="accounts-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs accounts-reports__tabs">
					<TabList class="accounts-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
					</TabList>
					<TabPanels class="accounts-reports__panels">
						<TabPanel :key="active" :value="active">
							<component :is="currentTab.component" v-bind="currentTab.componentProps" />
						</TabPanel>
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

import { getAccountsCapabilities } from "../../api/accounts.js"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { accountsReportTabs } from "./accountsViews.js"
import "../finishing/finishing.css"

const REPORT_COMPONENTS = {
	stock_balance: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")),
	cutting_dpr: defineAsyncComponent(() => import("../cutting/reports/DailyProductionReport.vue")),
	sewing_dpr: defineAsyncComponent(() => import("./reports/AccountsSewingDpr.vue")),
	finishing_dispatch: defineAsyncComponent(() => import("../finishing/reports/FinishingDispatchReport.vue")),
	ironing_dpr: defineAsyncComponent(() => import("../finishing/reports/FinishingIroningDpr.vue")),
	audit_pending_finishing_plans: defineAsyncComponent(() => import("./reports/AuditPendingFinishingPlans.vue")),
}

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const capabilities = ref({ reports: {} })
const tabs = computed(() => accountsReportTabs(capabilities.value.reports).map((report) => ({
	...report,
	component: REPORT_COMPONENTS[report.key] || DeskBackedReport,
})))
const active = computed({
	get: () => (tabs.value.some((tab) => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value),
	set: (report) => router.replace({ query: { ...route.query, report }, hash: route.hash }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		capabilities.value = await getAccountsCapabilities() || { reports: {} }
	} catch (reason) {
		capabilities.value = { reports: {} }
		loadError.value = reason?.message || "Unable to load Accounts reports."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.accounts-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: 0; }
.accounts-reports__loading { display: grid; gap: var(--erp-space-3); }
.accounts-reports__tabs { min-width: 0; }
.accounts-reports__tabs :deep(.p-tab) { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.accounts-reports__panels { padding: 12px 0 0; background: transparent; }
.accounts-reports__panels :deep(.p-tabpanel) { padding: 0; }
.accounts-reports__mobile { display: none; }
@media (max-width: 700px) {
	.accounts-reports__desktop { display: none; }
	.accounts-reports__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
	.accounts-reports__panels { padding-top: 6px; }
}
</style>

<template>
	<DepartmentPage title="Accounts Reports" back-to="/accounts" back-label="Accounts" :show-title="false" flat full-width inline-navigation>
		<div class="accounts-reports erp-workspace">
			<div v-if="loading" class="accounts-reports__loading" aria-label="Loading Accounts reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Accounts reports." :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" label="Accounts reports" storage-key="accounts" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"

import { getAccountsCapabilities } from "../../api/accounts.js"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
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

const loading = ref(true)
const loadError = ref("")
const capabilities = ref({ reports: {} })
const tabs = computed(() => accountsReportTabs(capabilities.value.reports).map((report) => ({
	...report,
	component: REPORT_COMPONENTS[report.key] || DeskBackedReport,
	props: report.componentProps,
})))

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
.accounts-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
.accounts-reports__loading { display: grid; gap: var(--erp-space-3); }
</style>

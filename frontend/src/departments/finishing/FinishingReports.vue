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

import { getFinishingCapabilities } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import { finishingReportTabs } from "../departmentReports.js"
import "./finishing.css"

const COMPONENTS = {
	stock_balance: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")),
	packing_dpr: defineAsyncComponent(() => import("./reports/FinishingPackingDpr.vue")),
	dispatch_report: defineAsyncComponent(() => import("./reports/FinishingDispatchReport.vue")),
	ironing_dpr: defineAsyncComponent(() => import("./reports/FinishingIroningDpr.vue")),
	finishing_plan_report: defineAsyncComponent(() => import("./reports/FinishingPlanReport.vue")),
	rejection_details: defineAsyncComponent(() => import("./reports/FinishingRejectionReport.vue")),
	rework_completion: defineAsyncComponent(() => import("./reports/FinishingReworkCompletion.vue")),
	lot_cut_quantity: defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue")),
	inhouse_quantity: defineAsyncComponent(() => import("../planning/reports/InhouseQuantityReport.vue")),
}

const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const tabs = computed(() => finishingReportTabs(reports.value).map((tab) => ({ ...tab, component: COMPONENTS[tab.key] || DeskBackedReport })))

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

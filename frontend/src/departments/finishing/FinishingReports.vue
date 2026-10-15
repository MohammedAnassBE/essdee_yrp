<template>
	<DepartmentPage title="Finishing Reports" back-to="/finishing" back-label="Finishing" :show-title="false" :embedded="embedded" flat full-width inline-navigation>
		<div class="finishing-reports erp-workspace">
			<div v-if="loading" class="finishing-reports__loading" aria-label="Loading Finishing reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Finishing reports." :retryable="false" />
			<template v-else>
				<div class="finishing-reports__mobile common-field">
					<label for="finishing-report-view">Report</label>
					<Select input-id="finishing-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs finishing-reports__tabs">
					<TabList class="finishing-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
					</TabList>
					<TabPanels class="finishing-reports__panels">
						<TabPanel :key="active" :value="active">
							<component :is="currentTab.component" />
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

import { getFinishingCapabilities } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import "./finishing.css"

defineProps({ embedded: { type: Boolean, default: false } })

const REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")) },
	{ key: "packing_dpr", value: "packing-dpr", label: "Packing DPR", icon: "pi pi-box", component: defineAsyncComponent(() => import("./reports/FinishingPackingDpr.vue")) },
	{ key: "dispatch_report", value: "dispatch-report", label: "Dispatch Report", icon: "pi pi-truck", component: defineAsyncComponent(() => import("./reports/FinishingDispatchReport.vue")) },
	{ key: "ironing_dpr", value: "ironing-dpr", label: "Ironing DPR", icon: "pi pi-sliders-h", component: defineAsyncComponent(() => import("./reports/FinishingIroningDpr.vue")) },
	{ key: "finishing_plan_report", value: "finishing-plan-report", label: "Finishing Plan Report", icon: "pi pi-table", component: defineAsyncComponent(() => import("./reports/FinishingPlanReport.vue")) },
	{ key: "rejection_details", value: "rejection-details", label: "Rejection Details", icon: "pi pi-ban", component: defineAsyncComponent(() => import("./reports/FinishingRejectionReport.vue")) },
	{ key: "rework_completion", value: "rework-completion", label: "Rework Completion", icon: "pi pi-check-square", component: defineAsyncComponent(() => import("./reports/FinishingReworkCompletion.vue")) },
]

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const tabs = computed(() => REPORTS.filter((report) => reports.value[report.key]?.can_read))
const active = computed({
	get: () => (tabs.value.some((tab) => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value),
	set: (report) => router.replace({ query: { ...route.query, report } }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])

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
.finishing-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: 0; }
.finishing-reports__loading { display: grid; gap: var(--erp-space-3); }
.finishing-reports__tabs { min-width: 0; }
.finishing-reports__tabs :deep(.p-tab) { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.finishing-reports__panels { padding: 12px 0 0; background: transparent; }
.finishing-reports__panels :deep(.p-tabpanel) { padding: 0; }
.finishing-reports__mobile { display: none; }
@media (max-width: 700px) {
	.finishing-reports__desktop { display: none; }
	.finishing-reports__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
	.finishing-reports__panels { padding-top: 6px; }
}
</style>

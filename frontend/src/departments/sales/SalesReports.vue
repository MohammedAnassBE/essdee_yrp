<template>
	<DepartmentPage title="Sales Reports" back-to="/sales" back-label="Sales" :show-title="false" flat full-width inline-navigation>
		<section class="sales-reports erp-workspace" aria-label="Sales Reports">
			<div v-if="loading" class="sales-reports__loading"><Skeleton height="76px" /><Skeleton height="420px" /></div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!tabs.length" severity="warn" :closable="false">You do not have permission to view Sales reports.</Message>
			<template v-else>
				<div class="sales-reports__mobile common-field">
					<label for="sales-report-view">Report</label>
					<Select input-id="sales-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs sales-reports__tabs">
					<TabList class="sales-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</Tab>
					</TabList>
					<TabPanels class="sales-reports__panels">
						<TabPanel :key="active" :value="active">
							<PpoReport v-if="active === 'ppo-report'" :can-export="Boolean(ppoCapability?.can_export)" />
							<FinishingDispatchReport v-else-if="active === 'finishing-dispatch'" />
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>
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
import { computed, defineAsyncComponent, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getSalesCapabilities } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import PpoReport from "./PpoReport.vue"

const REPORTS = [
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report" },
	{ key: "finishing_dispatch", value: "finishing-dispatch", label: "Finishing Plan Dispatch" },
]
const FinishingDispatchReport = defineAsyncComponent(() => import("../finishing/reports/FinishingDispatchReport.vue"))
const route = useRoute()
const router = useRouter()
const loading = ref(true)
const error = ref("")
const capabilities = ref({ sections: {}, reports: {} })
const tabs = computed(() => {
	const section = capabilities.value.sections?.reports
	return section?.can_read ? REPORTS.filter(report => capabilities.value.reports?.[report.key]?.can_read) : []
})
const active = computed({
	get: () => tabs.value.some(tab => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value,
	set: report => router.replace({ query: { ...route.query, report }, hash: route.hash }),
})
const ppoCapability = computed(() => capabilities.value.reports?.ppo_report)

async function load() {
	loading.value = true
	error.value = ""
	try {
		capabilities.value = await getSalesCapabilities() || { sections: {}, reports: {} }
	} catch (reason) {
		error.value = reason?.message || "Unable to load Sales Reports."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.sales-reports { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; padding: 2px 0 var(--erp-space-5); }
.sales-reports__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.sales-reports__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
.sales-reports__tabs { min-width: 0; }
.sales-reports__tabs :deep(.p-tab) { min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.sales-reports__panels { padding: 12px 0 0; background: transparent; }
.sales-reports__panels :deep(.p-tabpanel) { padding: 0; }
.sales-reports__mobile { display: none; }
@media (max-width: 700px) {
	.sales-reports__desktop { display: none; }
	.sales-reports__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
	.sales-reports__panels { padding-top: 6px; }
}
</style>

<template>
	<DepartmentPage title="HR Reports" back-to="/hr" back-label="HR" :show-title="false" flat full-width inline-navigation>
		<div class="hr-reports erp-workspace">
			<div v-if="loading" class="hr-reports__loading" aria-label="Loading HR reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view HR reports." :retryable="false" />
			<template v-else>
				<div class="hr-reports__mobile common-field">
					<label for="hr-report-view">Report</label>
					<Select input-id="hr-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs hr-reports__tabs">
					<TabList class="hr-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
					</TabList>
					<TabPanels class="hr-reports__panels">
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

import { getHrCapabilities } from "../../api/hr.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"

const REPORTS = [
	{
		key: "attendance",
		value: "attendance",
		label: "Attendance",
		icon: "pi pi-users",
		component: defineAsyncComponent(() => import("../../components/reports/AttendanceStrengthReport.vue")),
	},
]

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const capabilities = ref({ reports: {} })
const tabs = computed(() => REPORTS.filter((report) => capabilities.value.reports?.[report.key]?.can_read))
const active = computed({
	get: () => (tabs.value.some((tab) => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value),
	set: (report) => router.replace({ query: { ...route.query, report }, hash: route.hash }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		capabilities.value = await getHrCapabilities() || { reports: {} }
	} catch (reason) {
		capabilities.value = { reports: {} }
		loadError.value = reason?.message || "Unable to load HR reports."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.hr-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: 0; }
.hr-reports__loading { display: grid; gap: var(--erp-space-3); }
.hr-reports__tabs { min-width: 0; }
.hr-reports__tabs :deep(.p-tab) { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.hr-reports__panels { padding: 12px 0 0; background: transparent; }
.hr-reports__panels :deep(.p-tabpanel) { padding: 0; }
.hr-reports__mobile { display: none; }
@media (max-width: 700px) {
	.hr-reports__desktop { display: none; }
	.hr-reports__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
	.hr-reports__panels { padding-top: 6px; }
}
</style>

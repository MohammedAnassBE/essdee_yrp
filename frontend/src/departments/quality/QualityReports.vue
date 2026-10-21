<template>
	<DepartmentPage title="Quality Reports" back-to="/quality" back-label="Quality" :show-title="false" flat full-width inline-navigation>
		<div class="quality-reports erp-workspace">
			<div v-if="loading" class="quality-reports__loading" aria-label="Loading Quality reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Quality reports." :retryable="false" />
			<template v-else>
				<div class="quality-reports__mobile common-field">
					<label for="quality-report-view">Report</label>
					<Select input-id="quality-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report" fluid />
				</div>
				<Tabs v-model:value="active" scrollable class="erp-tabs quality-reports__tabs">
					<TabList class="quality-reports__desktop">
						<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
					</TabList>
					<TabPanels class="quality-reports__panels">
						<TabPanel :key="active" :value="active">
							<DeskBackedReport :report-key="currentTab.value" />
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
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getQualityCapabilities } from "../../api/quality.js"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"

const REPORTS = [
	{ key: "quality_inspection_rft", value: "quality-inspection-rft", label: "Quality Inspection RFT", icon: "pi pi-verified" },
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
		capabilities.value = await getQualityCapabilities() || { reports: {} }
	} catch (reason) {
		capabilities.value = { reports: {} }
		loadError.value = reason?.message || "Unable to load Quality reports."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.quality-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: 0; }
.quality-reports__loading { display: grid; gap: var(--erp-space-3); }
.quality-reports__tabs { min-width: 0; }
.quality-reports__tabs :deep(.p-tab) { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 9px 14px; font-size: var(--erp-font-size-table); white-space: nowrap; }
.quality-reports__panels { padding: 12px 0 0; background: transparent; }
.quality-reports__panels :deep(.p-tabpanel) { padding: 0; }
.quality-reports__mobile { display: none; }
@media (max-width: 700px) {
	.quality-reports__desktop { display: none; }
	.quality-reports__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
	.quality-reports__panels { padding-top: 6px; }
}
</style>

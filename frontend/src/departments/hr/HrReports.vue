<template>
	<DepartmentPage title="HR Reports" back-to="/hr" back-label="HR" :show-title="false" flat full-width inline-navigation>
		<div class="hr-reports erp-workspace">
			<div v-if="loading" class="hr-reports__loading" aria-label="Loading HR reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view HR reports." :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" label="HR reports" storage-key="hr" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"

import { getHrCapabilities } from "../../api/hr.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"

const REPORTS = [
	{
		key: "attendance",
		value: "attendance",
		label: "Attendance",
		icon: "pi pi-users",
		component: defineAsyncComponent(() => import("../../components/reports/AttendanceStrengthReport.vue")),
	},
]

const loading = ref(true)
const loadError = ref("")
const capabilities = ref({ reports: {} })
const tabs = computed(() => REPORTS.filter((report) => capabilities.value.reports?.[report.key]?.can_read))

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
.hr-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
.hr-reports__loading { display: grid; gap: var(--erp-space-3); }
</style>

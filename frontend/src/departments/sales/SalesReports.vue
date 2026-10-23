<template>
	<DepartmentPage title="Sales Reports" back-to="/sales" back-label="Sales" :show-title="false" flat full-width inline-navigation>
		<section class="sales-reports erp-workspace" aria-label="Sales Reports">
			<div v-if="loading" class="sales-reports__loading"><Skeleton height="76px" /><Skeleton height="420px" /></div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!tabs.length" severity="warn" :closable="false">You do not have permission to view Sales reports.</Message>
			<ReportWorkspace v-else :reports="tabs" label="Sales reports" storage-key="sales" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"

import { getSalesCapabilities } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import PpoReport from "./PpoReport.vue"

const REPORTS = [
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report", icon: "pi pi-file", component: PpoReport },
	{ key: "finishing_dispatch", value: "finishing-dispatch", label: "Finishing Plan Dispatch", icon: "pi pi-truck", component: defineAsyncComponent(() => import("../finishing/reports/FinishingDispatchReport.vue")) },
]
const loading = ref(true)
const error = ref("")
const capabilities = ref({ sections: {}, reports: {} })
const tabs = computed(() => {
	const section = capabilities.value.sections?.reports
	if (!section?.can_read) return []
	return REPORTS.filter(report => capabilities.value.reports?.[report.key]?.can_read)
		.map(report => report.key === "ppo_report" ? { ...report, props: { canExport: Boolean(capabilities.value.reports.ppo_report.can_export) } } : report)
})

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
.sales-reports { width: 100%; min-width: 0; padding: var(--erp-space-2) 0 var(--erp-space-5); }
.sales-reports__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.sales-reports__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
</style>

<template>
	<DepartmentPage title="Sales Reports" accent="#b7493f" back-to="/sales" back-label="Sales" :show-title="false" flat full-width inline-navigation>
		<section class="sales-reports erp-workspace" aria-label="Sales Reports">
			<div v-if="loading" class="sales-reports__loading"><Skeleton height="76px" /><Skeleton height="420px" /></div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!reportCapability" severity="warn" :closable="false">You do not have permission to view the PPO Report.</Message>
			<PpoReport v-else :can-export="Boolean(reportCapability.can_export)" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref } from "vue"

import { getSalesCapabilities } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import PpoReport from "./PpoReport.vue"

const loading = ref(true)
const error = ref("")
const capabilities = ref({ sections: {}, reports: {} })
const reportCapability = computed(() => {
	const section = capabilities.value.sections?.reports
	const report = capabilities.value.reports?.ppo_report
	return section?.can_read && report?.can_read ? report : null
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
.sales-reports { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; padding: 2px 0 var(--erp-space-5); }
.sales-reports__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.sales-reports__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
</style>

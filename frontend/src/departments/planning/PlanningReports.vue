<template>
	<DepartmentPage title="Planning Reports" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<section class="planning-reports erp-workspace" aria-label="Planning Reports">
			<div v-if="loading" class="planning-reports__loading"><Skeleton height="76px" /><Skeleton height="420px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!reports.length" severity="warn" :closable="false">You do not have permission to view Planning reports.</Message>
			<ReportWorkspace v-else :reports="reports" label="Planning reports" storage-key="planning" keep-alive />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getCuttingReportPermissions } from "../../api/cuttingReports.js"
import { getFinishingCapabilities } from "../../api/finishing.js"
import { getPlanningCapabilities } from "../../api/planning.js"
import { getSewingCapabilities } from "../../api/sewing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import { legacyPlanningReportQuery, planningReports } from "./reports/planningReportCatalog.js"

const GROUP_LOADERS = { cutting: getCuttingReportPermissions, sewing: getSewingCapabilities, finishing: getFinishingCapabilities }
const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const reports = ref([])

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		const section = (await getPlanningCapabilities())?.sections?.reports || {}
		const groups = Object.keys(GROUP_LOADERS).filter(group => section.groups?.[group] === true)
		const loaded = await Promise.all(groups.map(group => GROUP_LOADERS[group]()))
		const capabilities = Object.fromEntries(groups.map((group, index) => [group, loaded[index] || {}]))
		reports.value = planningReports({ ...capabilities, production: section.groups?.production === true ? section.production : {} })
	} catch (reason) {
		reports.value = []
		loadError.value = reason?.message || "Unable to load Planning reports."
	} finally {
		loading.value = false
	}
}

onMounted(() => {
	const query = legacyPlanningReportQuery(route.query)
	if (query) router.replace({ query, hash: route.hash })
	load()
})
</script>

<style scoped>
.planning-reports { width: 100%; min-width: 0; padding: var(--erp-space-2) 0 var(--erp-space-5); }
.planning-reports__loading { display: grid; gap: var(--erp-space-3); }
</style>

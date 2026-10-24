<template>
	<DepartmentPage title="Quality Reports" back-to="/quality" back-label="Quality" :show-title="false" flat full-width inline-navigation>
		<div class="quality-reports erp-workspace">
			<div v-if="loading" class="quality-reports__loading" aria-label="Loading Quality reports"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" message="You do not have permission to view Quality reports." :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" label="Quality reports" storage-key="quality" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"

import { getQualityCapabilities } from "../../api/quality.js"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"

const REPORTS = [
	{ key: "quality_inspection_rft", value: "quality-inspection-rft", label: "Quality Inspection RFT", icon: "pi pi-verified", component: DeskBackedReport, props: { reportKey: "quality-inspection-rft" } },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue")), capabilityProps: (report) => ({ canReadCuttingPlan: Boolean(report.can_read_cutting_plan) }) },
]

const loading = ref(true)
const loadError = ref("")
const capabilities = ref({ reports: {} })
const tabs = computed(() => REPORTS.filter((report) => capabilities.value.reports?.[report.key]?.can_read)
	.map((report) => ({ ...report, props: { ...report.props, ...report.capabilityProps?.(capabilities.value.reports[report.key]) } })))

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
.quality-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
.quality-reports__loading { display: grid; gap: var(--erp-space-3); }
</style>

<template>
	<DepartmentPage :title="`${source.label} · Reports`" :back-to="source.path" :back-label="source.label" :show-title="false" flat full-width inline-navigation>
		<div class="merch-reports erp-workspace">
			<div v-if="loading" :aria-label="`Loading ${source.label} reports`"><Skeleton height="56px" /><Skeleton height="320px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<WorkspaceLoadError v-else-if="!tabs.length" title="Reports unavailable" :message="`You do not have permission to view ${source.label} reports.`" :retryable="false" />
			<ReportWorkspace v-else :reports="tabs" :label="`${source.label} reports`" :storage-key="department" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onMounted, ref } from "vue"
import { getMerchCapabilities, getMerchPurchaseCapabilities } from "../../api/merch.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import { merchReportTabs } from "../departmentReports.js"
import { departments } from "../registry.js"

const COMPONENTS = {
	work_in_progress: defineAsyncComponent(() => import("./reports/WorkInProgressReport.vue")),
	inward_quantity: defineAsyncComponent(() => import("../planning/reports/InwardQuantityReport.vue")),
	work_order: defineAsyncComponent(() => import("../planning/reports/WorkOrderReport.vue")),
	planning_work_in_progress: defineAsyncComponent(() => import("../planning/reports/WorkInProgressReport.vue")),
	size_wise_stock: defineAsyncComponent(() => import("../planning/reports/SizeWiseStockReport.vue")),
	multi_ccr: defineAsyncComponent(() => import("../cutting/reports/MultiCCRReport.vue")),
	ppo_report: defineAsyncComponent(() => import("../sales/PpoReport.vue")),
	stock_balance: defineAsyncComponent(() => import("../../components/reports/StockBalanceReport.vue")),
	lot_cut_quantity: defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue")),
}
const LOADERS = { merch: getMerchCapabilities, "merch-purchase": getMerchPurchaseCapabilities }
const props = defineProps({ department: { type: String, default: "merch" } })
const source = { ...departments.find((item) => item.key === props.department), load: LOADERS[props.department] }
const loading = ref(true)
const loadError = ref("")
const reports = ref({})
const tabs = computed(() => merchReportTabs(props.department, reports.value).map((tab) => ({ ...tab, component: COMPONENTS[tab.key] || DeskBackedReport })))
async function load() {
	loading.value = true
	loadError.value = ""
	try {
		reports.value = (await source.load())?.reports || {}
	} catch (reason) {
		reports.value = {}
		loadError.value = reason?.message || `Unable to load ${source.label} reports.`
	} finally {
		loading.value = false
	}
}
onMounted(load)
</script>

<style scoped>
.merch-reports { display: grid; min-width: 0; gap: var(--erp-space-2); padding-top: var(--erp-space-2); }
</style>

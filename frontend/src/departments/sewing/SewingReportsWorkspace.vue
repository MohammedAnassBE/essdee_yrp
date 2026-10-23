<template>
	<section data-sewing-destination="reports" class="sewing-reports-workspace" aria-label="Sewing Reports workspace">
		<ReportWorkspace :reports="tabs" label="Sewing reports" query-key="tab" storage-key="sewing" v-slot="{ report }">
			<Message v-if="!isAllowed(report)" severity="warn" :closable="false">You do not have permission to view this report.</Message>
			<SewingStatusSummary v-else-if="report.value === 'status-summary'" :filters="statusFilters" />
			<SewingDpr v-else-if="report.value === 'dpr'" :filters="dprFilters" />
			<SewingScr v-else-if="report.value === 'scr'" :filters="scrFilters" />
			<SewingMonthlySummary v-else-if="report.value === 'monthly-summary'" :filters="monthlyFilters" />
			<SewingItemSummary v-else-if="report.value === 'item-summary'" :filters="itemFilters" />
			<FinishingDispatchReport v-else-if="report.value === 'finishing-dispatch'" />
			<LotCutQuantityReport v-else-if="report.value === 'lot-cut-quantity'" :can-read-cutting-plan="Boolean(props.capabilities.reports?.lot_cut_quantity?.can_read_cutting_plan)" />
			<InhouseQuantityReport v-else-if="report.value === 'inhouse-quantity'" />
			<DeskBackedReport v-else :report-key="report.value" :supplier="report.value === 'finishing-inward-updates' ? supplier : ''" />
		</ReportWorkspace>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { computed, defineAsyncComponent, reactive } from "vue"
import { useRoute } from "vue-router"

import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import { useSewingContext } from "./useSewingContext.js"

const { supplier } = useSewingContext()
const SewingStatusSummary = defineAsyncComponent(() => import("./reports/SewingStatusSummary.vue"))
const SewingDpr = defineAsyncComponent(() => import("./reports/SewingDpr.vue"))
const SewingScr = defineAsyncComponent(() => import("./reports/SewingScr.vue"))
const SewingMonthlySummary = defineAsyncComponent(() => import("./reports/SewingMonthlySummary.vue"))
const SewingItemSummary = defineAsyncComponent(() => import("./reports/SewingItemSummary.vue"))
const FinishingDispatchReport = defineAsyncComponent(() => import("../finishing/reports/FinishingDispatchReport.vue"))
const LotCutQuantityReport = defineAsyncComponent(() => import("../../components/reports/LotCutQuantityReport.vue"))
const InhouseQuantityReport = defineAsyncComponent(() => import("../planning/reports/InhouseQuantityReport.vue"))
const props = defineProps({ capabilities: { type: Object, required: true } })
const route = useRoute()
const REPORTS = [
	{ value: "status-summary", key: "status_summary", label: "Status Summary" },
	{ value: "dpr", key: "dpr", label: "DPR" },
	{ value: "scr", key: "scr", label: "SCR" },
	{ value: "monthly-summary", key: "monthly_summary", label: "Monthly Summary" },
	{ value: "item-summary", key: "item_summary", label: "Item Summary" },
	{ value: "finishing-dispatch", key: "finishing_dispatch", label: "Finishing Plan Dispatch" },
	{ value: "lot-cut-quantity", key: "lot_cut_quantity", label: "Lot Cut Quantity" },
	{ value: "inhouse-quantity", key: "inhouse_quantity", label: "In-house Quantity" },
]
const deskTabs = computed(() => departmentDeskReports(route.path.split("/")[1], props.capabilities.reports))
const tabs = computed(() => [...REPORTS.filter(tab => props.capabilities.reports?.[tab.key]?.can_read), ...deskTabs.value])
function isAllowed(report) {
	const capability = props.capabilities.reports?.[report.key]
	return capability?.can_read && capability?.can_report
}
// Only filters survive report switches. Business rows remain owned by the active
// report; a Supplier change remounts this workspace and clears its local state.
const statusFilters = reactive({ lot: [], item: [], colour: [], part: [], fromDate: "", toDate: "" })
const dprFilters = reactive({ mode: "daily", date: "", fromDate: "", toDate: "", workStation: "", inputType: "", lot: "", item: "" })
const scrFilters = reactive({ lot: "", colours: [] })
const monthlyFilters = reactive({ fromDate: "", toDate: "", inputType: "", showGrn: false })
const itemFilters = reactive({ lots: [], items: [] })
</script>

<style scoped>
.sewing-reports-workspace { min-width: 0; max-width: 100%; padding-top: var(--erp-space-2); }
@media (max-width: 430px) {
	.sewing-reports-workspace :deep(.report-filter-grid .erp-date-time-field) { grid-column: 1 / -1; }
	.sewing-reports-workspace :deep(.report-shell__commands) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.sewing-reports-workspace :deep(.report-shell__commands .p-button:first-child) { grid-column: 1 / -1; }
	.sewing-reports-workspace :deep(.report-shell__commands .p-button) { width: 100%; min-width: 0; min-height: 44px; }
}
</style>

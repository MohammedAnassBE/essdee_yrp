<template>
	<section class="cut-panel-store-reports" aria-label="Cut Panel Store reports">
		<ReportWorkspace v-if="visibleTabs.length" :reports="visibleTabs" label="Cut Panel Store reports" storage-key="cut-panel-store" keep-alive />
		<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { computed } from "vue"

import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"
import { cutPanelReportTabs } from "../departmentReports.js"
import CutBundleBalanceReport from "./CutBundleBalanceReport.vue"

const props = defineProps({ capability: { type: Object, default: () => ({}) } })
const COMPONENTS = { stock_balance: StockBalanceReport, cut_bundle_balance: CutBundleBalanceReport }
const visibleTabs = computed(() => cutPanelReportTabs(props.capability?.reports).map((tab) => ({ ...tab, component: COMPONENTS[tab.key] || DeskBackedReport })))
</script>

<style scoped>
.cut-panel-store-reports { min-width: 0; padding-top: var(--erp-space-2); }
</style>

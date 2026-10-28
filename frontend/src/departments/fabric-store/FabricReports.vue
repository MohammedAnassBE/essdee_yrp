<template>
	<section class="fabric-reports" aria-label="Reports">
		<ReportWorkspace v-if="visibleTabs.length" :reports="visibleTabs" :storage-key="department" keep-alive />
		<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { computed } from "vue"

import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import LotCutQuantityReport from "../../components/reports/LotCutQuantityReport.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"
import { storeReportTabs } from "../departmentReports.js"

const props = defineProps({
	capability: { type: Object, default: () => ({}) },
	department: { type: String, default: "fabric-store" },
	reportKeys: { type: Array, default: () => ["stock_balance"] },
})
const COMPONENTS = { stock_balance: StockBalanceReport, lot_cut_quantity: LotCutQuantityReport }
const visibleTabs = computed(() => storeReportTabs(props.capability?.reports, props.department, props.reportKeys)
	.map((tab) => ({ ...tab, component: COMPONENTS[tab.key] || DeskBackedReport })))
</script>

<style scoped>
.fabric-reports {
	display: grid;
	min-width: 0;
	gap: var(--erp-space-2);
	padding-top: var(--erp-space-2);
}
</style>

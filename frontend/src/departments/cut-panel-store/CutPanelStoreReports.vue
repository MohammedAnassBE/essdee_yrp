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
import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"
import CutBundleBalanceReport from "./CutBundleBalanceReport.vue"

const props = defineProps({ capability: { type: Object, default: () => ({}) } })
const tabs = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
	{ key: "cut_bundle_balance", value: "cut-bundle-balance", label: "Cut Bundle Balance", icon: "pi pi-box", component: CutBundleBalanceReport },
]
const deskTabs = computed(() => departmentDeskReports("cut-panel-store", props.capability?.reports).map((tab) => ({ ...tab, component: DeskBackedReport })))
const visibleTabs = computed(() => [...tabs.filter((tab) => props.capability?.reports?.[tab.key]?.can_read), ...deskTabs.value])
</script>

<style scoped>
.cut-panel-store-reports { min-width: 0; padding-top: var(--erp-space-2); }
</style>

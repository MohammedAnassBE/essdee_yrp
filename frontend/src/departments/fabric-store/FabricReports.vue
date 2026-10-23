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
import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"
import LotCutQuantityReport from "../../components/reports/LotCutQuantityReport.vue"
import ReportWorkspace from "../../components/reports/ReportWorkspace.vue"
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"

const props = defineProps({
	capability: { type: Object, default: () => ({}) },
	department: { type: String, default: "fabric-store" },
	reportKeys: { type: Array, default: () => ["stock_balance"] },
})
const tabs = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: LotCutQuantityReport },
]
const deskTabs = computed(() => departmentDeskReports(props.department, props.capability?.reports, props.reportKeys.some(key => props.capability?.reports?.[key]?.can_read)).map(tab => ({ ...tab, component: DeskBackedReport })))
const visibleTabs = computed(() => [...tabs.filter((tab) => (
	props.reportKeys.includes(tab.key) && props.capability?.reports?.[tab.key]?.can_read
)).map((tab) => ({
	...tab,
	props: tab.key === "lot_cut_quantity" ? {
		canReadCuttingPlan: Boolean(props.capability?.reports?.[tab.key]?.can_read_cutting_plan),
	} : {},
})), ...deskTabs.value])
</script>

<style scoped>
.fabric-reports {
	display: grid;
	min-width: 0;
	gap: var(--erp-space-2);
	padding-top: var(--erp-space-2);
}
</style>

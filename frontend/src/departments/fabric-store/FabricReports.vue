<template>
	<section class="fabric-reports" aria-label="Reports">
		<component :is="visibleTabs[0].component" v-if="visibleTabs.length === 1" v-bind="visibleTabs[0].componentProps" />
		<Tabs v-else-if="visibleTabs.length > 1" v-model:value="activeTab" class="erp-tabs fabric-reports__tabs">
			<TabList class="fabric-reports__tab-list">
				<Tab v-for="tab in visibleTabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" /><span>{{ tab.label }}</span></Tab>
			</TabList>
			<TabPanels class="fabric-reports__panels">
				<TabPanel v-for="tab in visibleTabs" :key="tab.value" :value="tab.value"><component :is="tab.component" v-bind="tab.componentProps" /></TabPanel>
			</TabPanels>
		</Tabs>
		<Message v-else severity="warn" :closable="false">You do not have permission to view these reports.</Message>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, ref, watch } from "vue"

import DeskBackedReport from "../../components/reports/DeskBackedReport.vue"
import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"
import LotCutQuantityReport from "../../components/reports/LotCutQuantityReport.vue"
import PurchaseOrderItemwiseReport from "../../components/reports/PurchaseOrderItemwiseReport.vue"
import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"

const props = defineProps({
	capability: { type: Object, default: () => ({}) },
	department: { type: String, default: "fabric-store" },
	reportKeys: { type: Array, default: () => ["stock_balance"] },
})
const activeTab = ref("")
const tabs = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
	{ key: "purchase_order_itemwise", value: "purchase-order-itemwise", label: "Purchase Order Itemwise", icon: "pi pi-shopping-cart", component: PurchaseOrderItemwiseReport },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: LotCutQuantityReport },
]
const deskTabs = computed(() => departmentDeskReports(props.department, props.capability?.reports, tabs.some(tab => props.reportKeys.includes(tab.key) && props.capability?.reports?.[tab.key]?.can_read)).map(tab => ({ ...tab, component: DeskBackedReport })))
const visibleTabs = computed(() => [...tabs.filter((tab) => (
	props.reportKeys.includes(tab.key) && props.capability?.reports?.[tab.key]?.can_read
)).map((tab) => ({
	...tab,
	componentProps: tab.key === "lot_cut_quantity" ? {
		canReadCuttingPlan: Boolean(props.capability?.reports?.[tab.key]?.can_read_cutting_plan),
	} : {},
})), ...deskTabs.value])

watch(visibleTabs, (available) => {
	if (!available.some((tab) => tab.value === activeTab.value)) activeTab.value = available[0]?.value || ""
}, { immediate: true })
</script>

<style scoped>
.fabric-reports {
	display: grid;
	min-width: 0;
	gap: var(--erp-space-2);
}

.fabric-reports__tabs {
	min-width: 0;
}

.fabric-reports__tab-list {
	position: sticky;
	z-index: var(--erp-layer-sticky);
	top: var(--erp-shell-header-height);
	background: var(--erp-bg);
}

.fabric-reports__tabs :deep(.p-tab) {
	display: inline-flex;
	min-height: 44px;
	align-items: center;
	gap: 7px;
	padding: 10px 14px;
	font-size: 13px;
}

.fabric-reports__panels {
	padding: var(--erp-space-3) 0 0;
	background: transparent;
}

.fabric-reports__panels :deep(.p-tabpanel) {
	padding: 0;
}

@media (max-width: 600px) {
	.fabric-reports__tab-list {
		overflow-x: auto;
		overscroll-behavior-x: contain;
	}

	.fabric-reports__tabs :deep(.p-tab) {
		padding: 9px 10px;
	}

	.fabric-reports__panels {
		padding-top: var(--erp-space-2);
	}
}
</style>

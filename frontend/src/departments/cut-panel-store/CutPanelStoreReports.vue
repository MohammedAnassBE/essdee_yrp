<template>
	<section class="cut-panel-store-reports" aria-label="Cut Panel Store reports">
		<Tabs v-if="visibleTabs.length" v-model:value="activeTab" class="erp-tabs cut-panel-store-reports__tabs">
			<TabList class="cut-panel-store-reports__tab-list">
				<Tab v-for="tab in visibleTabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" /><span>{{ tab.label }}</span></Tab>
			</TabList>
			<TabPanels class="cut-panel-store-reports__panels">
				<TabPanel v-if="hasReport('stock_balance')" value="stock-balance"><StockBalanceReport /></TabPanel>
				<TabPanel v-if="hasReport('cut_bundle_balance')" value="cut-bundle-balance"><CutBundleBalanceReport /></TabPanel>
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

import StockBalanceReport from "../../components/reports/StockBalanceReport.vue"
import CutBundleBalanceReport from "./CutBundleBalanceReport.vue"

const props = defineProps({ capability: { type: Object, default: () => ({}) } })
const activeTab = ref("")
const tabs = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "cut_bundle_balance", value: "cut-bundle-balance", label: "Cut Bundle Balance", icon: "pi pi-box" },
]
const visibleTabs = computed(() => tabs.filter((tab) => hasReport(tab.key)))

function hasReport(key) {
	return Boolean(props.capability?.reports?.[key]?.can_read)
}

watch(visibleTabs, (available) => {
	if (!available.some((tab) => tab.value === activeTab.value)) activeTab.value = available[0]?.value || ""
}, { immediate: true })
</script>

<style scoped>
.cut-panel-store-reports{min-width:0}.cut-panel-store-reports__tabs{min-width:0}.cut-panel-store-reports__tab-list{position:sticky;z-index:var(--erp-layer-sticky);top:var(--erp-shell-header-height);background:var(--erp-bg)}.cut-panel-store-reports__tabs :deep(.p-tab){display:inline-flex;align-items:center;gap:7px;padding:10px 14px;font-size:13px}.cut-panel-store-reports__panels{padding:12px 0 0;background:transparent}.cut-panel-store-reports__panels :deep(.p-tabpanel){padding:0}
@media(max-width:600px){.cut-panel-store-reports__tabs :deep(.p-tab){min-height:44px;padding:9px 10px}.cut-panel-store-reports__tab-list{overflow-x:auto;overscroll-behavior-x:contain}.cut-panel-store-reports__panels{padding-top:8px}}
</style>

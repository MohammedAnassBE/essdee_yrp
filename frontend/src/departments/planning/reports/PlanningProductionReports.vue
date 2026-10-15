<template>
	<section class="planning-production" aria-label="Production / WIP reports">
		<Message v-if="!tabs.length" severity="warn" :closable="false">You do not have permission to view Production / WIP reports.</Message>
		<template v-else>
			<div class="planning-production__mobile common-field">
				<label for="planning-production-report">Report</label>
				<Select input-id="planning-production-report" v-model="active" :options="tabs" option-label="label" option-value="value" fluid />
			</div>
			<Tabs v-model:value="active" scrollable class="erp-tabs">
				<TabList class="planning-production__desktop">
					<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value"><i :class="tab.icon" aria-hidden="true" /><span>{{ tab.label }}</span></Tab>
				</TabList>
				<TabPanels class="planning-production__panels">
					<TabPanel :key="active" :value="active"><component :is="currentTab.component" v-bind="currentTab.key === 'work_order_bulk_close' ? { permissions: reports[currentTab.key] } : {}" /></TabPanel>
				</TabPanels>
			</Tabs>
		</template>
	</section>
</template>

<script setup>
import Message from "primevue/message"
import Select from "primevue/select"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, defineAsyncComponent, provide } from "vue"
import { useRoute, useRouter } from "vue-router"
import { pageNavigationKey, usePageNavigation } from "../../../components/navigation/pageNavigationContext.js"
import { visibleProductionReports } from "../planningViews.js"
import "../../finishing/finishing.css"

const props = defineProps({ reports: { type: Object, default: () => ({}) } })
const navigation = usePageNavigation()
provide(pageNavigationKey, { ...navigation, inline: computed(() => false) })
const components = {
	work_order: defineAsyncComponent(() => import("./WorkOrderReport.vue")),
	dispatch_percentage: defineAsyncComponent(() => import("./DispatchPercentageReport.vue")),
	work_order_pending: defineAsyncComponent(() => import("./WorkOrderPendingReport.vue")),
	finishing_plan: defineAsyncComponent(() => import("../../finishing/reports/FinishingPlanReport.vue")),
	inward_quantity: defineAsyncComponent(() => import("./InwardQuantityReport.vue")),
	inhouse_quantity: defineAsyncComponent(() => import("./InhouseQuantityReport.vue")),
	month_wise_detail: defineAsyncComponent(() => import("./MonthWiseDetailReport.vue")),
	process_pending: defineAsyncComponent(() => import("./ProcessPendingReport.vue")),
	size_wise_stock: defineAsyncComponent(() => import("./SizeWiseStockReport.vue")),
	colour_wise_diff: defineAsyncComponent(() => import("./ColourWiseDiffReport.vue")),
	work_in_progress: defineAsyncComponent(() => import("./WorkInProgressReport.vue")),
	work_order_bulk_close: defineAsyncComponent(() => import("./WorkOrderBulkClose.vue")),
}
const route = useRoute()
const router = useRouter()
const tabs = computed(() => visibleProductionReports(props.reports).map((report) => ({ ...report, component: components[report.key] })))
const active = computed({
	get: () => tabs.value.some((tab) => tab.value === route.query.report) ? route.query.report : tabs.value[0]?.value,
	set: (report) => router.replace({ query: { ...route.query, report } }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])
</script>

<style scoped>
.planning-production { min-width: 0; padding: 0 0 var(--erp-space-5); }
.planning-production__desktop, .planning-production__mobile { position: sticky; top: calc(var(--erp-shell-header-height) + var(--planning-reports-sticky-offset, 0px)); z-index: var(--erp-layer-sticky); background: var(--erp-bg); }
.planning-production__desktop :deep(.p-tab) { display: inline-flex; align-items: center; gap: var(--erp-space-2); }
.planning-production__panels { padding: var(--erp-space-3) 0 0; background: transparent; }
.planning-production__panels :deep(.p-tabpanel) { padding: 0; }
.planning-production__mobile { display: none; }
@media (max-width: 700px) {
	.planning-production__desktop { display: none; }
	.planning-production__mobile { display: grid; gap: var(--erp-space-2); }
}
</style>

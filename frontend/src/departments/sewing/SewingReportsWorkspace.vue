<template>
	<section data-sewing-destination="reports" class="sewing-reports-workspace" aria-label="Sewing Reports workspace">
		<div class="sewing-reports-workspace__mobile common-field">
			<label for="sewing-report-view">Report view</label>
			<Select input-id="sewing-report-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Report view" fluid />
		</div>
		<Tabs v-model:value="active" class="erp-tabs">
			<TabList class="sewing-reports-workspace__desktop"><Tab v-for="tab in tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</Tab></TabList>
			<TabPanels><TabPanel :value="active" :key="active">
				<Message v-if="!allowed" severity="warn" :closable="false">You do not have permission to view this report.</Message>
				<SewingStatusSummary v-else-if="active === 'status-summary'" :filters="statusFilters" />
				<SewingDpr v-else-if="active === 'dpr'" :filters="dprFilters" />
				<SewingScr v-else-if="active === 'scr'" :filters="scrFilters" />
				<SewingMonthlySummary v-else-if="active === 'monthly-summary'" :filters="monthlyFilters" />
				<SewingItemSummary v-else-if="active === 'item-summary'" :filters="itemFilters" />
			</TabPanel></TabPanels>
		</Tabs>
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
import { computed, defineAsyncComponent, reactive } from "vue"
import { useRoute, useRouter } from "vue-router"

const SewingStatusSummary = defineAsyncComponent(() => import("./reports/SewingStatusSummary.vue"))
const SewingDpr = defineAsyncComponent(() => import("./reports/SewingDpr.vue"))
const SewingScr = defineAsyncComponent(() => import("./reports/SewingScr.vue"))
const SewingMonthlySummary = defineAsyncComponent(() => import("./reports/SewingMonthlySummary.vue"))
const SewingItemSummary = defineAsyncComponent(() => import("./reports/SewingItemSummary.vue"))
const props = defineProps({ capabilities: { type: Object, required: true } })
const route = useRoute(), router = useRouter()
const tabs = [
	{ value: "status-summary", key: "status_summary", label: "Status Summary" },
	{ value: "dpr", key: "dpr", label: "DPR" },
	{ value: "scr", key: "scr", label: "SCR" },
	{ value: "monthly-summary", key: "monthly_summary", label: "Monthly Summary" },
	{ value: "item-summary", key: "item_summary", label: "Item Summary" },
]
const active = computed({
	get: () => tabs.some(tab => tab.value === route.query.tab) ? route.query.tab : "status-summary",
	set: tab => router.replace({ query: { ...route.query, tab }, hash: route.hash }),
})
const allowed = computed(() => {
	const capability = props.capabilities.reports?.[tabs.find(tab => tab.value === active.value).key]
	return capability?.can_read && capability?.can_report
})
// Only filters survive tab switches. Business rows remain owned by the active
// report; a Supplier change remounts this workspace and clears its local state.
const statusFilters = reactive({ lot: [], item: [], colour: [], part: [], fromDate: "", toDate: "" })
const dprFilters = reactive({ mode: "daily", date: "", fromDate: "", toDate: "", workStation: "", inputType: "" })
const scrFilters = reactive({ lot: "", colours: [] })
const monthlyFilters = reactive({ fromDate: "", toDate: "", inputType: "", showGrn: false })
const itemFilters = reactive({ lots: [], items: [] })
</script>

<style scoped>
.sewing-reports-workspace { min-width: 0; max-width: 100%; }
.sewing-reports-workspace :deep(.p-tabpanels) { background: transparent; padding: 8px 0 0; }
.sewing-reports-workspace :deep(.p-tab) { min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.sewing-reports-workspace__mobile { display: none; }
@media (max-width: 700px) {
	.sewing-reports-workspace__desktop { display: none; }
	.sewing-reports-workspace__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
}
@media (max-width: 430px) {
	.sewing-reports-workspace :deep(.report-filter-grid .erp-date-time-field) { grid-column: 1 / -1; }
	.sewing-reports-workspace :deep(.report-shell__commands) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.sewing-reports-workspace :deep(.report-shell__commands .p-button:first-child) { grid-column: 1 / -1; }
	.sewing-reports-workspace :deep(.report-shell__commands .p-button) { width: 100%; min-width: 0; min-height: 44px; }
}
</style>

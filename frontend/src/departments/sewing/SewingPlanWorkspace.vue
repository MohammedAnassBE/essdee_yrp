<template>
	<section data-sewing-destination="plans" class="sewing-plan-workspace" aria-label="Sewing Plan workspace">
		<div class="sewing-plan-workspace__mobile common-field">
			<label for="sewing-plan-view">Plan view</label>
			<Select input-id="sewing-plan-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Plan view" fluid />
		</div>
		<Tabs v-model:value="active" class="erp-tabs">
			<TabList class="sewing-plan-workspace__desktop">
				<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</Tab>
			</TabList>
			<TabPanels>
				<TabPanel :value="active" :key="active">
					<SewingDashboard v-if="active === 'dashboard'" />
					<SewingDataEntry v-else-if="active === 'data-entry'" :filters="entryFilters" :actions="capabilities.plan_actions" />
					<div v-else :data-sewing-plan-tab="active" class="erp-empty-state" role="status">{{ tabs.find(tab => tab.value === active).label }} is not loaded yet.</div>
				</TabPanel>
			</TabPanels>
		</Tabs>
	</section>
</template>

<script setup>
import Select from "primevue/select"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, defineAsyncComponent, reactive } from "vue"
import { useRoute, useRouter } from "vue-router"

const SewingDashboard = defineAsyncComponent(() => import("./plan/SewingDashboard.vue"))
const SewingDataEntry = defineAsyncComponent(() => import("./plan/SewingDataEntry.vue"))
defineProps({ capabilities: { type: Object, default: () => ({}) } })
const route = useRoute(), router = useRouter()
const tabs = [
	{ value: "dashboard", label: "Dashboard" },
	{ value: "data-entry", label: "Data Entry" },
	{ value: "entries", label: "Entries" },
	{ value: "consumption", label: "Consumption" },
	{ value: "closed-work-order-grn", label: "Closed Work Order GRN" },
]
const active = computed({
	get: () => tabs.some(tab => tab.value === route.query.tab) ? route.query.tab : "dashboard",
	set: tab => router.replace({ query: { ...route.query, tab }, hash: route.hash }),
})
// Only filter values survive an inactive tab; business records belong to its view.
const entryFilters = reactive({ lot: "", plan: "", inputType: "", workStation: "", receivedType: "", date: "", time: "", inspectionType: "pre_final" })
</script>

<style scoped>
.sewing-plan-workspace { min-width: 0; max-width: 100%; }
.sewing-plan-workspace :deep(.p-tabpanels) { background: transparent; padding: 14px 0 0; }
.sewing-plan-workspace :deep(.p-tab) { min-height: 44px; padding: 10px 14px; font-size: var(--erp-font-size-caption); white-space: nowrap; }
.sewing-plan-workspace__mobile { display: none; }
@media (max-width: 700px) {
	.sewing-plan-workspace__desktop { display: none; }
	.sewing-plan-workspace__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
}
</style>

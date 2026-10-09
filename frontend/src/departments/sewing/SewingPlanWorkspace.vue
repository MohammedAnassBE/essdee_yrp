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
					<SewingDataEntry v-else-if="active === 'data-entry'" :state="entryState" :filters="entryFilters" :actions="capabilities.plan_actions" :mutate="saveDataEntry" />
					<SewingEntries v-else-if="active === 'entries'" :state="entriesState" :mutate="cancelEntry" />
					<SewingConsumption v-else-if="active === 'consumption'" :state="consumptionState" :actions="capabilities.plan_actions" :mutate="saveConsumption" />
					<SewingClosedWorkOrderGrn v-else-if="active === 'closed-work-order-grn'" :state="closedGrnState" :actions="capabilities.plan_actions" :mutate="createClosedGrn" />
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
import { cancelSewingEntry, createClosedWorkOrderGrn, saveSewingConsumption, submitSewingDataEntry, updateSewingInspection } from "../../api/sewing.js"
import { useSewingContext } from "./useSewingContext.js"

const SewingDashboard = defineAsyncComponent(() => import("./plan/SewingDashboard.vue"))
const SewingDataEntry = defineAsyncComponent(() => import("./plan/SewingDataEntry.vue"))
const SewingEntries = defineAsyncComponent(() => import("./plan/SewingEntries.vue"))
const SewingConsumption = defineAsyncComponent(() => import("./plan/SewingConsumption.vue"))
const SewingClosedWorkOrderGrn = defineAsyncComponent(() => import("./plan/SewingClosedWorkOrderGrn.vue"))
defineProps({ capabilities: { type: Object, default: () => ({}) } })
const route = useRoute(), router = useRouter()
const { supplier, beginRequest } = useSewingContext()
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
const entryFilters = reactive({ lot: "", plan: "", inputType: "", workStation: "", receivedType: "", date: "", time: "", inspectionType: "pre_final" })
const entryState = reactive({ response: {}, loaded: false, entryDrafts: {}, inspectionDrafts: {}, attempted: false, success: "", error: "", loadError: "", busy: false, refreshRequired: false, operationVersion: 0, operation: null })
// The Supplier-keyed shell retains local filters and consumption drafts without
// mounting inactive tabs. Mutation locks and recovery survive a tab switch too.
const entriesState = reactive({ filters: { workStation: "", inputType: "", lot: "" }, busy: false, refreshRequired: false, operationVersion: 0, operation: null })
const consumptionState = reactive({ lot: "", data: null, busy: false, refreshRequired: false, loadError: "", operationVersion: 0, operation: null })
const closedGrnState = reactive({ workOrder: "", data: null, values: {}, namingField: null, busy: false, refreshRequired: false, loadError: "", result: null, operationVersion: 0, operation: null })

// The Supplier-keyed shell owns the entire write lifetime. Tab unmounts may
// invalidate reads, but must not discard a write's acknowledgement or failure.
// No read is performed here: only the mounted affected view may refresh.
async function mutate(state, identity, request, fallback) {
	if (state.busy || state.refreshRequired) return
	const version = ++state.operationVersion
	beginRequest()
	state.busy = true
	state.operation = { ...identity, version, status: "pending", error: "", acknowledged: false, noticeShown: false }
	try {
		await request()
		if (state.operation?.version !== version) return
		state.refreshRequired = true
		state.operation.status = "succeeded"
	} catch (reason) {
		if (state.operation?.version !== version) return
		state.operation.error = reason.message || fallback
		if (identity.recoverRejection) state.refreshRequired = true
		state.operation.status = "rejected"
	} finally { if (state.operation?.version === version) state.busy = false }
}
function saveDataEntry(payload, message, resetEntry = false) {
	entryState.error = ""; entryState.success = ""
	return mutate(entryState, { kind: resetEntry ? "entry" : "inspection", supplier: payload.supplier, plan: payload.plan, lot: payload.lot, message, recoverRejection: true }, async () => {
		await (resetEntry ? submitSewingDataEntry(payload) : updateSewingInspection(payload))
		if (resetEntry) entryState.entryDrafts[payload.plan] = {}
	}, "Unable to save Sewing quantities.")
}
function cancelEntry(docId) {
	return mutate(entriesState, { kind: "cancel", supplier: supplier.value, docId }, () => cancelSewingEntry(docId), "Unable to cancel this entry.")
}
function saveConsumption(payload) {
	return mutate(consumptionState, { kind: "consumption", supplier: payload.supplier, lot: payload.lot }, () => saveSewingConsumption(payload.supplier, payload.lot, payload.sections, payload.cloth_acc_data), "Unable to save consumption.")
}
function createClosedGrn(payload) {
	return mutate(closedGrnState, { kind: "closed-grn", supplier: payload.supplier, workOrder: payload.work_order }, async () => {
		const result = await createClosedWorkOrderGrn(payload)
		// Acknowledgement belongs to the shell, including after the editor unmounts.
		closedGrnState.result = result
		closedGrnState.workOrder = ""
		closedGrnState.data = null
		closedGrnState.values = {}
	}, "Unable to create this Goods Received Note.")
}
</script>

<style scoped>
.sewing-plan-workspace { min-width: 0; max-width: 100%; }
.sewing-plan-workspace :deep(.p-tabpanels) { background: transparent; padding: 8px 0 0; }
.sewing-plan-workspace :deep(.p-tab) { min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.sewing-plan-workspace__mobile { display: none; }
@media (max-width: 700px) {
	.sewing-plan-workspace__desktop { display: none; }
	.sewing-plan-workspace__mobile { display: grid; gap: 6px; font-size: var(--erp-font-size-caption); font-weight: 650; }
}
</style>

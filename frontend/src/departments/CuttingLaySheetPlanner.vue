<template>
	<DepartmentPage title="LaySheet Planner" accent="#059669" back-to="/cutting/lay-sheet-planner" back-label="LaySheet Planner" :show-title="false" flat full-width>
		<div class="planner-workspace erp-workspace">
			<div v-if="loading && !payload.record" class="planner-workspace__loading"><Skeleton height="76px" /><Skeleton height="520px" /></div>
			<template v-else>
				<header class="planner-record-header erp-card">
					<div class="planner-record-identity">
						<div class="planner-record-title"><h1>LaySheet Planner</h1><span>{{ plannerName }}</span></div>
						<div class="planner-record-meta">
							<Tag :value="record.optimization_status || 'Not Started'" :severity="statusSeverity(record.optimization_status)" rounded />
							<span class="planner-header-fact planner-header-fact--lot" :title="record.lot || 'No Lot'"><small>Lot</small><strong>{{ record.lot || "—" }}</strong></span>
							<span class="planner-header-fact planner-header-fact--item" :title="record.item || 'No Item'"><small>Item</small><strong>{{ record.item || "—" }}</strong></span>
						</div>
					</div>
					<div class="planner-record-actions"><Button v-if="activeTab === 'inputs' && actions.can_edit_inputs" label="Save Inputs" icon="pi pi-save" severity="secondary" outlined :loading="saving" :disabled="saving || !plannerInputs?.canSave" @click="plannerInputs?.save()" /><Button v-if="actions.can_optimize" :label="actions.can_retry ? 'Retry Optimization' : results.successful?.length ? 'Re-optimize' : 'Optimize'" icon="pi pi-calculator" :loading="optimizing" @click="optimize" /><Button icon="pi pi-refresh" aria-label="Refresh LaySheet Plan" severity="secondary" text rounded :loading="loading" @click="load" /></div>
				</header>
				<Message v-if="error || optimizationFailure" severity="error" :closable="false">{{ error || optimizationFailure }}</Message>
				<Tabs v-model:value="activeTab" class="planner-tabs erp-card" :class="{ 'planner-tabs--plan': activeTab === 'plan' }">
					<TabList><Tab value="inputs">Inputs</Tab><Tab value="plan">Plan</Tab></TabList>
					<TabPanels>
						<TabPanel value="inputs"><PlannerInputs ref="plannerInputs" :record="record" :editable="actions.can_edit_inputs" :saving="saving" @save="saveInputs" /></TabPanel>
						<TabPanel value="plan">
							<PlannerPlanWorkspace
								:successful="results.successful"
								:failed="results.failed"
								:selected="record.selected_strategy"
								:result="selectedResult"
								:tolerance="Number(record.tolerance_pct || 3)"
								:can-select="actions.can_select_result"
								:selecting="selecting"
								@select="selectStrategy"
							/>
						</TabPanel>
					</TabPanels>
				</Tabs>
			</template>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import Tag from "primevue/tag"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute } from "vue-router"

import { getLaySheetOptimizationStatus, getLaySheetPlannerEditor, saveLaySheetPlanner, selectLaySheetStrategy, startLaySheetOptimization } from "../api/cuttingLaySheetPlanner.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import PlannerInputs from "./cutting/planner/PlannerInputs.vue"
import PlannerPlanWorkspace from "./cutting/planner/PlannerPlanWorkspace.vue"

const route = useRoute()
const plannerName = computed(() => String(route.params.plannerId || ""))
const payload = ref({})
const loading = ref(true)
const saving = ref(false)
const optimizing = ref(false)
const selecting = ref("")
const error = ref("")
const activeTab = ref("inputs")
const plannerInputs = ref(null)
let pollTimer = null
let loadSequence = 0
let disposed = false
let initializedPlanner = ""
const record = computed(() => payload.value.record || {})
const results = computed(() => payload.value.results || { successful: [], failed: [] })
const actions = computed(() => payload.value.actions || {})
const optimizationFailure = computed(() => record.value.optimization_status === "Failed" ? record.value.optimization_error || "No feasible lay plan was found." : "")
const selectedResult = computed(() => {
	const successful = results.value.successful || []
	const selected = record.value.selected_strategy
	const direct = successful.find((result) => result.strategy === selected)
	if (direct) return direct
	const duplicate = (results.value.failed || []).find((result) => result.strategy === selected && result.same_as)
	return successful.find((result) => result.strategy === duplicate?.same_as) || successful[0] || null
})

function stopPolling() { if (pollTimer) clearTimeout(pollTimer); pollTimer = null }
async function load() {
	stopPolling()
	const sequence = ++loadSequence; loading.value = true; error.value = ""
	try {
		const next = await getLaySheetPlannerEditor(plannerName.value)
		if (sequence !== loadSequence) return
		payload.value = next || {}
		if (initializedPlanner !== plannerName.value) {
			activeTab.value = next?.results?.successful?.length ? "plan" : "inputs"
			initializedPlanner = plannerName.value
		}
		if (next?.actions?.should_poll) schedulePoll(600)
	}
	catch (reason) { if (sequence === loadSequence) error.value = reason?.message || "Unable to load LaySheet Planner." }
	finally { if (sequence === loadSequence) loading.value = false }
}
async function saveInputs(values) {
	saving.value = true; error.value = ""
	try { payload.value = await saveLaySheetPlanner(values, { name: plannerName.value, expectedModified: record.value.modified }) }
	catch (reason) { error.value = reason?.message || "Unable to save Planner inputs." }
	finally { saving.value = false }
}
async function optimize() {
	if (optimizing.value || !actions.value.can_optimize) return
	optimizing.value = true; error.value = ""
	try {
		const status = await startLaySheetOptimization(plannerName.value, record.value.modified)
		applyStatus(status); activeTab.value = "plan"
		if (status?.actions?.should_poll || ["Queued", "Running"].includes(status?.status)) schedulePoll(500)
	} catch (reason) { error.value = reason?.message || "Unable to start lay optimization." }
	finally { optimizing.value = false }
}
function schedulePoll(delay = 1000) { stopPolling(); pollTimer = setTimeout(poll, delay) }
async function poll() {
	pollTimer = null
	const planner = plannerName.value
	const sequence = loadSequence
	try {
		const status = await getLaySheetOptimizationStatus(planner)
		if (disposed || planner !== plannerName.value || sequence !== loadSequence) return
		applyStatus(status)
		if (status?.terminal || ["Completed", "Failed"].includes(status?.status)) { await load(); if (status.status === "Completed") activeTab.value = "plan"; return }
		if (status?.actions?.should_poll || ["Queued", "Running"].includes(status?.status)) schedulePoll(1000)
	} catch (reason) {
		if (disposed || planner !== plannerName.value || sequence !== loadSequence) return
		error.value = reason?.message || "Unable to refresh optimization status."
		schedulePoll(5000)
	}
}
function applyStatus(status) {
	if (!status) return
	payload.value = {
		...payload.value,
		record: { ...record.value, optimization_status: status.status || record.value.optimization_status, optimization_error: status.error_message || "", optimization_started_on: status.started_on ?? record.value.optimization_started_on, optimization_completed_on: status.completed_on ?? record.value.optimization_completed_on, modified: status.modified || record.value.modified },
		actions: { ...actions.value, ...(status.actions || {}) },
	}
}
async function selectStrategy(strategy) {
	selecting.value = strategy; error.value = ""
	try { payload.value = await selectLaySheetStrategy(plannerName.value, strategy, record.value.modified) }
	catch (reason) { error.value = reason?.message || "Unable to select this strategy." }
	finally { selecting.value = "" }
}
function statusSeverity(status) { if (status === "Completed") return "success"; if (status === "Failed") return "danger"; if (["Queued", "Running"].includes(status)) return "info"; return "secondary" }
watch(plannerName, () => { disposed = false; initializedPlanner = ""; activeTab.value = "inputs"; load() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; loadSequence += 1; stopPolling() })
</script>

<style scoped>
.planner-workspace { display: flex; width: 100%; max-width: 1900px; min-width: 0; height: calc(100dvh - var(--erp-shell-header-height) - 82px); margin: 0 auto; flex-direction: column; gap: 8px; overflow: hidden; }.planner-workspace__loading { display: grid; gap: 8px; }.planner-record-header { display: flex; min-height: 60px; padding: 8px 12px; flex: 0 0 auto; align-items: center; justify-content: space-between; gap: 12px; }.planner-record-identity, .planner-record-actions, .planner-record-meta { display: flex; min-width: 0; align-items: center; gap: 10px; }.planner-record-title { display: grid; gap: 2px; min-width: 0; }.planner-record-identity h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); letter-spacing: -.025em; }.planner-record-title > span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 600; }.planner-header-fact { display: grid; min-width: 100px; max-width: 220px; gap: 2px; padding-left: 11px; border-left: 1px solid var(--erp-border); }.planner-header-fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; line-height: 1; text-transform: uppercase; }.planner-header-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 730; text-overflow: ellipsis; white-space: nowrap; }
.planner-tabs { display: flex; min-height: 0; flex: 1; overflow: hidden; flex-direction: column; }.planner-tabs :deep(.p-tablist) { flex: 0 0 auto; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }.planner-tabs :deep(.p-tablist-tab-list) { padding: 0 12px; gap: 8px; background: transparent; border: 0; }.planner-tabs :deep(.p-tab) { min-height: 48px; padding: 0 11px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 680; }.planner-tabs :deep(.p-tab-active) { color: var(--erp-accent-dark); }.planner-tabs :deep(.p-tablist-active-bar) { height: 2px; background: var(--erp-accent); }.planner-tabs :deep(.p-tabpanels) { min-height: 0; padding: 0; flex: 1; overflow-y: auto; background: var(--erp-surface); }.planner-tabs :deep(.p-tabpanel) { min-height: 100%; }
.planner-tabs--plan :deep(.p-tabpanels), .planner-tabs--plan :deep(.p-tabpanel) { overflow: hidden; }
.planner-tabs--plan :deep(.p-tabpanel) { height: 100%; min-height: 0; }
@media (max-width: 700px) { .planner-tabs--plan :deep(.p-tabpanels) { overflow-y: auto; }.planner-tabs--plan :deep(.p-tabpanel) { height: auto; min-height: 100%; overflow: visible; } }
@media (max-width: 700px) { .planner-workspace { height: auto; min-height: calc(100dvh - var(--erp-shell-header-height) - 82px); overflow: visible; }.planner-record-header { align-items: flex-start; flex-direction: column; }.planner-tabs { min-height: 660px; }.planner-record-actions { width: 100%; } }
@media (max-width: 650px) { .planner-record-identity { align-items: flex-start; flex-direction: column; }.planner-record-meta { flex-wrap: wrap; }.planner-header-fact:first-of-type { padding-left: 0; border-left: 0; } }
</style>

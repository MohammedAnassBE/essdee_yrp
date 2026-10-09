<template>
	<section class="finishing-tabs" aria-label="Finishing Plan views">
		<div class="finishing-tabs__mobile common-field">
			<label for="finishing-plan-view">Plan view</label>
			<Select input-id="finishing-plan-view" v-model="active" :options="tabs" option-label="label" option-value="value" aria-label="Plan view" fluid />
		</div>
		<Tabs v-model:value="active" scrollable class="erp-tabs">
			<TabList class="finishing-tabs__desktop">
				<Tab v-for="tab in tabs" :key="tab.value" :value="tab.value">{{ tab.label }}</Tab>
			</TabList>
			<TabPanels>
				<TabPanel :key="active" :value="active">
					<div class="finishing-stack" :data-finishing-tab="active">
						<div v-if="tabEntries.length" class="finishing-tabs__toolbar" role="group" :aria-label="`${currentTab.label} actions`">
							<Button
								v-for="(action, index) in tabEntries"
								:key="action"
								:label="ENTRY_DEFINITIONS[action].label"
								:icon="index === 0 ? 'pi pi-plus' : undefined"
								:severity="index === 0 ? undefined : 'secondary'"
								:outlined="index !== 0"
								:disabled="busy"
								@click="emit('entry', action)"
							/>
						</div>
						<FinishingLinkedDocuments
							v-if="currentTab.linked"
							:groups="workspace.linked_documents || []"
							:keys="currentTab.linked"
							:can-cancel="Boolean(workspace.actions?.cancel_linked_document)"
							:busy="busy"
							@open="(doctype, name) => emit('open', doctype, name)"
							@cancel="(doctype, name) => emit('cancel', doctype, name)"
						/>
						<p v-if="active === 'incomplete-transfer' && !hasIncompleteTransfers" class="finishing-empty">No incomplete transfers.</p>
						<FinishingDispatchHistoryTab v-if="active === 'dispatch-history'" :logs="workspace.dispatch_logs || []" @open="(doctype, name) => emit('open', doctype, name)" />
						<template v-else-if="currentTab.source">
							<div v-if="entry.loading" class="finishing-stack" :aria-label="`Loading ${currentTab.label}`"><Skeleton height="40px" /><Skeleton height="220px" /></div>
							<WorkspaceLoadError v-else-if="entry.error" :title="`${currentTab.label} unavailable`" :message="entry.error" @retry="load(true)" />
							<template v-else-if="entry.data">
								<dl v-if="facts.length" class="finishing-facts">
									<div v-for="fact in facts" :key="fact.label"><dt>{{ fact.label }}</dt><dd>{{ fact.value }}</dd></div>
								</dl>
								<FinishingMatrix v-if="active === 'details'" :model="detailsMatrix(entry.data)" />
								<template v-else-if="active === 'item-details'">
									<FinishingMatrix title="Inward Details" :model="quantityMatrix(entry.data)" />
									<FinishingMatrix title="Rework Details" :model="reworkMatrix(entry.data)" empty-text="No rework quantities." />
								</template>
								<FinishingGrnTab v-else-if="active === 'grn'" :data="entry.data" />
								<FinishingMatrix v-else-if="active === 'inward'" :model="inwardMatrix(entry.data)" />
								<FinishingOldLotTab v-else-if="active === 'old-lot'" :data="entry.data" :can-transfer="Boolean(workspace.actions?.fetch_old_lot)" :busy="busy" @fetch="load(true)" @transfer="(transfers) => emit('transfer', transfers)" />
								<FinishingMatrix v-else-if="active === 'ironing-excess'" title="Ironing Excess Quantity" :model="singleMetricMatrix(entry.data, 'ironing')" />
								<FinishingMatrix v-else-if="active === 'pack-return'" title="Pack Returned Items" :model="singleMetricMatrix(entry.data, 'pack_returned_qty')" />
								<FinishingOcrTab v-else-if="active === 'ocr'" :name="name" :data="entry.data" />
								<FinishingProfitAndLossTab
									v-else-if="active === 'p-and-l'"
									:documents="entry.data.documents || []"
									:status="workspace.record?.fp_status || ''"
									:can-manage="Boolean(workspace.actions?.manage_p_and_l)"
									:busy="busy"
									@upload="(values) => emit('upload', values)"
									@delete="(document) => emit('delete-document', document)"
								/>
								<FinishingAlternativesTab v-else-if="active === 'alternatives'" :data="entry.data" />
								<FinishingRejectionTab v-else-if="active === 'rejection'" :data="entry.data" />
							</template>
						</template>
					</div>
				</TabPanel>
			</TabPanels>
		</Tabs>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, defineAsyncComponent, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getFinishingPlanTab } from "../../api/finishing.js"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { formatDate } from "../../components/reports/reportUtils.js"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import FinishingLinkedDocuments from "./components/FinishingLinkedDocuments.vue"
import FinishingMatrix from "./components/FinishingMatrix.vue"
import { ENTRY_DEFINITIONS } from "./finishingEntryDefinitions.js"
import { detailsMatrix, inwardMatrix, quantityMatrix, reworkMatrix, singleMetricMatrix } from "./finishingViews.js"

const FinishingGrnTab = defineAsyncComponent(() => import("./plan/FinishingGrnTab.vue"))
const FinishingOldLotTab = defineAsyncComponent(() => import("./plan/FinishingOldLotTab.vue"))
const FinishingDispatchHistoryTab = defineAsyncComponent(() => import("./plan/FinishingDispatchHistoryTab.vue"))
const FinishingOcrTab = defineAsyncComponent(() => import("./plan/FinishingOcrTab.vue"))
const FinishingProfitAndLossTab = defineAsyncComponent(() => import("./plan/FinishingProfitAndLossTab.vue"))
const FinishingAlternativesTab = defineAsyncComponent(() => import("./plan/FinishingAlternativesTab.vue"))
const FinishingRejectionTab = defineAsyncComponent(() => import("./plan/FinishingRejectionTab.vue"))

const props = defineProps({
	name: { type: String, required: true },
	workspace: { type: Object, required: true },
	version: { type: Number, default: 0 },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["open", "cancel", "upload", "delete-document", "entry", "transfer"])
const route = useRoute()
const router = useRouter()
const tabs = computed(() => [
	{ value: "details", label: "Details", source: "details" },
	{ value: "item-details", label: "Item Details", source: "item_details", linked: ["dc_list", "return_grn_list"], entries: ["create_delivery_challan", "return_items", "convert_to_loose_piece"] },
	{ value: "grn", label: "GRN", source: "grn", linked: ["grn_list", "stock_entry_list"], entries: ["create_grn", "dispatch_box"] },
	{ value: "inward", label: "Inward", source: "inward" },
	{ value: "old-lot", label: "Fetch From Old Lot", source: "old_lot", linked: ["lot_transfer_list"] },
	{ value: "dispatch-history", label: "Dispatch History" },
	{ value: "ironing-excess", label: "Ironing Excess", source: "ironing_excess", linked: ["ironing_excess_list"], entries: ["add_ironing_excess"] },
	{ value: "pack-return", label: "Pack Return", source: "pack_return", linked: ["pack_return_list"], entries: ["return_pack"] },
	{ value: "ocr", label: "OCR", source: "ocr" },
	...(props.workspace.actions?.view_p_and_l ? [{ value: "p-and-l", label: "P & L", source: "p_and_l" }] : []),
	{ value: "incomplete-transfer", label: "InComplete Transfer", linked: ["incomplete_transfer_dc_list", "incomplete_transfer_grn_list"] },
	{ value: "alternatives", label: "Alternatives", source: "alternatives" },
	{ value: "rejection", label: "Rejection", source: "rejection" },
])
const active = computed({
	get: () => (tabs.value.some((tab) => tab.value === route.query.tab) ? route.query.tab : "details"),
	set: (tab) => router.replace({ query: { ...route.query, tab }, hash: route.hash, state: preserveListNavigationState() }),
})
const currentTab = computed(() => tabs.value.find((tab) => tab.value === active.value) || tabs.value[0])
const tabEntries = computed(() => (props.workspace.actions?.create_entries ? currentTab.value.entries || [] : []))
const hasIncompleteTransfers = computed(() => (props.workspace.linked_documents || [])
	.some((group) => group.key.startsWith("incomplete_transfer") && group.documents.length))
const store = ref({})
const entry = computed(() => store.value[active.value] || { loading: true })
const facts = computed(() => {
	const record = props.workspace.record || {}
	if (active.value !== "inward") return []
	return [
		{ label: "Finishing Start Date", value: formatDate(record.finishing_start_date) },
		{ label: "Finishing End Date", value: formatDate(record.finishing_end_date) },
		{ label: "Audit Requested Date", value: formatDate(record.audit_requested_date) },
		{ label: "Audit Completed Date", value: formatDate(record.audit_completed_date) },
	]
})

async function load(force = false) {
	const tab = currentTab.value
	if (!tab.source || (store.value[tab.value] && !force)) return
	const target = store.value
	const plan = props.name
	const state = reactive({ loading: true, error: "", data: null })
	target[tab.value] = state
	try {
		const data = await getFinishingPlanTab(plan, tab.source)
		if (target[tab.value] === state) state.data = data || {}
	} catch (reason) {
		if (target[tab.value] === state) state.error = reason?.message || `Unable to load ${tab.label}.`
	} finally {
		state.loading = false
	}
}

watch(() => [props.name, props.version], () => {
	store.value = {}
	load()
})
watch(active, () => load(), { immediate: true })
</script>

<style scoped>
.finishing-tabs { min-width: 0; max-width: 100%; }
.finishing-tabs :deep(.p-tabpanels) { padding: 10px 0 0; background: transparent; }
.finishing-tabs :deep(.p-tabpanel) { padding: 0; }
.finishing-tabs :deep(.p-tab) { min-height: 42px; padding: 9px 14px; font-size: 0.86rem; white-space: nowrap; }
.finishing-tabs__mobile { display: none; }
.finishing-tabs__toolbar { display: flex; flex-wrap: wrap; gap: var(--erp-space-2); }
.finishing-facts { display: flex; flex-wrap: wrap; gap: 6px 22px; margin: 0; }
.finishing-facts div { display: grid; gap: 1px; }
.finishing-facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; }
.finishing-facts dd { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 650; font-variant-numeric: tabular-nums; }
@media (max-width: 700px) {
	.finishing-tabs__desktop { display: none; }
	.finishing-tabs__mobile { display: grid; gap: 6px; margin-bottom: 4px; font-size: var(--erp-font-size-caption); font-weight: 650; }
}
</style>

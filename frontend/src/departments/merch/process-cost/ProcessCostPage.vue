<template>
	<DepartmentPage title="Process Cost" :back-to="PROCESS_COST_LIST_PATH" back-label="Process Costs" :show-title="false" flat full-width inline-navigation>
		<section class="purchase-lot-frame merch-lot-frame process-cost-frame">
			<FabricDocumentWorkspace doctype="YRP Process Cost" title="Process Cost" :workspace="workspace" :loading="loading" :error="error" :acting="acting ? 'action' : ''" :show-lifecycle-actions="false" :show-delete="false" @reload="load">
				<template #header="{ record, headingId }">
					<div class="fabric-document-workspace__identity">
						<div><h1 class="erp-doc-title" :id="headingId">Process Cost · <DocumentLink doctype="YRP Process" :name="record.process_name" /></h1><span class="erp-doc-id">{{ record.name }}</span></div>
						<DocumentStatusBadge :label="record.workflow_state" :docstatus="record.docstatus" />
					</div>
				</template>
				<template #header-actions><DocumentActionStrip :actions="actions" /></template>
				<template #matrix>
					<Message v-if="workspace.waiting_note" severity="info" :closable="false">{{ workspace.waiting_note }}</Message>
					<Tabs v-model:value="activeTab" scrollable class="lot-tabs erp-tabs">
						<TabList class="lot-tablist">
							<Tab v-for="tab in PROCESS_COST_TABS" :key="tab.key" :value="tab.key">
								{{ tab.label }}<span v-if="tab.key === 'values'">{{ workspace.tiers?.length || 0 }}</span>
							</Tab>
						</TabList>
						<TabPanels class="lot-panels">
							<TabPanel v-if="activeTab === 'details'" value="details">
								<DocumentOverview :fields="workspace.fields" :definitions="PROCESS_COST_SECTIONS" id-prefix="process-cost" aria-label="Process Cost details" include-empty />
							</TabPanel>
							<TabPanel v-if="activeTab === 'values'" value="values">
								<ProcessCostGrid :tiers="workspace.tiers" :fields="workspace.tier_fields" readonly />
							</TabPanel>
						</TabPanels>
					</Tabs>
				</template>
				<template #rail>
					<LotDocumentsRail v-if="workspace.work_orders?.permitted" :documents="{ work_orders: workspace.work_orders }" :sections="PROCESS_COST_DOCUMENT_SECTIONS" aria-label="Process Cost work orders" @open="openWorkOrder" />
				</template>
			</FabricDocumentWorkspace>
		</section>
		<DocumentConfirmationDialog :visible="Boolean(pending)" :title="`${pending?.label || 'Confirm'} Process Cost`" :message="pending ? processCostActionMessage(pending) : ''" :confirm-label="pending?.label || 'Continue'" :busy="acting" :severity="['Expired', 'Reject', 'Delete'].includes(pending?.action) ? 'danger' : 'primary'" @update:visible="!$event && (pending = null)" @confirm="confirmAction" />
		<DocumentErrorDialog :message="actionError" retry-label="Reload" @dismiss="actionError = ''" @retry="reload" />
	</DepartmentPage>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import Message from "primevue/message"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { deleteProcessCost, executeProcessCostCommand, getProcessCostWorkspace } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../../fabric-store/FabricDocumentWorkspace.vue"
import LotDocumentsRail from "../../purchase/lot/LotDocumentsRail.vue"
import { MERCH_ROUTES } from "../merchViews.js"
import ProcessCostGrid from "./ProcessCostGrid.vue"
import { PROCESS_COST_DOCUMENT_SECTIONS, PROCESS_COST_LIST_PATH, PROCESS_COST_SECTIONS, PROCESS_COST_TABS, processCostActions, processCostActionMessage, processCostPath } from "./processCostViews.js"
import "../../purchase/lot/lot.css"
import "../lot/merchLot.css"

const props = defineProps({ processCostId: { type: String, required: true } })
const route = useRoute()
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const acting = ref(false)
const error = ref("")
const actionError = ref("")
const pending = ref(null)
let loadSequence = 0
const activeTab = computed({
	get: () => PROCESS_COST_TABS.some((tab) => tab.key === route.query.tab) ? route.query.tab : "details",
	set: (tab) => router.replace({ query: { ...route.query, tab }, state: preserveListNavigationState() }),
})
const actions = computed(() => processCostActions(workspace.value, {
	busy: acting.value, execute: (action) => { pending.value = action },
	edit: () => router.push(`${processCostPath(props.processCostId)}/edit`),
	remove: () => { pending.value = { action: "Delete", label: "Delete" } },
}))
async function load() {
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	if (workspace.value.record?.name !== props.processCostId) { workspace.value = {}; pending.value = null }
	try { const result = await getProcessCostWorkspace(props.processCostId); if (sequence === loadSequence) workspace.value = result }
	catch (reason) { if (sequence === loadSequence) error.value = reason.message }
	finally { if (sequence === loadSequence) loading.value = false }
}
function reload() { actionError.value = ""; load() }
function openWorkOrder(doc) {
	return router.push({ name: MERCH_ROUTES.workOrder, params: { workOrderId: doc.name } })
}
async function confirmAction() {
	if (acting.value || !pending.value) return
	acting.value = true
	try {
		if (pending.value.action === "Delete") {
			await deleteProcessCost(props.processCostId, workspace.value.record.modified)
			await router.push(PROCESS_COST_LIST_PATH)
		} else workspace.value = await executeProcessCostCommand(props.processCostId, pending.value.action, workspace.value.record.modified)
		pending.value = null
	} catch (reason) { pending.value = null; actionError.value = reason.message }
	finally { acting.value = false }
}
watch(() => props.processCostId, load, { immediate: true })
</script>

<style scoped>
.fabric-document-workspace__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.fabric-document-workspace__identity > div { display: grid; min-width: 0; gap: 2px; }
.process-cost-frame :deep(.fabric-document-workspace__rail:empty) { display: none; }
.process-cost-frame :deep(.fabric-document-workspace__columns:has(> .fabric-document-workspace__rail:empty)) {
	grid-template-areas: "main";
	grid-template-columns: minmax(0, 1fr);
}
</style>

<template>
	<DepartmentPage title="Process Cost" :back-to="PROCESS_COST_LIST_PATH" back-label="Process Costs" :show-title="false" flat full-width inline-navigation>
		<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
		<div v-else-if="loading" class="erp-empty-state">Loading Process Cost…</div>
		<article v-else class="process-cost-page erp-workspace">
			<header class="process-cost-page__header">
				<InlinePageNavigation title-target="process-cost-title" />
				<div class="process-cost-page__title"><h1 id="process-cost-title" class="erp-doc-title">Process Cost · {{ workspace.record.process_name }}</h1><span class="erp-doc-id">{{ workspace.record.name }}</span></div>
				<DocumentStatusBadge :label="workspace.record.workflow_state" :docstatus="workspace.record.docstatus" />
				<DocumentActionStrip :actions="actions" />
			</header>
			<Message v-if="workspace.waiting_note" severity="info" :closable="false">{{ workspace.waiting_note }}</Message>
			<DocumentOverview :fields="workspace.fields" :definitions="PROCESS_COST_SECTIONS" include-empty />
			<ProcessCostGrid :tiers="workspace.tiers" :fields="workspace.tier_fields" readonly />
		</article>
		<DocumentConfirmationDialog :visible="Boolean(pending)" :title="`${pending?.label || 'Confirm'} Process Cost`" :message="pending ? processCostActionMessage(pending) : ''" :confirm-label="pending?.label || 'Continue'" :busy="acting" :severity="['Expired', 'Reject', 'Delete'].includes(pending?.action) ? 'danger' : 'primary'" @update:visible="!$event && (pending = null)" @confirm="confirmAction" />
		<DocumentErrorDialog :message="actionError" retry-label="Reload" @dismiss="actionError = ''" @retry="reload" />
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import { computed, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { deleteProcessCost, executeProcessCostCommand, getProcessCostWorkspace } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import DocumentActionStrip from "../../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import InlinePageNavigation from "../../../components/navigation/InlinePageNavigation.vue"
import ProcessCostGrid from "./ProcessCostGrid.vue"
import { PROCESS_COST_LIST_PATH, PROCESS_COST_SECTIONS, processCostActions, processCostActionMessage, processCostPath } from "./processCostViews.js"

const props = defineProps({ processCostId: { type: String, required: true } })
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const acting = ref(false)
const error = ref("")
const actionError = ref("")
const pending = ref(null)
let loadSequence = 0
const actions = computed(() => processCostActions(workspace.value, {
	busy: acting.value, execute: (action) => { pending.value = action },
	edit: () => router.push(`${processCostPath(props.processCostId)}/edit`),
	remove: () => { pending.value = { action: "Delete", label: "Delete" } },
}))
async function load() {
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	try { const result = await getProcessCostWorkspace(props.processCostId); if (sequence === loadSequence) workspace.value = result }
	catch (reason) { if (sequence === loadSequence) error.value = reason.message }
	finally { if (sequence === loadSequence) loading.value = false }
}
function reload() { actionError.value = ""; load() }
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
.process-cost-page { min-width: 0; display: grid; gap: 18px; padding: clamp(12px, 2vw, 24px); }
.process-cost-page__header { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.process-cost-page__title { min-width: 0; overflow-wrap: anywhere; margin-right: auto; }
</style>

<template>
	<DepartmentPage title="Cutting Order" accent="#059669" back-to="/cutting/orders" back-label="Cutting Orders" :show-title="false" flat full-width>
		<div v-if="checking" class="order-probe erp-workspace" aria-label="Loading Cutting Order"><Skeleton height="76px" /><Skeleton height="420px" /></div>
		<div v-else-if="showDraftEditor" class="order-editor-route erp-workspace">
			<CuttingOrderEditor :name="cuttingOrderId" :initial-payload="editorProbe" @saved="editorSaved" @cancel="router.push('/cutting/orders')" />
		</div>
		<div v-else class="cutting-order-layout erp-workspace" :class="{ 'cutting-order-layout--without-sidebar': !showSidebar }">
			<main class="cutting-order-main erp-card">
				<header class="order-record-header">
					<div class="order-record-identity">
						<div class="order-record-title"><h1>Cutting Order</h1><span>{{ cuttingOrderId }}</span></div>
						<div class="order-record-meta">
							<Tag :value="record.status || 'Draft'" :severity="statusSeverity(record.status)" rounded />
							<span class="order-header-fact order-header-fact--detail" :title="record.cutting_order_detail || 'No Cutting Order Detail'">
								<small>Order Detail</small><strong>{{ record.cutting_order_detail || "—" }}</strong>
							</span>
							<span class="order-header-fact order-header-fact--item" :title="record.item || 'No Item'">
								<small>Item</small><strong>{{ record.item || "—" }}</strong>
							</span>
						</div>
					</div>
					<div class="order-record-actions">
						<DocumentPrintButton v-if="workspace.permissions?.can_print" doctype="SD YRP Cutting Order" :name="cuttingOrderId" :formats="workspace.print_formats || []" :disabled="workspaceLoading" />
						<CuttingOrderActions v-if="record.name" :doc="record" :data="workspace" @refresh="loadWorkspace" />
						<Button v-if="workspace.permissions?.can_cancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :loading="lifecycleBusy === 'cancel'" @click="changeStatus('cancel')" />
						<Button v-if="workspace.permissions?.can_amend" label="Amend" icon="pi pi-copy" :loading="lifecycleBusy === 'amend'" @click="changeStatus('amend')" />
					</div>
				</header>
				<Message v-if="workspaceError" severity="error" :closable="false">{{ workspaceError }}</Message>
				<CuttingOrderTabs :data="workspace" :loading="workspaceLoading" :error="workspaceError" />
			</main>
			<CuttingParentSidebar
				v-if="showSidebar"
				parent-doctype="SD YRP Cutting Order"
				:parent-name="cuttingOrderId"
				parent-field="cutting_order"
				:data="workspace"
				:loading="workspaceLoading"
				:error="workspaceError"
				@refresh="loadWorkspace"
			/>
		</div>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tag from "primevue/tag"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { changeCuttingOrderStatus, getCuttingOrderEditor, getCuttingOrderWorkspace } from "../api/cuttingOrder.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import { useActionConfirmation } from "../utils/useActionConfirmation.js"
import CuttingOrderActions from "./cutting/order/CuttingOrderActions.vue"
import CuttingOrderEditor from "./cutting/order/CuttingOrderEditor.vue"
import CuttingOrderTabs from "./cutting/order/CuttingOrderTabs.vue"
import CuttingParentSidebar from "./cutting/shared/CuttingParentSidebar.vue"
import DocumentPrintButton from "./cutting/DocumentPrintButton.vue"

const route = useRoute()
const router = useRouter()
const confirmAction = useActionConfirmation()
const cuttingOrderId = computed(() => String(route.params.cuttingOrderId || ""))
const checking = ref(true)
const editorProbe = ref(null)
const workspace = ref({})
const workspaceLoading = ref(true)
const workspaceError = ref("")
const lifecycleBusy = ref("")
let loadSequence = 0
const showDraftEditor = computed(() => Boolean(editorProbe.value?.record?.docstatus === 0 && editorProbe.value?.permissions?.can_write))
const record = computed(() => workspace.value.record || editorProbe.value?.record || {})
const showSidebar = computed(() => Boolean(workspaceLoading.value || workspace.value.permissions?.can_read_marker || workspace.value.permissions?.can_read_laysheet))

async function initialise() {
	checking.value = true
	editorProbe.value = null
	try { editorProbe.value = await getCuttingOrderEditor(cuttingOrderId.value) }
	catch (reason) { workspaceError.value = reason?.message || "Unable to load the Cutting Order." }
	finally { checking.value = false }
	if (!showDraftEditor.value) await loadWorkspace()
}

async function loadWorkspace() {
	const sequence = ++loadSequence
	workspaceLoading.value = true; workspaceError.value = ""
	try { const data = await getCuttingOrderWorkspace(cuttingOrderId.value); if (sequence === loadSequence) workspace.value = data || {} }
	catch (reason) { if (sequence === loadSequence) workspaceError.value = reason?.message || "Unable to load Cutting Order details." }
	finally { if (sequence === loadSequence) workspaceLoading.value = false }
}

async function editorSaved(saved) {
	editorProbe.value = { ...editorProbe.value, record: { ...(editorProbe.value?.record || {}), ...saved } }
	if (saved?.docstatus !== 0) await loadWorkspace()
}

async function changeStatus(action) {
	if (action === "cancel") return confirmAction({
		header: "Cancel Cutting Order?",
		message: `Cancel Cutting Order ${cuttingOrderId.value}? This changes the document status and cannot be undone here.`,
		acceptLabel: "Cancel Cutting Order",
		accept: () => performStatusChange(action),
	})
	return performStatusChange(action)
}

async function performStatusChange(action) {
	lifecycleBusy.value = action; workspaceError.value = ""
	try {
		const payload = await changeCuttingOrderStatus(cuttingOrderId.value, action, record.value.modified)
		const name = payload?.record?.name || cuttingOrderId.value
		if (name !== cuttingOrderId.value) return router.replace({ name: "cutting-order", params: { cuttingOrderId: name } })
		editorProbe.value = payload
		await loadWorkspace()
	} catch (reason) { workspaceError.value = reason?.message || `Unable to ${action} the Cutting Order.` }
	finally { lifecycleBusy.value = "" }
}

function statusSeverity(status) { if (status === "Completed") return "success"; if (status === "Partially Completed") return "warn"; if (status === "Cutting In Progress") return "info"; if (status === "Cancelled") return "danger"; return "secondary" }
watch(cuttingOrderId, initialise, { immediate: true })
</script>

<style scoped>
.order-probe { display: grid; gap: var(--erp-space-3); }
.order-editor-route { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }
.cutting-order-layout { display: grid; grid-template-columns: minmax(0, 4fr) minmax(286px, 1fr); align-items: stretch; gap: var(--erp-space-3); height: calc(100dvh - var(--erp-shell-header-height) - 97px); min-height: 0; overflow: hidden; }
.cutting-order-layout--without-sidebar { grid-template-columns: minmax(0, 1fr); }
.cutting-order-main { display: flex; min-width: 0; min-height: 0; padding: 14px; flex-direction: column; gap: 8px; overflow: hidden; }
.order-record-header { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 52px; padding-bottom: 12px; border-bottom: 1px solid var(--erp-border); }
.order-record-identity { display: flex; align-items: center; gap: 14px; min-width: 0; }
.order-record-title { display: grid; gap: 3px; min-width: 0; }
.order-record-identity h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 760; letter-spacing: -0.025em; line-height: 1.05; white-space: nowrap; }
.order-record-title > span { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.order-record-meta { display: flex; align-items: center; gap: 12px; min-width: 0; }
.order-header-fact { display: grid; gap: 2px; min-width: 112px; max-width: 230px; padding-left: 12px; border-left: 1px solid var(--erp-border); }
.order-header-fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; line-height: 1; text-transform: uppercase; }
.order-header-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 730; text-overflow: ellipsis; white-space: nowrap; }
.order-header-fact--item { max-width: 280px; }
.order-record-actions { display: flex; align-items: center; gap: 7px; }
@media (max-width: 1050px) { .cutting-order-layout { grid-template-columns: 1fr; height: auto; overflow: visible; } .cutting-order-main { min-height: 760px; overflow: visible; } }
@media (max-width: 850px) { .order-record-header { align-items: stretch; flex-direction: column; } .order-record-actions { flex-wrap: wrap; } }
@media (max-width: 650px) { .order-record-identity { align-items: flex-start; flex-direction: column; } .order-record-meta { flex-wrap: wrap; } .order-header-fact:first-of-type { padding-left: 0; border-left: 0; } }
</style>

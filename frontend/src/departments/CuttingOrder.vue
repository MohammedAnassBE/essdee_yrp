<template>
	<DepartmentPage title="Cutting Order" back-to="/cutting/orders" back-label="Cutting Orders" :show-title="false" flat full-width :inline-navigation="!checking && !showDraftEditor" activity-doctype="SD YRP Cutting Order" :activity-name="checking ? '' : record.name || ''" :activity-record="record">
		<div v-if="checking" class="order-probe erp-workspace" aria-label="Loading Cutting Order"><Skeleton height="76px" /><Skeleton height="420px" /></div>
		<div v-else-if="showDraftEditor" class="order-editor-route erp-workspace">
			<CuttingOrderEditor :name="cuttingOrderId" :initial-payload="editorProbe" @saved="editorSaved" @cancel="router.push('/cutting/orders')">
				<template #document-actions="{ busy, dirty }">
					<DocumentPrintButton doctype="SD YRP Cutting Order" :name="cuttingOrderId" :docstatus="record.docstatus" :disabled="busy" />
					<DocumentDeleteButton doctype="SD YRP Cutting Order" :name="cuttingOrderId" :docstatus="record.docstatus" :disabled="busy || dirty" redirect-to="/cutting/orders" />
					<DocumentActionStrip :actions="duplicateActions" />
				</template>
			</CuttingOrderEditor>
		</div>
		<div v-else-if="workspaceError && !workspaceReady" class="order-probe erp-workspace">
			<WorkspaceLoadError title="Cutting Order unavailable" :message="workspaceError" @retry="initialise" />
		</div>
		<div v-else class="cutting-order-layout erp-workspace" :class="{ 'cutting-order-layout--without-sidebar': !showSidebar }">
			<section class="cutting-order-main erp-card" aria-label="Cutting Order details">
				<header class="order-record-header">
					<InlinePageNavigation
						title-target="cutting-order-title"
						show-document-navigation
						:current-name="cuttingOrderId"
						document-label="Cutting Order"
						:navigation-disabled="workspaceLoading || Boolean(lifecycleBusy)"
					/>
					<div class="order-record-identity">
						<div class="order-record-title"><h1 id="cutting-order-title">Cutting Order</h1><span>{{ cuttingOrderId }}</span></div>
						<div class="order-record-meta">
							<DocumentStatusBadge :docstatus="record.docstatus" :label="record.status || 'Draft'" />
							<span class="order-header-fact order-header-fact--detail" :title="record.cutting_order_detail || 'No Cutting Order Detail'">
								<small>Order Detail</small><strong><DocumentLink doctype="SD YRP Cutting Order Detail" :name="record.cutting_order_detail" :label="record.cutting_order_detail || '—'" /></strong>
							</span>
							<span class="order-header-fact order-header-fact--item" :title="record.item || 'No Item'">
								<small>Item</small><strong>{{ record.item || "—" }}</strong>
							</span>
						</div>
					</div>
					<div class="order-record-actions">
						<DocumentShortcuts :busy="workspaceLoading || Boolean(lifecycleBusy)" :can-cancel="Boolean(workspace.permissions?.can_cancel)" cancel-confirms @cancel="changeStatus('cancel')" />
						<DocumentPrintButton v-if="workspace.permissions?.can_print" doctype="SD YRP Cutting Order" :name="cuttingOrderId" :formats="workspace.print_formats || []" :disabled="workspaceLoading" />
						<DocumentDeleteButton doctype="SD YRP Cutting Order" :name="cuttingOrderId" :docstatus="record.docstatus" :disabled="workspaceLoading || Boolean(lifecycleBusy)" redirect-to="/cutting/orders" />
						<CuttingOrderActions v-if="record.name" :doc="record" :data="workspace" :extra-actions="duplicateActions" @refresh="loadWorkspace" />
						<Button v-if="workspace.permissions?.can_cancel" label="Cancel" :title="withShortcutHint('Cancel', 'cancel')" icon="pi pi-ban" severity="danger" outlined :loading="lifecycleBusy === 'cancel'" @click="changeStatus('cancel')" />
						<Button v-if="workspace.permissions?.can_amend" label="Amend" icon="pi pi-copy" :loading="lifecycleBusy === 'amend'" @click="changeStatus('amend')" />
					</div>
				</header>
				<Message v-if="workspaceError" severity="error" :closable="false">{{ workspaceError }}</Message>
				<CuttingOrderTabs :data="workspace" :loading="workspaceLoading" error="" />
			</section>
			<CuttingParentSidebar
				v-if="showSidebar"
				parent-doctype="SD YRP Cutting Order"
				:parent-name="cuttingOrderId"
				parent-field="cutting_order"
				:data="workspace"
				:loading="workspaceLoading"
				error=""
				@refresh="loadWorkspace"
			/>
		</div>
		<DocumentErrorDialog :message="actionError" title="Cutting Order action failed" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import DocumentLink from "../components/common/DocumentLink.vue"
import DocumentDeleteButton from "../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { changeCuttingOrderStatus, getCuttingOrderEditor, getCuttingOrderWorkspace } from "../api/cuttingOrder.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../components/documents/DocumentActionStrip.vue"
import DocumentErrorDialog from "../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"
import InlinePageNavigation from "../components/navigation/InlinePageNavigation.vue"
import { useDuplicateAction } from "../composables/useDuplicateAction.js"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import { useActionConfirmation } from "../utils/useActionConfirmation.js"
import DocumentShortcuts from "../components/documents/DocumentShortcuts.vue"
import { withShortcutHint } from "../utils/documentShortcuts.js"
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
const actionError = ref("")
const lifecycleBusy = ref("")
let loadSequence = 0
let initialiseSequence = 0
let lifecycleSequence = 0
let disposed = false
const showDraftEditor = computed(() => Boolean(editorProbe.value?.record?.docstatus === 0 && editorProbe.value?.permissions?.can_write))
const record = computed(() => workspace.value.record || editorProbe.value?.record || {})
const workspaceReady = computed(() => Boolean(workspace.value.record?.name))
const showSidebar = computed(() => Boolean(workspaceLoading.value || workspace.value.permissions?.can_read_marker || workspace.value.permissions?.can_read_laysheet))
const duplicateAction = useDuplicateAction({
	canCreate: () => (workspace.value.permissions || editorProbe.value?.permissions)?.can_create,
	newRouteName: "cutting-order-new",
	name: () => record.value.name,
	busy: () => workspaceLoading.value || Boolean(lifecycleBusy.value),
	router,
})
const duplicateActions = computed(() => duplicateAction.value ? [duplicateAction.value] : [])

async function initialise() {
	const sequence = ++initialiseSequence
	const requestedId = cuttingOrderId.value
	loadSequence += 1
	lifecycleSequence += 1
	checking.value = true
	lifecycleBusy.value = ""
	editorProbe.value = null
	workspace.value = {}
	workspaceLoading.value = true
	workspaceError.value = ""
	actionError.value = ""
	try {
		const data = await getCuttingOrderEditor(requestedId)
		if (sequence !== initialiseSequence || requestedId !== cuttingOrderId.value) return
		editorProbe.value = data
		checking.value = false
		if (!(data?.record?.docstatus === 0 && data?.permissions?.can_write)) await loadWorkspace(requestedId)
	} catch (reason) {
		if (sequence !== initialiseSequence || requestedId !== cuttingOrderId.value) return
		workspaceError.value = reason?.message || "Unable to load the Cutting Order."
		workspaceLoading.value = false
	} finally {
		if (sequence === initialiseSequence && requestedId === cuttingOrderId.value) checking.value = false
	}
}

async function loadWorkspace(requestedId = cuttingOrderId.value) {
	const sequence = ++loadSequence
	workspaceLoading.value = true; workspaceError.value = ""
	try {
		const data = await getCuttingOrderWorkspace(requestedId)
		if (sequence === loadSequence && requestedId === cuttingOrderId.value) workspace.value = data || {}
	} catch (reason) {
		if (sequence === loadSequence && requestedId === cuttingOrderId.value) workspaceError.value = reason?.message || "Unable to load Cutting Order details."
	} finally {
		if (sequence === loadSequence && requestedId === cuttingOrderId.value) workspaceLoading.value = false
	}
}

async function editorSaved(saved) {
	editorProbe.value = { ...editorProbe.value, record: { ...(editorProbe.value?.record || {}), ...saved } }
	if (saved?.docstatus !== 0) await loadWorkspace()
}


async function changeStatus(action) {
	const requestedId = cuttingOrderId.value
	const expectedModified = record.value.modified
	if (action === "cancel") return confirmAction({
		header: "Cancel Cutting Order?",
		message: `Cancel Cutting Order ${requestedId}? This changes the document status and cannot be undone here.`,
		acceptLabel: "Cancel Cutting Order",
		accept: () => performStatusChange(action, requestedId, expectedModified),
	})
	return performStatusChange(action, requestedId, expectedModified)
}

async function performStatusChange(action, requestedId = cuttingOrderId.value, expectedModified = record.value.modified) {
	if (disposed || requestedId !== cuttingOrderId.value) return
	const sequence = ++lifecycleSequence
	lifecycleBusy.value = action; actionError.value = ""
	try {
		const payload = await changeCuttingOrderStatus(requestedId, action, expectedModified)
		if (lifecycleActionIsStale(sequence, requestedId)) return
		const name = payload?.record?.name || requestedId
		if (name !== requestedId) return router.replace({ name: "cutting-order", params: { cuttingOrderId: name }, state: preserveListNavigationState(name) })
		editorProbe.value = payload
		await loadWorkspace(requestedId)
	} catch (reason) {
		if (!lifecycleActionIsStale(sequence, requestedId)) actionError.value = reason?.message || `Unable to ${action} the Cutting Order.`
	} finally {
		if (!lifecycleActionIsStale(sequence, requestedId)) lifecycleBusy.value = ""
	}
}

function lifecycleActionIsStale(sequence, requestedId) {
	return disposed || sequence !== lifecycleSequence || requestedId !== cuttingOrderId.value
}

watch(cuttingOrderId, initialise, { immediate: true })
onBeforeUnmount(() => { disposed = true; lifecycleSequence += 1; loadSequence += 1; initialiseSequence += 1 })
</script>

<style scoped>
.order-probe { display: grid; gap: var(--erp-space-3); }
.order-editor-route { width: 100%; min-width: 0; }
.cutting-order-layout { display: grid; grid-template-columns: minmax(0, 4fr) minmax(286px, 1fr); align-items: stretch; gap: var(--erp-space-3); height: calc(100dvh - var(--erp-shell-header-height) - 97px); min-height: 0; overflow: hidden; }
.cutting-order-layout--without-sidebar { grid-template-columns: minmax(0, 1fr); }
.cutting-order-main { display: flex; min-width: 0; min-height: 0; padding: 14px; flex-direction: column; gap: 8px; overflow: hidden; }
.order-record-header { display: flex; align-items: center; justify-content: flex-start; gap: 14px; min-height: 52px; padding-bottom: 12px; border-bottom: 1px solid var(--erp-border); }
.order-record-identity { display: flex; min-width: 0; flex: 1 1 auto; align-items: center; gap: 14px; }
.order-record-title { display: grid; gap: 3px; min-width: 0; }
.order-record-identity h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 760; letter-spacing: -0.025em; line-height: 1.05; white-space: nowrap; }
.order-record-title > span { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.order-record-meta { display: flex; align-items: center; gap: 12px; min-width: 0; }
.order-header-fact { display: grid; gap: 2px; min-width: 112px; max-width: 230px; padding-left: 12px; border-left: 1px solid var(--erp-border); }
.order-header-fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .035em; line-height: 1; text-transform: uppercase; }
.order-header-fact strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 730; text-overflow: ellipsis; white-space: nowrap; }
.order-header-fact--item { max-width: 280px; }
.order-record-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 7px; margin-left: auto; }
@media (max-width: 1050px) { .cutting-order-layout { grid-template-columns: 1fr; height: auto; overflow: visible; } .cutting-order-main { min-height: 0; overflow: visible; } .order-record-header { align-items: stretch; flex-direction: column; } .order-record-actions { margin-left: 0; } }
@media (max-width: 850px) { .order-record-actions { flex-wrap: wrap; } }
@media (max-width: 650px) { .order-record-identity { align-items: flex-start; flex-direction: column; } .order-record-meta { flex-wrap: wrap; } .order-header-fact:first-of-type { padding-left: 0; border-left: 0; } }
</style>

<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		:header="dialogTitle"
		class="document-transaction-dialog erp-entity-dialog erp-dialog--lg"
		@update:visible="requestVisibility"
	>
		<div ref="content" class="document-transaction-dialog__content">
			<div v-if="loading" class="document-transaction-dialog__loading"><Skeleton v-for="index in 5" :key="index" height="3rem" /></div>
			<template v-else>
				<DocumentLiveBar v-if="remoteChange" state="modified" :modified-at="String(remoteChange.modified || '')" :dirty="dirty" :reloading="refreshing" @reload="load({ background: true })" />
				<div v-if="payload.record" class="document-transaction-dialog__status-row">
					<DocumentStatusBadge :docstatus="payload.record.docstatus" :label="payload.record.status" />
					<small>Updated {{ formatDisplayDatetime(payload.record.modified) }}</small>
				</div>
				<section v-if="payload.transit?.status" class="document-transit-status">
					<strong>{{ payload.transit.status }}</strong>
					<div v-if="payload.transit.received_entries?.length">Received Stock Entries: <a v-for="entry in payload.transit.received_entries" :key="entry.name" :href="stockEntryPath(entry.name)" target="_blank" rel="noopener">{{ entry.name }}{{ entry.docstatus === 0 ? ' (Draft)' : '' }} </a></div>
				</section>
				<section v-if="summaryDetails.length" class="document-summary-strip" aria-label="Document totals">
					<div v-for="field in summaryDetails" :key="field.fieldname" class="document-summary-metric"><span>{{ field.label }}</span><strong :title="formatField(field)">{{ formatField(field) }}</strong></div>
				</section>
				<section v-if="visibleDetails.length" class="document-detail-grid">
					<div v-for="field in visibleDetails" :key="field.fieldname"><span>{{ field.label }}</span><strong :class="{ 'document-detail-link': field.fieldtype === 'Link' }" :title="formatField(field)">{{ formatField(field) }}</strong></div>
				</section>
				<StockItemMatrix :dimensions="payload.dimensions || []" v-if="payload.item_groups?.length" :groups="payload.item_groups" :doctype="payload.record?.doctype" :physical-row-count="payload.item_row_count || 0" :group-by-item="Boolean(payload.context?.work_order)" />
				<div v-else-if="payload.item_row_count" class="document-items-unavailable"><i class="pi pi-exclamation-circle" /><div><strong>Item matrix unavailable</strong><span>The item variants could not be grouped for display.</span></div></div>
			</template>
		</div>

		<DocumentActivity :doctype="payload.record?.doctype || doctype" :name="payload.record?.name || ''" :record="payload.record" />
		<template #footer>
			<div class="document-transaction-dialog__footer">
				<Button label="Close" severity="secondary" text :disabled="Boolean(acting)" @click="requestVisibility(false)" />
				<div>
					<DocumentDeleteButton v-if="payload.record?.name" :doctype="payload.record?.doctype || doctype" :name="payload.record.name" :docstatus="payload.record.docstatus" :disabled="Boolean(acting)" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="payload.permissions?.can_print" :doctype="payload.record?.doctype || doctype" :name="payload.record?.name || name" :formats="payload.print_formats || []" :disabled="Boolean(acting)" />
					<Button v-if="payload.actions?.can_make_delivery_challan" label="Make Delivery Challan" icon="pi pi-send" severity="secondary" outlined @click="makeDcVisible = true" />
					<Button v-if="payload.actions?.can_end_transit" label="End Transit" icon="pi pi-check" :loading="acting === 'end-transit'" @click="endTransit" />
					<Button v-if="payload.actions?.can_complete_transfer" label="Complete Transfer" icon="pi pi-arrow-right-arrow-left" severity="secondary" outlined :loading="acting === 'complete-transfer'" @click="completeTransfer" />
					<Button v-if="payload.actions?.can_return" label="Return" icon="pi pi-replay" severity="secondary" outlined :disabled="Boolean(acting)" @click="emit('return', payload)" />
					<Button v-if="showEdit && payload.permissions?.can_write" label="Edit" icon="pi pi-pencil" severity="secondary" outlined :disabled="Boolean(acting)" @click="editDocument" />
					<Button v-if="payload.permissions?.can_amend" label="Amend" icon="pi pi-copy" severity="secondary" outlined :loading="acting === 'amend'" @click="changeStatus('amend')" />
					<Button v-if="payload.permissions?.can_cancel && workflowReady && !activeWorkflow" label="Cancel Document" :title="withShortcutHint('Cancel Document', 'cancel')" icon="pi pi-ban" severity="danger" outlined :loading="acting === 'cancel'" @click="changeStatus('cancel')" />
					<Button v-if="payload.permissions?.can_submit && workflowReady && !activeWorkflow" label="Submit" :title="withShortcutHint('Submit', 'submit')" icon="pi pi-check" :loading="acting === 'submit'" @click="changeStatus('submit')" />
				</div>
			</div>
		</template>
	</Dialog>
	<StockEntryMakeDcModal v-if="payload.record?.doctype === 'YRP Stock Entry'" v-model:visible="makeDcVisible" :stock-entry="payload.record.name" @created="deliveryChallanCreated" />
	<FabricStockOperationDialog v-model:visible="receiptVisible" operation="stock_entry" :initial-editor="receiptEditor" @changed="receiptChanged" />
	<DocumentErrorDialog :message="error" :title="`${dialogTitle} could not be completed`" @dismiss="error = ''" />

	<Dialog v-model:visible="closeConfirmationVisible" class="erp-dialog--sm" modal header="Discard changes?">
		<p class="dirty-close-copy">This document has unsaved changes. Close it and discard those changes?</p>
		<template #footer><Button label="Keep Editing" severity="secondary" text @click="closeConfirmationVisible = false" /><Button label="Discard Changes" severity="danger" @click="closeNow" /></template>
	</Dialog>
</template>

<script setup>
import DocumentActivity from "./DocumentActivity.vue"
import DocumentDeleteButton from "./DocumentDeleteButton.vue"
import DocumentLiveBar from "./DocumentLiveBar.vue"
import { useDocRealtime } from "../../composables/live/useDocRealtime.js"
import { useRouter } from "vue-router"
import StockEntryMakeDcModal from "../../views/dynamic/StockEntryMakeDcModal.vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { changeFabricStoreDocumentStatus, endStockEntryTransit, completeWorkOrderDocumentTransfer, getFabricStoreDocument } from "../../api/fabricStore.js"
import { getActiveWorkflow } from "../../api/frappe.js"
import FabricStockOperationDialog from "../../departments/fabric-store/FabricStockOperationDialog.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import { useDocumentShortcuts } from "../../composables/useDocumentShortcuts.js"
import { withShortcutHint } from "../../utils/documentShortcuts.js"
import { formatDisplayByFieldtype, formatDisplayDatetime } from "../../utils/dateFormat.js"
import StockItemMatrix from "../stock/StockItemMatrix.vue"
import DocumentErrorDialog from "./DocumentErrorDialog.vue"
import DocumentPrintButton from "./DocumentPrintButton.vue"
import DocumentStatusBadge from "./DocumentStatusBadge.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	name: { type: String, default: "" },
	editable: { type: Boolean, default: false },
	showEdit: { type: Boolean, default: true },
})
const emit = defineEmits(["update:visible", "changed", "amended", "edit", "return", "replacement"])
const confirmAction = useActionConfirmation()

const workflowReady = ref(false)
const activeWorkflow = ref(null)
const makeDcVisible = ref(false)
const router = useRouter()
function deliveryChallanCreated(created) { emit("update:visible", false); router.push(`/fabric-store/delivery-challans/${encodeURIComponent(created.name || created)}`) }
const loading = ref(false)
const acting = ref("")
const error = ref("")
const payload = ref({})
const receiptVisible = ref(false)
const receiptEditor = ref(null)
const dirty = ref(false)
const refreshing = ref(false)
const remoteChange = ref(null)
const closeConfirmationVisible = ref(false)
const dialogTitle = computed(() => `${payload.value.record?.doctype || props.doctype}${payload.value.record?.name || props.name ? ` · ${payload.value.record?.name || props.name}` : ""}`)
const summaryFieldnames = computed(() => payload.value.record?.doctype === "YRP Delivery Challan"
	? new Set(["total_delivered_qty", "stock_value"])
	: payload.value.record?.doctype === "YRP Goods Received Note"
		? new Set(["total_received_quantity", "total"])
		: new Set())
const summaryDetails = computed(() => (payload.value.details || []).filter((field) => summaryFieldnames.value.has(field.fieldname)))
const visibleDetails = computed(() => {
	const excluded = payload.value.context?.work_order
		? new Set(["naming_series", "work_order", "against", "against_id", "supplier", "supplier_name", "item", "lot", "production_detail", ...summaryFieldnames.value])
		: new Set()
	return (payload.value.details || []).filter((field) => !excluded.has(field.fieldname))
})

watch(() => [props.visible, props.doctype, props.name], ([visible]) => { if (visible && props.name) load() }, { immediate: true })

/** `background` keeps the current document on screen while it refetches. */
async function load({ background = false } = {}) {
	if (background) refreshing.value = true
	else { loading.value = true; workflowReady.value = false }
	error.value = ""
	dirty.value = false
	try {
		const [document, workflow] = await Promise.all([getFabricStoreDocument(props.doctype, props.name), getActiveWorkflow(props.doctype)])
		payload.value = document || {}
		activeWorkflow.value = workflow
		workflowReady.value = true
		remoteChange.value = null
	}
	catch (reason) { error.value = reason?.message || `Unable to load ${props.doctype}.` }
	finally { loading.value = false; refreshing.value = false }
}

useDocRealtime(() => payload.value.record?.doctype || props.doctype, () => props.visible ? payload.value.record?.name || "" : "", {
	localModified: () => payload.value.record?.modified,
	isBusy: () => Boolean(acting.value) || loading.value || refreshing.value,
	onRemoteChange(change) {
		if (dirty.value) remoteChange.value = change
		else load({ background: true })
	},
})

const content = ref(null)
const canChangeStatus = (permission) => Boolean(!loading.value && payload.value.record && payload.value.permissions?.[permission] && workflowReady.value && !activeWorkflow.value)
useDocumentShortcuts({
	element: () => content.value,
	isBusy: () => loading.value || Boolean(acting.value),
	canSubmit: () => canChangeStatus("can_submit"),
	submit: () => changeStatus("submit"),
	canCancel: () => canChangeStatus("can_cancel"),
	cancel: () => changeStatus("cancel"),
	cancelConfirms: true,
})

async function changeStatus(action) {
	if (["submit", "cancel"].includes(action) && (!workflowReady.value || activeWorkflow.value)) return
	if (["cancel", "amend"].includes(action)) {
		const actionLabel = action === "cancel" ? "Cancel" : "Amend"
		return confirmAction({
			header: `${actionLabel} ${payload.value.record?.doctype}?`,
			message: action === "cancel"
				? `Cancel ${payload.value.record?.doctype} ${payload.value.record?.name}? This changes the document status and may affect linked work.`
				: `Create an amended draft from ${payload.value.record?.doctype} ${payload.value.record?.name}?`,
			acceptLabel: `${actionLabel} Document`,
			acceptIcon: action === "cancel" ? "pi pi-ban" : "pi pi-copy",
			accept: () => performStatusChange(action),
		})
	}
	return performStatusChange(action)
}

async function performStatusChange(action) {
	if (["submit", "cancel"].includes(action) && (!workflowReady.value || activeWorkflow.value)) return
	acting.value = action
	error.value = ""
	try {
		payload.value = await changeFabricStoreDocumentStatus(
			payload.value.record.doctype,
			payload.value.record.name,
			action,
			payload.value.record.modified,
		) || {}
		dirty.value = false
		emit("changed", payload.value)
		if (action === "amend") emit("amended", payload.value)
	} catch (reason) { error.value = reason?.message || `Unable to ${action} this document.` }
	finally { acting.value = "" }
}

async function completeTransfer() {
	acting.value = "complete-transfer"
	error.value = ""
	try {
		const created = await completeWorkOrderDocumentTransfer(payload.value.record.doctype, payload.value.record.name)
		emit("replacement", created)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to complete this transfer."
	} finally {
		acting.value = ""
	}
}

function stockEntryPath(name) { return `/app/yrp-stock-entry/${encodeURIComponent(name)}` }
async function endTransit() {
	acting.value = "end-transit"
	error.value = ""
	try {
		receiptEditor.value = await endStockEntryTransit(payload.value.record.name)
		receiptVisible.value = true
	} catch (reason) { error.value = reason?.message || "Unable to prepare the receiving entry." }
	finally { acting.value = "" }
}
async function receiptChanged(saved) {
	await load({ background: true })
	emit("changed", saved)
}

function requestVisibility(value) {
	if (value) return
	if (props.editable && dirty.value) { closeConfirmationVisible.value = true; return }
	closeNow()
}
function editDocument() { emit("edit", payload.value); emit("update:visible", false) }
function closeNow() { closeConfirmationVisible.value = false; dirty.value = false; emit("update:visible", false) }
function markDirty(value = true) { dirty.value = Boolean(value) }
function formatField(field) {
	if (["Date", "Datetime"].includes(field.fieldtype)) return formatDisplayByFieldtype(field.value, field.fieldtype)
	if (field.fieldtype === "Check") return Number(field.value) ? "Yes" : "No"
	return field.value === null || field.value === undefined || field.value === "" ? "—" : String(field.value)
}

defineExpose({ markDirty, reload: load })
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.document-transaction-dialog__content { display: grid; min-height: 180px; overflow-y: visible; gap: 10px; padding: 2px; }
.document-transaction-dialog__loading { display: grid; gap: var(--erp-space-2); }
.document-transaction-dialog__status-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.document-transaction-dialog__status-row small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.document-status { padding: 4px 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 800; text-transform: uppercase; background: var(--erp-surface-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); }
.document-status--submitted { color: var(--erp-success-text); background: var(--erp-success-soft); border-color: color-mix(in srgb, var(--erp-success) 22%, var(--erp-surface)); }
.document-status--cancelled { color: var(--erp-danger); background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 28%, var(--erp-border)); }
.document-summary-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); overflow: hidden; background: var(--erp-surface); border: 1px solid var(--erp-border-strong); border-radius: var(--erp-control-radius); box-shadow: inset 3px 0 0 var(--erp-accent), var(--erp-shadow-xs); }
.document-summary-metric { display: grid; min-height: 58px; align-content: center; gap: 2px; padding: 8px 12px; border-right: 1px solid var(--erp-border); }
.document-summary-metric:last-child { border-right: 0; }
.document-summary-metric span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.document-summary-metric strong { color: var(--erp-accent-hover); font-size: 18px; font-weight: 780; font-variant-numeric: tabular-nums; }
.document-detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; background: var(--erp-border); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); gap: 1px; }
.document-detail-grid > div { display: grid; min-height: 48px; align-content: center; gap: 2px; padding: 7px 10px; background: var(--erp-surface); }
.document-detail-grid span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.document-detail-grid strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.document-detail-grid .document-detail-link { color: var(--erp-accent); }
.document-items-unavailable { display: flex; align-items: center; gap: 10px; padding: 14px; color: var(--erp-text-muted); background: color-mix(in srgb, var(--erp-warning) 7%, var(--erp-surface)); border: 1px solid color-mix(in srgb, var(--erp-warning) 24%, var(--erp-surface)); border-radius: var(--erp-control-radius); }
.document-items-unavailable > i { color: var(--erp-warning); }
.document-items-unavailable div { display: grid; gap: 2px; }
.document-items-unavailable strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.document-items-unavailable span { font-size: var(--erp-font-size-min); }
.document-transaction-dialog__footer { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.document-transaction-dialog__footer > div { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.document-transaction-dialog__footer :deep(.p-button) { white-space: nowrap; }
.dirty-close-copy { margin: 0; color: var(--erp-text-muted); line-height: 1.55; }
@media (max-width: 900px) { .document-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .document-transaction-dialog__footer { align-items: stretch; flex-direction: column; } .document-transaction-dialog__footer > div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .document-transaction-dialog__footer :deep(.p-button) { width: 100%; } }
@media (max-width: 480px) { .document-summary-strip, .document-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .document-summary-metric { min-height: 52px; padding: 7px 9px; } .document-detail-grid > div { min-height: 46px; padding: 6px 8px; } }
</style>

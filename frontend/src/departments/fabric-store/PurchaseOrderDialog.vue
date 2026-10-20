<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		maximizable
		:header="dialogTitle"
		class="purchase-order-dialog erp-entity-dialog erp-dialog--lg"
		@update:visible="requestVisibility"
	>
		<div class="purchase-order-dialog__content">
			<div v-if="loading" class="purchase-order-loading"><Skeleton v-for="index in 6" :key="index" height="3rem" /></div>
			<template v-else>
				<div v-if="payload.record" class="purchase-order-status-row">
					<div><DocumentStatusBadge :docstatus="payload.record.docstatus" :label="payload.record.status" /><strong>{{ payload.record.supplier_name || payload.record.supplier || "—" }}</strong></div>
					<small>Updated {{ formatDate(payload.record.modified, true) }}</small>
				</div>
				<section v-if="payload.details?.length" class="purchase-order-detail-grid">
					<div v-for="field in payload.details" :key="field.fieldname"><span>{{ field.label }}</span><strong :class="{ 'purchase-order-detail-link': field.fieldtype === 'Link' }" :title="formatField(field)">{{ formatField(field) }}</strong></div>
				</section>
				<StockItemMatrix :dimensions="payload.dimensions || []" v-if="payload.item_groups?.length" :groups="payload.item_groups" doctype="Purchase Order" :physical-row-count="payload.item_row_count || 0" />
				<div v-else class="purchase-order-empty"><i class="pi pi-inbox" /><div><strong>No item details</strong><span>This Purchase Order has no grouped item quantities to display.</span></div></div>
				<Message v-if="payload.grn && !payload.grn.can_create && payload.grn.reason" severity="secondary" :closable="false">{{ payload.grn.reason }}</Message>
			</template>
		</div>

		<template #footer>
			<div class="purchase-order-footer">
				<Button label="Close" severity="secondary" text :disabled="acting" @click="requestVisibility(false)" />
				<div>
					<DocumentPrintButton v-if="payload.permissions?.can_print" doctype="Purchase Order" :name="payload.record?.name || currentName" :formats="payload.print_formats || []" :disabled="Boolean(acting)" />
					<Button v-if="payload.permissions?.can_amend" label="Amend" icon="pi pi-copy" severity="secondary" outlined :loading="acting === 'amend'" @click="changeStatus('amend')" />
					<Button v-if="payload.permissions?.can_cancel" label="Cancel Document" icon="pi pi-ban" severity="danger" outlined :loading="acting === 'cancel'" @click="changeStatus('cancel')" />
					<Button v-if="payload.permissions?.can_submit" label="Submit" icon="pi pi-check" severity="secondary" outlined :loading="acting === 'submit'" @click="changeStatus('submit')" />
					<Button v-if="payload.grn?.can_create" label="Create GRN" icon="pi pi-plus" @click="grnVisible = true" />
				</div>
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" :title="`${dialogTitle} could not be completed`" @dismiss="error = ''" />

	<RelatedDocumentWorkspaceDialog
		v-model:visible="grnVisible"
		doctype="YRP Goods Received Note"
		:source-context="{ purchase_order: currentName }"
		@changed="grnChanged"
	/>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { changeFabricStoreDocumentStatus, getPurchaseOrderWorkspace } from "../../api/fabricStore.js"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import StockItemMatrix from "../../components/stock/StockItemMatrix.vue"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import RelatedDocumentWorkspaceDialog from "./RelatedDocumentWorkspaceDialog.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	purchaseOrder: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()

const currentName = ref("")
const loading = ref(false)
const acting = ref("")
const error = ref("")
const payload = ref({})
const grnVisible = ref(false)
const dialogTitle = computed(() => `Purchase Order${currentName.value ? ` · ${currentName.value}` : ""}`)

watch(() => [props.visible, props.purchaseOrder], ([visible, purchaseOrder]) => {
	if (!visible || !purchaseOrder) return
	currentName.value = purchaseOrder
	load()
}, { immediate: true })

async function load() {
	loading.value = true
	error.value = ""
	try { payload.value = await getPurchaseOrderWorkspace(currentName.value) || {} }
	catch (reason) { error.value = reason?.message || "Unable to load this Purchase Order." }
	finally { loading.value = false }
}

async function changeStatus(action) {
	if (["cancel", "amend"].includes(action)) {
		const actionLabel = action === "cancel" ? "Cancel" : "Amend"
		return confirmAction({
			header: `${actionLabel} Purchase Order?`,
			message: action === "cancel"
				? `Cancel Purchase Order ${currentName.value}? This changes the document status and may affect linked work.`
				: `Create an amended draft from Purchase Order ${currentName.value}?`,
			acceptLabel: `${actionLabel} Document`,
			acceptIcon: action === "cancel" ? "pi pi-ban" : "pi pi-copy",
			accept: () => performStatusChange(action),
		})
	}
	return performStatusChange(action)
}

async function performStatusChange(action) {
	acting.value = action
	error.value = ""
	try {
		const changed = await changeFabricStoreDocumentStatus("Purchase Order", currentName.value, action, payload.value.record?.modified)
		if (action === "amend" && changed?.record?.name) currentName.value = changed.record.name
		await load()
		emit("changed", payload.value)
	} catch (reason) { error.value = reason?.message || `Unable to ${action} this Purchase Order.` }
	finally { acting.value = "" }
}

async function grnChanged(saved) {
	await load()
	emit("changed", saved)
}
function requestVisibility(value) { if (!value) emit("update:visible", false) }
function formatField(field) {
	if (["Date", "Datetime"].includes(field.fieldtype)) return formatDate(field.value, field.fieldtype === "Datetime")
	if (field.fieldtype === "Check") return Number(field.value) ? "Yes" : "No"
	if (["Currency", "Float", "Int", "Percent"].includes(field.fieldtype) && field.value !== "") return Number(field.value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return field.value === null || field.value === undefined || field.value === "" ? "—" : String(field.value)
}
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} · ${match[4]}:${match[5]}` : date }
</script>

<style scoped>
.purchase-order-dialog__content { display: grid; min-height: 240px; overflow-y: visible; gap: var(--erp-space-3); padding: 1px; }
.purchase-order-loading { display: grid; gap: var(--erp-space-2); }
.purchase-order-status-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.purchase-order-status-row > div { display: flex; align-items: center; gap: 10px; }
.purchase-order-status-row > div > strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.purchase-order-status-row small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.document-status { padding: 4px 9px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-bold); text-transform: uppercase; background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); }
.document-status--submitted { color: var(--erp-success); background: var(--erp-success-soft); }
.document-status--cancelled { color: var(--erp-danger); background: var(--erp-danger-soft); }
.purchase-order-detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 5px 16px rgb(28 61 45 / 4%); }
.purchase-order-detail-grid > div { display: grid; min-height: 56px; align-content: center; gap: 4px; padding: 9px 11px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.purchase-order-detail-grid span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; }
.purchase-order-detail-grid strong { overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.purchase-order-detail-grid .purchase-order-detail-link { color: var(--erp-accent); }
.purchase-order-empty { display: flex; min-height: 112px; align-items: center; justify-content: center; gap: 10px; padding: 16px; color: var(--erp-text-muted); background: color-mix(in srgb, var(--erp-surface-soft) 72%, var(--erp-surface)); border: 1px dashed var(--erp-border-strong); border-radius: var(--erp-control-radius); }
.purchase-order-empty div { display: grid; gap: 2px; }
.purchase-order-empty strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.purchase-order-empty span { font-size: var(--erp-font-size-min); }
.purchase-order-footer { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.purchase-order-footer > div { display: flex; align-items: center; justify-content: flex-end; gap: var(--erp-space-2); }
@media (max-width: 900px) { .purchase-order-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .purchase-order-detail-grid > div { min-height: 50px; padding: 7px 9px; } .purchase-order-footer { align-items: stretch; flex-direction: column; } .purchase-order-footer > div { flex-wrap: wrap; } }
</style>

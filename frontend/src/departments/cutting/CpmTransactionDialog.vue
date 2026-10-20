<template>
	<Dialog :visible="visible" modal dismissable-mask maximizable :header="record ? `${record.doctype} · ${record.name}` : 'Transaction'" class="erp-transaction-dialog erp-entity-dialog erp-dialog--lg" @update:visible="emit('update:visible', $event)">
		<div v-if="loading" class="erp-transaction-loading"><Skeleton v-for="index in 5" :key="index" height="3rem" /></div>
		<div v-else class="erp-transaction-detail">
			<div v-if="record" class="erp-transaction-status"><DocumentStatusBadge :docstatus="record.docstatus" :label="record.status" /><small>Updated {{ formatDate(record.modified, true) }}</small></div>
			<section v-if="record?.details?.length" class="erp-detail-grid"><div v-for="row in record.details" :key="row.fieldname"><span>{{ row.label }}</span><strong>{{ display(row.value) }}</strong></div></section>
			<StockItemMatrix :dimensions="record.dimensions || []" v-if="record?.item_groups?.length" :groups="record.item_groups" :doctype="record.doctype" :physical-row-count="record.item_row_count || 0" />
			<section v-else-if="record?.item_row_count" class="erp-items-empty"><i class="pi pi-exclamation-circle"></i><div><strong>Item matrix unavailable</strong><span>The transaction has item rows, but their parent-item attributes could not be resolved.</span></div></section>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="saving" @click="emit('update:visible', false)" />
			<DocumentDeleteButton v-if="record?.name" :doctype="record.doctype" :name="record.name" :docstatus="record.docstatus" :disabled="saving" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record?.permissions?.can_print" :doctype="record.doctype" :name="record.name" :formats="record.print_formats || []" :disabled="saving" />
			<Button v-if="record?.permissions?.can_cancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :loading="saving" @click="changeStatus('cancel')" />
			<Button v-if="record?.permissions?.can_submit" label="Submit" icon="pi pi-check" :loading="saving" @click="changeStatus('submit')" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Transaction could not be updated" />
</template>

<script setup>
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import { ref, watch } from "vue"

import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { changeLinkedTransactionStatus, getLinkedTransaction } from "./cpmApi.js"
import DocumentPrintButton from "./DocumentPrintButton.vue"
import StockItemMatrix from "./StockItemMatrix.vue"

const props = defineProps({ visible: Boolean, cuttingPlan: { type: String, required: true }, transaction: { type: Object, default: null } })
const emit = defineEmits(["update:visible", "changed"])
const confirmAction = useActionConfirmation()
const record = ref(null)
const loading = ref(false)
const saving = ref(false)
const error = ref("")

watch(() => [props.visible, props.transaction?.doctype, props.transaction?.name], ([visible]) => { if (visible) load() })

async function load() {
	if (!props.transaction?.name) return
	loading.value = true
	error.value = ""
	try {
		record.value = await getLinkedTransaction(props.cuttingPlan, props.transaction.doctype, props.transaction.name)
	} catch (reason) {
		error.value = reason.message || "Unable to load the transaction."
	} finally {
		loading.value = false
	}
}

async function changeStatus(action) {
	if (action === "submit") return confirmAction({
		header: `Submit ${record.value.doctype}?`,
		message: `Permanently submit ${record.value.doctype} ${record.value.name}?`,
		acceptLabel: "Submit",
		acceptIcon: "pi pi-check",
		acceptSeverity: "primary",
		accept: () => performStatusChange(action),
	})
	if (action === "cancel") return confirmAction({
		header: `Cancel ${record.value.doctype}?`,
		message: `Cancel ${record.value.doctype} ${record.value.name}? This changes the document status and cannot be undone here.`,
		acceptLabel: "Cancel Document",
		acceptIcon: "pi pi-ban",
		accept: () => performStatusChange(action),
	})
	return performStatusChange(action)
}

async function performStatusChange(action) {
	saving.value = true
	error.value = ""
	try {
		record.value = await changeLinkedTransactionStatus(props.cuttingPlan, record.value.doctype, record.value.name, action)
		emit("changed", record.value)
	} catch (reason) {
		error.value = reason.message || `Unable to ${action} the transaction.`
	} finally {
		saving.value = false
	}
}

function display(value) { return value === null || value === undefined || value === "" ? "—" : String(value) }
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} ${match[4]}:${match[5]}` : date }
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.erp-transaction-loading,.erp-transaction-detail{display:grid;gap:14px}.erp-transaction-status{display:flex;align-items:center;justify-content:space-between}.erp-transaction-status small{color:var(--erp-text-muted);font-size:var(--erp-font-size-min)}.erp-status{padding:4px 9px;border-radius:var(--erp-pill-radius);background:var(--erp-surface-muted);color:var(--erp-text-secondary);font-size:var(--erp-font-size-min);font-weight:700;text-transform:uppercase}.erp-status--submitted{background:var(--erp-success-soft);color:var(--erp-success-text)}.erp-status--cancelled{background:var(--erp-danger-soft);color:var(--erp-danger)}.erp-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius)}.erp-detail-grid>div{display:grid;gap:4px;padding:11px 13px;border-right:1px solid var(--erp-border);border-bottom:1px solid var(--erp-border)}.erp-detail-grid span{color:var(--erp-text-muted);font-size:var(--erp-font-size-min);text-transform:uppercase}.erp-detail-grid strong{overflow:hidden;color:var(--erp-text);font-size:13px;text-overflow:ellipsis}.erp-items-empty{display:flex;align-items:center;gap:10px;padding:16px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface-soft);color:var(--erp-text-muted)}.erp-items-empty>i{color:var(--erp-warning)}.erp-items-empty>div{display:grid;gap:2px}.erp-items-empty strong{color:var(--erp-text);font-size:var(--erp-font-size-caption)}.erp-items-empty span{font-size:var(--erp-font-size-min)}@media(max-width:750px){.erp-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>

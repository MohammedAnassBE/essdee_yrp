<template>
	<Dialog
		:visible="visible"
		modal
		maximizable
		:dismissable-mask="false"
		:closable="!busy"
		:close-on-escape="!busy"
		:header="record?.name ? `Cut Panel Movement · ${record.name}` : 'New Cut Panel Movement'"
		class="erp-cut-panel-movement-dialog erp-entity-dialog erp-dialog--xl"
		@update:visible="emit('update:visible', $event)"
	>
		<div v-if="loading" class="movement-dialog__loading"><Skeleton v-for="index in 7" :key="index" height="3rem" /></div>
		<div v-else class="movement-dialog__body">
			<div class="cut-panel-movement-layout" :class="{ 'cut-panel-movement-layout--without-rail': !record }">
				<div class="cut-panel-movement-layout__main">
					<section class="movement-document-card">
						<header><span>DOCUMENT</span><h3>Movement source & posting</h3><DocumentStatusBadge :docstatus="record?.docstatus" :label="record?.status || 'Draft'" /></header>
						<div class="movement-document-grid">
							<LinkField v-model="form.lot" doctype="SD YRP Lot" label="Lot" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
							<LinkField v-model="form.from_warehouse" doctype="Supplier" label="From Warehouse" required :disabled="Boolean(record) || busy" @update:model-value="sourceChanged" />
							<div class="movement-context-value"><span>Item</span><strong>{{ editor.context?.item || "Derived from Lot" }}</strong></div>
							<DateField v-model="form.posting_date" label="Posting Date" required :disabled="!form.edit_posting_date_and_time || busy" />
							<TimeField v-model="form.posting_time" label="Posting Time" required :disabled="!form.edit_posting_date_and_time || busy" />
							<label class="movement-toggle"><span>Edit Posting Date and Time</span><ToggleSwitch v-model="form.edit_posting_date_and_time" :disabled="busy" /></label>
						</div>
					</section>

					<CutPanelMovementEditor
						ref="movementEditor"
						:model-value="movementData"
						:context="editor.context"
						:record="record"
						:editable="canEdit"
						:generated="generated"
						:show-generate="canEdit"
						:generating="acting === 'generate'"
						@update:model-value="replaceMovement"
						@generate="generateBundles"
					/>
				</div>
				<CutPanelMovementRail
					v-if="record"
					:linked="linked"
					:loading="linkedLoading"
					:busy="busy"
					@refresh="loadLinked"
					@create="openTransactionCreator"
					@open-document="openLinkedDocument"
				/>
			</div>
		</div>

		<template #footer>
			<div class="movement-dialog__footer">
				<span>{{ hasSelection ? selectionSummaryText : "Generate current stock, then select what is moving." }}</span>
				<div>
					<Button label="Close" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
					<DocumentDeleteButton v-if="record?.name" doctype="SD YRP Cut Panel Movement" document-label="Cut Panel Movement" :name="record.name" :docstatus="record.docstatus" :disabled="busy" :redirect="false" @deleted="documentDeleted" />
					<DocumentPrintButton v-if="record?.name" doctype="SD YRP Cut Panel Movement" :name="record.name" :docstatus="record.docstatus" :disabled="busy" />
					<Button v-if="record?.permissions?.can_cancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :disabled="busy" @click="requestCommand('cancel')" />
					<Button v-if="record?.permissions?.can_submit" label="Submit" icon="pi pi-check" severity="secondary" outlined :disabled="busy || !hasSelection" @click="requestCommand('submit')" />
					<Button v-if="canEdit" label="Save" icon="pi pi-save" :loading="acting === 'save'" :disabled="busy || !generated" @click="save" />
				</div>
			</div>
		</template>
	</Dialog>

	<Dialog
		v-model:visible="transactionCreateVisible"
		modal
		:dismissable-mask="false"
		:header="transactionCreateTitle"
		class="cut-panel-transaction-create-dialog erp-entity-dialog erp-dialog--md"
	>
		<div class="transaction-create-content">
			<div class="transaction-create-source"><span>Cut Panel Movement</span><strong>{{ record?.name }}</strong><small>{{ editor.context?.lot }} · {{ editor.context?.item }}</small></div>
			<LinkField v-if="createOperation === 'stock_entry'" v-model="transactionForm.to_warehouse" label="To Warehouse" doctype="Warehouse" required :show-open-button="false" />
			<label v-if="createOperation === 'stock_entry'" class="movement-toggle"><span>Skip Transit</span><Checkbox v-model="transactionForm.skip_transit" binary :disabled="busy" /></label>
			<template v-else>
				<div class="transaction-work-order-heading"><span>Submitted Work Orders for this Lot</span><strong>{{ workOrders.length }}</strong></div>
				<div v-if="workOrdersLoading" class="transaction-work-order-loading"><Skeleton v-for="index in 3" :key="index" height="3.5rem" /></div>
				<div v-else-if="workOrders.length" class="transaction-work-orders">
					<button v-for="workOrder in workOrders" :key="workOrder.name" type="button" :class="{ selected: transactionForm.work_order === workOrder.name }" :aria-pressed="transactionForm.work_order === workOrder.name" @click="transactionForm.work_order = workOrder.name">
						<span><strong>{{ [workOrder.name, workOrder.process_name, workOrder.supplier].filter(Boolean).join(' · ') }}</strong><i v-if="transactionForm.work_order === workOrder.name" class="pi pi-check-circle" /></span>
						<small>{{ [workOrder.item, workOrder.supplier].filter(Boolean).join(' · ') || editor.context?.lot }}</small>
					</button>
				</div>
				<div v-else class="transaction-work-orders-empty">No submitted Work Orders are available for {{ editor.context?.lot }}.</div>
			</template>
		</div>
		<template #footer>
			<Button label="Close" severity="secondary" text :disabled="creatingTransaction" @click="transactionCreateVisible = false" />
			<Button :label="transactionCreateButtonLabel" icon="pi pi-plus" :loading="creatingTransaction" :disabled="!canCreateTransaction" @click="createTransaction" />
		</template>
	</Dialog>

	<StockDocumentDialog v-model:visible="stockDocumentVisible" :name="linkedDocumentName" :docstatus="linkedDocumentDocstatus" @changed="linkedDocumentChanged" />
	<RelatedDocumentWorkspaceDialog v-model:visible="relatedDocumentVisible" :doctype="linkedDocumentDoctype" :name="linkedDocumentName" @changed="linkedDocumentChanged" @closed="relatedDocumentVisible = false" />

	<DocumentConfirmationDialog
		v-model:visible="confirmationVisible"
		:title="pendingCommand === 'cancel' ? 'Cancel Cut Panel Movement?' : 'Submit Cut Panel Movement?'"
		:message="pendingCommand === 'cancel' ? `Cancel ${record?.name}?` : `Submit ${record?.name}? Stock will be validated again before submission.`"
		:confirm-label="pendingCommand === 'cancel' ? 'Cancel Movement' : 'Submit Movement'"
		:severity="pendingCommand === 'cancel' ? 'danger' : 'success'"
		:busy="acting === pendingCommand"
		@confirm="confirmCommand"
	/>
	<DocumentErrorDialog :message="error" title="Cut Panel Movement action failed" @dismiss="error = ''" />
</template>

<script setup>
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import { useRouter } from "vue-router"
import { webDocumentRoute } from "../../router/webDocumentRoutes.js"
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Skeleton from "primevue/skeleton"
import ToggleSwitch from "primevue/toggleswitch"
import { computed, reactive, ref, watch } from "vue"

import { createCutPanelMovementTransaction, executeCutPanelMovementCommand, generateCutPanelMovementBundles, getCutPanelMovementEditor, getCutPanelMovementLinkedDocuments, getCutPanelMovementWorkOrders, saveCutPanelMovement } from "../../api/cutPanelStore.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import TimeField from "../../components/common/TimeField.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import CutPanelMovementEditor from "../cutting/CutPanelMovementEditor.vue"
import RelatedDocumentWorkspaceDialog from "../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import StockDocumentDialog from "../fabric-store/StockDocumentDialog.vue"
import CutPanelMovementRail from "./CutPanelMovementRail.vue"

const router = useRouter()
const props = defineProps({ visible: Boolean, movement: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "changed"])
const loading = ref(false)
const acting = ref("")
const error = ref("")
const generated = ref(false)
const confirmationVisible = ref(false)
const pendingCommand = ref("")
const movementEditor = ref(null)
const editor = reactive({ context: {}, permissions: {}, record: null })
const form = reactive({ lot: "", from_warehouse: "", posting_date: "", posting_time: "", edit_posting_date_and_time: false })
const movementData = reactive(emptyMovement())
const linked = reactive({ sections: {}, actions: {} })
const linkedLoading = ref(false)
const transactionCreateVisible = ref(false)
const createOperation = ref("")
const creatingTransaction = ref(false)
const workOrdersLoading = ref(false)
const workOrders = ref([])
const transactionForm = reactive({ to_warehouse: "", work_order: "", skip_transit: false })
const stockDocumentVisible = ref(false)
const relatedDocumentVisible = ref(false)
const linkedDocumentDoctype = ref("")
const linkedDocumentName = ref("")
const linkedDocumentDocstatus = ref(0)
let loadSequence = 0
let actionSequence = 0
const record = computed(() => editor.record)
const busy = computed(() => Boolean(acting.value))
const canEdit = computed(() => record.value ? Boolean(record.value.permissions?.can_write) : Boolean(editor.permissions?.can_create))
const hasSelection = computed(() => Boolean(movementEditor.value?.hasSelection))
const selectionSummaryText = computed(() => movementEditor.value?.selectionSummaryText || "")
const transactionLabels = { stock_entry: "Stock Entry", delivery_challan: "Delivery Challan", goods_received_note: "Goods Received Note" }
const transactionCreateTitle = computed(() => `Create ${transactionLabels[createOperation.value] || "Movement transaction"}`)
const transactionCreateButtonLabel = computed(() => `Create ${transactionLabels[createOperation.value] || "Document"}`)
const canCreateTransaction = computed(() => createOperation.value === "stock_entry" ? Boolean(transactionForm.to_warehouse) : Boolean(transactionForm.work_order))

watch(() => [props.visible, props.movement], ([visible]) => {
	if (visible) load()
	else {
		loadSequence += 1
		actionSequence += 1
		loading.value = false
		linkedLoading.value = false
		acting.value = ""
		creatingTransaction.value = false
		workOrdersLoading.value = false
	}
})

async function load() {
	const sequence = ++loadSequence
	actionSequence += 1
	const requestedMovement = props.movement
	loading.value = true; error.value = ""; generated.value = false
	resetLoadedState()
	try {
		const payload = await getCutPanelMovementEditor(requestedMovement)
		if (loadIsStale(sequence, requestedMovement)) return
		Object.assign(editor, payload || {})
		Object.assign(form, payload?.defaults || {})
		form.edit_posting_date_and_time = Boolean(form.edit_posting_date_and_time)
		replaceMovement(payload?.movement_data || payload?.record?.movement_data || {})
		generated.value = Boolean(payload?.record)
		if (payload?.record?.name) await loadLinked(sequence, payload.record.name)
		else Object.assign(linked, { sections: {}, actions: {} })
	} catch (reason) {
		if (!loadIsStale(sequence, requestedMovement)) error.value = reason.message || "Unable to load the Cut Panel Movement."
	} finally {
		if (!loadIsStale(sequence, requestedMovement)) loading.value = false
	}
}

function loadIsStale(sequence, requestedMovement) {
	return sequence !== loadSequence || !props.visible || requestedMovement !== props.movement
}

function actionIsStale(sequence, requestedMovement, requestedLoadSequence) {
	return sequence !== actionSequence || requestedLoadSequence !== loadSequence || !props.visible || requestedMovement !== props.movement
}

function resetLoadedState() {
	for (const key of Object.keys(editor)) delete editor[key]
	Object.assign(editor, { context: {}, permissions: {}, record: null })
	Object.assign(form, { lot: "", from_warehouse: "", posting_date: "", posting_time: "", edit_posting_date_and_time: false })
	replaceMovement({})
	Object.assign(linked, { sections: {}, actions: {} })
	transactionCreateVisible.value = false
	stockDocumentVisible.value = false
	relatedDocumentVisible.value = false
}

function sourceChanged() { generated.value = false; replaceMovement({}) }

async function generateBundles() {
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedLoadSequence = loadSequence
	const request = { ...form }
	acting.value = "generate"; error.value = ""
	try {
		const payload = await generateCutPanelMovementBundles(request)
		if (actionIsStale(sequence, requestedMovement, requestedLoadSequence)) return
		replaceMovement(payload || {}); generated.value = true
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) error.value = reason.message || "Unable to generate the available bundles."
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) acting.value = ""
	}
}

async function save() {
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedLoadSequence = loadSequence
	const request = { ...form, movement_data: clone(movementData) }
	const requestedRecord = record.value?.name
	const expectedModified = record.value?.modified
	acting.value = "save"; error.value = ""
	try {
		const saved = await saveCutPanelMovement(request, { name: requestedRecord, expectedModified })
		if (actionIsStale(sequence, requestedMovement, requestedLoadSequence)) return
		editor.record = saved; Object.assign(editor.context, { lot: saved.lot, item: saved.item, source_supplier: saved.from_warehouse }); replaceMovement(saved.movement_data || {}); generated.value = true; await loadLinked(); emit("changed", saved)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) error.value = reason.message || "Unable to save the Cut Panel Movement."
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) acting.value = ""
	}
	}

async function loadLinked(parentSequence = loadSequence, requestedRecord = record.value?.name) {
	if (!requestedRecord) return
	linkedLoading.value = true
	try {
		const nextLinked = await getCutPanelMovementLinkedDocuments(requestedRecord) || { sections: {}, actions: {} }
		if (parentSequence !== loadSequence || !props.visible || requestedRecord !== record.value?.name) return
		Object.assign(linked, nextLinked)
	} catch (reason) {
		if (parentSequence === loadSequence && props.visible && requestedRecord === record.value?.name) error.value = reason.message || "Unable to load linked movement documents."
	} finally {
		if (parentSequence === loadSequence && props.visible && requestedRecord === record.value?.name) linkedLoading.value = false
	}
}

async function openTransactionCreator(operation) {
	if (busy.value) return
	createOperation.value = operation
	transactionForm.to_warehouse = ""
	transactionForm.work_order = ""
	transactionForm.skip_transit = false
	workOrders.value = []
	transactionCreateVisible.value = true
	if (operation === "stock_entry") return
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value.name
	workOrdersLoading.value = true
	try {
		const nextWorkOrders = await getCutPanelMovementWorkOrders(requestedRecord) || []
		if (actionIsStale(sequence, requestedMovement, requestedLoadSequence) || requestedRecord !== record.value?.name) return
		workOrders.value = nextWorkOrders
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) { transactionCreateVisible.value = false; error.value = reason.message || "Unable to load Work Orders for this movement." }
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) workOrdersLoading.value = false
	}
}

async function createTransaction() {
	if (!canCreateTransaction.value || !record.value?.name) return
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value.name
	const requestedOperation = createOperation.value
	const request = { ...transactionForm }
	creatingTransaction.value = true
	try {
		const result = await createCutPanelMovementTransaction(requestedRecord, requestedOperation, request)
		if (actionIsStale(sequence, requestedMovement, requestedLoadSequence) || requestedRecord !== record.value?.name) return
		transactionCreateVisible.value = false
		Object.assign(linked, result?.linked_documents || { sections: {}, actions: {} })
		emit("changed", result?.record)
		openLinkedDocument(result?.record)
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) error.value = reason.message || `Unable to create the ${transactionLabels[requestedOperation] || "movement transaction"}.`
	} finally { if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) creatingTransaction.value = false }
}

function openLinkedDocument(document) {
	if (!document?.name || !document?.doctype) return
	if (["YRP Delivery Challan", "YRP Goods Received Note"].includes(document.doctype)) {
		router.push(webDocumentRoute(document.doctype, document.name, "/web/cut-panel-store"))
		return
	}
	linkedDocumentDoctype.value = document.doctype
	linkedDocumentName.value = document.name
	linkedDocumentDocstatus.value = Number(document.docstatus || 0)
	if (document.doctype === "YRP Stock Entry") stockDocumentVisible.value = true
	else relatedDocumentVisible.value = true
}

async function linkedDocumentChanged() {
	await loadLinked()
	emit("changed", record.value)
}

function requestCommand(command) { pendingCommand.value = command; confirmationVisible.value = true }
async function confirmCommand() {
	const sequence = ++actionSequence
	const requestedMovement = props.movement
	const requestedLoadSequence = loadSequence
	const requestedRecord = record.value?.name
	const expectedModified = record.value?.modified
	const command = pendingCommand.value; acting.value = command; error.value = ""
	try {
		const changed = await executeCutPanelMovementCommand(requestedRecord, command, expectedModified)
		if (actionIsStale(sequence, requestedMovement, requestedLoadSequence) || requestedRecord !== record.value?.name) return
		editor.record = changed; replaceMovement(changed.movement_data || movementData); confirmationVisible.value = false; emit("changed", changed)
		if (command === "cancel") emit("update:visible", false)
		else await loadLinked()
	} catch (reason) {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) { confirmationVisible.value = false; error.value = reason.message || `Unable to ${command} the Cut Panel Movement.` }
	} finally {
		if (!actionIsStale(sequence, requestedMovement, requestedLoadSequence)) { acting.value = ""; pendingCommand.value = "" }
	}
}

function replaceMovement(value) { Object.assign(movementData, emptyMovement(), clone(value)) }
function emptyMovement() { return { panels: [], data: {}, accessory_data: [], collapsed_details: [], is_set_item: 0 } }
function clone(value) { return JSON.parse(JSON.stringify(value || {})) }
function documentDeleted() {
	emit("update:visible", false)
	emit("changed")
}
</script>

<style scoped>
.movement-dialog__loading,.movement-dialog__body,.cut-panel-movement-layout__main{display:grid;gap:12px}.cut-panel-movement-layout{display:grid;grid-template-columns:minmax(0,4fr) minmax(230px,1fr);gap:12px;align-items:start}.cut-panel-movement-layout--without-rail{grid-template-columns:minmax(0,1fr)}.cut-panel-movement-layout__main{min-width:0}.movement-document-card{overflow:hidden;border:1px solid var(--erp-border);border-radius:var(--erp-panel-radius);background:var(--erp-surface)}.movement-document-card>header{display:flex;align-items:center;gap:9px;padding:11px 13px;border-bottom:1px solid var(--erp-border);background:var(--erp-surface-soft)}.movement-document-card>header span{color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.09em}.movement-document-card>header h3{margin:0;color:var(--erp-text);font-size:.96rem}.movement-document-card>header em{margin-left:auto;color:var(--erp-text-muted);font-size:var(--erp-font-size-caption);font-style:normal}.movement-document-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;padding:13px}.movement-context-value,.movement-toggle{display:grid;align-content:start;gap:7px}.movement-context-value span,.movement-toggle span{color:var(--erp-text);font-size:var(--erp-font-size-caption);font-weight:680}.movement-context-value strong{display:block;min-height:auto;padding:2px 0 7px;border:0;border-bottom:1px solid var(--erp-border);border-radius:0;background:transparent;color:var(--erp-text);font-size:13px;font-weight:750}.movement-toggle{justify-items:start}.movement-dialog__footer{display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%}.movement-dialog__footer>span{color:var(--erp-text-muted);font-size:var(--erp-font-size-caption)}.movement-dialog__footer>div{display:flex;gap:8px}.transaction-create-content{display:grid;gap:13px}.transaction-create-source{display:grid;grid-template-columns:minmax(0,1fr);gap:3px 10px;padding:12px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface-soft)}.transaction-create-source span{grid-row:auto;color:var(--erp-accent-hover);font-size:var(--erp-font-size-min);font-weight:800;letter-spacing:.07em;writing-mode:horizontal-tb}.transaction-create-source strong{color:var(--erp-text);font-size:13px}.transaction-create-source small{color:var(--erp-text-muted);font-size:11px}.transaction-work-order-heading{display:flex;justify-content:space-between;color:var(--erp-text-secondary);font-size:12px;font-weight:700}.transaction-work-order-heading strong{color:var(--erp-accent-hover)}.transaction-work-order-loading,.transaction-work-orders{display:grid;gap:7px}.transaction-work-orders button{display:grid;min-height:52px;gap:3px;padding:10px 11px;border:1px solid var(--erp-border);border-radius:var(--erp-control-radius);background:var(--erp-surface);color:var(--erp-text);text-align:left;cursor:pointer}.transaction-work-orders button:hover,.transaction-work-orders button.selected{border-color:var(--erp-accent);background:var(--erp-accent-soft)}.transaction-work-orders button>span{display:flex;align-items:center;justify-content:space-between}.transaction-work-orders button i{color:var(--erp-accent)}.transaction-work-orders button small,.transaction-work-orders-empty{color:var(--erp-text-muted);font-size:11px}.transaction-work-orders-empty{padding:18px;border:1px dashed var(--erp-border-strong);border-radius:var(--erp-control-radius);text-align:center}
@media(max-width:1050px){.cut-panel-movement-layout{grid-template-columns:minmax(0,1fr)}.movement-document-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.movement-document-grid{grid-template-columns:1fr}.movement-dialog__footer{align-items:stretch;flex-direction:column}.movement-dialog__footer>div{justify-content:flex-end;flex-wrap:wrap}}
</style>

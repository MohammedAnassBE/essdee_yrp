<template>
	<DepartmentPage title="Purchase Order" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<section class="fabric-purchase-order-frame">
			<FabricDocumentWorkspace
				doctype="Purchase Order"
				title="Purchase Order"
				:workspace="workspace"
				:loading="loading"
				:error="error || actionError"
				:acting="acting"
				:show-lifecycle-actions="false"
				@reload="loadWorkspace(true)"
				@action="runWorkspaceAction"
			>
				<template #header="{ record, headingId }">
					<div class="purchase-order-page__identity">
						<div><h1 class="erp-doc-title" :id="headingId">Purchase Order</h1><span class="erp-doc-id">{{ record.name }}</span></div>
						<DocumentStatusBadge :docstatus="record.docstatus" :label="record.status || statusLabel(record.docstatus)" />
						<div class="purchase-order-page__facts" role="region" aria-label="Purchase Order context" tabindex="0">
							<div><span>Supplier</span><strong :title="record.supplier_name || record.supplier || '—'">{{ record.supplier_name || record.supplier || "—" }}</strong></div>
							<div><span>Order date</span><strong>{{ formatDate(record.transaction_date) }}</strong></div>
							<div><span>Grand total</span><strong>{{ formatAmount(record.grand_total, record.currency) }}</strong></div>
						</div>
					</div>
				</template>

				<template #header-actions>
					<DocumentActionStrip :actions="purchaseOrderActions" />
				</template>

				<template #fields>
					<Tabs v-model:value="activeTab" class="purchase-order-tabs erp-tabs">
						<TabList><Tab value="overview">Overview</Tab><Tab value="items">Items <span v-if="workspace.item_row_count">{{ workspace.item_row_count }}</span></Tab></TabList>
						<TabPanels>
							<TabPanel value="overview">
								<DocumentOverview :fields="overviewFields" :definitions="overviewDefinitions" include-unclaimed :unclaimed-definition="overviewAdditionalDefinition" aria-label="Purchase Order overview" id-prefix="purchase-order-overview" />
							</TabPanel>
							<TabPanel value="items">
								<StockItemMatrix v-if="itemGroups.length" :groups="itemGroups" doctype="Purchase Order" :physical-row-count="workspace.item_row_count || 0" :currency="workspace.record?.currency || ''" group-by-item show-lot-column show-pricing show-fulfillment :show-received="false" :show-amount="false" pricing-before-fulfillment />
								<div v-else-if="!loading" class="purchase-order-page__empty"><i class="pi pi-inbox" /><div><strong>No item details</strong><span>This Purchase Order has no grouped item quantities.</span></div></div>
							</TabPanel>
						</TabPanels>
					</Tabs>
				</template>

				<template #rail>
					<section v-if="relatedDocuments.length" class="purchase-order-related" aria-label="Related Purchase Order documents">
						<header><span>Related documents</span><strong>{{ relatedDocuments.length }}</strong></header>
						<button v-for="row in relatedDocuments" :key="`${row.doctype}-${row.name}`" type="button" @click="openRelated(row.doctype, {}, row.name)">
							<div><strong>{{ row.name }}</strong><span>{{ row.label }}</span></div><DocumentStatusBadge :docstatus="row.docstatus" :label="statusLabel(row.docstatus)" /><i class="pi pi-chevron-right" />
						</button>
					</section>
					<div class="purchase-order-page__totals">
						<div v-for="total in workspace.totals || []" :key="total.fieldname" class="purchase-order-page__total" :class="{ 'purchase-order-page__total--primary': primaryTotalFieldnames.has(total.fieldname) }">
							<span>{{ total.label }}</span><strong>{{ formatTotal(total) }}</strong>
						</div>
					</div>
				</template>

				<template #panel>
					<Message v-if="workspace.grn && !workspace.grn.can_create && workspace.grn.reason" severity="secondary" :closable="false">{{ workspace.grn.reason }}</Message>
				</template>
			</FabricDocumentWorkspace>
		</section>

		<RelatedDocumentWorkspaceDialog
			v-model:visible="relatedVisible"
			:doctype="relatedDoctype"
			:name="relatedName"
			:source-context="relatedSourceContext"
			@changed="relatedChanged"
			@closed="relatedVisible = false"
		/>
		<DocumentConfirmationDialog v-model:visible="lifecycleConfirmVisible" :title="lifecycleConfirmTitle" :message="lifecycleConfirmMessage" :confirm-label="lifecycleConfirmLabel" :busy="Boolean(acting)" @confirm="confirmLifecycleAction" />

		<Dialog v-model:visible="lotEditorVisible" modal header="Manage Linked Lots" class="fabric-action-dialog erp-dialog--md">
			<div class="purchase-order-lots">
				<div class="purchase-order-lots__list">
					<span v-for="lot in lotDraft" :key="lot" class="purchase-order-lots__chip">{{ lot }}<Button icon="pi pi-times" severity="secondary" text rounded :aria-label="`Remove ${lot}`" @click="removeLot(lot)" /></span>
					<span v-if="!lotDraft.length" class="purchase-order-lots__empty">No Lots linked</span>
				</div>
				<div class="purchase-order-lots__add"><LinkField v-model="lotCandidate" label="Add Lot" doctype="SD YRP Lot" :show-open-button="false" /><Button label="Add" severity="secondary" outlined :disabled="!lotCandidate || lotDraft.includes(lotCandidate)" @click="addLot" /></div>
				<label class="purchase-order-lots__reason" for="purchase-order-lot-reason"><span>Reason *</span><Textarea id="purchase-order-lot-reason" v-model="lotReason" aria-label="Reason *" rows="3" auto-resize fluid /></label>
			</div>
			<template #footer><Button label="Cancel" severity="secondary" text @click="lotEditorVisible = false" /><Button label="Save Changes" icon="pi pi-save" :disabled="!lotChanged || !lotReason.trim()" :loading="acting === 'update_linked_lots'" @click="saveLinkedLots" /></template>
		</Dialog>

		<Dialog v-model:visible="deliverySourceVisible" modal header="Create Delivery Challan" class="fabric-action-dialog erp-dialog--sm">
			<div class="purchase-order-dc-source"><LinkField v-model="deliveryWorkOrder" label="Work Order *" doctype="YRP Work Order" :filters="{ docstatus: 1 }" :show-open-button="false" help-text="The Purchase Order remains the traceability source." /></div>
			<template #footer><Button label="Cancel" severity="secondary" text @click="deliverySourceVisible = false" /><Button label="Continue" icon="pi pi-arrow-right" :disabled="!deliveryWorkOrder" @click="openDeliveryChallan" /></template>
		</Dialog>
		<Dialog v-model:visible="rejectVisible" modal header="Reject Purchase Order" class="fabric-action-dialog erp-dialog--sm" :closable="acting !== 'reject'" :dismissable-mask="false">
			<div class="purchase-order-rejection">
				<Message severity="warn" :closable="false">This returns the Purchase Order to Draft and records the reason in its audit trail.</Message>
				<label for="purchase-order-rejection-reason"><span>Rejection reason *</span><Textarea id="purchase-order-rejection-reason" v-model="rejectReason" aria-label="Rejection reason *" rows="4" auto-resize fluid autofocus /></label>
			</div>
			<template #footer><Button label="Keep Pending" severity="secondary" text :disabled="acting === 'reject'" @click="rejectVisible = false" /><Button label="Reject Purchase Order" icon="pi pi-times-circle" severity="danger" :disabled="!rejectReason.trim()" :loading="acting === 'reject'" @click="submitRejection" /></template>
		</Dialog>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import Textarea from "primevue/textarea"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { changeFabricStoreDocumentStatus, executePurchaseOrderCommand, getPurchaseOrderWorkspace } from "../api/fabricStore.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import LinkField from "../components/common/LinkField.vue"
import DocumentActionStrip from "../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../components/documents/DocumentConfirmationDialog.vue"
import DocumentOverview from "../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge.vue"
import StockItemMatrix from "../components/stock/StockItemMatrix.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "./fabric-store/FabricDocumentWorkspace.vue"
import RelatedDocumentWorkspaceDialog from "./fabric-store/RelatedDocumentWorkspaceDialog.vue"

const props = defineProps({
	backTo: { type: String, default: "/fabric-store/purchase-orders" },
	backLabel: { type: String, default: "Purchase Orders" },
	viewRouteName: { type: String, default: "fabric-purchase-order" },
	newRouteName: { type: String, default: "fabric-purchase-order-new" },
	editRouteName: { type: String, default: "fabric-purchase-order-edit" },
})

const route = useRoute()
const router = useRouter()
const primaryTotalFieldnames = new Set(["total_qty", "grand_total"])
const loading = ref(true)
const refreshing = ref(false)
const acting = ref("")
const error = ref("")
const actionError = ref("")
const workspace = ref({})
const relatedVisible = ref(false)
const relatedDoctype = ref("YRP Goods Received Note")
const relatedName = ref("")
const relatedSourceContext = ref({})
const lotEditorVisible = ref(false)
const lotOriginal = ref([])
const lotDraft = ref([])
const lotCandidate = ref("")
const lotReason = ref("")
const deliverySourceVisible = ref(false)
const deliveryWorkOrder = ref("")
const rejectVisible = ref(false)
const rejectReason = ref("")
const lifecycleConfirmVisible = ref(false)
const pendingLifecycleCommand = ref("")
const activeTab = ref("overview")
let loadSequence = 0
let actionSequence = 0
const overviewDefinitions = [
	{ key: "identity", label: "Order identity", description: "Company and procurement references", icon: "pi pi-id-card", fields: ["company", "naming_series", "is_yrp_managed", "approved_by"] },
	{ key: "delivery", label: "Supplier & delivery", description: "Supplier and material destination", icon: "pi pi-truck", fields: ["supplier", "supplier_name", "deliver_to_supplier", "default_delivery_location", "set_warehouse"] },
	{ key: "schedule", label: "Schedule", description: "Ordering and required dates", icon: "pi pi-calendar", fields: ["transaction_date", "schedule_date"] },
	{ key: "status", label: "Status & notes", description: "Fulfilment state and instructions", icon: "pi pi-clipboard", fields: ["status", "open_status", "yrp_fulfillment_status", "terms_and_condition", "comments"] },
]
const overviewAdditionalDefinition = { key: "additional", label: "Additional details", description: "Other order information", icon: "pi pi-ellipsis-h", wide: true }
const overviewFields = computed(() => {
	const fields = [...(workspace.value.fields?.length ? workspace.value.fields : workspace.value.details || [])]
	const existing = new Set(fields.map((field) => field.fieldname))
	for (const [fieldname, label, fieldtype] of [["status", "Status", "Data"], ["is_yrp_managed", "YRP Managed", "Check"]]) {
		if (!existing.has(fieldname) && workspace.value.record?.[fieldname] !== undefined) fields.push({ fieldname, label, fieldtype, value: workspace.value.record[fieldname] })
	}
	return fields
})
const itemGroups = computed(() => workspace.value.matrices?.items || workspace.value.item_groups || [])
const relatedDocuments = computed(() => [
	...(workspace.value.related?.delivery_challans || []).map((row) => ({ ...row, doctype: "YRP Delivery Challan", label: "Delivery Challan" })),
	...(workspace.value.related?.goods_received_notes || []).map((row) => ({ ...row, doctype: "YRP Goods Received Note", label: "Goods Received Note" })),
])
const capabilities = computed(() => workspace.value.capabilities || {})
const purchaseOrderActions = computed(() => {
	const busy = Boolean(acting.value)
	const actions = []
	const add = (key, fallback, icon, command, options = {}) => {
		if (!capabilities.value[key]) return
		actions.push({
			key, label: capabilityLabel(key, fallback), icon, command,
			disabled: busy, loading: acting.value === key,
			menuOnly: Boolean(options.menuOnly),
		})
	}
	add("create_goods_received_note", "Create GRN", "pi pi-plus", () => openRelated("YRP Goods Received Note", capabilities.value.create_goods_received_note.source_context))
	add("approve", "Approve PO", "pi pi-check-circle", () => runDomainCommand("approve"))
	add("send_approval_request", "Send Request", "pi pi-send", () => runDomainCommand("send_approval_request"))
	add("close", "Close", "pi pi-lock", () => requestLifecycleAction("close"))
	add("reopen", "Reopen", "pi pi-lock-open", () => runDomainCommand("reopen"))
	add("update_linked_lots", "Manage Linked Lots", "pi pi-link", openLotEditor)
	add("save", "Edit", "pi pi-pencil", editPurchaseOrder)
	add("submit", "Submit", "pi pi-check", () => changeStatus("submit"))
	add("cancel", "Cancel Document", "pi pi-ban", () => requestLifecycleAction("cancel"), { menuOnly: true })
	add("amend", "Amend", "pi pi-copy", () => requestLifecycleAction("amend"), { menuOnly: true })
	if (workspace.value.permissions?.can_create) actions.push({ key: "duplicate", label: "Duplicate", icon: "pi pi-clone", command: duplicatePurchaseOrder, disabled: busy, loading: false, menuOnly: true })
	add("reject", "Reject PO", "pi pi-times-circle", beginRejection, { menuOnly: true })
	add("create_delivery_challan", "Create Delivery Challan", "pi pi-truck", beginDeliveryChallan, { menuOnly: true })
	add("refresh_status", "Refresh Status", "pi pi-sync", () => runDomainCommand("refresh_status"), { menuOnly: true })
	const primaryKey = capabilities.value.approve ? "approve"
		: capabilities.value.send_approval_request ? "send_approval_request"
			: capabilities.value.create_goods_received_note ? "create_goods_received_note"
				: capabilities.value.submit ? "submit" : capabilities.value.amend ? "amend" : ""
	return actions.map((action) => ({ ...action, primary: action.key === primaryKey }))
})
const lotChanged = computed(() => JSON.stringify([...lotOriginal.value].sort()) !== JSON.stringify([...lotDraft.value].sort()))
async function loadWorkspace(isRefresh = false) {
	const requestedId = String(route.params.purchaseOrderId || "")
	const sequence = ++loadSequence
	actionSequence += 1
	if (isRefresh) {
		refreshing.value = true
		acting.value = "reload"
	}
	else {
		acting.value = ""
		loading.value = true
		workspace.value = {}
		actionError.value = ""
		relatedVisible.value = false
		relatedName.value = ""
		relatedSourceContext.value = {}
		lotEditorVisible.value = false
		lotOriginal.value = []
		lotDraft.value = []
		lotCandidate.value = ""
		lotReason.value = ""
		deliverySourceVisible.value = false
		deliveryWorkOrder.value = ""
		rejectVisible.value = false
		rejectReason.value = ""
		activeTab.value = "overview"
		lifecycleConfirmVisible.value = false
		pendingLifecycleCommand.value = ""
	}
	error.value = ""
	try {
		const data = await getPurchaseOrderWorkspace(requestedId) || {}
		if (sequence === loadSequence && requestedId === String(route.params.purchaseOrderId || "")) {
			workspace.value = data
		}
	}
	catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load this Purchase Order."
	}
	finally {
		if (sequence === loadSequence) {
			loading.value = false
			refreshing.value = false
			if (acting.value === "reload") acting.value = ""
		}
	}
}
function capabilityLabel(name, fallback) { return capabilities.value[name]?.label || fallback }
async function runWorkspaceAction(action) {
	if (action === "save") return editPurchaseOrder()
	if (["cancel", "amend"].includes(action)) return requestLifecycleAction(action)
	if (action === "submit") return changeStatus(action)
	return runDomainCommand(action)
}
async function runDomainCommand(command, payload = {}) {
	const requestedId = String(route.params.purchaseOrderId || "")
	const source = workspace.value.record
	const sequence = ++actionSequence
	acting.value = command
	actionError.value = ""
	try {
		const result = await executePurchaseOrderCommand(source.name, command, payload, source.modified) || {}
		if (sequence !== actionSequence || requestedId !== String(route.params.purchaseOrderId || "")) return false
		workspace.value = result
		return true
	}
	catch (reason) { if (sequence === actionSequence && requestedId === String(route.params.purchaseOrderId || "")) actionError.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Purchase Order.`; return false }
	finally { if (sequence === actionSequence) acting.value = "" }
}
async function changeStatus(action) {
	const requestedId = String(route.params.purchaseOrderId || "")
	const source = workspace.value.record
	const sequence = ++actionSequence
	acting.value = action
	actionError.value = ""
	try {
		const changed = await changeFabricStoreDocumentStatus("Purchase Order", source.name, action, source.modified)
		if (sequence !== actionSequence || requestedId !== String(route.params.purchaseOrderId || "")) return
		const name = changed?.record?.name || source.name
		if (name !== requestedId) await router.replace({ name: props.viewRouteName, params: { purchaseOrderId: name }, state: preserveListNavigationState(name) })
		else await loadWorkspace(true)
	} catch (reason) { if (sequence === actionSequence && requestedId === String(route.params.purchaseOrderId || "")) actionError.value = reason?.message || `Unable to ${action} this Purchase Order.` }
	finally { if (sequence === actionSequence) acting.value = "" }
}
const lifecycleConfirmTitle = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel Purchase Order?" : pendingLifecycleCommand.value === "close" ? "Close Purchase Order?" : "Amend Purchase Order?")
const lifecycleConfirmLabel = computed(() => pendingLifecycleCommand.value === "cancel" ? "Cancel Purchase Order" : pendingLifecycleCommand.value === "close" ? "Close Purchase Order" : "Create Amendment")
const lifecycleConfirmMessage = computed(() => pendingLifecycleCommand.value === "cancel" ? `Cancel ${workspace.value.record?.name}? This keeps the document for audit but stops further processing.` : pendingLifecycleCommand.value === "close" ? `Close ${workspace.value.record?.name}? No further receipts can be created until it is reopened.` : `Create a new draft amendment from ${workspace.value.record?.name}?`)
function requestLifecycleAction(command) { pendingLifecycleCommand.value = command; lifecycleConfirmVisible.value = true }
async function confirmLifecycleAction() { const command = pendingLifecycleCommand.value; lifecycleConfirmVisible.value = false; pendingLifecycleCommand.value = ""; if (command === "close") await runDomainCommand(command); else if (command) await changeStatus(command) }
function editPurchaseOrder() { router.push({ name: props.editRouteName, params: { purchaseOrderId: workspace.value.record.name }, state: preserveListNavigationState(workspace.value.record.name, workspace.value.record.modified) }) }
function duplicatePurchaseOrder() { router.push({ name: props.newRouteName, query: { duplicate_from: workspace.value.record.name } }) }
function openRelated(doctype, sourceContext = {}, name = "") {
	relatedDoctype.value = doctype
	relatedName.value = name
	relatedSourceContext.value = { ...(sourceContext || {}) }
	relatedVisible.value = true
}
async function relatedChanged() { await loadWorkspace(true) }
function openLotEditor() {
	lotOriginal.value = [...(workspace.value.linked_lots || [])]
	lotDraft.value = [...lotOriginal.value]
	lotCandidate.value = ""
	lotReason.value = ""
	lotEditorVisible.value = true
}
function removeLot(lot) { lotDraft.value = lotDraft.value.filter((value) => value !== lot) }
function addLot() {
	if (lotCandidate.value && !lotDraft.value.includes(lotCandidate.value)) lotDraft.value = [...lotDraft.value, lotCandidate.value]
	lotCandidate.value = ""
}
async function saveLinkedLots() {
	const original = new Set(lotOriginal.value)
	const desired = new Set(lotDraft.value)
	await runDomainCommand("update_linked_lots", {
		add_lots: lotDraft.value.filter((lot) => !original.has(lot)),
		remove_lots: lotOriginal.value.filter((lot) => !desired.has(lot)),
		comment: lotReason.value,
	})
	if (!actionError.value) lotEditorVisible.value = false
}
function beginDeliveryChallan() { deliveryWorkOrder.value = ""; deliverySourceVisible.value = true }
function openDeliveryChallan() {
	deliverySourceVisible.value = false
	openRelated("YRP Delivery Challan", { ...(capabilities.value.create_delivery_challan?.source_context || {}), work_order: deliveryWorkOrder.value })
}
function beginRejection() {
	rejectReason.value = ""
	rejectVisible.value = true
}
async function submitRejection() {
	const succeeded = await runDomainCommand("reject", { reason: rejectReason.value.trim() })
	if (succeeded) rejectVisible.value = false
}
function statusLabel(docstatus) { return Number(docstatus) === 1 ? "Submitted" : Number(docstatus) === 2 ? "Cancelled" : "Draft" }
function formatDate(value) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return match ? `${match[3]}-${match[2]}-${match[1]}` : value || "—" }
function formatAmount(value, currency = "") { return `${currency ? `${currency} ` : ""}${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` }
function formatTotal(total) {
	if (total.fieldname === "total_qty") return Number(total.value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return formatAmount(total.value, workspace.value.record?.currency)
}

watch(() => route.params.purchaseOrderId, () => loadWorkspace(false), { immediate: true })
</script>

<style scoped>
.fabric-purchase-order-frame {
	width: 100%;
	min-width: 0;
}
.purchase-order-page__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.purchase-order-page__identity > div:first-child {
	display: grid;
	min-width: 0;
	gap: 2px;
}
.purchase-order-page__identity h1 { margin: 0; color: var(--erp-text); }
.purchase-order-page__identity > div:first-child > span {
	font-variant-numeric: tabular-nums;
}
.purchase-order-page__facts { display: flex; min-width: 0; align-items: center; gap: 18px; padding-left: 14px; border-left: 1px solid var(--erp-border); }
.purchase-order-page__facts > div { display: grid; min-width: 0; gap: 2px; }
.purchase-order-page__facts span {
	min-width: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	letter-spacing: .03em;
	text-transform: uppercase;
	overflow-wrap: anywhere;
}
.purchase-order-page__total span {
	min-width: 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	letter-spacing: .07em;
	text-transform: uppercase;
	overflow-wrap: anywhere;
}
.purchase-order-page__facts strong {
	overflow: hidden;
	max-width: 220px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-md);
	text-overflow: ellipsis;
	white-space: nowrap;
	font-variant-numeric: tabular-nums;
	font-weight: 600;
}
.purchase-order-tabs :deep(.p-tabpanels) { padding: 12px 0 0; background: transparent; }
.purchase-order-tabs :deep(.p-tablist-tab-list) { padding-inline: 2px; }
.purchase-order-tabs :deep(.p-tab span) { margin-left: 5px; padding: 2px 6px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.purchase-order-page__totals {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 1px;
	overflow: hidden;
	background: var(--erp-border);
}
.purchase-order-page__total {
	display: grid;
	min-width: 0;
	min-height: 58px;
	align-content: center;
	gap: 3px;
	padding: 8px 10px;
	background: var(--erp-surface);
}
.purchase-order-page__total:last-child:nth-child(odd) { grid-column: 1 / -1; }
.purchase-order-page__total strong {
	min-width: 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
	font-weight: 700;
	letter-spacing: -.01em;
	font-variant-numeric: tabular-nums;
	overflow-wrap: anywhere;
}
.purchase-order-related {
	display: grid;
	overflow: hidden;
	background: var(--erp-surface);
}
.purchase-order-related > header {
	display: flex;
	min-height: 40px;
	align-items: center;
	justify-content: space-between;
	padding: 7px 10px;
	border-bottom: 1px solid var(--erp-border-subtle);
}
.purchase-order-related > header span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
	letter-spacing: .03em;
	text-transform: uppercase;
}
.purchase-order-related > header strong {
	padding: 1px 7px;
	color: var(--erp-accent-ink);
	background: var(--erp-accent-soft);
	border-radius: var(--erp-pill-radius);
	font-size: var(--erp-font-size-min);
	font-weight: 600;
}
.purchase-order-related > button {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto auto;
	align-items: center;
	gap: 8px;
	padding: 9px 10px;
	color: inherit;
	font: inherit;
	text-align: left;
	border: 0;
	border-bottom: 1px solid var(--erp-border-subtle);
	background: transparent;
	cursor: pointer;
	transition: background-color var(--erp-transition-fast), padding-left var(--erp-transition-fast);
}
.purchase-order-related > button:last-child { border-bottom: 0; }

.purchase-order-related > button:hover { padding-left: 13px; background: color-mix(in srgb, var(--erp-accent-soft) 45%, white); }
.purchase-order-related > button:focus-visible { outline: 2px solid color-mix(in srgb, var(--erp-accent) 72%, white); outline-offset: -2px; }
.purchase-order-related > button > div { display: grid; min-width: 0; gap: 2px; }
.purchase-order-related > button > div strong { overflow: hidden; font-size: var(--erp-font-size-caption); text-overflow: ellipsis; white-space: nowrap; }
.purchase-order-related > button > div span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.purchase-order-related > button > i {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}
.purchase-order-page__empty { display: flex; align-items: center; gap: 10px; padding: 18px; color: var(--erp-text-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); }
.purchase-order-page__empty div { display: grid; gap: 2px; }
.purchase-order-page__empty strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.purchase-order-page__empty span { font-size: var(--erp-font-size-min); }
.purchase-order-lots { display: grid; gap: var(--erp-space-3); }
.purchase-order-lots__list { display: flex; min-height: 42px; align-items: center; gap: 7px; flex-wrap: wrap; }
.purchase-order-lots__chip { display: inline-flex; align-items: center; gap: 2px; padding-left: 10px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); background: var(--erp-surface-soft); }
.purchase-order-lots__empty { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.purchase-order-lots__add { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 8px; }
.purchase-order-lots__reason, .purchase-order-rejection label {
	display: grid;
	gap: 6px;
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
	font-weight: 600;
}
.purchase-order-dc-source { padding: 2px 0; }
.purchase-order-rejection { display: grid; gap: var(--erp-space-3); }
@media (max-width: 1100px) { .purchase-order-page__identity { align-items: flex-start; flex-wrap: wrap; }  }
@media (max-width: 900px) { .purchase-order-related, .purchase-order-page__totals { grid-column: 1 / -1; } }
@media (max-width: 650px) { .fabric-purchase-order-frame { margin-bottom: 0; padding: 0; } .purchase-order-page__identity { width: 100%; }
	.fabric-purchase-order-frame :deep(.fabric-document-workspace__header) {
		align-items: flex-start;
	}
	.purchase-order-page__facts {
		display: grid;
		width: 100%;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px 16px;
		padding: 8px 0 0;
		border-top: 1px solid var(--erp-border);
		border-left: 0;
	}     .purchase-order-lots__add { grid-template-columns: 1fr; }
}
:global(.fabric-action-dialog .p-dialog-content) { min-height: 0; }
@media (max-width: 620px) { :global(.fabric-action-dialog) { width: 100vw !important; height: 100dvh !important; max-height: 100dvh !important; margin: 0; border-radius: 0; } :global(.fabric-action-dialog .p-dialog-content) { flex: 1; overflow-y: auto; } }
</style>

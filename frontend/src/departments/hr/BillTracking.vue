<template>
	<DepartmentPage
		title="Bill Tracking"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="bill-tracking-page">
			<FabricDocumentWorkspace :show-delete="false"
				doctype="YRP Bill Tracking"
				title="Bill Tracking"
				:workspace="workspace"
				:loading="loading"
				:error="loadError"
				:acting="acting"
				:show-lifecycle-actions="false"
				compact-mobile-rail
				@reload="load(true)" :live-reload="() => load(true)"
			>
				<template #header="{ record, headingId }">
					<div class="bill-tracking-header">
						<div class="bill-tracking-header__identity">
							<h1 :id="headingId">Bill Tracking · {{ record.name }}</h1>
							<DocumentStatusBadge :docstatus="record.docstatus" :label="record.form_status" />
						</div>
						<dl class="bill-tracking-header__facts">
							<div><dt>Supplier</dt><dd :title="record.supplier || '—'"><DocumentLink doctype="Supplier" :name="record.supplier" :label="record.supplier || '—'" /></dd></div>
							<div><dt>GSTIN / UIN</dt><dd :title="record.gstin || '—'">{{ record.gstin || "—" }}</dd></div>
							<div><dt>Bill No</dt><dd :title="record.bill_no || '—'">{{ record.bill_no || "—" }}</dd></div>
							<div><dt>Bill Date</dt><dd>{{ formatDisplayDate(record.bill_date) }}</dd></div>
							<div><dt>Invoice Value</dt><dd>{{ money(record.invoice_value) }}</dd></div>
						</dl>
					</div>
				</template>
				<template #header-actions>
					<DocumentActionStrip :actions="actions" />
				</template>
				<template #fields>
					<div class="bill-tracking-body">
						<DocumentOverview
							:fields="detailFields"
							:definitions="DETAIL_GROUPS"
							include-empty
							aria-label="Bill Tracking details"
							id-prefix="bill-tracking-overview"
						/>
						<section class="bill-tracking-history erp-card" aria-labelledby="bill-tracking-history-title">
							<h2 id="bill-tracking-history-title" class="bill-tracking-history__title">Bill Tracking History <span>{{ workspace.history?.length || 0 }}</span></h2>
							<div v-if="workspace.history?.length" class="bill-tracking-history__table" role="region" tabindex="0">
								<table>
									<thead><tr><th>Action</th><th>Assigned To</th><th>Assigned By</th><th>Assigned On</th><th>Received</th><th>Remarks</th></tr></thead>
									<tbody>
										<tr v-for="(row, index) in workspace.history" :key="`${row.assigned_on || 'history'}-${index}`">
											<td>{{ row.action || "—" }}</td>
											<td><DocumentLink doctype="Department" :name="row.assigned_to" :label="row.assigned_to || '—'" /></td>
											<td><DocumentLink doctype="User" :name="row.assigned_by" :label="row.assigned_by || '—'" /></td>
											<td>{{ formatDisplayDatetime(row.assigned_on) }}</td>
											<td>{{ Number(row.received) ? "Yes" : "No" }}</td>
											<td>{{ row.remarks || "—" }}</td>
										</tr>
									</tbody>
								</table>
							</div>
							<div v-else class="bill-tracking-history__empty"><i class="pi pi-inbox" /><span>No history has been recorded.</span></div>
						</section>
					</div>
				</template>
				<template #rail>
					<div class="bill-tracking-metric"><span>History entries</span><strong>{{ workspace.history?.length || 0 }}</strong></div>
				</template>
			</FabricDocumentWorkspace>
		</section>

		<BillTrackingAssignDialog
			v-model:visible="assignVisible"
			:busy="acting === 'assign'"
			@assign="confirmAssign"
		/>
		<BillTrackingCancelDialog
			v-model:visible="cancelVisible"
			:busy="acting === 'cancel'"
			@confirm="confirmCancel"
		/>
		<DocumentConfirmationDialog
			v-model:visible="confirmationVisible"
			:title="confirmation.title"
			:message="confirmation.message"
			:confirm-label="confirmation.label"
			:confirm-icon="confirmation.icon"
			:severity="confirmation.severity"
			cancel-label="Keep"
			:busy="Boolean(acting)"
			@confirm="confirmPendingAction"
		/>
		<DocumentErrorDialog
			:message="actionError"
			title="Bill Tracking action could not be completed"
			@dismiss="actionError = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import DocumentLink from "../../components/common/DocumentLink.vue"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
	acknowledgeBillReceived,
	approveBillCancellation,
	assignBill,
	cancelBill,
	executeBillTrackingCommand,
	getBillTrackingWorkspace,
	requestBillCancellation,
} from "../../api/hr.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { useDuplicateAction } from "../../composables/useDuplicateAction.js"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import { formatDisplayDate, formatDisplayDatetime } from "../../utils/dateFormat.js"
import FabricDocumentWorkspace from "../fabric-store/FabricDocumentWorkspace.vue"
import BillTrackingAssignDialog from "./components/BillTrackingAssignDialog.vue"
import BillTrackingCancelDialog from "./components/BillTrackingCancelDialog.vue"
import { billTrackingActionItems } from "./hrViews.js"

const DETAIL_GROUPS = [
	{
		key: "vendor",
		label: "Vendor Details",
		icon: "pi pi-receipt",
		fields: ["supplier", "bill_no", "gstin", "bill_date", "pan", "invoice_value", "purchase_invoice", "department", "erp_purchase_invoice"],
	},
	{
		key: "delivery",
		label: "Delivery Details",
		icon: "pi pi-truck",
		fields: ["received_date", "received_via", "delivery_mob_no", "delivery_person", "assigned_to", "receive_comment"],
	},
	{ key: "status", label: "Status", icon: "pi pi-flag", fields: ["form_status", "cancel_reason", "amended_from"] },
]
const OPTIONAL_DETAIL_FIELDS = new Set(["cancel_reason", "amended_from"])

const props = defineProps({
	billTrackingId: { type: String, default: "" },
	backTo: { type: String, default: "/hr/bill-tracking" },
	backLabel: { type: String, default: "Bill Tracking" },
	listRouteName: { type: String, default: "hr-bill-trackings" },
	editRouteName: { type: String, default: "hr-bill-tracking-edit" },
	newRouteName: { type: String, default: "" },
	purchaseInvoiceNewRouteName: { type: String, default: "accounts-purchase-invoice-new" },
	purchaseInvoiceViewRouteName: { type: String, default: "accounts-purchase-invoice" },
})
const route = useRoute()
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const assignVisible = ref(false)
const cancelVisible = ref(false)
const confirmationVisible = ref(false)
const pendingAction = ref("")
let loadSequence = 0
let actionSequence = 0
let isAlive = true

const handlers = {
	assign: () => { assignVisible.value = true },
	bill_received: () => requestConfirmation("bill_received"),
	request_cancel: () => requestConfirmation("request_cancel"),
	approve_cancel: () => requestConfirmation("approve_cancel"),
	cancel: () => { cancelVisible.value = true },
	create_purchase_invoice: createPurchaseInvoice,
	create_erp_purchase_invoice: createErpPurchaseInvoice,
	show_purchase_invoice: showPurchaseInvoice,
	show_erp_purchase_invoice: showErpPurchaseInvoice,
	submit: () => requestConfirmation("submit"),
	delete: () => requestConfirmation("delete"),
	edit: openEditor,
}
const duplicateAction = useDuplicateAction({
	canCreate: () => workspace.value.permissions?.can_create,
	newRouteName: () => props.newRouteName || props.editRouteName.replace(/-edit$/, "-new"),
	name: () => workspace.value.record?.name,
	busy: () => Boolean(acting.value),
	router,
})
const actions = computed(() => [...billTrackingActionItems(workspace.value.capabilities, handlers)
	.filter((action) => action.key !== "show_erp_purchase_invoice" || workspace.value.can_open_desk)
	.map((action) => ({
		...action,
		disabled: Boolean(acting.value),
		loading: acting.value === action.key,
	})), ...(duplicateAction.value ? [duplicateAction.value] : [])])
const detailFields = computed(() => (workspace.value.details || [])
	.filter((field) => !OPTIONAL_DETAIL_FIELDS.has(field.fieldname) || ![null, undefined, ""].includes(field.value)))
const confirmation = computed(() => ({
	bill_received: {
		title: "Mark bill as received?",
		message: `Confirm receipt of ${recordName()}?`,
		label: "Bill Received",
		icon: "pi pi-inbox",
		severity: "primary",
	},
	request_cancel: {
		title: "Request cancellation?",
		message: `Request cancellation of ${recordName()}?`,
		label: "Request Cancellation",
		icon: "pi pi-times-circle",
		severity: "danger",
	},
	approve_cancel: {
		title: "Approve cancellation request?",
		message: `Approve the cancellation request for ${recordName()}?`,
		label: "Approve Request",
		icon: "pi pi-check-circle",
		severity: "danger",
	},
	submit: {
		title: "Submit bill?",
		message: `Submit ${recordName()}? Existing Bill Tracking validations will be applied.`,
		label: "Submit",
		icon: "pi pi-check",
		severity: "primary",
	},
	delete: {
		title: "Delete bill?",
		message: `Delete ${recordName()}? This action cannot be undone.`,
		label: "Delete Bill",
		icon: "pi pi-trash",
		severity: "danger",
	},
}[pendingAction.value] || {
	title: "Confirm action",
	message: "Continue with this Bill Tracking action?",
	label: "Continue",
	icon: "pi pi-check",
	severity: "primary",
}))

function currentName() {
	return String(props.billTrackingId || route.params.billTrackingId || "")
}

function recordName() {
	return workspace.value.record?.name || "this bill"
}

async function load(refresh = false) {
	const name = currentName()
	const request = {
		name,
		sequence: ++loadSequence,
	}
	if (!refresh) {
		loading.value = true
		workspace.value = {}
	} else if (!acting.value) {
		acting.value = "reload"
	}
	loadError.value = ""
	actionError.value = ""
	try {
		const payload = await getBillTrackingWorkspace(name) || {}
		if (isCurrentLoad(request)) workspace.value = payload
	} catch (reason) {
		if (isCurrentLoad(request)) loadError.value = reason?.message || "Unable to load this bill."
	} finally {
		if (isCurrentLoad(request)) {
			loading.value = false
			if (acting.value === "reload") acting.value = ""
		}
	}
}

function isCurrentLoad(request) {
	return isAlive && request.name === currentName() && request.sequence === loadSequence
}

function resetRecordState() {
	loadSequence += 1
	actionSequence += 1
	acting.value = ""
	actionError.value = ""
	assignVisible.value = false
	cancelVisible.value = false
	confirmationVisible.value = false
	pendingAction.value = ""
}

function beginRecordAction(command) {
	const record = workspace.value.record || {}
	acting.value = command
	actionError.value = ""
	return {
		command,
		name: String(record.name || ""),
		sequence: ++actionSequence,
	}
}

function isOriginatingRecord(action) {
	return isAlive && action.name === currentName() && action.sequence === actionSequence
}

function finishRecordAction(action) {
	if (isOriginatingRecord(action) && acting.value === action.command) acting.value = ""
}

function requestConfirmation(action) {
	pendingAction.value = action
	confirmationVisible.value = true
}

async function confirmPendingAction() {
	const action = pendingAction.value
	confirmationVisible.value = false
	pendingAction.value = ""
	if (action === "submit" || action === "delete") {
		await runDocumentCommand(action)
		return
	}
	const commands = {
		bill_received: acknowledgeBillReceived,
		request_cancel: requestBillCancellation,
		approve_cancel: approveBillCancellation,
	}
	if (commands[action]) await runAction(action, commands[action])
}

async function confirmAssign({ assignedTo, remarks }) {
	const succeeded = await runAction("assign", (name) => assignBill(name, assignedTo, remarks))
	if (succeeded) assignVisible.value = false
}

async function confirmCancel(reason) {
	const succeeded = await runAction("cancel", (name) => cancelBill(name, reason))
	if (succeeded) cancelVisible.value = false
}

async function runAction(action, command) {
	const request = beginRecordAction(action)
	try {
		await command(request.name)
		if (!isOriginatingRecord(request)) return false
		await load(true)
		return isOriginatingRecord(request)
	} catch (reason) {
		if (isOriginatingRecord(request)) {
			actionError.value = reason?.message || `Unable to ${action.replaceAll("_", " ")} this bill.`
		}
		return false
	} finally {
		finishRecordAction(request)
	}
}

async function runDocumentCommand(command) {
	const record = workspace.value.record || {}
	const request = beginRecordAction(command)
	try {
		const result = await executeBillTrackingCommand(request.name, command, record.modified) || {}
		if (!isOriginatingRecord(request)) return false
		if (result.deleted) {
			await router.replace({ name: props.listRouteName })
			return true
		}
		workspace.value = result
		return true
	} catch (reason) {
		if (isOriginatingRecord(request)) {
			actionError.value = reason?.message || `Unable to ${command} this bill.`
		}
		return false
	} finally {
		finishRecordAction(request)
	}
}

function openEditor() {
	const record = workspace.value.record || {}
	router.push({
		name: props.editRouteName,
		params: { billTrackingId: record.name },
		state: preserveListNavigationState(record.name, record.modified),
	})
}

function createPurchaseInvoice() {
	router.push({
		name: props.purchaseInvoiceNewRouteName,
		query: { bill_tracking: recordName() },
	})
}

function createErpPurchaseInvoice() {
	const name = workspace.value.record?.name
	if (!name) return
	const query = new URLSearchParams({ vendor_bill_tracking: name })
	window.open(`/app/purchase-invoice/new?${query}`, "_blank", "noopener")
}

function showPurchaseInvoice() {
	const name = workspace.value.record?.purchase_invoice
	if (name) router.push({ name: props.purchaseInvoiceViewRouteName, params: { purchaseInvoiceId: name } })
}

function showErpPurchaseInvoice() {
	const name = workspace.value.record?.erp_purchase_invoice
	if (name && workspace.value.can_open_desk) {
		window.open(`/app/purchase-invoice/${encodeURIComponent(name)}`, "_blank", "noopener")
	}
}

function money(input) {
	if (input === null || input === undefined || input === "") return "—"
	const value = Number(input)
	return Number.isFinite(value)
		? value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}

watch(currentName, () => {
	resetRecordState()
	load(false)
}, { immediate: true })

onBeforeUnmount(() => {
	isAlive = false
	loadSequence += 1
	actionSequence += 1
})
</script>

<style scoped>
.bill-tracking-page { width: 100%; min-width: 0; margin: 0 0 var(--erp-space-3); }
.bill-tracking-header { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 14px; padding-block: 3px; }
.bill-tracking-header__identity { display: flex; min-width: 0; align-items: center; gap: 10px; }
.bill-tracking-header__identity h1 { margin: 0; overflow: hidden; color: var(--erp-text); font-size: 19px; line-height: 1.15; letter-spacing: -.018em; text-overflow: ellipsis; white-space: nowrap; }
.bill-tracking-header__facts { display: flex; min-width: 0; margin: 0; }
.bill-tracking-header__facts > div { display: grid; min-width: 120px; gap: 2px; padding: 0 13px; border-left: 1px solid var(--erp-border); }
.bill-tracking-header__facts dt, .bill-tracking-metric span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.bill-tracking-header__facts dd { max-width: 190px; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
.bill-tracking-metric { display: grid; min-height: 76px; align-content: center; gap: 4px; padding: 12px 14px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface); }
.bill-tracking-metric strong { color: var(--erp-accent-hover); font-size: 22px; font-variant-numeric: tabular-nums; }
.bill-tracking-body { display: grid; min-width: 0; gap: var(--erp-space-4); }
.bill-tracking-history__title { display: flex; align-items: center; gap: 6px; margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--erp-border); color: var(--erp-text); font-size: var(--erp-font-size-body, 14px); font-weight: 700; }
.bill-tracking-history__title span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.bill-tracking-history { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.bill-tracking-history__table { max-width: 100%; overflow: auto; }
.bill-tracking-history table { width: 100%; min-width: 820px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.bill-tracking-history th, .bill-tracking-history td { padding: 9px 10px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.bill-tracking-history th { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.bill-tracking-history th:last-child, .bill-tracking-history td:last-child { border-right: 0; }
.bill-tracking-history tbody tr:last-child td { border-bottom: 0; }
.bill-tracking-history__empty { display: grid; min-height: 180px; place-content: center; justify-items: center; gap: 8px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.bill-tracking-history__empty i { font-size: 22px; }
@media (max-width: 900px) { .bill-tracking-header { align-items: flex-start; flex-direction: column; } .bill-tracking-header__facts { width: 100%; overflow-x: auto; } .bill-tracking-header__facts > div:first-child { padding-left: 0; border-left: 0; } }
@media (max-width: 620px) { .bill-tracking-page { padding: 0; } .bill-tracking-header__identity { align-items: flex-start; flex-direction: column; gap: 5px; } .bill-tracking-header__identity h1 { max-width: 86vw; font-size: 16px; } .bill-tracking-header__facts > div { min-width: 112px; padding-inline: 10px; } }
</style>

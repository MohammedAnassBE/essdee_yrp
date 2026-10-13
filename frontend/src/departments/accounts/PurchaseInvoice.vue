<template>
	<DepartmentPage
		title="Purchase Invoice"
		back-to="/accounts/purchase-invoices"
		back-label="Purchase Invoices"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="purchase-invoice-page">
			<FabricDocumentWorkspace
				doctype="YRP Purchase Invoice"
				title="Purchase Invoice"
				:workspace="workspace"
				:loading="loading"
				:error="loadError"
				:acting="acting"
				:show-lifecycle-actions="false"
				compact-mobile-rail
				@reload="load(true)"
			>
				<template #header="{ record, headingId }">
					<PurchaseInvoiceHeader :record="record" :heading-id="headingId" />
				</template>
				<template #header-actions>
					<div class="purchase-invoice-actions">
						<DocumentActionStrip :actions="actions" />
					</div>
				</template>
				<template #fields>
					<PurchaseInvoiceTabs
						:active-tab="activeTab"
						:workspace="workspace"
						@update:active-tab="activeTab = $event"
						@open-grn="openGrn"
						@changed="load(true)"
					/>
				</template>
				<template #rail>
					<div v-for="total in workspace.totals || []" :key="total.key" class="purchase-invoice-metric">
						<span>{{ total.label }}</span>
						<strong>{{ totalValue(total) }}</strong>
					</div>
				</template>
			</FabricDocumentWorkspace>
		</section>

		<PurchaseInvoiceApproveDialog
			v-model:visible="approveVisible"
			:busy="acting === 'approve'"
			@approve="confirmApprove"
		/>
		<PurchaseInvoiceCancelDialog
			v-model:visible="cancelVisible"
			:busy="acting === 'cancel'"
			:has-erp-invoice="hasErpInvoice"
			@confirm="confirmCancel"
		/>
		<DocumentConfirmationDialog
			v-model:visible="confirmationVisible"
			:title="confirmation.title"
			:message="confirmation.message"
			:confirm-label="confirmation.label"
			:confirm-icon="confirmation.icon"
			:severity="confirmation.severity"
			:busy="Boolean(acting)"
			@confirm="confirmPendingAction"
		/>
		<DocumentErrorDialog
			:message="actionError"
			title="Purchase Invoice action could not be completed"
			@dismiss="actionError = ''"
		/>
		<RelatedDocumentWorkspaceDialog
			v-model:visible="grnVisible"
			doctype="YRP Goods Received Note"
			:name="selectedGrn"
			@changed="load(true)"
			@closed="selectedGrn = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import {
	approveInvoice,
	executePurchaseInvoiceCommand,
	getErpBillLink,
	getPurchaseInvoiceWorkspace,
	submitErpBill,
} from "../../api/accounts.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import FabricDocumentWorkspace from "../fabric-store/FabricDocumentWorkspace.vue"
import RelatedDocumentWorkspaceDialog from "../fabric-store/RelatedDocumentWorkspaceDialog.vue"
import { isCurrentRecordAction, purchaseInvoiceActionItems } from "./accountsViews.js"
import PurchaseInvoiceApproveDialog from "./components/PurchaseInvoiceApproveDialog.vue"
import PurchaseInvoiceCancelDialog from "./components/PurchaseInvoiceCancelDialog.vue"
import PurchaseInvoiceHeader from "./components/PurchaseInvoiceHeader.vue"
import PurchaseInvoiceTabs from "./components/PurchaseInvoiceTabs.vue"

const props = defineProps({
	purchaseInvoiceId: { type: String, default: "" },
})
const route = useRoute()
const router = useRouter()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const actionError = ref("")
const acting = ref("")
const activeTab = ref("details")
const approveVisible = ref(false)
const cancelVisible = ref(false)
const confirmationVisible = ref(false)
const pendingAction = ref("")
const grnVisible = ref(false)
const selectedGrn = ref("")
let loadSequence = 0
let actionSequence = 0
let isAlive = true

const handlers = {
	approve: () => { approveVisible.value = true },
	submit: () => requestConfirmation("submit"),
	cancel: () => { cancelVisible.value = true },
	amend: () => runDocumentCommand("amend"),
	delete: () => requestConfirmation("delete"),
	edit: openEditor,
	show_erp_bill: showErpBill,
	submit_erp_bill: () => requestConfirmation("submit_erp_bill"),
	fetch_expense_head: openExpenseHeadEditor,
}
const actions = computed(() => purchaseInvoiceActionItems(workspace.value.capabilities, handlers).map((action) => ({
	...action,
	disabled: Boolean(acting.value),
	loading: acting.value === action.key,
})))
const hasErpInvoice = computed(() => Boolean(
	workspace.value.record?.erp_inv_name
	|| workspace.value.details?.find((field) => field.fieldname === "erp_inv_name")?.value,
))
const confirmation = computed(() => ({
	submit: {
		title: "Submit Purchase Invoice?",
		message: `Submit ${workspace.value.record?.name || "this Purchase Invoice"}? Existing invoice validations will be applied.`,
		label: "Submit",
		icon: "pi pi-check",
		severity: "primary",
	},
	delete: {
		title: "Delete Purchase Invoice?",
		message: `Delete ${workspace.value.record?.name || "this Purchase Invoice"}? This action cannot be undone.`,
		label: "Delete Purchase Invoice",
		icon: "pi pi-trash",
		severity: "danger",
	},
	submit_erp_bill: {
		title: "Submit ERP Bill?",
		message: `Submit the ERP bill linked to ${workspace.value.record?.name || "this Purchase Invoice"}?`,
		label: "Submit ERP Bill",
		icon: "pi pi-send",
		severity: "primary",
	},
}[pendingAction.value] || {
	title: "Confirm action",
	message: "Continue with this Purchase Invoice action?",
	label: "Continue",
	icon: "pi pi-check",
	severity: "primary",
}))

function currentName() {
	return String(props.purchaseInvoiceId || route.params.purchaseInvoiceId || "")
}

async function load(refresh = false) {
	const name = currentName()
	const sequence = ++loadSequence
	if (!refresh) {
		loading.value = true
		workspace.value = {}
	} else {
		acting.value = "reload"
	}
	loadError.value = ""
	actionError.value = ""
	try {
		const payload = await getPurchaseInvoiceWorkspace(name) || {}
		if (sequence === loadSequence && name === currentName()) workspace.value = payload
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load this Purchase Invoice."
	} finally {
		if (sequence === loadSequence) {
			loading.value = false
			acting.value = ""
		}
	}
}

function resetRecordState() {
	actionSequence += 1
	acting.value = ""
	actionError.value = ""
	approveVisible.value = false
	cancelVisible.value = false
	confirmationVisible.value = false
	pendingAction.value = ""
	grnVisible.value = false
	selectedGrn.value = ""
	activeTab.value = "details"
}

function beginRecordAction(command, source) {
	acting.value = command
	actionError.value = ""
	return {
		command,
		name: String(source.name || ""),
		route: route.fullPath,
		sequence: ++actionSequence,
	}
}

function isOriginatingRecord(action) {
	return isAlive && isCurrentRecordAction(action, {
		name: currentName(),
		route: route.fullPath,
		sequence: actionSequence,
	})
}

function finishRecordAction(action) {
	if (isOriginatingRecord(action) && acting.value === action.command) acting.value = ""
}

function requestConfirmation(command) {
	pendingAction.value = command
	confirmationVisible.value = true
}

async function confirmPendingAction() {
	const command = pendingAction.value
	confirmationVisible.value = false
	pendingAction.value = ""
	if (command === "submit_erp_bill") {
		await runSubmitErpBill()
		return
	}
	if (command) await runDocumentCommand(command)
}

async function confirmApprove(comments) {
	const source = workspace.value.record || {}
	const action = beginRecordAction("approve", source)
	try {
		await approveInvoice(source.name, comments)
		if (!isOriginatingRecord(action)) return
		approveVisible.value = false
		await load(true)
	} catch (reason) {
		if (isOriginatingRecord(action)) {
			actionError.value = reason?.message || "Unable to approve this Purchase Invoice."
		}
	} finally {
		finishRecordAction(action)
	}
}

async function confirmCancel(payload) {
	const succeeded = await runDocumentCommand("cancel", payload)
	if (succeeded) cancelVisible.value = false
}

async function runDocumentCommand(command, payload = {}) {
	const source = workspace.value.record || {}
	const action = beginRecordAction(command, source)
	try {
		const result = await executePurchaseInvoiceCommand(source.name, command, payload, source.modified) || {}
		if (!isOriginatingRecord(action)) return false
		if (result.deleted) {
			await router.replace({ name: "accounts-purchase-invoices" })
			return true
		}
		if (command === "amend") {
			const amendedName = result.record?.name
			await router.push({
				name: "accounts-purchase-invoice-edit",
				params: { purchaseInvoiceId: amendedName },
				state: preserveListNavigationState(amendedName, result.record?.modified),
			})
			return true
		}
		workspace.value = result
		return true
	} catch (reason) {
		if (isOriginatingRecord(action)) {
			actionError.value = reason?.message || `Unable to ${command.replaceAll("_", " ")} this Purchase Invoice.`
		}
		return false
	} finally {
		finishRecordAction(action)
	}
}

function openEditor() {
	const record = workspace.value.record || {}
	router.push({
		name: "accounts-purchase-invoice-edit",
		params: { purchaseInvoiceId: record.name },
		state: preserveListNavigationState(record.name, record.modified),
	})
}

function openExpenseHeadEditor() {
	const record = workspace.value.record || {}
	router.push({
		name: "accounts-purchase-invoice-edit",
		params: { purchaseInvoiceId: record.name },
		query: { fetchExpenseHead: "1" },
		state: preserveListNavigationState(record.name, record.modified),
	})
}

async function showErpBill() {
	const source = workspace.value.record || {}
	const action = beginRecordAction("show_erp_bill", source)
	try {
		const url = await getErpBillLink(source.name)
		if (!isOriginatingRecord(action)) return
		if (!url) throw new Error("The ERP bill link is not available.")
		window.open(url, "_blank", "noopener")
	} catch (reason) {
		if (isOriginatingRecord(action)) actionError.value = reason?.message || "Unable to open the ERP bill."
	} finally {
		finishRecordAction(action)
	}
}

async function runSubmitErpBill() {
	const source = workspace.value.record || {}
	const action = beginRecordAction("submit_erp_bill", source)
	try {
		await submitErpBill(source.name)
		if (!isOriginatingRecord(action)) return
		await load(true)
	} catch (reason) {
		if (isOriginatingRecord(action)) actionError.value = reason?.message || "Unable to submit the ERP bill."
	} finally {
		finishRecordAction(action)
	}
}

function openGrn(name) {
	selectedGrn.value = name
	grnVisible.value = true
}

function totalValue(total) {
	return total.key === "total_quantity" ? number(total.value) : money(total.value)
}

function number(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "—"
}

function money(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
.purchase-invoice-page { width: 100%; max-width: 1840px; min-width: 0; margin: 0 auto var(--erp-space-3); padding: 0 clamp(2px, .7vw, 10px); }
.purchase-invoice-actions { display: flex; min-width: 0; align-items: center; gap: 6px; }
.purchase-invoice-metric { display: grid; min-height: 72px; align-content: center; gap: 3px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-metric:last-child { border-bottom: 0; }
.purchase-invoice-metric span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.purchase-invoice-metric strong { color: var(--erp-accent-hover); font-size: 19px; font-variant-numeric: tabular-nums; }
@media (max-width: 620px) { .purchase-invoice-actions { width: 100%; } .purchase-invoice-actions :deep(.document-action-strip) { flex: 1; } }
</style>

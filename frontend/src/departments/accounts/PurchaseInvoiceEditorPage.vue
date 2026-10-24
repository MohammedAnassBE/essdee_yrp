<template>
	<DepartmentPage
		title="Purchase Invoice"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
	>
		<section class="purchase-invoice-editor erp-card erp-editor-shell" aria-label="Purchase Invoice editor" :aria-busy="loading">
			<PurchaseInvoiceEditorHeader
				:current-name="currentName"
				:saved="Boolean(currentName)"
				:dirty="dirty"
				:docstatus="docstatus"
				:bill-tracking="form.bill_tracking"
				:busy="busy"
				:can-submit="canSubmit"
				:can-save="canSave"
				:saving="Boolean(saving)"
				@cancel="requestExit"
				@save="save"
			/>

			<div v-if="loading" class="purchase-invoice-editor__loading" role="status" aria-label="Loading Purchase Invoice editor">
				<Skeleton height="180px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError
				v-else-if="loadFailed"
				title="Purchase Invoice editor unavailable"
				:message="loadError"
				:loading="loading"
				@retry="load"
			/>
			<PurchaseInvoiceEditorBody
				v-else
				v-model:grns="grns"
				v-model:items="items"
				:groups="editorGroups"
				:form="form"
				:preview-totals="previewTotals"
				:current-name="currentName"
				:busy="busy"
				:fetching="fetching"
				:fetch-warnings="fetchWarnings"
				:is-rate-editable="isRateEditable"
				:erp-sync-enabled="erpSyncEnabled"
				@update-field="updateField"
				@fetch="requestFetch"
			/>
		</section>

		<DocumentConfirmationDialog
			v-model:visible="fetchConfirmationVisible"
			title="Replace migrated rows?"
			message="Fetching GRNs replaces the migrated rows. Continue?"
			confirm-label="Fetch GRNs"
			cancel-label="Keep Rows"
			confirm-icon="pi pi-download"
			severity="warn"
			:busy="fetching"
			@confirm="fetchSelectedGrns"
		/>
		<DocumentConfirmationDialog
			v-model:visible="discardVisible"
			title="Discard unsaved changes?"
			message="Your unsaved Purchase Invoice changes will be lost."
			confirm-label="Discard Changes"
			cancel-label="Keep Editing"
			confirm-icon="pi pi-trash"
			severity="danger"
			@update:visible="discardVisibilityChanged"
			@confirm="discardChanges"
		/>
		<DocumentErrorDialog
			:message="actionError"
			:title="actionErrorTitle"
			@dismiss="actionError = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"

import {
	fetchExpenseHeads,
	fetchGrnDetails,
	getPurchaseInvoiceEditor,
	savePurchaseInvoice,
} from "../../api/accounts.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import {
	PURCHASE_INVOICE_DISPLAY_FIELDS,
	PURCHASE_INVOICE_EDITOR_GROUPS,
	applySupplierChange,
	cloneValue,
	hasValue,
	isCurrentRecordAction,
	isMaskedValue,
	purchaseInvoiceEditorField,
	purchaseInvoicePreviewTotals,
	purchaseInvoiceSaveValues,
	queryValue,
} from "./accountsViews.js"
import PurchaseInvoiceEditorBody from "./components/PurchaseInvoiceEditorBody.vue"
import PurchaseInvoiceEditorHeader from "./components/PurchaseInvoiceEditorHeader.vue"
import { takeNewDocumentDefaults, withNewDocumentDefaults } from "../../utils/newDocumentDefaults.js"

const FORM_FIELDS = PURCHASE_INVOICE_EDITOR_GROUPS.flatMap((group) => group.fields)

const props = defineProps({
	purchaseInvoiceId: { type: String, default: "" },
	basePath: { type: String, default: "/accounts/purchase-invoices" },
	viewRouteName: { type: String, default: "accounts-purchase-invoice" },
	listRouteName: { type: String, default: "accounts-purchase-invoices" },
})
const route = useRoute()
const router = useRouter()
const toast = useToast()
const editor = ref({})
const form = reactive({ ...Object.fromEntries(FORM_FIELDS.map((fieldname) => [fieldname, ""])), bill_tracking: "" })
const grns = ref([])
const items = ref([])
const fetchWarnings = ref([])
const taxRates = ref({})
const loading = ref(true)
const loadFailed = ref(false)
const loadError = ref("")
const actionError = ref("")
const actionErrorTitle = ref("Purchase Invoice could not be saved")
const saving = ref("")
const fetching = ref(false)
const cleanSignature = ref("")
const fetchConfirmationVisible = ref(false)
const discardVisible = ref(false)
let allowNavigation = false
let pendingNavigation = null
let requestSequence = 0
let isAlive = true
let filterDefaults = takeNewDocumentDefaults("YRP Purchase Invoice")

const currentName = computed(() => String(props.purchaseInvoiceId || route.params.purchaseInvoiceId || ""))
const backTo = computed(() => currentName.value
	? `${props.basePath}/${encodeURIComponent(currentName.value)}`
	: props.basePath)
const backLabel = computed(() => currentName.value ? "Purchase Invoice" : "Purchase Invoices")
const billTracking = computed(() => queryValue(route.query.bill_tracking))
const duplicateFrom = computed(() => queryValue(route.query.duplicate_from))
const shouldFetchExpenseHeads = computed(() => queryValue(route.query.fetchExpenseHead) === "1")
const requestIdentity = computed(() => ({ name: currentName.value, route: route.fullPath }))
const signature = computed(() => JSON.stringify({ values: form, grns: grns.value, items: items.value }))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
const busy = computed(() => loading.value || Boolean(saving.value) || fetching.value)
const docstatus = computed(() => Number(editor.value.docstatus ?? editor.value.record?.docstatus ?? 0))
const isRateEditable = computed(() => !busy.value && (!editor.value.is_rate_only || docstatus.value === 0))
const canSubmit = computed(() => {
	const editorPermission = editor.value.permissions?.can_submit
		?? editor.value.can_submit
		?? editor.value.capabilities?.submit?.allowed
	if (editorPermission !== undefined && editorPermission !== null) return Boolean(editorPermission)
	return (window.frappe?.boot?.user?.can_submit || []).includes("YRP Purchase Invoice")
})
const erpSyncEnabled = computed(() => Boolean(editor.value.erp_sync_enabled || shouldFetchExpenseHeads.value))
const canSave = computed(() => !loadFailed.value && FORM_FIELDS.every((fieldname) => {
	const field = purchaseInvoiceEditorField(fieldname, editor.value)
	return !field.reqd || hasValue(form[fieldname])
}))
const previewTotals = computed(() => purchaseInvoicePreviewTotals(items.value, taxRates.value))
const editorGroups = computed(() => PURCHASE_INVOICE_EDITOR_GROUPS.map((group) => ({
	...group,
	fields: group.fields
		.filter((fieldname) => !PURCHASE_INVOICE_DISPLAY_FIELDS.includes(fieldname) || hasValue(form[fieldname]))
		.map((fieldname) => purchaseInvoiceEditorField(fieldname, editor.value)),
})))

async function load() {
	const request = beginRequest("load")
	startLoad()
	try {
		const payload = await getPurchaseInvoiceEditor(request.name || null, billTracking.value || null, request.name ? null : duplicateFrom.value || null) || {}
		if (!isCurrentRequest(request)) return
		applyEditor(payload)
		applyFilterDefaults(request)
		cleanSignature.value = signature.value
		if (shouldFetchExpenseHeads.value && items.value.length) await loadExpenseHeads(request)
	} catch (reason) {
		if (!isCurrentRequest(request)) return
		loadFailed.value = true
		loadError.value = reason?.message || "Unable to load the Purchase Invoice editor."
	} finally {
		if (isCurrentRequest(request)) loading.value = false
	}
}

/** Fills the list's filter values into a blank new invoice once; Bill Tracking and duplicate sources skip them. */
function applyFilterDefaults(request) {
	const defaults = Object.fromEntries(Object.entries(filterDefaults).filter(([fieldname]) => FORM_FIELDS.includes(fieldname)))
	filterDefaults = {}
	if (request.name || billTracking.value || duplicateFrom.value) return
	Object.assign(form, withNewDocumentDefaults({ ...form }, defaults))
}

function startLoad() {
	loading.value = true
	loadFailed.value = false
	loadError.value = ""
	actionError.value = ""
	saving.value = ""
	fetching.value = false
	fetchConfirmationVisible.value = false
	allowNavigation = false
	applyEditor({})
	cleanSignature.value = signature.value
}

function beginRequest(command) {
	return {
		command,
		...requestIdentity.value,
		sequence: ++requestSequence,
	}
}

function isCurrentRequest(request) {
	return isAlive && isCurrentRecordAction(request, {
		...requestIdentity.value,
		sequence: requestSequence,
	})
}

function applyEditor(payload) {
	editor.value = payload
	for (const fieldname of FORM_FIELDS) form[fieldname] = payload.values?.[fieldname] ?? ""
	form.bill_tracking = payload.values?.bill_tracking || ""
	grns.value = cloneValue(payload.grns || [])
	items.value = cloneValue(payload.items || [])
	fetchWarnings.value = []
	taxRates.value = {}
}

async function loadExpenseHeads(request) {
	try {
		const rows = await fetchExpenseHeads(cloneValue(items.value))
		if (!isCurrentRequest(request)) return
		mergeExpenseHeads(rows || [])
	} catch (reason) {
		if (!isCurrentRequest(request)) return
		showActionError("Expense heads could not be fetched", reason, "Unable to fetch expense heads.")
	}
}

function mergeExpenseHeads(rows) {
	const expenseHeads = new Map(rows.map((row) => [row.group_key, row.expense_head]))
	items.value = items.value.map((row) => expenseHeads.has(row.group_key)
		? { ...row, expense_head: expenseHeads.get(row.group_key) }
		: row)
}

function updateField(fieldname, value) {
	if (fieldname === "supplier") {
		const next = applySupplierChange({ values: { ...form }, grns: grns.value, items: items.value }, value || "")
		Object.assign(form, next.values)
		grns.value = next.grns
		items.value = next.items
		fetchWarnings.value = []
		taxRates.value = {}
		return
	}
	form[fieldname] = value ?? ""
	if (fieldname !== "against") return
	grns.value = []
	items.value = []
	fetchWarnings.value = []
	taxRates.value = {}
}

function requestFetch() {
	if (!grns.value.length) return
	if (editor.value.is_rate_only && items.value.length) {
		fetchConfirmationVisible.value = true
		return
	}
	fetchSelectedGrns()
}

async function fetchSelectedGrns() {
	fetchConfirmationVisible.value = false
	const request = beginRequest("fetch_grns")
	fetching.value = true
	fetchWarnings.value = []
	actionError.value = ""
	try {
		const payload = await fetchGrnDetails({
			grns: grns.value,
			against: form.against,
			supplier: isMaskedValue(form.supplier) ? undefined : form.supplier,
			purchaseInvoice: request.name || undefined,
			billTracking: form.bill_tracking || undefined,
		}) || {}
		if (!isCurrentRequest(request)) return
		applyFetchedGrns(payload)
	} catch (reason) {
		if (isCurrentRequest(request)) {
			showActionError("GRNs could not be fetched", reason, "Unable to fetch the selected GRNs.")
		}
	} finally {
		if (isCurrentRequest(request)) fetching.value = false
	}
}

function applyFetchedGrns(payload) {
	const additionalRows = payload.additional_field_values?.essdee_items
	const rows = Array.isArray(additionalRows) ? additionalRows : payload.commercial_items
	items.value = cloneValue(Array.isArray(rows) ? rows : [])
	fetchWarnings.value = cloneValue(Array.isArray(payload.warnings) ? payload.warnings : [])
	taxRates.value = { ...(payload.tax_rates || {}) }
	editor.value = {
		...editor.value,
		is_rate_only: false,
		essdee_rate_table_source: payload.additional_field_values?.essdee_rate_table_source || "yrp_grn_v1",
	}
}

async function save(submit) {
	const request = beginRequest(submit ? "submit" : "save")
	saving.value = submit ? "submit" : "save"
	actionError.value = ""
	try {
		const workspace = await savePurchaseInvoice({
			values: purchaseInvoiceSaveValues(form, FORM_FIELDS),
			grns: cloneValue(grns.value),
			items: cloneValue(items.value),
		}, {
			name: request.name || undefined,
			submit,
			expectedModified: editor.value.modified,
		})
		if (!isCurrentRequest(request)) return
		await finishSave(workspace, submit)
	} catch (reason) {
		if (isCurrentRequest(request)) {
			showActionError("Purchase Invoice could not be saved", reason, "Unable to save this Purchase Invoice.")
		}
	} finally {
		if (isCurrentRequest(request)) saving.value = ""
	}
}

async function finishSave(workspace, submit) {
	const record = workspace?.record || {}
	if (!record.name) throw new Error("The saved Purchase Invoice name was not returned.")
	cleanSignature.value = signature.value
	allowNavigation = true
	toast.add({
		severity: "success",
		summary: submit ? "Purchase Invoice submitted" : "Purchase Invoice saved",
		detail: record.name,
		life: 3500,
	})
	await router.replace({
		name: props.viewRouteName,
		params: { purchaseInvoiceId: record.name },
		state: preserveListNavigationState(record.name, record.modified),
	})
}

function requestExit() {
	if (dirty.value) {
		discardVisible.value = true
		return
	}
	navigateBack()
}

function discardVisibilityChanged(visible) {
	if (visible || !pendingNavigation) return
	pendingNavigation(false)
	pendingNavigation = null
}

function discardChanges() {
	discardVisible.value = false
	allowNavigation = true
	if (pendingNavigation) {
		const next = pendingNavigation
		pendingNavigation = null
		next()
		return
	}
	navigateBack()
}

function navigateBack() {
	if (!currentName.value) {
		router.push({ name: props.listRouteName })
		return
	}
	router.push({
		name: props.viewRouteName,
		params: { purchaseInvoiceId: currentName.value },
		state: preserveListNavigationState(currentName.value, editor.value.modified),
	})
}

function showActionError(title, reason, fallback) {
	actionErrorTitle.value = title
	actionError.value = reason?.message || fallback
}

function beforeUnload(event) {
	if (!dirty.value) return
	event.preventDefault()
	event.returnValue = ""
}

function guardUnsavedChanges(_to, _from, next) {
	if (allowNavigation || !dirty.value) return next()
	pendingNavigation = next
	discardVisible.value = true
}

onBeforeRouteLeave(guardUnsavedChanges)
onBeforeRouteUpdate(guardUnsavedChanges)
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
	isAlive = false
	requestSequence += 1
	if (pendingNavigation) pendingNavigation(false)
	pendingNavigation = null
	window.removeEventListener("beforeunload", beforeUnload)
})
watch(
	requestIdentity,
	load,
	{ immediate: true },
)
watch(grns, () => {
	fetchWarnings.value = []
}, { deep: true })
</script>

<style scoped>
.purchase-invoice-editor { --purchase-invoice-editor-inline: clamp(14px, 1.5vw, 24px); display: flex; width: 100%; min-height: calc(100dvh - var(--erp-shell-header-height) - 78px); flex-direction: column; gap: var(--erp-space-3); padding: 0 var(--purchase-invoice-editor-inline) var(--erp-space-4); border-color: color-mix(in srgb, var(--erp-border) 84%, var(--erp-surface)); background: var(--erp-bg); }
.purchase-invoice-editor__loading { display: grid; min-width: 0; gap: var(--erp-space-3); }
@media (max-width: 700px) { .purchase-invoice-editor { padding: 0 var(--erp-space-3) var(--erp-space-3); } }
</style>

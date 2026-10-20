<template>
	<DepartmentPage
		title="Bill Tracking"
		:back-to="backTo"
		back-label="Bill Tracking"
		:show-title="false"
		flat
		full-width
	>
		<section class="bill-tracking-editor erp-card erp-editor-shell" aria-label="Bill Tracking editor" :aria-busy="loading">
			<header class="bill-tracking-editor__header erp-editor-header">
				<div>
					<span>{{ currentName || "New document" }}</span>
					<h1 class="erp-doc-title">{{ currentName ? "Edit Bill Tracking" : "New Bill Tracking" }}</h1>
				</div>
				<div class="erp-editor-actions">
					<Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="busy" @click="requestExit" />
					<DocumentSaveButton :saved="Boolean(currentName)" :dirty="dirty" :docstatus="Number(editor.docstatus || editor.record?.docstatus || 0)" :document-label="`Bill Tracking ${currentName}`.trim()"
						:show-submit="canSubmit"
						:loading="Boolean(saving)"
						:disabled="busy || !canSave"
						@save="save(false)"
						@submit="save(true)"
					/>
				</div>
			</header>

			<div v-if="loading" class="bill-tracking-editor__loading" role="status" aria-label="Loading Bill Tracking editor">
				<Skeleton height="160px" />
				<Skeleton height="340px" />
			</div>
			<WorkspaceLoadError
				v-else-if="loadFailed"
				:message="loadError"
				:loading="loading"
				@retry="load"
			/>
			<div v-else class="bill-tracking-editor__body">
				<Message v-if="validationMessage" severity="warn" closable @close="validationMessage = ''">
					{{ validationMessage }}
				</Message>
				<DocumentFieldGroupGrid
					:groups="FIELD_GROUPS"
					aria-label="Bill Tracking fields"
					root-class="bill-tracking-editor__groups"
					content-class="bill-tracking-editor__fields"
				>
					<template #default="{ group }">
						<FormField
							v-for="field in fieldsFor(group)"
							:key="field.fieldname"
							v-model="form[field.fieldname]"
							:field="field"
							:form="form"
							:required="isRequired(field)"
							:invalid="hasFieldError(field.fieldname)"
							:error="fieldError(field.fieldname)"
							:disabled="busy"
						/>
						<DeliveryPersonSuggestion
							v-if="group.key === 'delivery' && form.supplier"
							v-model="form.delivery_mob_no"
							:supplier="form.supplier"
							:can-create-delivery-person="Boolean(editor.can_create_delivery_person)"
							:disabled="busy"
							@saving-change="deliveryPersonSaving = $event"
						/>
					</template>
				</DocumentFieldGroupGrid>
			</div>
		</section>

		<DocumentConfirmationDialog
			v-model:visible="discardVisible"
			title="Discard unsaved changes?"
			message="Your unsaved Bill Tracking changes will be lost."
			confirm-label="Discard Changes"
			cancel-label="Keep Editing"
			confirm-icon="pi pi-trash"
			severity="danger"
			@update:visible="discardVisibilityChanged"
			@confirm="discardChanges"
		/>
		<DocumentErrorDialog
			:message="saveError"
			title="Bill Tracking could not be saved"
			@dismiss="saveError = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"

import { getBillTrackingEditor, saveBillTracking } from "../../api/hr.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import FormField from "../../components/common/FormField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentFieldGroupGrid from "../../components/documents/DocumentFieldGroupGrid.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import DeliveryPersonSuggestion from "./components/DeliveryPersonSuggestion.vue"

const FIELD_GROUPS = [
	{
		key: "bill",
		eyebrow: "Vendor invoice",
		label: "Bill",
		fields: ["supplier", "bill_no", "bill_date", "invoice_value"],
	},
	{
		key: "delivery",
		eyebrow: "Receipt",
		label: "Delivery",
		fields: ["received_date", "received_via", "receive_comment"],
	},
]
const FORM_FIELDS = [
	"supplier",
	"bill_no",
	"bill_date",
	"invoice_value",
	"received_date",
	"received_via",
	"receive_comment",
	"delivery_mob_no",
]
const REQUIRED_FIELDS = new Set(["supplier", "bill_no", "bill_date", "invoice_value", "received_date", "received_via"])
const FALLBACK_SCHEMA = {
	supplier: { label: "Supplier", fieldtype: "Link", options: "Supplier" },
	bill_no: { label: "Bill No", fieldtype: "Data" },
	bill_date: { label: "Bill Date", fieldtype: "Date" },
	invoice_value: { label: "Invoice Value", fieldtype: "Currency" },
	received_date: { label: "Received Date", fieldtype: "Date" },
	received_via: { label: "Received Via", fieldtype: "Select" },
	receive_comment: { label: "Receive Comment", fieldtype: "Small Text" },
	delivery_mob_no: { label: "Delivery Person Mobile No", fieldtype: "Link", options: "YRP Vendor Bill Delivery Person" },
}

const props = defineProps({
	billTrackingId: { type: String, default: "" },
	basePath: { type: String, default: "/hr/bill-tracking" },
	viewRouteName: { type: String, default: "hr-bill-tracking" },
	listRouteName: { type: String, default: "hr-bill-trackings" },
})
const route = useRoute()
const router = useRouter()
const toast = useToast()
const editor = ref({})
const form = reactive(Object.fromEntries(FORM_FIELDS.map((fieldname) => [fieldname, ""])))
const loading = ref(true)
const loadFailed = ref(false)
const loadError = ref("")
const saving = ref("")
const saveError = ref("")
const validationMessage = ref("")
const attempted = ref(false)
const cleanSignature = ref("")
const discardVisible = ref(false)
const deliveryPersonSaving = ref(false)
let allowNavigation = false
let pendingNavigation = null
let requestSequence = 0
let isAlive = true

const currentName = computed(() => String(props.billTrackingId || route.params.billTrackingId || ""))
const backTo = computed(() => currentName.value
	? `${props.basePath}/${encodeURIComponent(currentName.value)}`
	: props.basePath)
const signature = computed(() => JSON.stringify(FORM_FIELDS.map((fieldname) => form[fieldname] ?? "")))
const dirty = computed(() => !loading.value && signature.value !== cleanSignature.value)
const busy = computed(() => loading.value || Boolean(saving.value) || deliveryPersonSaving.value)
const canSubmit = computed(() => Boolean(editor.value.can_submit))
const canSave = computed(() => REQUIRED_FIELDS.size > 0 && [...REQUIRED_FIELDS].every(hasValue)
	&& (form.received_via !== "Others" || hasValue("receive_comment")))

async function load() {
	const request = beginRequest("load")
	loading.value = true
	loadFailed.value = false
	loadError.value = ""
	saveError.value = ""
	saving.value = ""
	deliveryPersonSaving.value = false
	attempted.value = false
	allowNavigation = false
	try {
		const payload = await getBillTrackingEditor(request.name || null) || {}
		if (!isCurrentRequest(request)) return
		editor.value = payload
		for (const fieldname of FORM_FIELDS) form[fieldname] = payload.values?.[fieldname] ?? ""
		form.received_date ||= today()
		cleanSignature.value = signature.value
	} catch (reason) {
		if (!isCurrentRequest(request)) return
		loadFailed.value = true
		loadError.value = reason?.message || "Unable to load the Bill Tracking editor."
	} finally {
		if (isCurrentRequest(request)) loading.value = false
	}
}

function beginRequest(command) {
	return {
		command,
		name: currentName.value,
		sequence: ++requestSequence,
	}
}

function isCurrentRequest(request) {
	return isAlive && request.name === currentName.value && request.sequence === requestSequence
}

function fieldsFor(group) {
	return group.fields
		.filter((fieldname) => fieldname !== "receive_comment" || form.received_via === "Others")
		.map(editorField)
}

function editorField(fieldname) {
	const schema = { ...FALLBACK_SCHEMA[fieldname], ...(editor.value.schema?.[fieldname] || {}), fieldname }
	if (fieldname === "supplier") schema.link_filters = { disabled: 0 }
	if (fieldname === "received_via") {
		schema.fieldtype = "Select"
		schema.options = (editor.value.received_via_options || []).join("\n")
	}
	return schema
}

function hasValue(fieldname) {
	const value = form[fieldname]
	return value !== null && value !== undefined && String(value).trim() !== ""
}

function isRequired(field) {
	return Boolean(field.reqd) || REQUIRED_FIELDS.has(field.fieldname)
		|| (field.fieldname === "receive_comment" && form.received_via === "Others")
}

function hasFieldError(fieldname) {
	return Boolean(attempted.value && isRequired(editorField(fieldname)) && !hasValue(fieldname))
}

function fieldError(fieldname) {
	return hasFieldError(fieldname) ? `${editorField(fieldname).label} is required.` : ""
}

async function save(submit) {
	attempted.value = true
	validationMessage.value = ""
	saveError.value = ""
	if (submit && !canSubmit.value) {
		validationMessage.value = "You do not have permission to submit this bill."
		return
	}
	if (!canSave.value) {
		validationMessage.value = "Complete the required Bill and Delivery fields."
		return
	}
	const request = beginRequest(submit ? "submit" : "save")
	saving.value = submit ? "submit" : "save"
	try {
		const workspace = await saveBillTracking({ ...form }, {
			name: request.name || undefined,
			submit,
			expectedModified: editor.value.modified,
		})
		if (!isCurrentRequest(request)) return
		const record = workspace?.record || {}
		cleanSignature.value = signature.value
		allowNavigation = true
		toast.add({
			severity: "success",
			summary: submit ? "Bill submitted" : "Bill saved",
			detail: record.name || "Your changes are saved.",
			life: 3500,
		})
		await router.replace({
			name: props.viewRouteName,
			params: { billTrackingId: record.name },
			state: preserveListNavigationState(record.name, record.modified),
		})
	} catch (reason) {
		if (isCurrentRequest(request)) saveError.value = reason?.message || "Unable to save this bill."
	} finally {
		if (isCurrentRequest(request)) saving.value = ""
	}
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
	if (currentName.value) {
		router.push({
			name: props.viewRouteName,
			params: { billTrackingId: currentName.value },
			state: preserveListNavigationState(currentName.value, editor.value.modified),
		})
		return
	}
	router.push({ name: props.listRouteName })
}

function today() {
	const now = new Date()
	const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
	return localTime.toISOString().slice(0, 10)
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
watch(currentName, load, { immediate: true })
</script>

<style scoped>
.bill-tracking-editor { display: flex; width: 100%; min-height: calc(100dvh - var(--erp-shell-header-height) - 78px); flex-direction: column; gap: var(--erp-space-3); padding: 0 0 var(--erp-space-4); border-color: color-mix(in srgb, var(--erp-border) 84%, var(--erp-surface)); background: color-mix(in srgb, var(--erp-bg) 72%, var(--erp-surface)); }
.bill-tracking-editor__loading, .bill-tracking-editor__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.bill-tracking-editor__body { width: 100%; }
.bill-tracking-editor__fields { align-items: end; }
</style>

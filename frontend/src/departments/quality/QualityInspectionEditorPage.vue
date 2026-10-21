<template>
	<DepartmentPage title="Quality Inspection" :back-to="backTo" back-label="Inspections" :show-title="false" flat full-width>
		<section class="quality-page" :aria-busy="busy" aria-label="Quality Inspection editor">
			<header class="quality-page__header"><h1 class="erp-doc-title">{{ currentName ? `Edit ${currentName}` : amendFrom ? `Amend ${amendFrom}` : 'New Quality Inspection' }}</h1></header>
			<ListPageSkeleton v-if="loading" />
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<template v-else>
				<section v-for="group in INSPECTION_GROUPS" :key="group.key" class="quality-page__section" :aria-labelledby="`inspection-${group.key}`">
					<h2 :id="`inspection-${group.key}`">{{ group.label }}</h2>
					<InspectionColourSizePicker v-if="group.key === 'selection'" v-model="selection" :disabled="busy" />
					<InspectionImageUpload v-else-if="group.key === 'approval'" v-model="form.upload_quality_approval_sheet"
						:docname="currentName" :disabled="busy && !uploading" @uploading-change="uploading = $event" />
					<div v-else class="quality-page__grid">
						<template v-for="field in visibleInspectionFields(group, form)" :key="field.fieldname">
							<dl v-if="field.read_only" class="quality-page__fact">
								<dt>{{ field.label }}</dt><dd><DocumentLink v-if="field.fieldtype === 'Link'" :doctype="field.options" :name="form[field.fieldname]" />
									<template v-else>{{ formatDocumentOverviewValue({ ...field, value: form[field.fieldname] }) }}</template></dd>
							</dl>
							<FormField v-else v-model="form[field.fieldname]" :field="field" :form="form" :required="Boolean(field.reqd)" :disabled="busy" />
						</template>
					</div>
					<p v-if="group.key === 'work_order' && fetchingWorkOrder" role="status">Loading Work Order…</p>
					<p v-if="group.key === 'quantities' && fetchingAql" role="status">Calculating AQL limits…</p>
					<div v-if="group.key === 'defects' && preview" class="quality-page__preview">
						<span>Calculated result preview</span><DocumentStatusBadge :label="preview" :tone="resultTone(preview)" />
					</div>
				</section>
				<footer class="quality-page__footer">
					<Button label="Cancel" severity="secondary" :disabled="busy" @click="router.push(backTo)" />
					<DocumentSaveButton :saved="Boolean(currentName)" :dirty="dirty" :docstatus="Number(workspace.record?.docstatus || 0)"
						:document-label="`Quality Inspection ${currentName}`" :show-submit="Boolean(workspace.actions?.submit?.allowed)"
						:loading="saving" :disabled="busy || !canSave" @save="save" @submit="submit" />
				</footer>
			</template>
		</section>
		<DocumentConfirmationDialog v-model:visible="discardVisible" title="Discard unsaved changes?" message="Your unsaved inspection changes will be lost."
			confirm-label="Discard Changes" cancel-label="Keep Editing" @confirm="discard" @update:visible="discardVisibilityChanged" />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import { useToast } from "primevue/usetoast"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"
import { submitDoc } from "../../api/frappe.js"
import { getInspectionWorkspace, getNewInspectionDefaults, getInspectionAgainstDetails, getInspectionAqlLimits, saveInspection } from "../../api/quality.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentLink from "../../components/common/DocumentLink.vue"
import FormField from "../../components/common/FormField.vue"
import ListPageSkeleton from "../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import { formatDocumentOverviewValue } from "../../utils/documentOverview.js"
import InspectionColourSizePicker from "./components/InspectionColourSizePicker.vue"
import InspectionImageUpload from "./components/InspectionImageUpload.vue"
import { INSPECTION_GROUPS, visibleInspectionFields } from "./inspectionFields.js"
import { INSPECTION_DOCTYPE, INSPECTION_EDITABLE_FIELDS, cleanSelection, inspectionPayload, inspectionResultPreview, resultTone, validAqlInputs } from "./qualityViews.js"
import "./quality.css"

const props = defineProps({ inspectionId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const toast = useToast()
const form = reactive({})
const workspace = ref({})
const selection = ref(cleanSelection())
const loading = ref(true)
const loadError = ref("")
const error = ref("")
const saving = ref(false)
const uploading = ref(false)
const fetchingWorkOrder = ref(false)
const fetchingAql = ref(false)
const workOrderReady = ref(false)
const aqlReady = ref(false)
const cleanSignature = ref("")
const discardVisible = ref(false)
let pendingNavigation = null
let allowNavigation = false
let active = true
let loadSequence = 0
let workOrderSequence = 0
let aqlSequence = 0
const currentName = computed(() => props.inspectionId || String(route.params.inspectionId || ""))
const amendFrom = computed(() => String(route.query.amend_from || ""))
const backTo = computed(() => currentName.value ? `/quality/inspections/${encodeURIComponent(currentName.value)}` : "/quality/inspections")
const signature = computed(() => JSON.stringify(inspectionPayload(form, selection.value)))
const dirty = computed(() => !loading.value && !loadError.value && signature.value !== cleanSignature.value)
const busy = computed(() => loading.value || saving.value || uploading.value || fetchingWorkOrder.value || fetchingAql.value)
const preview = computed(() => aqlReady.value ? inspectionResultPreview(form) : "")
const canSave = computed(() => workOrderReady.value && aqlReady.value && validAqlInputs(form)
	&& Boolean(form.against_id && form.inspection_type)
	&& (!Number(form.is_third_party) || Boolean(form.third_party_supplier)))

async function load() {
	const sequence = ++loadSequence
	++workOrderSequence
	++aqlSequence
	loading.value = true
	loadError.value = ""
	error.value = ""
	workOrderReady.value = false
	aqlReady.value = false
	fetchingWorkOrder.value = false
	fetchingAql.value = false
	allowNavigation = false
	try {
		const payload = currentName.value ? await getInspectionWorkspace(currentName.value)
			: await getNewInspectionDefaults({ against_id: route.query.against_id, grn: route.query.grn, amend_from: amendFrom.value || undefined })
		if (!active || sequence !== loadSequence) return
		if (currentName.value && !payload.actions?.edit?.allowed) throw new Error("This inspection cannot be edited.")
		workspace.value = currentName.value ? payload : {}
		for (const key of Object.keys(form)) delete form[key]
		Object.assign(form, Object.fromEntries(INSPECTION_EDITABLE_FIELDS.map((key) => [key, ""])), {
			against: "YRP Work Order", is_third_party: 0, major_defect_found: 0, minor_defect_found: 0, spi_found: 0,
		}, payload.record || payload)
		delete form.against_details
		if (payload.against_details) applyAgainstDetails(payload.against_details)
		else selection.value = cleanSelection(payload.colour_size_data || {})
		workOrderReady.value = Boolean(form.against_id)
		await nextTick()
		cleanSignature.value = signature.value
	} catch (reason) {
		if (active && sequence === loadSequence) loadError.value = reason?.message || "Unable to load inspection."
	} finally {
		if (active && sequence === loadSequence) {
			loading.value = false
			if (!loadError.value) refreshAql()
		}
	}
}

function applyAgainstDetails(details = {}) {
	for (const key of ["item", "lot", "supplier", "order_qty"]) form[key] = details[key] ?? ""
	selection.value = cleanSelection(details)
}

async function refreshWorkOrder(name) {
	const sequence = ++workOrderSequence
	workOrderReady.value = false
	fetchingWorkOrder.value = false
	applyAgainstDetails()
	if (!name) return
	fetchingWorkOrder.value = true
	try {
		const details = await getInspectionAgainstDetails(name)
		if (!active || sequence !== workOrderSequence) return
		applyAgainstDetails(details)
		workOrderReady.value = true
	} catch (reason) {
		if (active && sequence === workOrderSequence) error.value = reason?.message || "Unable to load Work Order."
	} finally {
		if (active && sequence === workOrderSequence) fetchingWorkOrder.value = false
	}
}

async function refreshAql() {
	const sequence = ++aqlSequence
	aqlReady.value = false
	fetchingAql.value = false
	for (const key of ["sample_piece_count", "major_defect_maximum_allowed", "minor_defect_maximum_allowed"]) form[key] = null
	if (!validAqlInputs(form)) return
	fetchingAql.value = true
	try {
		const limits = await getInspectionAqlLimits({ ...form })
		if (!active || sequence !== aqlSequence) return
		Object.assign(form, { sample_piece_count: limits.sample, major_defect_maximum_allowed: limits.major_allowed, minor_defect_maximum_allowed: limits.minor_allowed })
		aqlReady.value = true
	} catch (reason) {
		if (active && sequence === aqlSequence) error.value = reason?.message || "Unable to calculate AQL limits."
	} finally {
		if (active && sequence === aqlSequence) fetchingAql.value = false
	}
}

async function save() {
	if (busy.value || !canSave.value) return
	saving.value = true
	try {
		const payload = await saveInspection(inspectionPayload(form, selection.value), { name: currentName.value, expectedModified: workspace.value.record?.modified })
		if (!active) return
		cleanSignature.value = signature.value
		allowNavigation = true
		toast.add({ severity: "success", summary: "Inspection saved", detail: payload.record.name, life: 3500 })
		await router.replace({ name: "quality-inspection", params: { inspectionId: payload.record.name }, state: preserveListNavigationState(payload.record.name, payload.record.modified) })
	} catch (reason) {
		if (active) error.value = reason?.message || "Unable to save inspection."
	} finally {
		if (active) saving.value = false
	}
}

async function submit() {
	if (busy.value || dirty.value || !workspace.value.actions?.submit?.allowed) return
	saving.value = true
	try {
		await submitDoc(INSPECTION_DOCTYPE, currentName.value, workspace.value.record.modified)
		if (!active) return
		allowNavigation = true
		toast.add({ severity: "success", summary: "Inspection submitted", life: 3500 })
		await router.replace(backTo.value)
	} catch (reason) {
		if (active) error.value = reason?.message || "Unable to submit inspection."
	} finally {
		if (active) saving.value = false
	}
}

function guard(_to, _from, next) {
	if (allowNavigation) return next()
	if (saving.value || uploading.value) return next(false)
	if (!dirty.value) return next()
	pendingNavigation = next
	discardVisible.value = true
}
function discard() {
	const next = pendingNavigation
	pendingNavigation = null
	discardVisible.value = false
	next?.()
}
function discardVisibilityChanged(visible) {
	if (visible || !pendingNavigation) return
	pendingNavigation(false)
	pendingNavigation = null
}
function beforeUnload(event) {
	if (!dirty.value && !uploading.value && !saving.value) return
	event.preventDefault()
	event.returnValue = ""
}

watch(() => form.against_id, (name) => { if (!loading.value) refreshWorkOrder(name) })
watch(() => [form.offer_qty, form.checking_level, form.major_aql_level, form.minor_aql_level], () => { if (!loading.value) refreshAql() })
watch(() => [currentName.value, route.query.against_id, route.query.grn, amendFrom.value], load, { immediate: true })
onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
onMounted(() => window.addEventListener("beforeunload", beforeUnload))
onBeforeUnmount(() => {
	active = false
	++loadSequence
	++workOrderSequence
	++aqlSequence
	pendingNavigation?.(false)
	window.removeEventListener("beforeunload", beforeUnload)
})
</script>

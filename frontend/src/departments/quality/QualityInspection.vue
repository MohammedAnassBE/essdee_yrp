<template>
	<DepartmentPage title="Quality Inspection" back-to="/quality/inspections" back-label="Inspections" :show-title="false" flat full-width>
		<ListPageSkeleton v-if="loading" />
		<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
		<section v-else class="quality-page" :aria-busy="Boolean(acting)">
			<header class="quality-page__header">
				<div><h1 class="erp-doc-title">{{ record.name }}</h1><div class="quality-page__badges">
					<DocumentStatusBadge :docstatus="record.docstatus" />
					<DocumentStatusBadge v-if="record.result" :label="record.result" :tone="resultTone(record.result)" />
				</div></div>
			</header>
			<section v-for="group in INSPECTION_GROUPS" :key="group.key" class="quality-page__section" :aria-labelledby="`inspection-view-${group.key}`">
				<h2 :id="`inspection-view-${group.key}`">{{ group.label }}</h2>
				<InspectionColourSizePicker v-if="group.key === 'selection'" :model-value="workspace.colour_size_data || {}" readonly />
				<template v-else-if="group.key === 'approval'">
					<a v-if="record.upload_quality_approval_sheet" class="quality-page__image" :href="record.upload_quality_approval_sheet" target="_blank" rel="noopener" aria-label="Open approval sheet image">
						<img :src="record.upload_quality_approval_sheet" alt="Quality approval sheet" />
					</a>
					<span v-else class="quality-page__muted">No approval sheet attached.</span>
				</template>
				<div v-else class="quality-page__grid">
					<dl v-for="field in visibleInspectionFields(group, record, true)" :key="field.fieldname" class="quality-page__fact">
						<dt>{{ field.label }}</dt>
						<dd><DocumentLink v-if="['Link', 'Dynamic Link'].includes(field.fieldtype)" :doctype="field.fieldtype === 'Dynamic Link' ? record[field.options] : field.options" :name="record[field.fieldname]" current-path="/web/quality/inspections" />
							<DocumentStatusBadge v-else-if="['result', 'calculated_result'].includes(field.fieldname) && record[field.fieldname]" :label="record[field.fieldname]" :tone="resultTone(record[field.fieldname])" />
							<template v-else>{{ formatDocumentOverviewValue({ ...field, value: record[field.fieldname] }) }}</template>
						</dd>
					</dl>
				</div>
			</section>
			<InspectionDebitDetails :debits="workspace.debit_details || []" />
			<footer class="quality-page__footer quality-page__actions">
				<DocumentActionStrip :actions="actions">
					<template v-if="workspace.actions?.submit?.allowed" #primary>
						<DocumentSaveButton class="document-action-strip__primary" saved :dirty="false" :show-save="false" show-submit
							:docstatus="Number(record.docstatus)" :document-label="`Quality Inspection ${record.name}`" :disabled="Boolean(acting)" :loading="acting === 'submit'" @submit="submit" />
					</template>
				</DocumentActionStrip>
			</footer>
			<DocumentDeleteButton v-if="workspace.actions?.delete?.allowed" ref="deleteControl" :show-trigger="false" :doctype="INSPECTION_DOCTYPE" :name="record.name" :docstatus="record.docstatus" :disabled="Boolean(acting)" redirect-to="/quality/inspections" />
			<DocumentPrintButton ref="printControl" :show-trigger="false" :doctype="INSPECTION_DOCTYPE" :name="record.name" :docstatus="record.docstatus" :formats="workspace.print_formats || []" :disabled="Boolean(acting)" />
		</section>
		<InspectionResultDialog :key="`result-${currentName}`" v-model:visible="resultVisible" :busy="acting === 'update_status'" @confirm="updateResult" />
		<InspectionDebitDialog :key="`debit-${currentName}`" v-model:visible="debitVisible" :busy="acting === 'create_debit'" @confirm="createDebit" />
		<DocumentConfirmationDialog v-model:visible="cancelVisible" title="Cancel inspection?" :message="`Cancel Quality Inspection ${record.name}?`" confirm-label="Cancel Inspection" :busy="Boolean(acting)" @confirm="cancel" />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import { useToast } from "primevue/usetoast"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { cancelDoc, submitDoc } from "../../api/frappe.js"
import { createInspectionDebit, getInspectionWorkspace, updateInspectionResult } from "../../api/quality.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import DocumentLink from "../../components/common/DocumentLink.vue"
import ListPageSkeleton from "../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentActionStrip from "../../components/documents/DocumentActionStrip.vue"
import DocumentConfirmationDialog from "../../components/documents/DocumentConfirmationDialog.vue"
import DocumentDeleteButton from "../../components/documents/DocumentDeleteButton.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import InspectionColourSizePicker from "./components/InspectionColourSizePicker.vue"
import InspectionDebitDetails from "./components/InspectionDebitDetails.vue"
import InspectionDebitDialog from "./components/InspectionDebitDialog.vue"
import InspectionResultDialog from "./components/InspectionResultDialog.vue"
import { INSPECTION_GROUPS, visibleInspectionFields } from "./inspectionFields.js"
import { formatDocumentOverviewValue } from "../../utils/documentOverview.js"
import { INSPECTION_DOCTYPE, copyText, inspectionActionItems, inspectionShareCaption, resultTone } from "./qualityViews.js"
import "./quality.css"

const props = defineProps({ inspectionId: { type: String, default: "" } })
const route = useRoute()
const router = useRouter()
const toast = useToast()
const workspace = ref({})
const loading = ref(true)
const loadError = ref("")
const error = ref("")
const acting = ref("")
const resultVisible = ref(false)
const debitVisible = ref(false)
const cancelVisible = ref(false)
const deleteControl = ref(null)
const printControl = ref(null)
const currentName = computed(() => props.inspectionId || String(route.params.inspectionId || ""))
const record = computed(() => workspace.value.record || {})
let active = true
let loadSequence = 0
const actions = computed(() => {
	const items = inspectionActionItems(workspace.value.actions, {
		submit,
		edit: () => router.push(`/quality/inspections/${encodeURIComponent(record.value.name)}/edit`),
		amend: () => router.push(`/quality/inspections/new?amend_from=${encodeURIComponent(record.value.name)}`),
		update_status: () => { resultVisible.value = true },
		create_debit: () => { debitVisible.value = true },
		share,
		cancel: () => { cancelVisible.value = true },
		delete: () => deleteControl.value?.open(),
	})
	if (workspace.value.permissions?.can_print || workspace.value.print_formats?.length) items.push({
		key: "print", label: "Print", icon: "pi pi-print", menuOnly: true,
		command: () => printControl.value?.open(), disabled: !workspace.value.print_formats?.length,
	})
	return items.map((action) => ({ ...action, disabled: Boolean(acting.value) || Boolean(action.disabled) }))
})

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getInspectionWorkspace(currentName.value)
		if (active && sequence === loadSequence) workspace.value = payload
	} catch (reason) {
		if (active && sequence === loadSequence) loadError.value = reason?.message || "Unable to load inspection."
	} finally {
		if (active && sequence === loadSequence) loading.value = false
	}
}

async function run(key, operation, summary) {
	if (acting.value || !workspace.value.actions?.[key]?.allowed) return
	const name = currentName.value
	acting.value = key
	error.value = ""
	try {
		const result = await operation({ ...record.value })
		if (!active || currentName.value !== name) return
		resultVisible.value = debitVisible.value = cancelVisible.value = false
		toast.add({ severity: "success", summary: typeof summary === "function" ? summary(result) : summary, life: 3500 })
		await load()
	} catch (reason) {
		if (active && currentName.value === name) error.value = reason?.message || "Unable to complete inspection action."
	} finally {
		if (active && currentName.value === name) acting.value = ""
	}
}

function submit() {
	return run("submit", (doc) => submitDoc(INSPECTION_DOCTYPE, doc.name, doc.modified), "Inspection submitted")
}
function cancel() {
	return run("cancel", (doc) => cancelDoc(INSPECTION_DOCTYPE, doc.name, doc.modified), "Inspection cancelled")
}
function updateResult(result) {
	return run("update_status", (doc) => updateInspectionResult(doc.name, result, doc.modified), "Inspection status updated")
}
function createDebit(values) {
	return run("create_debit", (doc) => createInspectionDebit(doc.name, values), (debit) => `Debit ${debit.name} created`)
}

async function share() {
	if (acting.value || !workspace.value.actions?.share?.allowed) return
	acting.value = "share"
	let copied = false
	try {
		const caption = inspectionShareCaption(record.value, workspace.value.colour_size_data || {})
		copied = await copyText(caption)
		if (navigator.share && record.value.upload_quality_approval_sheet) {
			const url = `/api/method/frappe.handler.download_file?file_url=${encodeURIComponent(record.value.upload_quality_approval_sheet)}`
			const response = await fetch(url, { credentials: "include" })
			if (!response.ok) throw new Error("Unable to download approval sheet.")
			const blob = await response.blob()
			const data = { text: caption, files: [new File([blob], record.value.upload_quality_approval_sheet.split("/").pop(), { type: blob.type })] }
			if (!navigator.canShare || navigator.canShare(data)) {
				await navigator.share(data)
				return
			}
		}
	} catch (reason) {
		if (reason?.name !== "AbortError") {
			if (active) error.value = copied ? "Sharing failed, but inspection details were copied." : reason?.message || "Unable to share inspection."
			return
		}
	} finally {
		if (active) acting.value = ""
	}
	if (active && !copied) error.value = "Unable to copy inspection details on this device."
	else if (active) toast.add({ severity: "success", summary: "Inspection details copied", life: 3500 })
}

watch(currentName, () => {
	resultVisible.value = debitVisible.value = cancelVisible.value = false
	acting.value = error.value = ""
	load()
}, { immediate: true })
onBeforeUnmount(() => { active = false; ++loadSequence })
</script>
